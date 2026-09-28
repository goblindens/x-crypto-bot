"""Retrato do mercado MEDIDO AGORA -- nada escrito antes.

Correcao dele em 17/09/2026: "não quero isso. Quero coisas reais em tempo real,
não coisa programada assim."

A versao anterior do Termometro sorteava uma piada de uma lista de 12. Medido:
o indice de Medo & Ganancia ficou **35 dias seguidos na mesma faixa** nos ultimos
90 -- com 2 piadas naquela faixa, a mesma frase sairia 17 vezes. Conteudo
enlatado com cara de novidade.

Aqui nao existe frase pronta. Cada numero e buscado no momento da geracao, e a
LEITURA do dia sai da comparacao entre eles -- muda porque o mercado mudou, nao
porque um random.choice escolheu outra.

Tudo de graca e sem chave de API.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

TIMEOUT = 12
UA = {"User-Agent": "Mozilla/5.0 (Macintosh)"}
BR = timezone(timedelta(hours=-3))


def _tenta(fn, padrao=None):
    """Uma fonte fora do ar nunca derruba o card inteiro."""
    try:
        return fn()
    except Exception:
        return padrao


def fng() -> dict:
    d = requests.get("https://api.alternative.me/fng/?limit=2", timeout=TIMEOUT).json()["data"]
    return {"valor": int(d[0]["value"]), "rotulo": d[0]["value_classification"],
            "ontem": int(d[1]["value"]) if len(d) > 1 else None}


def moeda(par: str) -> dict:
    d = requests.get("https://www.okx.com/api/v5/market/ticker",
                     params={"instId": par}, timeout=TIMEOUT, headers=UA).json()["data"][0]
    preco, abertura = float(d["last"]), float(d["open24h"])
    return {"preco": preco, "var": (preco / abertura - 1) * 100,
            "alta": float(d["high24h"]), "baixa": float(d["low24h"])}


def global_cripto() -> dict:
    g = requests.get("https://api.coingecko.com/api/v3/global",
                     timeout=TIMEOUT, headers=UA).json()["data"]
    return {"cap": g["total_market_cap"]["usd"],
            "var_cap": g["market_cap_change_percentage_24h_usd"],
            "dominancia": g["market_cap_percentage"]["btc"]}


def procuradas() -> list:
    d = requests.get("https://api.coingecko.com/api/v3/search/trending",
                     timeout=TIMEOUT, headers=UA).json()["coins"]
    return [c["item"]["symbol"].upper() for c in d[:5]]


def coletar() -> dict:
    """Uma foto do mercado no instante. Campo que falhou vem None."""
    return {
        "quando": datetime.now(BR),
        "fng": _tenta(fng, {}),
        "btc": _tenta(lambda: moeda("BTC-USDT"), {}),
        "eth": _tenta(lambda: moeda("ETH-USDT"), {}),
        "global": _tenta(global_cripto, {}),
        "procuradas": _tenta(procuradas, []),
    }


# ------------------------------------------------------------------ leitura
def leitura(m: dict) -> tuple[str, str]:
    """A frase do card, DERIVADA dos numeros -- nao escolhida de uma lista.

    Devolve (manchete, detalhe). A ordem das regras e por forca do sinal: o que
    for mais incomum hoje e o que vira o titulo. Em dia parado, o titulo E que
    o dia esta parado -- isso tambem e informacao, e e verdade.
    """
    btc, eth = m.get("btc") or {}, m.get("eth") or {}
    f, g = m.get("fng") or {}, m.get("global") or {}
    var = btc.get("var")
    valor, ontem = f.get("valor"), f.get("ontem")
    salto = (valor - ontem) if (valor is not None and ontem is not None) else None

    # 1. movimento forte de preco fala mais alto que qualquer outra coisa
    if var is not None and abs(var) >= 4:
        lado = "subiu" if var > 0 else "caiu"
        amp = ""
        if btc.get("alta") and btc.get("baixa"):
            amp = f" Entre {btc['baixa']:,.0f} e {btc['alta']:,.0f} nas últimas 24h."
        return (f"BTC {lado} {abs(var):.1f}% em 24 horas", f"Agora em US$ {btc['preco']:,.0f}.{amp}")

    # 2. virada de humor: o indice pulou de faixa de um dia pro outro
    if salto is not None and abs(salto) >= 8:
        lado = "subiu" if salto > 0 else "despencou"
        return (f"O humor {lado} {abs(salto)} pontos em um dia",
                f"Medo & Ganância foi de {ontem} para {valor} ({f.get('rotulo','')}).")

    # 3. BTC e altcoins andando em direcoes opostas
    if var is not None and eth.get("var") is not None and abs(var - eth["var"]) >= 3:
        quem = "BTC" if var > eth["var"] else "ETH"
        outro = "ETH" if quem == "BTC" else "BTC"
        return (f"{quem} e {outro} descolaram hoje",
                f"BTC {var:+.1f}% e ETH {eth['var']:+.1f}% nas últimas 24h.")

    # 4. dominancia em extremo
    dom = g.get("dominancia")
    if dom is not None and dom >= 60:
        return (f"Bitcoin é {dom:.0f}% do mercado", "Dinheiro concentrado nele, não nas altcoins.")
    if dom is not None and dom <= 45:
        return (f"Bitcoin caiu para {dom:.0f}% do mercado", "Dinheiro girando para altcoins.")

    # 5. mercado inteiro se mexendo junto
    vc = g.get("var_cap")
    if vc is not None and abs(vc) >= 3:
        return (f"O mercado inteiro {'subiu' if vc > 0 else 'caiu'} {abs(vc):.1f}%",
                f"Valor total agora em US$ {g['cap']/1e12:.2f} trilhões.")

    # 6. dia parado -- e o titulo diz isso, sem enfeitar
    if valor is not None:
        quase = f" Ontem estava {ontem}." if ontem is not None else ""
        return (f"Dia parado: Medo & Ganância em {valor}",
                f"{f.get('rotulo','')}.{quase} BTC {var:+.1f}% em 24h." if var is not None else f"{f.get('rotulo','')}.{quase}")
    return ("Mercado cripto agora", "")


def resumo_texto(m: dict) -> str:
    """Os numeros em uma linha cada, pro post de texto."""
    linhas = []
    f, btc, eth, g = m.get("fng") or {}, m.get("btc") or {}, m.get("eth") or {}, m.get("global") or {}
    if f.get("valor") is not None:
        ont = f" (ontem {f['ontem']})" if f.get("ontem") is not None else ""
        linhas.append(f"Medo & Ganância: {f['valor']} · {f.get('rotulo','')}{ont}")
    if btc.get("preco"):
        linhas.append(f"BTC: US$ {btc['preco']:,.0f} ({btc['var']:+.1f}% em 24h)")
    if eth.get("preco"):
        linhas.append(f"ETH: US$ {eth['preco']:,.0f} ({eth['var']:+.1f}% em 24h)")
    if g.get("dominancia"):
        linhas.append(f"Dominância BTC: {g['dominancia']:.1f}%")
    if m.get("procuradas"):
        linhas.append("Mais procuradas: " + ", ".join(m["procuradas"][:4]))
    return "\n".join(linhas)


if __name__ == "__main__":
    m = coletar()
    t, det = leitura(m)
    print(f"[{m['quando']:%d/%m %H:%M}]\n")
    print(" ", t)
    print(" ", det, "\n")
    print(resumo_texto(m))
