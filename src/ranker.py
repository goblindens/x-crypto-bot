"""Decide o que merece virar post: pontua, descarta lixo e ordena."""
from __future__ import annotations

from .util import fold, has_term, now_utc, similarity

WEIGHTS = {"parceiros": 6, "alta": 3, "media": 2, "baixa": 1}   # parceiros dele (OKX, Ledger, Kraken) furam a fila
SIMILARITY_CUTOFF = 0.45  # acima disso, tratamos como a mesma noticia


def score_article(article, config: dict) -> None:
    """Preenche article.score e article.reasons."""
    news_cfg = config["news"]
    haystack = fold(article.title + " " + article.summary)
    title_only = fold(article.title)

    score = 0
    reasons = []

    weight = next(
        (f.get("weight", 2) for f in news_cfg["feeds"] if f["name"] == article.source), 2
    )
    score += weight
    reasons.append(f"fonte {article.source} (+{weight})")

    bateu_palavra = False
    for tier, words in (news_cfg.get("keywords") or {}).items():
        bonus = WEIGHTS.get(tier, 1)
        for word in words:
            if has_term(haystack, word):
                score += bonus
                reasons.append(f"'{word}' (+{bonus})")
                if tier != "baixa":
                    bateu_palavra = True
                break  # so uma palavra por faixa, senao um texto longo infla a nota

    # Fonte de geopolitica/macro (14/09/2026): so passa se a manchete tiver um termo
    # que de fato mexe com cripto (guerra, petroleo, juros, dolar, China...).
    feed_cfg = next((f for f in news_cfg["feeds"] if f["name"] == article.source), {})
    if feed_cfg.get("grupo") == "macro":
        termos = news_cfg.get("macro_termos") or []
        acerto = next((t for t in termos if has_term(title_only, t)), None)
        if not acerto:
            score = -60
            reasons.append("macro sem termo que mexa com cripto")
            article.score, article.reasons = score, reasons
            return
        score += 3
        reasons.append(f"macro '{acerto}' (+3)")
        bateu_palavra = True

    # "Apenas relevantes" (regra dele, 13/09/2026): sem assunto forte (parceiro,
    # alta ou media), a manchete nao entra, por mais recente ou curta que seja.
    if news_cfg.get("exigir_assunto", False) and not bateu_palavra:
        score = -50
        reasons.append("sem assunto relevante (parceiro/alta/media)")

    if article.published:
        age_h = (now_utc() - article.published).total_seconds() / 3600
        if age_h <= 2:
            score += 3
            reasons.append("muito recente (+3)")
        elif age_h <= 5:
            score += 1
            reasons.append("recente (+1)")

    # Manchete curta e direta rende tweet melhor
    if len(article.title) <= 90:
        score += 1
        reasons.append("manchete curta (+1)")

    # Portugues nao precisa de traducao -> prioridade
    if article.lang == "pt":
        score += 2
        reasons.append("ja em portugues (+2)")

    if "?" in article.title and len(fold(article.title).split()) < 9:
        score -= 2
        reasons.append("manchete-isca (-2)")

    for blocked in news_cfg.get("blocklist", []):
        if has_term(title_only, blocked):
            score = -99
            reasons.append(f"BLOQUEADA por '{blocked}'")
            break

    article.score = score
    article.reasons = reasons


def select(articles: list, config: dict, state, limit: int) -> list:
    """Filtra, ordena e escolhe ate `limit` materias publicaveis."""
    news_cfg = config["news"]
    min_score = news_cfg.get("min_score", 4)
    max_per_source = config["limits"].get("max_per_source_per_run", 1)

    for article in articles:
        score_article(article, config)

    pool = []
    for article in articles:
        if article.score < min_score:
            continue
        if state.has_seen(article.url):
            continue
        pool.append(article)

    pool.sort(key=lambda a: (-a.score, a.published or now_utc()))

    published_titles = list(state.recent_titles(hours=72))
    chosen = []
    per_source = {}
    for article in pool:
        if len(chosen) >= limit:
            break
        if per_source.get(article.source, 0) >= max_per_source:
            continue
        if any(similarity(article.title, other) >= SIMILARITY_CUTOFF for other in published_titles):
            continue
        chosen.append(article)
        published_titles.append(article.title)
        per_source[article.source] = per_source.get(article.source, 0) + 1

    return chosen
