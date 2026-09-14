"""Posts fixos de dado (modo `dado`): imagem + legenda saindo da MESMA chamada
de API, na hora. Sao os posts que os canais grandes repetem todo dia e que
rendem tanto quanto noticia quente (medido em 14/09/2026 no @news_crypto).

tipos: mercado | fng | trending | stable | hashrate | btc
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import requests

from . import painel as painel_mod
from . import grafico
from .cards import card_mercado, card_trending

BR = timezone(timedelta(hours=-3))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh)"}


def _pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + f"{abs(v):.1f}".replace(".", ",") + "%"


def _usd(v: float) -> str:
    if v >= 10000:
        return "US$ " + f"{v/1000:.1f}".replace(".", ",") + " mil"
    if v >= 1000:
        return "US$ " + f"{v:,.0f}".replace(",", ".")
    return "US$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _saida(nome: str, config: dict) -> str:
    pasta = os.path.join(ROOT, (config.get("imagens") or {}).get("pasta", "artes/auto"))
    stamp = datetime.now(BR).strftime("%Y%m%d-%H%M%S")
    return os.path.join(pasta, f"{nome}-{stamp}.png")


def trending() -> list:
    d = requests.get("https://api.coingecko.com/api/v3/search/trending", timeout=20, headers=UA).json()
    out = []
    for c in d.get("coins", []):
        it = c["item"]; dd = it.get("data") or {}
        var = (dd.get("price_change_percentage_24h") or {}).get("usd")
        rank = it.get("market_cap_rank")
        # so moedas entre as 300 maiores: lista de busca sem filtro vira vitrine de token sem historico
        if not rank or rank > 300:
            continue
        out.append({"rank": len(out) + 1, "simbolo": it.get("symbol", ""), "nome": it.get("name", ""),
                    "var24h": float(var) if var is not None else None, "mcap_rank": rank})
        if len(out) == 8:
            break
    return out


def montar(tipo: str, config: dict) -> tuple[str, str, str]:
    """Devolve (legenda, caminho_da_imagem, titulo_curto)."""
    if tipo == "mercado":
        p = painel_mod.painel()
        img = card_mercado(p, _saida("mercado", config))
        pr = p.get("precos", {})
        partes = [f"{s} {_usd(pr[s]['preco'])} ({_pct(pr[s]['var'])})" for s in ("BTC", "ETH", "SOL") if s in pr]
        g = p.get("global") or {}; f = p.get("fng") or {}
        linha2 = []
        if g: linha2 += ["cap. total US$ " + f"{g['mcap_usd']/1e12:.2f}".replace(".", ",") + " tri", "domínio BTC " + f"{g['dom_btc']:.1f}".replace(".", ",") + "%"]
        if f: linha2.append(f"Medo & Ganância {f['valor']} ({f['rotulo'].lower()})")
        texto = (f"📊 Mercado agora, {p['quando']}\n\n" + " · ".join(partes) + "\n\n" + " · ".join(linha2) +
                 "\n\n(OKX, Binance, CoinGecko, alternative.me)")
        return texto, img, "mercado agora"
    if tipo == "trending":
        lista = trending()
        if len(lista) < 4:
            raise RuntimeError("poucas moedas grandes na lista de busca hoje; pulo o post")
        img = card_trending(lista, _saida("trending", config))
        linhas = [f"{m['rank']}. {m['simbolo'].upper()}" + (f" {_pct(m['var24h'])}" if m['var24h'] is not None else "") for m in lista[:8]]
        texto = ("🚀 Moedas mais buscadas hoje no CoinGecko (só entre as 300 maiores):\n\n" + "\n".join(linhas) +
                 "\n\nBusca não é compra. Qual dessas você já olhou?\n\n(CoinGecko)")
        return texto, img, "mais buscadas"
    if tipo in ("fng", "stable", "hashrate", "btc"):
        dias = 30 if tipo == "stable" else None
        r = grafico.gerar(tipo, _saida(tipo, config), dias=dias)
        if tipo == "fng":
            pts, _ = grafico.serie_fng(90)
            vals = [v for _, v in pts]
            i_max = max(i for i, v in enumerate(vals) if v == max(vals)); i_min = max(i for i, v in enumerate(vals) if v == min(vals))
            dmax = pts[i_max][0].astimezone(BR).strftime("%d/%m"); dmin = pts[i_min][0].astimezone(BR).strftime("%d/%m")
            ontem = int(vals[-2]) if len(vals) > 1 else None
            atual = int(r["atual"]); rot = r["rotulo"].lower()
            mov = "subiu" if ontem is not None and atual > ontem else ("caiu" if ontem is not None and atual < ontem else "ficou igual")
            texto = (f"😬 Medo & Ganância em {atual} ({rot}), {mov} de {ontem} ontem.\n\n"
                     f"Nos últimos 90 dias: máxima {int(max(vals))} em {dmax}, mínima {int(min(vals))} em {dmin}.\n\n"
                     f"Você opera com o índice ou contra ele?\n\n(alternative.me)")
            return texto, r["arquivo"], "medo e ganancia"
        def bi(v): return "US$ " + f"{v:.1f}".replace(".", ",") + " bi"
        def usd0(v): return "US$ " + f"{v:,.0f}".replace(",", ".")
        if tipo == "stable":
            delta = r["atual"] - r["primeiro"]
            sinal = "Entraram" if delta >= 0 else "Saíram"
            texto = (f"💵 {sinal} {bi(abs(delta))} em stablecoins em {r['dias']} dias.\n\n"
                     f"De {bi(r['primeiro'])} pra {bi(r['atual'])} em circulação. Stablecoin parada é dinheiro esperando pra entrar.\n\n"
                     f"Pólvora seca ou gente estacionada?\n\n(DefiLlama)")
            return texto, r["arquivo"], "stablecoins"
        if tipo == "hashrate":
            texto = (f"⛏️ Hashrate do Bitcoin em {r['atual_txt']} ({_pct(r['var_pct'])} em {r['dias']} dias).\n\n"
                     f"Mais poder de mineração = mais custo pra atacar a rede. É o dado que quase ninguém posta.\n\n(mempool.space)")
            return texto, r["arquivo"], "hashrate"
        if tipo == "btc":
            texto = (f"₿ Bitcoin em {_usd(r['atual'])} ({_pct(r['var_pct'])} em {r['dias']} dias).\n\n"
                     f"Máxima do período: {usd0(r['max'])}. Mínima: {usd0(r['min'])}.\n\n(CoinGecko)")
            return texto, r["arquivo"], "bitcoin 90 dias"
    raise ValueError(f"tipo desconhecido: {tipo}")
