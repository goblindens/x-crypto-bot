"""Ponto de entrada do bot.

Uso:
    python -m src.main --mode news    --dry-run
    python -m src.main --mode market  --dry-run
    python -m src.main --mode news                # publica de verdade
"""
from __future__ import annotations

import argparse
import os
import sys

import yaml

from .composer import compose_market, compose_news
from .publisher import Publisher, PublishError
from .publisher_threads import ThreadsPublisher
from .ranker import select
from .sources import collect_market, collect_news
from .state import State
from .util import fits, fold, set_platform, tweet_length
from datetime import datetime, timezone, timedelta

BR_TZ = timezone(timedelta(hours=-3))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
STATE_PATH = os.path.join(ROOT, "state", "state.json")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_dotenv() -> None:
    """Le um .env simples para rodar local. No GitHub Actions isso nao existe."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def make_publisher(config: dict, dry_run: bool):
    """Escolhe onde publicar. A variavel de ambiente PLATFORM tem prioridade
    sobre o config.yaml -- util para testar sem editar arquivo."""
    platform = (os.environ.get("PLATFORM") or config.get("platform") or "threads").strip().lower()
    set_platform(platform)     # ajusta o limite de caracteres do texto
    if platform == "threads":
        return platform, ThreadsPublisher(dry_run=dry_run)
    if platform == "x":
        return platform, Publisher(dry_run=dry_run)
    raise SystemExit(f"plataforma desconhecida no config.yaml: {platform} (use 'threads' ou 'x')")


def quota_gate(state: State, config: dict, force: bool) -> str:
    """Devolve uma mensagem de bloqueio, ou '' se pode postar."""
    limits = config["limits"]
    monthly_cap = int(limits.get("max_posts_per_month", 400))
    if state.posts_this_month() >= monthly_cap:
        return f"cota mensal atingida ({state.posts_this_month()}/{monthly_cap})"
    if force:
        return ""
    daily_cap = int(limits.get("max_posts_per_day", 8))
    if state.posts_last_24h() >= daily_cap:
        return f"teto diario atingido ({state.posts_last_24h()}/{daily_cap})"
    gap = limits.get("min_minutes_between_posts", 40)
    since = state.minutes_since_last_post()
    if since is not None and since < gap:
        return f"ultimo post foi ha {since:.0f} min (minimo {gap} min)"
    return ""


def _imagens_valem(config: dict) -> bool:
    """Imagem em todo post so publica a partir de `imagens.ligar_em`; antes, so mostra."""
    im = config.get("imagens") or {}
    if not im.get("ligado"):
        return False
    hoje = datetime.now(BR_TZ).strftime("%Y-%m-%d") if BR_TZ else datetime.utcnow().strftime("%Y-%m-%d")
    return str(im.get("ligar_em", "2000-01-01")) <= hoje


def publicar_com_imagem(publisher, text: str, caminho_png: str, config: dict, state: State, kind: str, title: str) -> str:
    """Publica texto + imagem na plataforma certa. Devolve o id, 'mostrar' (dia de prova) ou '' (falha)."""
    if publisher.dry_run:
        print(f"\n----- DRY RUN (imagem {os.path.basename(caminho_png)}) -----\n{text}\n----------------------------------------\n")
        return "dry-run"
    if not _imagens_valem(config):
        print(f"[mostrar] NAO publicado (imagens valem a partir de {(config.get('imagens') or {}).get('ligar_em')}):\n"
              f"  imagem: {caminho_png}\n{text}\n----------------------------------------")
        return "mostrar"
    try:
        if hasattr(publisher, "post_image"):                 # Threads: precisa de URL publica
            from .imagens import publicar as hospedar
            url = hospedar(caminho_png)
            post_id = publisher.post_image(url, text)
        elif hasattr(publisher, "post_with_media"):          # X: upload direto
            post_id = publisher.post_with_media(text, caminho_png)
        else:
            post_id = publisher.post(text)
    except (PublishError, RuntimeError) as exc:
        print(f"[erro] {exc}")
        publisher.last_error = str(exc)
        return ""
    state.record_post(kind, text, url=caminho_png, title=title, tweet_id=post_id)
    return post_id


def run_dado(config: dict, state: State, publisher, force: bool, tipo: str) -> int:
    """Post fixo de dado (mercado, fng, trending, stable, hashrate, btc) com imagem propria."""
    from .dado import montar
    from .verificador import verificar
    kind = f"dado/{tipo}"
    if not (force or publisher.dry_run) and state.posted_kind_today(kind):
        print(f"[dado] {tipo} ja publicado nas ultimas 20h")
        return 0
    blocked = quota_gate(state, config, force or publisher.dry_run)
    if blocked:
        print(f"[quota] parando: {blocked}")
        return 0
    try:
        text, png, title = montar(tipo, config)
    except Exception as exc:
        print(f"[dado] nao consegui montar {tipo}: {exc}")
        return 0
    ver = verificar(text, config)
    if not ver["ok"]:
        print("[verificacao] BLOQUEADO: " + " | ".join(ver["problemas"]))
        return 0
    print("[verificacao] OK")
    if not fits(text):
        print(f"[dado] texto com {tweet_length(text)} caracteres; descartando")
        return 0
    pid = publicar_com_imagem(publisher, text, png, config, state, kind, title)
    return 1 if pid and pid not in ("mostrar",) else 0


def run_news(config: dict, state: State, publisher: Publisher, force: bool, limit: int) -> int:
    articles = collect_news(config)
    if not articles:
        print("[news] nenhuma materia coletada")
        return 0

    chosen = select(articles, config, state, limit)
    if not chosen:
        print("[news] nada passou no filtro de relevancia")
        # marca as descartadas para nao reavaliar as mesmas eternamente
        return 0

    posted = 0
    for article in chosen:
        blocked = quota_gate(state, config, force or publisher.dry_run)
        if blocked:
            print(f"[quota] parando: {blocked}")
            break

        print(f"[news] nota {article.score} | {article.source} | {article.title}")
        print(f"        motivos: {', '.join(article.reasons)}")

        text = compose_news(article, config)
        if text == "SKIP":
            state.mark_seen(article.url)
            continue
        if not fits(text):
            print(f"[news] texto ficou com {tweet_length(text)} caracteres; descartando")
            state.mark_seen(article.url)
            continue

        # MODO VERIFICACAO (regra dele, 14/09/2026): numero ao vivo e fonte conferidos antes de sair.
        from .verificador import verificar
        ver = verificar(text, config)
        if not ver["ok"]:
            print("[verificacao] BLOQUEADO: " + " | ".join(ver["problemas"]))
            state.mark_seen(article.url)
            continue
        print("[verificacao] OK")

        parc_cfg = config.get("parceiros") or {}
        eh_parceiro = bool(getattr(article, "parceiro", False))
        if eh_parceiro and not parc_cfg.get("ligado", False) and not publisher.dry_run:
            # MODO MOSTRAR: escreve no log e nao publica (2 dias de prova, decisao dele 13/09)
            print("[parceiro] MODO MOSTRAR (nao publicado) ----------------\n" + text +
                  "\n  [resposta] " + parc_cfg.get("resposta", "") + "\n----------------------------------------")
            state.mark_seen(article.url)
            continue

        kind = "parceiro" if eh_parceiro else "news"
        if (config.get("imagens") or {}).get("ligado"):
            # Imagem em todo post (14/09): card SecretLab com a manchete, numero e fonte
            from .cards import card_manchete
            from .dado import _saida
            manchete = text.split("\n")[0].strip()
            for pref in ("NOVO:", "URGENTE:", "JUST IN:", "NEW:"):
                manchete = manchete.replace(pref, "").strip()
            urgente = any(k in fold(article.title) for k in ("hack", "ataque", "liquida", "invas", "roub", "exploit", "despenc", "dispar", "crash"))
            if not text.startswith(("NOVO:", "URGENTE:")):
                text = ("URGENTE: " if urgente else "NOVO: ") + text      # molde dos canais grandes (14/09)
            try:
                png = card_manchete(manchete, article.source, _saida("noticia", config), prefixo="URGENTE" if urgente else "NOVO")
            except Exception as exc:
                print(f"[card] nao gerou imagem ({exc}); vai so texto")
                png = ""
            if png:
                tweet_id = publicar_com_imagem(publisher, text, png, config, state, kind, article.title)
                if tweet_id == "mostrar":
                    state.mark_seen(article.url)
                    continue
                if not tweet_id:
                    return posted
                posted += 1
                if eh_parceiro and parc_cfg.get("resposta") and hasattr(publisher, "post_reply") and tweet_id != "dry-run":
                    try:
                        publisher.post_reply(parc_cfg["resposta"], tweet_id)
                    except PublishError as exc:
                        print(f"[parceiro] resposta com o link nao saiu: {exc}")
                continue
        try:
            tweet_id = publisher.post(text)
        except PublishError as exc:
            print(f"[erro] {exc}")
            publisher.last_error = str(exc)
            return posted
        state.record_post(kind, text, url=article.url, title=article.title, tweet_id=tweet_id)
        posted += 1
        if eh_parceiro and parc_cfg.get("resposta") and hasattr(publisher, "post_reply") and tweet_id != "dry-run":
            try:
                publisher.post_reply(parc_cfg["resposta"], tweet_id)
            except PublishError as exc:
                print(f"[parceiro] resposta com o link nao saiu: {exc}")

    return posted


def run_market(config: dict, state: State, publisher: Publisher, force: bool) -> int:
    if not (force or publisher.dry_run) and state.posted_kind_today("market"):
        print("[market] resumo de mercado ja publicado nas ultimas 20h")
        return 0
    blocked = quota_gate(state, config, force or publisher.dry_run)
    if blocked:
        print(f"[quota] parando: {blocked}")
        return 0

    snapshot = collect_market(config)
    if snapshot is None:
        print("[market] sem dados; nada a publicar")
        return 0

    text = compose_market(snapshot, config)
    from .verificador import verificar          # numeros conferidos ao vivo antes de sair (regra dele, 14/09)
    ver = verificar(text, config)
    if not ver["ok"]:
        print("[verificacao] BLOQUEADO: " + " | ".join(ver["problemas"]))
        return 0
    print("[verificacao] OK")
    if not fits(text):
        print(f"[market] texto com {tweet_length(text)} caracteres; descartando")
        return 0

    try:
        tweet_id = publisher.post(text)
    except PublishError as exc:
        print(f"[erro] {exc}")
        publisher.last_error = str(exc)
        return 0
    state.record_post("market", text, title="resumo de mercado", tweet_id=tweet_id)
    return 1


def run_ranking(config: dict, state: State, publisher, force: bool, image_url: str, caption_file: str) -> int:
    """Publica a arte do ranking da semana (imagem + legenda) no Threads.

    A imagem e a legenda chegam pelo repositorio (o Mac manda; ver
    ~/okx/ranking/enviar_threads.sh). So funciona no Threads -- e o unico
    publicador com suporte a imagem aqui.
    """
    if not hasattr(publisher, "post_image"):
        print("[ranking] esta plataforma nao publica imagem; use platform: threads")
        return 0
    if not (force or publisher.dry_run) and state.posted_kind_today("ranking"):
        print("[ranking] ranking ja publicado nas ultimas 20h")
        return 0
    blocked = quota_gate(state, config, force or publisher.dry_run)
    if blocked:
        print(f"[quota] parando: {blocked}")
        return 0
    if not image_url:
        print("[ranking] falta --image-url (endereco publico da imagem)")
        return 0
    try:
        with open(caption_file, "r", encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError as exc:
        print(f"[ranking] nao consegui ler a legenda {caption_file}: {exc}")
        return 0
    if not text:
        print("[ranking] legenda vazia; nada a publicar")
        return 0
    if not fits(text):
        print(f"[ranking] legenda com {tweet_length(text)} caracteres; descartando")
        return 0
    try:
        post_id = publisher.post_image(image_url, text)
    except PublishError as exc:
        print(f"[erro] {exc}")
        publisher.last_error = str(exc)
        return 0
    state.record_post("ranking", text, url=image_url, title="ranking da semana", tweet_id=post_id)
    # Se existir artes/ranking_resposta.txt, vai como 1a resposta (e onde o link entra).
    resposta_file = os.path.join(os.path.dirname(caption_file) or ".", "ranking_resposta.txt")
    if os.path.exists(resposta_file) and hasattr(publisher, "post_reply") and post_id != "dry-run":
        try:
            resposta = open(resposta_file, "r", encoding="utf-8").read().strip()
            if resposta:
                publisher.post_reply(resposta, post_id)
        except (OSError, PublishError) as exc:
            print(f"[ranking] resposta nao publicada: {exc}")
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bot de noticias de cripto para o X")
    parser.add_argument("--mode", choices=["news", "market", "ranking", "espelho", "dado", "loop"], default="news")
    parser.add_argument("--tipo", default="mercado", help="modo dado: mercado|fng|trending|stable|hashrate|btc")
    parser.add_argument("--minutos", type=int, default=350, help="modo loop: por quantos minutos ficar vivo")
    parser.add_argument("--a-cada", dest="a_cada", type=int, default=90, help="modo loop: segundos entre olhadas nos feeds")
    parser.add_argument("--seed", action="store_true", help="modo espelho: marca os posts atuais do Instagram como vistos, sem publicar")
    parser.add_argument("--show", type=int, default=0, help="modo espelho: so mostra como ficariam os ultimos N posts do Instagram")
    parser.add_argument("--repeat", type=int, default=1, help="modo espelho: repete a verificacao N vezes na mesma execucao")
    parser.add_argument("--every", type=int, default=40, help="modo espelho: segundos entre as repeticoes")
    parser.add_argument("--image-url", default="", help="modo ranking: URL https publica da imagem")
    parser.add_argument("--caption-file", default="artes/ranking.txt", help="modo ranking: arquivo com a legenda")
    parser.add_argument("--dry-run", action="store_true", help="mostra o post sem publicar")
    parser.add_argument("--force", action="store_true", help="ignora espacamento e teto diario")
    parser.add_argument("--max", type=int, default=None, help="maximo de posts nesta execucao")
    parser.add_argument("--config", default=CONFIG_PATH)
    args = parser.parse_args(argv)

    # Windows abre o console em cp1252 e quebra em qualquer emoji da legenda.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    load_dotenv()
    config = load_config(args.config)
    state = State(STATE_PATH)
    platform, publisher = make_publisher(config, args.dry_run)

    print(
        f"[bot] plataforma={platform} modo={args.mode} dry_run={args.dry_run} "
        f"| mes: {state.posts_this_month()} post(s) | 24h: {state.posts_last_24h()}"
    )

    if args.mode == "market":
        posted = run_market(config, state, publisher, args.force)
    elif args.mode == "dado":
        posted = run_dado(config, state, publisher, args.force, args.tipo)
    elif args.mode == "loop":
        # TEMPO REAL (dele, 14/09/2026: "soltar informacao em tempo real"): processo continuo
        # que olha os feeds a cada N segundos e publica na hora, 1 por rodada. O GitHub Actions
        # segura o job por ate ~6 h; o workflow re-dispara a cada 6 h.
        import subprocess
        import time
        # Nunca dois loops ao mesmo tempo (Windows: mutex nomeado; outros: arquivo de trava)
        if sys.platform.startswith("win"):
            import ctypes
            ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\x-crypto-bot-loop")
            if ctypes.windll.kernel32.GetLastError() == 183:          # ERROR_ALREADY_EXISTS
                print("[loop] ja existe um loop rodando nesta maquina; saindo")
                return 0
        os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
        try:
            open(os.path.join(ROOT, "logs", "noticias.pid"), "w").write(str(os.getpid()))
        except OSError:
            pass
        fim = time.time() + args.minutos * 60
        posted = 0
        while time.time() < fim:
            try:
                n = run_news(config, state, publisher, args.force, 1)
            except Exception as exc:                       # feed fora, API fora: segue vivo
                print(f"[loop] erro na rodada: {exc}")
                n = 0
            if not args.dry_run:
                state.save()
                if n and os.environ.get("GITHUB_ACTIONS"):   # guarda o historico no repo a cada post
                    try:
                        subprocess.run(["git", "-C", ROOT, "add", "state/state.json"], check=False)
                        subprocess.run(["git", "-C", ROOT, "commit", "-q", "-m", "chore: historico (tempo real) [skip ci]"], check=False)
                        subprocess.run(["git", "-C", ROOT, "pull", "--rebase", "--autostash", "-q", "origin", os.environ.get("GITHUB_REF_NAME", "main")], check=False)
                        subprocess.run(["git", "-C", ROOT, "push", "-q", "origin", f"HEAD:{os.environ.get('GITHUB_REF_NAME', 'main')}"], check=False)
                    except Exception as exc:
                        print(f"[loop] nao guardei o historico agora: {exc}")
            posted += n
            if publisher.last_error:
                print(f"[loop] erro de publicacao, pausando 10 min: {publisher.last_error}")
                publisher.last_error = ""
                time.sleep(600)
            time.sleep(max(30, args.a_cada))
    elif args.mode == "ranking":
        posted = run_ranking(config, state, publisher, args.force, args.image_url, args.caption_file)
    elif args.mode == "espelho":
        # Tempo real (decisao dele, 12/09/2026): a tarefa da VPS chama isto a
        # cada 2 min; com --repeat 3 --every 40 o Instagram e olhado a cada 40 s
        # sem mexer na tarefa. O estado e salvo a cada volta.
        from .espelho import run_espelho
        from .fila import run_fila
        import time
        posted = 0
        fila_path = os.path.join(ROOT, "state", "fila.json")
        for i in range(max(1, args.repeat)):
            if i:
                time.sleep(args.every)
            posted += run_espelho(config, state, publisher, args.force, seed=args.seed, show=args.show)
            if not args.show and not args.seed and not publisher.last_error:
                posted += run_fila(fila_path, state, publisher, args.force)
            if not args.dry_run and not args.show:
                state.save()
            if publisher.last_error or args.show or args.seed:
                break
    else:
        limit = args.max or int(config["limits"].get("max_posts_per_run", 2))
        posted = run_news(config, state, publisher, args.force, limit)

    if not args.dry_run and not args.show:
        state.save()

    if publisher.last_error:
        # Sai com erro de proposito: assim a execucao fica vermelha no GitHub
        # Actions e voce fica sabendo que algo quebrou, em vez de silencio.
        print(f"[bot] fim -- {posted} post(s), COM FALHA: {publisher.last_error}")
        return 1

    print(f"[bot] fim -- {posted} post(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
