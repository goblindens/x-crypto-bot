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
    return re.sub(r"\s+", " ", text).strip()[:600]


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
