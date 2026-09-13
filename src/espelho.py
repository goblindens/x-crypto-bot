"""Espelho Instagram -> X: tudo que sai no Instagram vai pro X, adaptado.

Automatico, sem aprovacao (decisao do Sinval em 12/09/2026). No lugar da
aprovacao entram regras fixas, medidas na conta dele e no nicho:

  - legenda vira so a primeira linha, sem hashtag, sem URL, ate N caracteres
    (curto rende 1,7x mais que longo no X dele)
  - post de parceria com sirene ou CAIXA ALTA nao espelha (1 a 5 likes em
    contas de 100 mil seguidores -- formato morto)
  - carrossel = primeira foto; Reel fica de fora na fase 1
  - nunca link no corpo (custa 13x mais e nao engaja)
  - so publica dentro das janelas boas (07h, 12-14h, 19-21h) e respeita o
    espacamento minimo; fora da janela o post espera a proxima execucao
  - nunca o historico: a primeira execucao real "semeia" (marca tudo o que ja
    existe como visto) e so os posts novos dali em diante sao espelhados

Modo --dry-run: mostra como ficariam os ultimos posts, sem tocar no estado.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

from .instagram import Instagram, InstagramError
from .publisher import PublishError

BR_TZ = timezone(timedelta(hours=-3))

_HASHTAG = re.compile(r"(?<!\w)#\w+")
_MENTION_ONLY = re.compile(r"^\s*@\w+\s*$")
_URL = re.compile(r"https?://\S+|\b[a-z0-9.-]+\.(com|com\.br|net|io|ai|app)(/\S*)?", re.I)
_SPACES = re.compile(r"[ \t]+")


# --------------------------------------------------------------- adaptacao
def adapt_caption(caption: str, max_chars: int, skip_terms: list[str], caps_words: int) -> tuple[str, str]:
    """Devolve (texto, motivo_de_pulo). motivo vazio = pode publicar."""
    raw = (caption or "").replace("\r", "")
    for term in skip_terms:
        if term and term in raw:
            return "", f"tem '{term}' (post de anuncio)"
    # primeira linha que nao seja so hashtag/mencao/vazia
    first = ""
    for line in raw.split("\n"):
        candidate = _HASHTAG.sub("", line)
        candidate = _URL.sub("", candidate)
        candidate = _SPACES.sub(" ", candidate).strip(" -–—·|")
        if candidate and not _MENTION_ONLY.match(candidate):
            first = candidate
            break
    if not first:
        return "", ""  # sem legenda util: vai so a imagem (formato que rende like)
    upper = [w for w in first.split() if len(w) > 3 and w.isupper() and w.isalpha()]
    if len(upper) >= caps_words:
        return "", f"{len(upper)} palavras em CAIXA ALTA (post de anuncio)"
    if len(first) > max_chars:
        cut = first[:max_chars].rsplit(" ", 1)[0].rstrip(",.;:-")
        first = cut + "…"
    return first, ""


# ------------------------------------------------------------------ janela
def in_window(now_br: datetime, windows: list[str]) -> bool:
    hm = now_br.hour * 60 + now_br.minute
    for w in windows:
        a, b = w.split("-")
        h1, m1 = (int(x) for x in a.split(":"))
        h2, m2 = (int(x) for x in b.split(":"))
        if h1 * 60 + m1 <= hm <= h2 * 60 + m2:
            return True
    return False


def _first_image(ig: Instagram, item: dict) -> str | None:
    mtype = item.get("media_type")
    if mtype == "IMAGE":
        return item.get("media_url")
    if mtype == "CAROUSEL_ALBUM":
        for child in ig.children(item["id"]):
            if child.get("media_type") == "IMAGE" and child.get("media_url"):
                return child["media_url"]
    return None


# ---------------------------------------------------------------- execucao
def run_espelho(config: dict, state, publisher, force: bool, seed: bool = False, show: int = 0) -> int:
    cfg = config.get("espelho", {}) or {}
    lookback = int(cfg.get("lookback", 10))
    max_chars = int(cfg.get("max_caption_chars", 120))
    skip_terms = list(cfg.get("skip_terms", ["\U0001F6A8"]))
    caps_words = int(cfg.get("caps_words_to_skip", 3))
    windows = list(cfg.get("windows", ["07:00-07:59", "12:00-14:59", "19:00-21:59"]))
    gap = int(cfg.get("min_minutes_between_posts", 90))
    max_per_run = int(cfg.get("max_per_run", 1))
    reels = bool(cfg.get("reels", True))

    try:
        ig = Instagram()
    except InstagramError as exc:
        print(f"[espelho] {exc}")
        publisher.last_error = str(exc)
        return 0
    print(f"[espelho] token do Instagram: {ig.token_origin}")

    try:
        items = ig.recent(max(lookback, show or 0))
    except InstagramError as exc:
        print(f"[espelho] {exc}")
        publisher.last_error = str(exc)
        return 0

    # --show N: so demonstra a adaptacao dos ultimos N, sem estado, sem publicar
    if show:
        print(f"[espelho] demonstracao dos ultimos {show} posts do Instagram (nada publicado):")
        for item in items[:show]:
            text, why = adapt_caption(item.get("caption", ""), max_chars, skip_terms, caps_words)
            kind = item.get("media_type")
            stamp = (item.get("timestamp") or "")[:16].replace("T", " ")
            flag = "PULA: " + why if why else ("OK (video)" if kind == "VIDEO" else "OK")
            print(f"\n  [{stamp}] {kind} -> {flag}")
            if not why:
                print(f"    texto : {text!r}" if text else "    texto : (so a imagem)")
        return 0

    # semear: marca tudo o que existe como visto e nao publica nada
    if seed or not state.data.get("espelho", {}).get("seeded"):
        for item in items:
            state.mark_seen(item.get("permalink") or item["id"])
        state.data.setdefault("espelho", {})["seeded"] = datetime.now(timezone.utc).isoformat()
        print(f"[espelho] semeado: {len(items)} post(s) atuais marcados como vistos; so os novos serao espelhados")
        return 0

    novos = [i for i in reversed(items) if not state.has_seen(i.get("permalink") or i["id"])]
    if not novos:
        print("[espelho] nada novo no Instagram")
        return 0

    now_br = datetime.now(BR_TZ)
    # windows vazio = tempo real (decisao dele, 12/09/2026: "postou no Insta, postou no X")
    if windows and not (force or publisher.dry_run) and not in_window(now_br, windows):
        print(f"[espelho] {len(novos)} post(s) novo(s) esperando a proxima janela ({', '.join(windows)}); agora sao {now_br:%H:%M}")
        return 0
    daily_cap = int((config.get("limits", {}) or {}).get("max_posts_per_day", 8))
    if not (force or publisher.dry_run) and state.posts_last_24h() >= daily_cap:
        print(f"[espelho] teto diario atingido ({state.posts_last_24h()}/{daily_cap}); espera")
        return 0

    posted = 0
    for item in novos:
        if posted >= max_per_run:
            break
        key = item.get("permalink") or item["id"]
        kind = item.get("media_type")
        is_video = kind == "VIDEO"
        if is_video and not reels:
            print(f"[espelho] pula Reel/video {key} (espelho.reels: false)")
            state.mark_seen(key)
            continue
        text, why = adapt_caption(item.get("caption", ""), max_chars, skip_terms, caps_words)
        if why:
            print(f"[espelho] pula {key}: {why}")
            state.mark_seen(key)
            continue
        image_url = item.get("media_url") if is_video else _first_image(ig, item)
        if not image_url:
            print(f"[espelho] pula {key}: sem midia")
            state.mark_seen(key)
            continue

        since = state.minutes_since_last_post()
        if gap and not (force or publisher.dry_run) and since is not None and since < gap:
            print(f"[espelho] ultimo post foi ha {since:.0f} min (minimo {gap}); espera")
            break

        tmp = os.path.join(tempfile.gettempdir(), f"espelho-{item['id']}.{'mp4' if is_video else 'jpg'}")
        try:
            ig.download(image_url, tmp)
            tweet_id = publisher.post_with_media(text, tmp, video=is_video)
        except (PublishError, OSError, InstagramError) as exc:
            print(f"[erro] {exc}")
            publisher.last_error = str(exc)
            return posted
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        state.record_post("espelho", text, url=key, title=item["id"], tweet_id=tweet_id)
        posted += 1
    return posted
