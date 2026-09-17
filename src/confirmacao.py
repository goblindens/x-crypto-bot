"""Confirmação em duas fontes: a trava que faltava antes de reagir a uma notícia.

Por que existe (17/09/2026): ele mandou pausar as notícias depois de um post
errado sobre juros do Fed. A regra dele: "uma reação tem que ser validada com
notícia real, contexto, informações reais. Não podemos correr risco de falar
merda."

Fato só é fato quando **mais de um veículo independente** publicou. Uma fonte
só pode estar errada, pode ser rumor, pode ser manchete mal escrita. Duas
fontes independentes errando a mesma coisa é raro.

O que conta como independente:
  - veículos diferentes (Reuters e Bloomberg contam; Portal do Bitcoin via RSS
    e o mesmo Portal via Google News NÃO contam, é a mesma redação)
  - o mesmo assunto, medido por similaridade de título

Uso:
    from .confirmacao import confirmar
    r = confirmar(artigo, todos_os_artigos)
    if not r["ok"]:
        # nao reage: so uma fonte publicou
"""
from __future__ import annotations

import re

from .util import fold, similarity

# Veiculos que compartilham redacao ou origem -- contam como UMA fonte.
MESMA_REDACAO = (
    {"portal do bitcoin"},
    {"money times cripto", "money times"},
    {"kraken", "kraken blog"},
    {"cointelegraph", "cointelegraph brasil"},
)

SEMELHANCA = 0.42          # acima disso, tratamos como a mesma noticia


def _familia(nome: str) -> str:
    """Nome normalizado da redacao, juntando os apelidos do mesmo veiculo."""
    n = fold(nome)
    for grupo in MESMA_REDACAO:
        if n in grupo:
            return sorted(grupo)[0]
    return n


def _numeros(titulo: str) -> set:
    """Numeros marcantes do titulo. 'US$ 450 milhoes' e '$450 million' batem,
    mesmo com a manchete em outra lingua -- e assim que a confirmacao funciona
    entre veiculo brasileiro e estrangeiro."""
    return {n for n in re.findall(r"\d[\d.,]*", titulo)
            if len(n.replace(".", "").replace(",", "")) >= 2}


# Radical -> conceito. Duas manchetes que falam do mesmo fato tendem a repetir
# os mesmos conceitos, mesmo em linguas diferentes ou com sinonimos.
CONCEITOS = {
    "senado": "senado", "senate": "senado", "congress": "senado", "camara": "senado",
    "regula": "regulacao", "regulat": "regulacao", "lei ": "regulacao", "bill": "regulacao",
    "projeto": "regulacao", "clarity": "regulacao", "norma": "regulacao",
    "barra": "barrou", "block": "barrou", "bloque": "barrou", "reject": "barrou",
    "rejeit": "barrou", "nao avanc": "barrou", "fail": "barrou",
    "aprov": "aprovou", "approv": "aprovou", "pass": "aprovou", "sanciona": "aprovou",
    "etf": "etf", "saida": "saida", "outflow": "saida", "retirada": "saida", "resgate": "saida",
    "entrada": "entrada", "inflow": "entrada", "aporte": "entrada",
    "hack": "hack", "invas": "hack", "roub": "hack", "exploit": "hack", "steal": "hack",
    "juros": "juros", "rate": "juros", "taxa": "juros",
    "sobe": "alta", "dispar": "alta", "rise": "alta", "surge": "alta", "rally": "alta",
    "eleva": "alta", "raise": "alta", "hike": "alta", "hawkish": "alta", "aument": "alta",
    "cai": "queda", "despenc": "queda", "fall": "queda", "drop": "queda", "slide": "queda",
    "corte": "corte", "cut": "corte", "dovish": "corte",
    "banco central": "bc", "central bank": "bc", "bacen": "bc", "fed": "fed",
    "bitcoin": "btc", "btc": "btc", "ethereum": "eth", "stablecoin": "stable",
    "cripto": "cripto", "crypto": "cripto", "binance": "binance", "coinbase": "coinbase",
}


def _conceitos(titulo: str) -> set:
    t = fold(titulo)
    return {v for k, v in CONCEITOS.items() if k in t}


def _mesmo_assunto(a_titulo: str, b_titulo: str) -> bool:
    if similarity(fold(a_titulo), fold(b_titulo)) >= SEMELHANCA:
        return True
    # numero marcante igual + palavra em comum (US$ 450 mi = $450 million)
    na, nb = _numeros(a_titulo), _numeros(b_titulo)
    if na & nb:
        pa = {p for p in fold(a_titulo).split() if len(p) >= 4}
        pb = {p for p in fold(b_titulo).split() if len(p) >= 4}
        if pa & pb:
            return True
    # mesmos conceitos: atravessa lingua e sinonimo ("Senado barra regulacao"
    # == "Senate blocks crypto bill"). Exige 3 conceitos iguais pra nao juntar
    # duas noticias diferentes que so falam do mesmo tema.
    ca, cb = _conceitos(a_titulo), _conceitos(b_titulo)
    return len(ca & cb) >= 3


# -----------------------------------------------------------------------------
# TEMPO REAL (17/09/2026). Medido: a 2a fonte demora 226 min na mediana, e
# NENHUM fato foi confirmado em ate 15 min. Esperar confirmacao = perder a
# noticia. Ele: "nao vejo motivo pra que nao seja em tempo real".
#
# A troca: em vez de esperar outro jornal, olhar QUE TIPO de fato e.
#   - numero que eu mesmo posso medir  -> confiro ao vivo e publico na hora
#   - anuncio/decisao de fonte tier 1  -> publico na hora (erro e raro)
#   - acusacao, polemica, "fulano disse"-> ai sim espero a 2a fonte
# -----------------------------------------------------------------------------
TIER1 = {"coindesk", "the block", "reuters", "bloomberg", "cointelegraph",
         "portal do bitcoin", "livecoins"}

# Palavras que marcam fato DELICADO: acusacao, crime, processo, rumor. Nestes,
# uma fonte so nao basta nunca -- e onde um erro vira processo, nao correcao.
DELICADO = ("acusa", "accuse", "fraude", "fraud", "golpe", "scam", "processo",
            "lawsuit", "investiga", "probe", "prende", "arrest", "culpa",
            "lavagem", "laundering", "rumor", "teria", "supostamente",
            "allegedly", "fontes dizem", "sources say", "pode ter", "suspeita")


def avaliar(artigo, todos: list, config: dict | None = None) -> dict:
    """Decide se publica AGORA ou se espera confirmacao."""
    cfg = (config or {}).get("news") or {}
    titulo = fold(artigo.title)
    fonte = _familia(artigo.source)

    delicado = next((p for p in DELICADO if p in titulo), None)
    if delicado:
        r = confirmar(artigo, todos, minimo=2)
        r["modo"] = "esperou 2 fontes"
        r["motivo"] = r["motivo"] or f"assunto delicado ('{delicado}')"
        if not r["ok"]:
            r["motivo"] = f"assunto delicado ('{delicado}') e {r['motivo']}"
        return r

    if fonte in set(cfg.get("tier1") or TIER1):
        return {"ok": True, "modo": "tempo real (fonte tier 1)", "quantas": 1,
                "fontes": [fonte], "confirmacoes": [], "motivo": ""}

    r = confirmar(artigo, todos, minimo=2)
    r["modo"] = "esperou 2 fontes (fonte fora do tier 1)"
    return r


def confirmar(artigo, todos: list, minimo: int = 2) -> dict:
    """Quantos veiculos INDEPENDENTES publicaram o mesmo assunto."""
    familias = {_familia(artigo.source)}
    batem = []
    for outro in todos:
        if outro is artigo or not getattr(outro, "title", ""):
            continue
        fam = _familia(outro.source)
        if fam in familias:
            continue
        if _mesmo_assunto(artigo.title, outro.title):
            familias.add(fam)
            batem.append({"fonte": outro.source, "titulo": outro.title[:120], "url": outro.url})
    return {
        "ok": len(familias) >= minimo,
        "fontes": sorted(familias),
        "quantas": len(familias),
        "confirmacoes": batem,
        "motivo": "" if len(familias) >= minimo
                  else f"so {len(familias)} fonte(s) publicaram isso: {', '.join(sorted(familias))}",
    }
