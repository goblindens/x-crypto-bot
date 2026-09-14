"""Modo verificacao (regra dele, 14/09/2026): nada sai sem conferir.

1. NUMERO QUE MUDA RAPIDO (preco de BTC/ETH/SOL, variacao 24h, Medo & Ganancia)
   e conferido AO VIVO, na hora, em tres fontes (OKX, Binance, CoinGecko).
   - o numero escrito tem que bater com o preco ao vivo na precisao escrita;
   - precisao grossa demais e barrada ("78 mil" quando esta 77.819 -> tem que
     ser "77,8 mil"): unidade escrita <= 0,2% do preco;
   - variacao 24h: tolerancia de 0,3 ponto; Medo & Ganancia: valor exato.
2. FATO COM FONTE: cada "via Fonte" precisa (a) ser fonte validada (lista do
   config + CoinDesk/Cointelegraph) e (b) o trecho antes do "via" precisa
   aparecer no que essa fonte publicou nas ultimas 24h.
3. PALAVRA PROIBIDA: previsao, alvo, garantido, "vai subir/cair" etc.

Uso:  python -m src.verificador caminho/do/post.txt
      (ou verificar(texto, config) de dentro do bot)
Sai com codigo 0 se OK, 2 se bloqueado.
"""
from __future__ import annotations

import re
import statistics
import sys
from datetime import timedelta

import requests

from .util import fold, now_utc, tokens

TIMEOUT = 12
UA = {"User-Agent": "Mozilla/5.0 (Macintosh)"}
FONTES_EXTRA = [  # validadas, mas fora do config (ingles)
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "lang": "en"},
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "lang": "en"},
]
PROIBIDAS = ["previsao", "previsão", "vai subir", "vai cair", "vai disparar", "alvo de preco", "preco-alvo",
             "garantido", "lucro certo", "sem risco", "compre agora", "compra agora", "recomendo comprar",
             "patrocinado pela okx", "a okx patrocina"]

_MOEDAS = {"BTC": ("BTC-USDT", "BTCUSDT", "bitcoin"), "ETH": ("ETH-USDT", "ETHUSDT", "ethereum"),
           "SOL": ("SOL-USDT", "SOLUSDT", "solana")}


# ------------------------------------------------------------------ ao vivo
def precos_ao_vivo() -> dict:
    """{'BTC': {'preco': 77819.0, 'var': 1.39, 'fontes': 3}, ...}, mediana de 3 fontes."""
    out = {}
    try:
        cg = requests.get("https://api.coingecko.com/api/v3/simple/price",
                          params={"ids": "bitcoin,ethereum,solana", "vs_currencies": "usd", "include_24hr_change": "true"},
                          timeout=TIMEOUT, headers=UA).json()
    except Exception:
        cg = {}
    for sym, (okx_id, bin_id, cg_id) in _MOEDAS.items():
        precos, vars_ = [], []
        try:
            d = requests.get("https://www.okx.com/api/v5/market/ticker", params={"instId": okx_id},
                             timeout=TIMEOUT, headers=UA).json()["data"][0]
            precos.append(float(d["last"])); vars_.append((float(d["last"]) / float(d["open24h"]) - 1) * 100)
        except Exception:
            pass
        try:
            d = requests.get("https://api.binance.com/api/v3/ticker/24hr", params={"symbol": bin_id},
                             timeout=TIMEOUT, headers=UA).json()
            precos.append(float(d["lastPrice"])); vars_.append(float(d["priceChangePercent"]))
        except Exception:
            pass
        if cg.get(cg_id):
            precos.append(float(cg[cg_id]["usd"])); vars_.append(float(cg[cg_id].get("usd_24h_change") or 0))
        if precos:
            out[sym] = {"preco": statistics.median(precos), "var": statistics.median(vars_), "fontes": len(precos)}
    return out


def fng_ao_vivo():
    try:
        d = requests.get("https://api.alternative.me/fng/?limit=1", timeout=TIMEOUT).json()["data"][0]
        return int(d["value"]), d["value_classification"]
    except Exception:
        return None, None


# ----------------------------------------------------------------- numeros
def _numero(txt: str):
    """'77,8 mil' -> (77800, 100)  '78 mil' -> (78000, 1000)  '2.514' -> (2514, 1)  '101,6' -> (101.6, 0.1)"""
    t = txt.lower().replace("us$", "").replace("$", "").replace("r$", "").strip()
    mil = bool(re.search(r"\b(mil|k)\b", t))
    t = re.sub(r"\b(mil|k)\b", "", t).strip()
    # formato BR: 77.819 (milhar) / 77,8 (decimal)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        val, unidade = float(t.replace(".", "")), 1.0
    elif "," in t:
        inteiro, dec = t.split(",", 1)
        val = float(inteiro.replace(".", "") + "." + dec); unidade = 10 ** (-len(dec))
    else:
        val, unidade = float(t.replace(".", "")), 1.0
    if mil:
        val *= 1000; unidade *= 1000
    return val, unidade


def checar_numeros(texto: str) -> list:
    problemas = []
    vivo = precos_ao_vivo()
    for sym in _MOEDAS:
        for m in re.finditer(rf"\b{sym}\b([^\d$\n]{{0,25}})((?:US\$|R\$|\$)?\s?\d[\d.,]*\s?(?:mil|k)?)(\s?(?:mi|bi|milh|bilh|%))?", texto, re.I):
            gap, bruto, sufixo = m.group(1), m.group(2).strip(), (m.group(3) or "")
            if sufixo:                       # "$463 mi", "+1,4%": nao e preco
                continue
            if re.search(r"etf|ganh|perd|fluxo|sa[ií]da|entrada|volume|domin|mi\b", fold(gap)):
                continue                     # "ETFs de BTC perderam $463 mi" nao e preco do BTC
            if re.search(r"\d\s?%", bruto):
                continue
            try:
                val, unidade = _numero(bruto)
            except ValueError:
                continue
            if sym not in vivo:
                problemas.append(f"{sym}: nao consegui conferir o preco ao vivo (fontes fora)"); continue
            p = vivo[sym]["preco"]
            if unidade > p * 0.002:
                problemas.append(f"{sym} '{bruto}': arredondado demais (ao vivo {p:,.0f}); escreva com precisao de {p*0.002:,.0f} ou melhor")
                continue
            if abs(val - p) > max(unidade, p * 0.004):
                problemas.append(f"{sym} '{bruto}' nao bate com o preco ao vivo {p:,.2f} ({vivo[sym]['fontes']} fontes)")
        # variacao 24h logo apos a moeda: "+1,4%"
        for m in re.finditer(rf"\b{sym}\b[^\n]{{0,40}}?\(?([+\-−]?\s?\d+[.,]?\d*)\s?%\)?", texto, re.I):
            try:
                v = float(m.group(1).replace("−", "-").replace(",", ".").replace(" ", ""))
            except ValueError:
                continue
            if sym in vivo and abs(v - vivo[sym]["var"]) > 0.3:
                problemas.append(f"{sym} variacao '{m.group(1)}%' nao bate com 24h ao vivo {vivo[sym]['var']:+.2f}%")
    m = re.search(r"(medo\s*&\s*gan[aâ]ncia|m&g)[^\d\n]{0,20}(\d{1,3})", texto, re.I)
    if m:
        val, rot = fng_ao_vivo()
        if val is None:
            problemas.append("Medo & Ganancia: nao consegui conferir ao vivo")
        elif int(m.group(2)) != val:
            problemas.append(f"Medo & Ganancia '{m.group(2)}' nao bate com o indice ao vivo {val} ({rot})")
    return problemas


# ------------------------------------------------------------------ fontes
def _artigos_recentes(config: dict, horas: int = 24) -> dict:
    from .sources import fetch_feed
    feeds = [f for f in (config or {}).get("news", {}).get("feeds", []) if f.get("enabled", True)] + FONTES_EXTRA
    corte = now_utc() - timedelta(hours=horas)
    por_fonte = {}
    for f in feeds:
        arts = [a for a in fetch_feed(f) if not a.published or a.published >= corte]
        por_fonte[fold(f["name"])] = arts
    return por_fonte


def checar_fontes(texto: str, config: dict) -> list:
    problemas = []
    cit = list(re.finditer(r"\(?\bvia\s+([A-Za-zÀ-ÿ0-9][^()\n]*?)\)?(?=\n|$|\))", texto))
    if not cit:
        return problemas
    recentes = _artigos_recentes(config)
    conhecidas = {k: v for k, v in recentes.items()}
    for m in cit:
        nomes = [n.strip() for n in re.split(r",| e ", m.group(1)) if n.strip()]
        antes = texto[:m.start()]
        paragrafo = re.split(r"\n\s*\n", antes.strip())[-1] if antes.strip() else ""
        # "(via A e B)" sozinho no fim do post = fonte do post inteiro
        trecho = texto if (not paragrafo.strip() or len(paragrafo.strip()) < 15
                           or re.fullmatch(r"\W*", paragrafo)) else paragrafo
        ancoras = _ancoras(trecho)
        for nome in nomes:
            chave = fold(nome)
            fonte = next((k for k in conhecidas if k in chave or chave in k), None)
            if not fonte:
                problemas.append(f"fonte '{nome}' nao esta na lista de fontes validadas"); continue
            arts = conhecidas[fonte]
            if not arts:
                problemas.append(f"'{nome}': nada publicado nas ultimas 24h pra confirmar"); continue
            melhor, melhor_titulo = 0, ""
            for a in arts:
                alvo = fold(a.title + " " + a.summary)
                acertos = sum(1 for anc in ancoras if anc in alvo)
                if acertos > melhor:
                    melhor, melhor_titulo = acertos, a.title
            minimo = 2 if len(ancoras) >= 4 else 1
            if melhor < minimo:
                problemas.append(f"'{nome}': nada nas ultimas 24h sustenta \"{trecho.strip()[:80]}…\" (ancoras batidas: {melhor})")
    return problemas


_PARADAS = {"enquanto", "porque", "quando", "sobre", "entre", "depois", "antes", "ainda", "hoje", "ontem", "semana",
            "muito", "pouco", "outro", "outra", "mesmo", "mesma", "nesta", "neste", "ganhou", "ganhar", "chora", "bolha",
            "pesada", "comeco", "apenas", "todos", "todas", "pouco", "coisa", "algo"}


def _ancoras(trecho: str) -> set:
    """Pedacos que tem que aparecer na materia: numeros e radicais (5 letras) de
    palavras longas. Radical casa inflexao ('descolou' ~ 'descola') e boa parte
    do ingles ('bitcoin', 'clarity', 'ether')."""
    t = fold(trecho)
    nums = set(re.findall(r"\d{2,}", t))
    rad = {w[:5] for w in re.findall(r"[a-z]{5,}", t) if w not in _PARADAS}
    return nums | rad


def checar_proibidas(texto: str) -> list:
    t = fold(texto)
    return [f"palavra proibida: '{p}'" for p in PROIBIDAS if fold(p) in t]


# -------------------------------------------------------------------- tudo
def verificar(texto: str, config: dict | None = None) -> dict:
    problemas = checar_proibidas(texto) + checar_numeros(texto) + checar_fontes(texto, config or {})
    return {"ok": not problemas, "problemas": problemas, "quando": now_utc().isoformat(timespec="seconds")}


def main(argv=None) -> int:
    import os
    import yaml
    argv = argv or sys.argv[1:]
    if not argv:
        print("uso: python -m src.verificador post.txt"); return 2
    texto = open(argv[0], encoding="utf-8").read()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = yaml.safe_load(open(os.path.join(root, "config.yaml"), encoding="utf-8"))
    r = verificar(texto, config)
    if r["ok"]:
        print(f"[verificacao] OK -- numeros ao vivo e fontes conferidos em {r['quando']}")
        return 0
    print("[verificacao] BLOQUEADO:")
    for p in r["problemas"]:
        print("  -", p)
    return 2


if __name__ == "__main__":
    sys.exit(main())
