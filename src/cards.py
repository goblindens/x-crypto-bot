"""Cards SecretLab pra acompanhar cada post (o Threads dele rende 2,7x com imagem).

- card_manchete: manchete grande + numero em destaque + fonte + hora
- card_mercado:  visao geral (BTC/ETH/SOL, cap total, dominancia, M&G, stablecoins)
- card_trending: moedas mais buscadas no CoinGecko, com variacao 24h

Todos 1080x1080 (1:1, o que o Threads mostra inteiro), preto, verde SecretLab,
sem foto de terceiro, sem banner alheio. O numero que aparece no card e o mesmo
que vai na legenda: sai da mesma chamada de API.
"""
from __future__ import annotations

import os
import re
import textwrap
from datetime import datetime, timezone, timedelta

from PIL import Image, ImageDraw

from .grafico import _fonte, LOGO

W = H = 1080
PRETO, PAINEL, LINHA, TEXTO, CINZA = (6, 8, 6), (12, 16, 12), (28, 36, 28), (238, 242, 238), (140, 150, 140)
VERDE, VERM, AMAR = (39, 201, 54), (224, 81, 58), (245, 166, 35)
BR = timezone(timedelta(hours=-3))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_NUM = re.compile(r"(US\$|R\$|\$|€)?\s?(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)\s?(mil|milhões|milhão|mi|bilhões|bilhão|bi|tri|trilhões|%|BTC|ETH|SOL|x)?", re.I)


def _rodape(d, fonte: str, quando: str | None = None):
    quando = quando or datetime.now(BR).strftime("%d/%m/%Y %H:%M")
    d.line([(60, H - 150), (W - 60, H - 150)], fill=LINHA, width=2)
    d.text((60, H - 125), f"Fonte: {fonte}", font=_fonte(28), fill=CINZA)
    d.text((60, H - 85), f"{quando} BRT  ·  dado conferido na hora  ·  não é recomendação de investimento", font=_fonte(20), fill=(90, 100, 90))


def _logo(img, d):
    """Canto inferior direito: QR do grupo do WhatsApp (pedido dele, 14/09) + logo SecretLab."""
    x_dir = W - 60
    try:
        from .qr import imagem as qr_imagem
        qr = qr_imagem(tamanho=124)
        if qr is not None:
            img.paste(qr, (x_dir - 124, H - 140))
            d.text((x_dir - 62, H - 12), "grupo", font=_fonte(16), fill=CINZA, anchor="ma")
            x_dir -= 124 + 24
    except Exception:
        pass
    if os.path.exists(LOGO):
        try:
            lg = Image.open(LOGO).convert("RGBA"); lg.thumbnail((200, 70))
            img.paste(lg, (x_dir - lg.width, H - 112), lg); return
        except Exception:
            pass
    d.text((x_dir, H - 100), "SecretLab", font=_fonte(26, True), fill=VERDE, anchor="ra")


def _quebrar(texto: str, fonte, largura: int, d) -> list:
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = (atual + " " + palavra).strip()
        if d.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            if atual: linhas.append(atual)
            atual = palavra
    if atual: linhas.append(atual)
    return linhas


def destaque_numero(texto: str) -> str | None:
    """Pega o numero mais 'grande' da manchete pra virar destaque: 'US$ 463 mi', '85%', '103.252 ETH'."""
    melhor = None
    for m in _NUM.finditer(texto):
        moeda, num, uni = m.group(1) or "", m.group(2), (m.group(3) or "")
        if not uni and not moeda and len(num.replace(".", "").replace(",", "")) < 4:
            continue                                  # '15' de 'dia 15' nao e destaque
        cand = f"{moeda} {num} {uni}".strip().replace("  ", " ")
        if melhor is None or len(cand) > len(melhor):
            melhor = cand
    return melhor


def card_manchete(manchete: str, fonte: str, saida: str, prefixo: str = "NOVO", numero: str | None = None) -> str:
    img = Image.new("RGB", (W, H), PRETO); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 18, H], fill=VERDE)                                  # barra lateral
    cor_pref = VERM if prefixo.upper().startswith("URG") else VERDE
    d.rounded_rectangle([60, 60, 60 + 40 + d.textlength(prefixo.upper(), font=_fonte(30, True)), 116], radius=10, fill=cor_pref)
    d.text((80, 71), prefixo.upper(), font=_fonte(30, True), fill=(0, 0, 0))
    d.text((W - 60, 76), datetime.now(BR).strftime("%d/%m · %H:%M"), font=_fonte(28), fill=CINZA, anchor="ra")
    numero = numero if numero is not None else destaque_numero(manchete)
    y = 190
    if numero:
        tam = 150 if len(numero) <= 9 else (110 if len(numero) <= 14 else 84)
        d.text((60, y), numero, font=_fonte(tam, True), fill=VERDE)
        y += tam + 40
    limpa = re.sub(r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF☀-➿]+", "", manchete).strip()
    tam = 64 if len(limpa) <= 90 else (54 if len(limpa) <= 140 else 46)
    f = _fonte(tam, True)
    for linha in _quebrar(limpa, f, W - 140, d)[:6]:
        d.text((60, y), linha, font=f, fill=TEXTO); y += int(tam * 1.22)
    _rodape(d, fonte); _logo(img, d)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True); img.save(saida); return saida


def card_mercado(p: dict, saida: str) -> str:
    """p = dict do src.painel.painel()."""
    img = Image.new("RGB", (W, H), PRETO); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 18, H], fill=VERDE)
    d.text((60, 60), "MERCADO AGORA", font=_fonte(34, True), fill=CINZA)
    d.text((W - 60, 66), p.get("quando", ""), font=_fonte(28), fill=CINZA, anchor="ra")
    y = 130
    for sym, nome in (("BTC", "Bitcoin"), ("ETH", "Ethereum"), ("SOL", "Solana")):
        m = p.get("precos", {}).get(sym)
        if not m: continue
        cor = VERDE if m["var"] >= 0 else VERM
        d.rounded_rectangle([60, y, W - 60, y + 150], radius=18, fill=PAINEL, outline=LINHA, width=2)
        d.text((90, y + 22), nome, font=_fonte(28), fill=CINZA)
        preco = "US$ " + (f"{m['preco']:,.0f}" if m["preco"] >= 1000 else f"{m['preco']:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")
        d.text((90, y + 58), preco, font=_fonte(64, True), fill=TEXTO)
        var = ("+" if m["var"] >= 0 else "−") + f"{abs(m['var']):.1f}%".replace(".", ",")
        d.text((W - 90, y + 62), var, font=_fonte(56, True), fill=cor, anchor="ra")
        d.text((W - 90, y + 24), "24h", font=_fonte(24), fill=CINZA, anchor="ra")
        y += 170
    y += 10
    itens = []
    g = p.get("global")
    if g: itens += [("Cap. total", f"US$ {g['mcap_usd']/1e12:.2f} tri".replace(".", ",")), ("Domínio BTC", f"{g['dom_btc']:.1f}%".replace(".", ","))]
    f = p.get("fng")
    if f: itens.append(("Medo & Ganância", f"{f['valor']} · {f['rotulo']}"))
    if p.get("stablecoins_usd"): itens.append(("Stablecoins", f"US$ {p['stablecoins_usd']/1e9:,.0f} bi".replace(",", ".")))
    col = (W - 120 - 20) // 2
    for i, (k, v) in enumerate(itens[:4]):
        x = 60 + (i % 2) * (col + 20); yy = y + (i // 2) * 120
        d.rounded_rectangle([x, yy, x + col, yy + 104], radius=16, fill=PAINEL, outline=LINHA, width=2)
        d.text((x + 24, yy + 16), k.upper(), font=_fonte(22), fill=CINZA)
        d.text((x + 24, yy + 48), v, font=_fonte(40, True), fill=TEXTO)
    _rodape(d, "OKX, Binance, CoinGecko, alternative.me, DefiLlama", p.get("quando")); _logo(img, d)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True); img.save(saida); return saida


def card_trending(moedas: list, saida: str) -> str:
    """moedas = [{'simbolo','nome','var24h','rank'}], do CoinGecko /search/trending."""
    img = Image.new("RGB", (W, H), PRETO); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 18, H], fill=VERDE)
    d.text((60, 60), "MAIS BUSCADAS HOJE", font=_fonte(34, True), fill=CINZA)
    d.text((60, 105), "no CoinGecko, pelo mundo inteiro", font=_fonte(26), fill=(90, 100, 90))
    d.text((W - 60, 66), datetime.now(BR).strftime("%d/%m · %H:%M"), font=_fonte(28), fill=CINZA, anchor="ra")
    y = 170
    for i, m in enumerate(moedas[:8], 1):
        d.rounded_rectangle([60, y, W - 60, y + 80], radius=14, fill=PAINEL, outline=LINHA, width=2)
        d.text((90, y + 20), f"{i}", font=_fonte(36, True), fill=VERDE)
        d.text((150, y + 14), m["simbolo"].upper(), font=_fonte(40, True), fill=TEXTO)
        d.text((330, y + 24), m["nome"][:28], font=_fonte(28), fill=CINZA)
        v = m.get("var24h")
        if v is not None:
            cor = VERDE if v >= 0 else VERM
            d.text((W - 90, y + 20), ("+" if v >= 0 else "−") + f"{abs(v):.1f}%".replace(".", ","), font=_fonte(36, True), fill=cor, anchor="ra")
        y += 92
    _rodape(d, "CoinGecko (busca), variação 24h"); _logo(img, d)
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True); img.save(saida); return saida
