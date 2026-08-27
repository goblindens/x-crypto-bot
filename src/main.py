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
from .ranker import select
from .sources import collect_market, collect_news
from .state import State
from .util import fits, tweet_length

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

        try:
            tweet_id = publisher.post(text)
        except PublishError as exc:
            print(f"[erro] {exc}")
            publisher.last_error = str(exc)
            return posted
        state.record_post("news", text, url=article.url, title=article.title, tweet_id=tweet_id)
        posted += 1

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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bot de noticias de cripto para o X")
    parser.add_argument("--mode", choices=["news", "market"], default="news")
    parser.add_argument("--dry-run", action="store_true", help="mostra o post sem publicar")
    parser.add_argument("--force", action="store_true", help="ignora espacamento e teto diario")
    parser.add_argument("--max", type=int, default=None, help="maximo de posts nesta execucao")
    parser.add_argument("--config", default=CONFIG_PATH)
    args = parser.parse_args(argv)

    load_dotenv()
    config = load_config(args.config)
    state = State(STATE_PATH)
    publisher = Publisher(dry_run=args.dry_run)

    print(
        f"[bot] modo={args.mode} dry_run={args.dry_run} "
        f"| mes: {state.posts_this_month()} post(s) | 24h: {state.posts_last_24h()}"
    )

    if args.mode == "market":
        posted = run_market(config, state, publisher, args.force)
    else:
        limit = args.max or int(config["limits"].get("max_posts_per_run", 2))
        posted = run_news(config, state, publisher, args.force, limit)

    if not args.dry_run:
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
