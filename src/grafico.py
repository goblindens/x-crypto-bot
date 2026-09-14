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
def _ticks(minv: float, maxv: float, n: int = 4) -> list:
    """Ticks 'limpos' (1-2-5 x 10^k) cobrindo a faixa -- eixo que passa credibilidade."""
    import math
    faixa = (maxv - minv) or 1.0
    bruto = faixa / n
    mag = 10 ** math.floor(math.log10(bruto))
    passo = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= bruto)
    ini = math.floor(minv / passo) * passo
    fim = math.ceil(maxv / passo) * passo
    out, v = [], ini
    while v <= fim + 1e-9:
        out.append(v); v += passo
    return out


def desenhar(pts, meta, saida: str, subtitulo: str = "") -> dict:
    """Anatomia institucional (skill dataviz, 14/09): titulo + subtitulo com periodo/unidade,
    numero-heroi, delta em texto neutro com ponto colorido, linha fina, area a 10%,
    marcador no fim com anel, rotulo direto so no ultimo ponto, grade hairline,
    eixo com numeros redondos, rodape com fonte. Desenhado em 2x e reduzido (antialias)."""
    S = 2                                                     # supersampling
    vals = [v for _, v in pts]
    atual, primeiro = vals[-1], vals[0]
    minv, maxv = min(vals), max(vals)
    var = (atual / primeiro - 1) * 100 if primeiro else 0.0
    n_dias = (pts[-1][0] - pts[0][0]).days or 1
    ontem = meta.get("ontem")
    sobe = (atual >= ontem) if (meta.get("indice") and ontem is not None) else (atual >= primeiro)
    cor = VERDE if sobe else VERM

    W2, H2 = W * S, H * S
    img = Image.new("RGBA", (W2, H2), PRETO + (255,))
    d = ImageDraw.Draw(img)
    F = lambda tam, neg=False: _fonte(tam * S, neg)
    M = 60 * S                                                # margem

    # --- cabecalho: o que e (titulo), periodo/unidade (subtitulo), numero-heroi, delta
    d.text((M, 46 * S), meta["titulo"].upper(), font=F(24, True), fill=CINZA)
    sub = f"{n_dias} dias  ·  {meta.get('unidade') or 'índice'}  ·  {meta['fonte']}"
    d.text((M, 78 * S), sub, font=F(20), fill=(110, 120, 110))
    d.text((M, 112 * S), meta["fmt"](atual), font=F(88, True), fill=TEXTO)
    y_delta = 222 * S
    d.ellipse([M, y_delta + 9 * S, M + 14 * S, y_delta + 23 * S], fill=cor)        # a cor fica na marca, nao no texto
    if meta.get("indice"):
        i_max = max(i for i, v in enumerate(vals) if v == maxv); i_min = max(i for i, v in enumerate(vals) if v == minv)
        delta_txt = (f"ontem {ontem:.0f}  ·  " if ontem is not None else "") + \
                    f"máx {maxv:.0f} em {pts[i_max][0].astimezone(BR).strftime('%d/%m')}  ·  mín {minv:.0f} em {pts[i_min][0].astimezone(BR).strftime('%d/%m')}"
    else:
        sinal = "+" if var >= 0 else "−"
        delta_txt = f"{sinal}{abs(var):.1f}% em {n_dias} dias".replace(".", ",") + f"  ·  de {meta['fmt'](primeiro)} para {meta['fmt'](atual)}"
    d.text((M + 24 * S, y_delta), delta_txt, font=F(26, True), fill=TEXTO)
    if meta.get("rotulo"):
        d.text((M, 262 * S), meta["rotulo"], font=F(22), fill=CINZA)

    # --- area do grafico
    x0, y0, x1, y1 = M, 318 * S, W2 - M, H2 - 150 * S
    ticks = _ticks(minv, maxv, n=5)                           # 5-6 linhas: eixo justo, sem ar sobrando
    lo, hi = ticks[0], ticks[-1]
    pad_l = max(d.textlength(meta["fmt"](t), font=F(18)) for t in ticks) + 16 * S
    gx0, gy0, gx1, gy1 = x0 + pad_l, y0 + 10 * S, x1 - 10 * S, y1 - 34 * S
    faixa = (hi - lo) or 1.0
    def X(i): return gx0 + (gx1 - gx0) * i / max(1, len(pts) - 1)
    def Y(v): return gy1 - (gy1 - gy0) * (v - lo) / faixa
    for t in ticks:                                           # grade hairline + eixo com numero redondo (texto neutro)
        yy = Y(t)
        d.line([(gx0, yy), (gx1, yy)], fill=LINHA, width=1 * S)
        d.text((gx0 - 12 * S, yy), meta["fmt"](t), font=F(18), fill=CINZA, anchor="rm")
    poly = [(X(i), Y(v)) for i, v in enumerate(vals)]
    area = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    ImageDraw.Draw(area).polygon(poly + [(gx1, gy1), (gx0, gy1)], fill=cor + (26,))   # ~10% de opacidade
    img = Image.alpha_composite(img, area); d = ImageDraw.Draw(img)
    d.line(poly, fill=cor, width=2 * S + 1, joint="curve")   # linha fina
    px, py = poly[-1]
    r = 6 * S
    d.ellipse([px - r - 2 * S, py - r - 2 * S, px + r + 2 * S, py + r + 2 * S], fill=PRETO)  # anel da superficie
    d.ellipse([px - r, py - r, px + r, py + r], fill=cor)
    rot = meta["fmt"](atual)                                  # rotulo direto so no ultimo ponto
    tw = d.textlength(rot, font=F(20, True))
    lx = min(px + 14 * S, gx1 - tw); ly = max(gy0, min(py - 32 * S, gy1 - 30 * S))
    d.rounded_rectangle([lx - 8 * S, ly - 4 * S, lx + tw + 8 * S, ly + 26 * S], radius=6 * S, fill=PAINEL)
    d.text((lx, ly), rot, font=F(20, True), fill=TEXTO)
    n = len(pts)                                              # datas: 5 marcas
    for i in sorted({0, n // 4, n // 2, (3 * n) // 4, n - 1}):
        d.text((X(i), gy1 + 8 * S), pts[i][0].astimezone(BR).strftime("%d/%m"), font=F(18), fill=CINZA, anchor="ma")
    d.line([(gx0, gy1), (gx1, gy1)], fill=LINHA, width=1 * S)

    # --- rodape: fonte (regra dele: sem horario, sem "conferido")
    quando = datetime.now(BR).strftime("%d/%m/%Y %H:%M")      # so pro registro (nao vai na imagem)
    d.line([(M, H2 - 118 * S), (W2 - M, H2 - 118 * S)], fill=LINHA, width=1 * S)
    d.text((M, H2 - 96 * S), f"Fonte: {meta['fonte']}", font=F(24), fill=CINZA)
    d.text((M, H2 - 60 * S), "Não é recomendação de investimento.", font=F(18), fill=(90, 100, 90))
    x_dir = W2 - M
    try:
        from .qr import imagem as qr_imagem
        qr = qr_imagem(tamanho=84 * S)
        if qr is not None:
            img.paste(qr, (x_dir - 84 * S, H2 - 112 * S)); x_dir -= 84 * S + 20 * S
    except Exception:
        pass
    if os.path.exists(LOGO):
        try:
            lg = Image.open(LOGO).convert("RGBA"); lg.thumbnail((200 * S, 64 * S))
            img.paste(lg, (x_dir - lg.width, H2 - 105 * S), lg)
        except Exception:
            d.text((x_dir, H2 - 62 * S), "SecretLab", font=F(22, True), fill=VERDE, anchor="ra")
    else:
        d.text((x_dir, H2 - 62 * S), "SecretLab", font=F(22, True), fill=VERDE, anchor="ra")

    final = img.convert("RGB").resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    final.save(saida, quality=94)
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
