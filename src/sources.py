"""Coleta de dados. Tudo por APIs publicas e gratuitas, sem chave obrigatoria."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import timedelta

import feedparser
import requests

from .util import fold, now_utc

USER_AGENT = "x-crypto-bot/1.0 (+https://github.com/)"
TIMEOUT = 20


@dataclass
class Article:
    title: str
    url: str
    source: str
    lang: str
    published: object
    summary: str = ""
    score: int = 0
    reasons: list = field(default_factory=list)
    parceiro: bool = False      # OKX / Kraken / Ledger: sai com chamada pra comunidade + link na resposta


# --------------------------------------------------------------------- RSS
def fetch_feed(feed_cfg: dict) -> list:
    """Le um feed RSS/Atom. Nunca levanta excecao: feed fora do ar so devolve []."""
    url = feed_cfg["url"]
    try:
        response = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
    except (requests.RequestException, ValueError) as exc:
        print(f"[rss] falhou {feed_cfg['name']}: {exc}")
        return []

    articles = []
    for entry in parsed.entries:
        link = entry.get("link") or ""
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        articles.append(
            Article(
                title=title,
                url=link,
                source=feed_cfg["name"],
                lang=feed_cfg.get("lang", "pt"),
                published=_entry_time(entry),
                summary=_clean_summary(entry.get("summary", "")),
                parceiro=bool(feed_cfg.get("parceiro", False)),
            )
        )
    return articles


def _entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            from datetime import datetime, timezone
            return datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)
    return None


def _clean_summary(raw: str) -> str:
    import html
    import re
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # rodape de feed WordPress ("O post X apareceu primeiro em Y." / "The post X appeared first on Y.")
    text = re.sub(r"\s*(O post|The post)\s.*?(apareceu primeiro em|appeared first on)\s.*?(\.|$)", "", text, flags=re.I).strip()
    return text[:600]


def fetch_okx_anuncios(cfg: dict) -> list:
    """Anuncios oficiais da OKX (pagina PT-BR). Nao tem RSS: a lista vem num JSON
    embutido na pagina (appState -> sectionData.articleList.list). Manutencao,
    delist e migracao sao pulados pelos termos do config."""
    import json
    import re
    from datetime import datetime, timezone
    url = cfg.get("url", "https://www.okx.com/pt-br/help/section/announcements-latest-announcements")
    try:
        html = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0 (Macintosh)"}).text
        m = re.search(r'id="appState">(.*?)</script>', html, re.S)
        lista = json.loads(m.group(1))["appContext"]["initialProps"]["sectionData"]["articleList"]["list"]
    except Exception as exc:
        print(f"[okx] nao consegui ler os anuncios: {exc}")
        return []
    pular = [fold(t) for t in cfg.get("pular_termos", [])]
    out = []
    for it in lista:
        titulo = (it.get("title") or "").strip()
        if not titulo or any(p in fold(titulo) for p in pular):
            continue
        ts = it.get("publishTime")
        pub = datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else None
        out.append(Article(title=titulo, url=f"https://www.okx.com/pt-br/help/{it.get('slug', it.get('id', ''))}",
                           source="OKX", lang="pt", published=pub, summary="", parceiro=True))
    return out


def collect_news(config: dict) -> list:
    """Busca todos os feeds habilitados e devolve os artigos dentro da janela de tempo."""
    news_cfg = config["news"]
    max_age = timedelta(hours=news_cfg.get("max_age_hours", 12))
    cutoff = now_utc() - max_age
    out = []
    for feed_cfg in news_cfg["feeds"]:
        if not feed_cfg.get("enabled", True):
            continue
        for article in fetch_feed(feed_cfg):
            if article.published and article.published < cutoff:
                continue
            out.append(article)
    okx_cfg = config.get("okx_anuncios") or {}
    if okx_cfg.get("enabled"):
        # anuncio oficial vale por 48h: a OKX publica poucos e a pagina nao e feed
        cutoff_okx = now_utc() - timedelta(hours=48)
        anuncios = [a for a in fetch_okx_anuncios(okx_cfg) if a.published and a.published >= cutoff_okx]
        print(f"[okx] {len(anuncios)} anuncio(s) oficial(is) nas ultimas 48h")
        out += anuncios
    print(f"[rss] {len(out)} materias dentro da janela de {news_cfg.get('max_age_hours')}h")
    return out


# ------------------------------------------------------------------ mercado
@dataclass
class MarketSnapshot:
    coins: list          # [{'symbol': 'BTC', 'price': 63412.0, 'change24h': 2.13}]
    btc_dominance: float = None
    fear_greed: dict = None   # {'value': 61, 'label': 'Ganancia'}


def _coingecko(path: str, params: dict) -> dict:
    """CoinGecko tem plano publico gratuito. A chave demo (tambem gratis) e opcional
    e so serve para nao esbarrar no limite de requisicoes por minuto."""
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    key = os.environ.get("COINGECKO_API_KEY", "").strip()
    if key:
        headers["x-cg-demo-api-key"] = key
    response = requests.get(
        f"https://api.coingecko.com/api/v3{path}", params=params, headers=headers, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.json()


_FNG_LABELS = {
    "extreme fear": "Medo extremo",
    "fear": "Medo",
    "neutral": "Neutro",
    "greed": "Ganância",
    "extreme greed": "Ganância extrema",
}


def collect_market(config: dict):
    """Precos, dominancia do BTC e indice medo/ganancia. Devolve None se tudo falhar."""
    market_cfg = config["market"]
    vs = market_cfg.get("vs_currency", "usd")
    coins_cfg = market_cfg["coins"]

    try:
        data = _coingecko(
            "/simple/price",
            {
                "ids": ",".join(c["id"] for c in coins_cfg),
                "vs_currencies": vs,
                "include_24hr_change": "true",
            },
        )
    except (requests.RequestException, ValueError) as exc:
        print(f"[market] CoinGecko falhou: {exc}")
        return None

    coins = []
    for coin_cfg in coins_cfg:
        entry = data.get(coin_cfg["id"])
        if not entry or entry.get(vs) is None:
            continue
        coins.append(
            {
                "symbol": coin_cfg["symbol"],
                "price": float(entry[vs]),
                "change24h": float(entry.get(f"{vs}_24h_change") or 0.0),
            }
        )
    if not coins:
        print("[market] nenhum preco retornado")
        return None

    snapshot = MarketSnapshot(coins=coins)

    if market_cfg.get("include_dominance", True):
        try:
            glob = _coingecko("/global", {})
            snapshot.btc_dominance = float(glob["data"]["market_cap_percentage"]["btc"])
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            print(f"[market] dominancia indisponivel: {exc}")

    if market_cfg.get("include_fear_greed", True):
        try:
            # alternative.me: publica, gratuita, sem chave
            response = requests.get(
                "https://api.alternative.me/fng/",
                params={"limit": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            item = response.json()["data"][0]
            snapshot.fear_greed = {
                "value": int(item["value"]),
                "label": _FNG_LABELS.get(fold(item["value_classification"]), item["value_classification"]),
            }
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            print(f"[market] indice medo/ganancia indisponivel: {exc}")

    return snapshot
