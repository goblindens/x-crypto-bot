"""Funcoes auxiliares sem dependencia de rede."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Limites por plataforma. O X encurta toda URL para 23 caracteres via t.co;
# o Threads conta a URL inteira, caractere por caractere.
PLATFORMS = {
    "x":       {"limit": 280, "url_weight": 23},
    "threads": {"limit": 500, "url_weight": 0},
}

TWEET_LIMIT = 280   # compatibilidade; use limit() no codigo novo
URL_WEIGHT = 23

_LIMIT = 280
_URL_WEIGHT = 23


def set_platform(name: str) -> None:
    """Define os limites de texto usados por fits()/truncate_to_fit()."""
    global _LIMIT, _URL_WEIGHT
    cfg = PLATFORMS.get(name)
    if not cfg:
        raise ValueError(f"plataforma desconhecida: {name} (use: {', '.join(PLATFORMS)})")
    _LIMIT = cfg["limit"]
    _URL_WEIGHT = cfg["url_weight"]


def limit() -> int:
    return _LIMIT

_URL_RE = re.compile(r"https?://\S+")
_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "ref", "source", "mc_cid", "mc_eid")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url(url: str) -> str:
    """Remove parametros de rastreamento para o dedup nao ver a mesma materia duas vezes."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING_PREFIXES)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:16]


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def fold(text: str) -> str:
    """minusculo, sem acento -- usado para casar palavras-chave."""
    return strip_accents(text).lower()


def tweet_length(text: str) -> int:
    """Comprimento do jeito que a plataforma conta.

    No X toda URL vale 23 caracteres (t.co), independente do tamanho real.
    No Threads (url_weight = 0) a URL conta pelo tamanho que tem.
    """
    if _URL_WEIGHT == 0:
        return len(text)
    without_urls = _URL_RE.sub("", text)
    n_urls = len(_URL_RE.findall(text))
    return len(without_urls) + n_urls * _URL_WEIGHT


def fits(text: str) -> bool:
    return tweet_length(text) <= _LIMIT


def truncate_to_fit(text: str, reserved: int = 0) -> str:
    """Corta o texto em limite de palavra para caber no post."""
    budget = _LIMIT - reserved
    if tweet_length(text) <= budget:
        return text
    words = text.split()
    out: list[str] = []
    for word in words:
        candidate = " ".join(out + [word])
        if tweet_length(candidate) + 1 > budget:  # +1 para as reticencias
            break
        out.append(word)
    return (" ".join(out).rstrip(",.;:-") + "...") if out else text[: budget - 3] + "..."


def has_term(haystack_folded: str, term: str) -> bool:
    """Casa `term` como inicio de palavra: 'hack' nao casa com 'hackathon',
    mas 'regulament' casa com 'regulamentacao'. Evita falso positivo bobo."""
    pattern = r"(?<![a-z0-9])" + re.escape(fold(term))
    return re.search(pattern, haystack_folded) is not None


def tokens(text: str) -> set:
    """Conjunto de palavras significativas, para medir semelhanca entre manchetes."""
    words = re.findall(r"[a-z0-9]{4,}", fold(text))
    return set(words)


def similarity(a: str, b: str) -> float:
    """Jaccard simples entre duas manchetes (0.0 a 1.0)."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def fmt_price(value: float) -> str:
    """1234.5 -> '$1.234'  |  0.4213 -> '$0,4213'"""
    if value >= 1000:
        return "$" + f"{value:,.0f}".replace(",", ".")
    if value >= 1:
        return "$" + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "$" + f"{value:.4f}".replace(".", ",")


def fmt_pct(value: float) -> str:
    """2.13 -> '+2,13%'"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}".replace(".", ",") + "%"
