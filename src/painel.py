"""Painel de dados do dia -- tudo gratis, tudo com fonte e hora.

Ideia (dele, 14/09/2026): opiniao boa e verificavel e numero, nao adjetivo.
"Mercado com medo" vira "Medo & Ganancia 57, caindo de 61". "Temendo alta de
juros" vira "Polymarket precifica 80% de chance de alta". Cada linha daqui
pode ir num post com a fonte entre parenteses.

Fontes (sem chave, sem custo): OKX + Binance + CoinGecko (preco), CoinGecko
(capitalizacao, dominancia), alternative.me (Medo & Ganancia), DefiLlama
(stablecoins), Polymarket (chance de juros do Fed), Yahoo Finance (Nasdaq,
S&P 500, petroleo, dolar), mempool.space (taxa de rede, hashrate).

Uso: python -m src.painel            (texto pronto)
     python -m src.painel --json     (dados crus)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta

import requests

from .verificador import precos_ao_vivo, fng_ao_vivo

UA = {"User-Agent": "Mozilla/5.0 (Macintosh)"}
T = 12
BR = timezone(timedelta(hours=-3))


def _get(url, **kw):
    r = requests.get(url, timeout=T, headers=UA, **kw)
    r.raise_for_status()
    return r.json()


def _fmt_usd(v: float) -> str:
    if v >= 1000:
        return "US$ " + f"{v:,.0f}".replace(",", ".")
    return "US$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v):.1f}".replace(".", ",") + "%"


def painel() -> dict:
    d = {"quando": datetime.now(BR).strftime("%d/%m %H:%M"), "erros": []}
    try:
        d["precos"] = precos_ao_vivo()                       # mediana OKX/Binance/CoinGecko
    except Exception as e:
        d["erros"].append(f"precos: {e}")
    try:
        v, rot = fng_ao_vivo()
        f = _get("https://api.alternative.me/fng/?limit=2")["data"]
        trad = {"Extreme Fear": "Medo extremo", "Fear": "Medo", "Neutral": "Neutro", "Greed": "Ganância", "Extreme Greed": "Ganância extrema"}
        d["fng"] = {"valor": v, "rotulo": trad.get(rot, rot), "ontem": int(f[1]["value"])}
    except Exception as e:
        d["erros"].append(f"fng: {e}")
    try:
        g = _get("https://api.coingecko.com/api/v3/global")["data"]
        d["global"] = {"mcap_usd": g["total_market_cap"]["usd"], "mcap_24h": g["market_cap_change_percentage_24h_usd"],
                       "dom_btc": g["market_cap_percentage"]["btc"], "dom_eth": g["market_cap_percentage"].get("eth")}
    except Exception as e:
        d["erros"].append(f"coingecko global: {e}")
    try:
        s = _get("https://stablecoins.llama.fi/stablecoins?includePrices=false")["peggedAssets"]
        total = sum(float((a.get("circulating") or {}).get("peggedUSD") or 0) for a in s)
        d["stablecoins_usd"] = total
    except Exception as e:
        d["erros"].append(f"defillama: {e}")
    try:
        ev = _get("https://gamma-api.polymarket.com/events", params={"limit": 6, "active": "true", "closed": "false",
                                                                     "order": "volume24hr", "ascending": "false", "tag_slug": "fed"})
        prox = next((e for e in ev if e.get("title", "").startswith("Fed Decision in")), None)
        if prox:
            mk = {"alta": 0.0, "manter": 0.0, "corte": 0.0}
            for m in prox.get("markets", []):
                q = m.get("question", "").lower()
                p = json.loads(m.get("outcomePrices") or "[0,0]")
                yes = float(p[0]) * 100
                # soma 25 bps + 50+ bps de cada lado; "no change" e um mercado so
                if "increase" in q: mk["alta"] += yes
                elif "no change" in q: mk["manter"] = yes
                elif "decrease" in q: mk["corte"] += yes
            d["fed"] = {"evento": prox["title"], **mk}
    except Exception as e:
        d["erros"].append(f"polymarket: {e}")
    try:
        idx = {}
        for sym, nome in (("^IXIC", "Nasdaq"), ("^GSPC", "S&P 500"), ("CL=F", "Petróleo WTI"), ("DX-Y.NYB", "Dólar (DXY)")):
            r = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym, safe='')}",
                     params={"range": "2d", "interval": "1d"})["chart"]["result"][0]
            m = r["meta"]; c = r["indicators"]["quote"][0]["close"]
            prev = m.get("chartPreviousClose") or c[0]; last = m.get("regularMarketPrice") or c[-1]
            idx[nome] = {"valor": last, "var": (last / prev - 1) * 100}
        d["indices"] = idx
    except Exception as e:
        d["erros"].append(f"yahoo: {e}")
    try:
        h = _get("https://mempool.space/api/v1/mining/hashrate/3d")
        fees = _get("https://mempool.space/api/v1/fees/recommended")
        d["rede"] = {"hashrate_eh": h["currentHashrate"] / 1e18, "taxa_sat_vb": fees["fastestFee"]}
    except Exception as e:
        d["erros"].append(f"mempool: {e}")
    return d


def texto(d: dict | None = None) -> str:
    d = d or painel()
    L = [f"PAINEL DO DIA — {d['quando']} (BRT), tudo ao vivo e com fonte", ""]
    p = d.get("precos", {})
    for sym in ("BTC", "ETH", "SOL"):
        if sym in p:
            L.append(f"{sym} {_fmt_usd(p[sym]['preco'])} ({_pct(p[sym]['var'])} 24h)  [OKX, Binance, CoinGecko]")
    if "fng" in d:
        f = d["fng"]; seta = "⬇️" if f["valor"] < f["ontem"] else ("⬆️" if f["valor"] > f["ontem"] else "➡️")
        L.append(f"Medo & Ganância {f['valor']} ({f['rotulo']}), ontem {f['ontem']} {seta}  [alternative.me]")
    if "global" in d:
        g = d["global"]
        L.append(f"Cripto total {_fmt_usd(g['mcap_usd']/1e12).replace('US$ ','US$ ')} tri ({_pct(g['mcap_24h'])} 24h); domínio BTC {g['dom_btc']:.1f}%".replace(".", ",") + "  [CoinGecko]")
    if "stablecoins_usd" in d:
        L.append(f"Stablecoins em circulação US$ {d['stablecoins_usd']/1e9:,.0f} bi  [DefiLlama]".replace(",", "."))
    if "fed" in d:
        f = d["fed"]; partes = []
        if "alta" in f: partes.append(f"alta {f['alta']:.0f}%")
        if "manter" in f: partes.append(f"manter {f['manter']:.0f}%")
        if "corte" in f: partes.append(f"corte {f['corte']:.0f}%")
        L.append(f"Fed ({f['evento']}): " + ", ".join(partes) + "  [Polymarket]")
    if "indices" in d:
        L.append("  ".join(f"{k} {_pct(v['var'])}" for k, v in d["indices"].items()) + "  [Yahoo Finance]")
    if "rede" in d:
        L.append(f"Rede Bitcoin: hashrate {d['rede']['hashrate_eh']:.0f} EH/s, taxa {d['rede']['taxa_sat_vb']} sat/vB  [mempool.space]")
    if d.get("erros"):
        L += ["", "fora do ar agora: " + "; ".join(d["erros"])]
    return "\n".join(L)


if __name__ == "__main__":
    dados = painel()
    print(json.dumps(dados, ensure_ascii=False, indent=2) if "--json" in sys.argv else texto(dados))
