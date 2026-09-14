"""Graficos proprios, com dado publico, na identidade SecretLab -- o modelo que
mais rendeu no Threads dele (imagem de dado real + legenda com numero).

Tudo gratis e verificavel: o numero da legenda e o mesmo ponto da serie que
esta no grafico, buscado na hora. Fontes com historico:
  - fng        Medo & Ganancia, 90 dias          alternative.me
  - stable     stablecoins em circulacao, 90 d   DefiLlama
  - btc        preco do Bitcoin, 90 dias         CoinGecko
  - hashrate   hashrate da rede, 3 meses         mempool.space

Uso: python -m src.grafico fng|stable|btc|hashrate [saida.png]
     -> imprime um JSON com o caminho, o valor atual, a variacao e a fonte,
        pra legenda usar exatamente o mesmo numero.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont

UA = {"User-Agent": "Mozilla/5.0 (Macintosh)"}
T = 20
BR = timezone(timedelta(hours=-3))
W, H = 1200, 900
PRETO, PAINEL, LINHA, TEXTO, CINZA = (6, 8, 6), (12, 16, 12), (28, 36, 28), (236, 240, 236), (140, 150, 140)
VERDE, VERDE_ESC, VERM, AMAR = (39, 201, 54), (16, 80, 24), (224, 81, 58), (245, 166, 35)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.expanduser("~/SecretLab/Identidade Visual/secretlab_logo.png")


def _fonte(tam: int, negrito: bool = False):
    cands = (["/System/Library/Fonts/SFNS.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if negrito else "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if negrito else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for c in cands:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, tam)
            except OSError:
                continue
    return ImageFont.load_default()


# ------------------------------------------------------------------- dados
def serie_fng(dias=90):
    d = requests.get("https://api.alternative.me/fng/", params={"limit": dias, "format": "json"}, timeout=T).json()["data"]
    # o indice e diario (data UTC); fixo ao meio-dia pra data nao "voltar um dia" ao converter pra BRT
    pts = [(datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc).replace(hour=12), float(x["value"])) for x in reversed(d)]
    trad = {"Extreme Fear": "Medo extremo", "Fear": "Medo", "Neutral": "Neutro", "Greed": "Ganância", "Extreme Greed": "Ganância extrema"}
    rot = trad.get(d[0]["value_classification"], d[0]["value_classification"])
    ontem = float(d[1]["value"]) if len(d) > 1 else None
    return pts, {"titulo": "Medo & Ganância", "unidade": "", "fonte": "alternative.me", "rotulo": rot, "indice": True,
                 "ontem": ontem, "fmt": lambda v: f"{v:.0f}"}


def serie_stable(dias=90):
    d = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", timeout=T).json()[-dias:]
    pts = [(datetime.fromtimestamp(int(x["date"]), tz=timezone.utc), float(x["totalCirculatingUSD"]["peggedUSD"]) / 1e9) for x in d]
    return pts, {"titulo": "Stablecoins em circulação", "unidade": "US$ bi", "fonte": "DefiLlama", "fmt": lambda v: f"US$ {v:,.1f} bi".replace(",", "X").replace(".", ",").replace("X", ".")}


def serie_btc(dias=90):
    d = requests.get("https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                     params={"vs_currency": "usd", "days": dias, "interval": "daily"}, timeout=T, headers=UA).json()["prices"]
    pts = [(datetime.fromtimestamp(t / 1000, tz=timezone.utc), float(p)) for t, p in d]
    return pts, {"titulo": "Bitcoin (US$)", "unidade": "US$", "fonte": "CoinGecko", "fmt": lambda v: "US$ " + f"{v:,.0f}".replace(",", ".")}


def serie_hashrate():
    d = requests.get("https://mempool.space/api/v1/mining/hashrate/3m", timeout=T).json()["hashrates"]
    pts = [(datetime.fromtimestamp(int(x["timestamp"]), tz=timezone.utc), float(x["avgHashrate"]) / 1e18) for x in d]
    return pts, {"titulo": "Hashrate da rede Bitcoin", "unidade": "EH/s", "fonte": "mempool.space", "fmt": lambda v: f"{v:,.0f} EH/s".replace(",", ".")}


SERIES = {"fng": serie_fng, "stable": serie_stable, "btc": serie_btc, "hashrate": serie_hashrate}


# ----------------------------------------------------------------- desenho
def desenhar(pts, meta, saida: str, subtitulo: str = "") -> dict:
    vals = [v for _, v in pts]
    atual, primeiro = vals[-1], vals[0]
    minv, maxv = min(vals), max(vals)
    var = (atual / primeiro - 1) * 100 if primeiro else 0.0
    n_dias = (pts[-1][0] - pts[0][0]).days or 1
    cor = VERDE if atual >= primeiro else VERM

    img = Image.new("RGB", (W, H), PRETO)
    d = ImageDraw.Draw(img)
    # cabecalho
    d.text((60, 50), meta["titulo"].upper(), font=_fonte(26, True), fill=CINZA)
    d.text((60, 90), meta["fmt"](atual), font=_fonte(92, True), fill=TEXTO)
    sinal = "+" if var >= 0 else "−"
    if meta.get("indice"):
        # indice (0-100): variacao percentual nao faz sentido; mostra ontem e a faixa do periodo
        # ultima ocorrencia da maxima/minima (a mais recente e a que a legenda cita)
        i_max = max(i for i, v in enumerate(vals) if v == maxv); i_min = max(i for i, v in enumerate(vals) if v == minv)
        ontem = meta.get("ontem")
        cor = VERDE if (ontem is None or atual >= ontem) else VERM
        linha2 = (f"ontem {ontem:.0f}  ·  " if ontem is not None else "") + \
                 f"máx {maxv:.0f} ({pts[i_max][0].astimezone(BR).strftime('%d/%m')})  ·  mín {minv:.0f} ({pts[i_min][0].astimezone(BR).strftime('%d/%m')})"
        d.text((60, 200), linha2, font=_fonte(30, True), fill=cor)
    else:
        d.text((60, 200), f"{sinal}{abs(var):.1f}% em {n_dias} dias".replace(".", ","), font=_fonte(34, True), fill=cor)
    if meta.get("rotulo"):
        d.text((60, 246), meta["rotulo"], font=_fonte(28), fill=CINZA)
    if subtitulo:
        d.text((60, 290), subtitulo, font=_fonte(28), fill=CINZA)
    # area do grafico
    x0, y0, x1, y1 = 60, 340, W - 60, H - 150
    d.rounded_rectangle([x0, y0, x1, y1], radius=18, fill=PAINEL, outline=LINHA, width=2)
    pad = 28
    gx0, gy0, gx1, gy1 = x0 + pad, y0 + pad, x1 - pad, y1 - pad
    faixa = (maxv - minv) or 1.0
    def X(i): return gx0 + (gx1 - gx0) * i / max(1, len(pts) - 1)
    def Y(v): return gy1 - (gy1 - gy0) * (v - minv) / faixa
    poly = [(X(i), Y(v)) for i, v in enumerate(vals)]
    d.polygon(poly + [(gx1, gy1), (gx0, gy1)], fill=(cor[0] // 6 + 6, cor[1] // 6 + 8, cor[2] // 6 + 6))
    for k in range(5):                                       # grade e rotulos (por cima da area)
        yy = gy0 + (gy1 - gy0) * k / 4
        d.line([(gx0, yy), (gx1, yy)], fill=LINHA, width=1)
        v = maxv - faixa * k / 4
        d.text((gx1 - 8, yy - 26), meta["fmt"](v), font=_fonte(20), fill=CINZA, anchor="ra")
    d.line(poly, fill=cor, width=4, joint="curve")
    px, py = poly[-1]
    d.ellipse([px - 9, py - 9, px + 9, py + 9], fill=cor)
    d.ellipse([px - 16, py - 16, px + 16, py + 16], outline=cor, width=2)
    # datas
    for i in (0, len(pts) // 2, len(pts) - 1):
        d.text((X(i), gy1 + 6), pts[i][0].astimezone(BR).strftime("%d/%m"), font=_fonte(20), fill=CINZA, anchor="ma")
    # rodape
    quando = datetime.now(BR).strftime("%d/%m/%Y %H:%M")          # so pro registro (nao vai na imagem)
    d.text((60, H - 100), f"Fonte: {meta['fonte']}", font=_fonte(24), fill=CINZA)
    d.text((60, H - 62), "Não é recomendação de investimento.", font=_fonte(20), fill=(90, 100, 90))
    x_dir = W - 60
    try:                                                     # QR do grupo (pedido dele, 14/09), pequeno, ao lado da logo
        from .qr import imagem as qr_imagem
        qr = qr_imagem(tamanho=84)
        if qr is not None:
            img.paste(qr, (x_dir - 84, H - 112))
            x_dir -= 84 + 20
    except Exception:
        pass
    if os.path.exists(LOGO):
        try:
            lg = Image.open(LOGO).convert("RGBA")
            lg.thumbnail((200, 64))
            img.paste(lg, (x_dir - lg.width, H - 105), lg)
        except Exception:
            d.text((x_dir, H - 62), "SecretLab", font=_fonte(22, True), fill=VERDE, anchor="ra")
    else:
        d.text((x_dir, H - 62), "SecretLab", font=_fonte(22, True), fill=VERDE, anchor="ra")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    img.save(saida, quality=92)
    return {"arquivo": saida, "atual": atual, "atual_txt": meta["fmt"](atual), "primeiro": primeiro, "var_pct": round(var, 2),
            "dias": n_dias, "min": minv, "max": maxv, "fonte": meta["fonte"], "quando": quando, "rotulo": meta.get("rotulo", "")}


def gerar(nome: str, saida: str | None = None, subtitulo: str = "", dias: int | None = None) -> dict:
    fn = SERIES[nome]
    pts, meta = (fn(dias) if (dias and nome != "hashrate") else fn())
    saida = saida or os.path.join(ROOT, "artes", f"grafico-{nome}.png")
    return desenhar(pts, meta, saida, subtitulo)


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in SERIES:
        print("uso: python -m src.grafico fng|stable|btc|hashrate [saida.png]"); sys.exit(2)
    dias = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--dias=")), None)
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    r = gerar(sys.argv[1], args[0] if args else None, dias=dias)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
