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

    # -------------------------------------------------------------------------
    # REGRA DELE, 16/09/2026: "os posts tem que ser exclusivo de cripto, e
    # geopolitica que tenha a ver com o mercado cripto ou financeiro".
    #
    # O que quebrou antes: "Cobre estabiliza a espera do Fed" passava, porque
    # tinha a palavra "Fed". Mas a materia e sobre COBRE. Idem ouro, petroleo,
    # FTSE, bolsas da Asia. Quatro dos cinco piores posts do X eram isso.
    #
    # A correcao olha o SUJEITO da manchete, nao so as palavras que aparecem:
    #   1. fala de cripto           -> passa sempre
    #   2. e sobre outro ativo      -> descarta, mesmo citando Fed/juros
    #   3. macro de verdade          -> passa (Fed, juros, inflacao, guerra...)
    # -------------------------------------------------------------------------
    cripto = [t for t in ("bitcoin", "cripto", "crypto", "stablecoin", "ethereum", "etf",
                          "blockchain", "btc", "eth", "solana", "xrp", "altcoin", "defi",
                          "binance", "coinbase", "okx", "kraken", "exchange", "corretora",
                          "token", "web3", "satoshi", "halving", "mineracao", "mining")
              if has_term(haystack, t)]
    # Ativos e mercados que NAO sao o assunto dele. Se a manchete e sobre isto e
    # nao cita cripto, nao entra -- por mais que mencione o Fed.
    OUTROS_ATIVOS = ("cobre", "copper", "ouro", "gold", "petroleo", "petróleo", "oil", "brent",
                     "minerio", "minério", "soja", "milho", "cafe", "café", "trigo", "gas natural",
                     "ftse", "nikkei", "ibovespa", "s&p 500", "dow", "nasdaq", "cac", "dax",
                     "bolsas", "bolsa", "stocks", "equities", "acoes", "ações", "shares",
                     "treasury", "treasuries", "bond", "bonds", "titulo", "título", "gilt",
                     "libra", "sterling", "iene", "yen", "euro", "rand", "peso", "rupia",
                     "imoveis", "imóveis", "real estate", "vinho", "arte")
    # Quem vem primeiro na manchete e o assunto de verdade. "Cobre estabiliza a
    # espera do Fed" comeca com cobre -> corta. "Ira dispara misseis contra
    # Israel; petroleo dispara" comeca com Ira -> passa, e geopolitica.
    def _onde(termos):
        pos = [title_only.find(t) for t in termos if has_term(title_only, t)]
        return min([p for p in pos if p >= 0], default=None)

    feed_cfg = next((f for f in news_cfg["feeds"] if f["name"] == article.source), {})
    if not cripto:
        p_ativo = _onde(OUTROS_ATIVOS)
        if p_ativo is not None:
            p_macro = _onde(news_cfg.get("macro_fortes") or [])
            if p_macro is None or p_ativo < p_macro:
                alvo = next(a for a in OUTROS_ATIVOS if has_term(title_only, a) and title_only.find(a) == p_ativo)
                score = -70
                reasons.append(f"a manchete e sobre '{alvo}', nao sobre cripto")
                article.score, article.reasons = score, reasons
                return

    if feed_cfg.get("grupo") == "macro":
        # Reuters e Bloomberg entram no feed com MUITA materia macro (68 da
        # Bloomberg numa janela de 2h, 17/09). Macro economico puro -- "Fed
        # eleva juros", "dolar sobe" -- vira 8 posts sobre o mesmo assunto e foi
        # o que encheu o feed dele. Entao, nestas fontes, so passa se:
        #   (a) a manchete fala de cripto, ou
        #   (b) e um EVENTO geopolitico (guerra, sancao, tarifa, Ira, China...)
        # "Fed eleva juros" sozinho nao entra: quando mexe com cripto de verdade,
        # as fontes de cripto cobrem, e ai passa por elas.
        # Evento por si so: guerra, missil, sancao, tarifa, Ormuz.
        GEO = ("guerra", "war", "missil", "míssil", "missile", "ormuz", "hormuz",
               "sancao", "sanção", "sanction", "tarifa", "tariff", "embargo",
               "shutdown", "default soberano", "opec", "opep", "ataque militar")
        # Pais sozinho nao e evento: "China's Gas Demand" e "Huawei vs Nvidia"
        # passavam so por citar China. Precisa vir junto de um evento.
        PAISES = ("ira", "irã", "iran", "israel", "russia", "rússia", "ucrania",
                  "ucrânia", "china", "taiwan", "venezuela", "coreia do norte")
        geo = next((t for t in GEO if has_term(title_only, t)), None)
        if not geo:
            pais = next((p for p in PAISES if has_term(title_only, p)), None)
            evento = next((e for e in ("ataque", "strike", "invas", "bomb", "conflito",
                                       "conflict", "proib", "ban ", "banir", "retalia")
                           if has_term(title_only, e)), None)
            if pais and evento:
                geo = f"{pais} + {evento}"
        if cripto:
            acerto = cripto[0]
        elif geo:
            acerto = f"geopolítica '{geo}'"
        else:
            score = -60
            reasons.append("fonte macro sem cripto nem evento geopolítico")
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
        # velocidade (14/09: "ser mais rapido que eles"): a ultima hora vale mais
        if age_h <= 1:
            score += 5
            reasons.append("ultima hora (+5)")
        elif age_h <= 2:
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
