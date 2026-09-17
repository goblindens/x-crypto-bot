"""TERMÔMETRO DA TROPA — o dado do dia com a cara da casa, direto no bot.

Criado em 17/09/2026, quando ele pediu "algo nosso, com a nossa identidade, que
pode ser remunerado, no modelo que mais tem alcance dentro do nosso nicho".

Por que este formato resolve três coisas ao mesmo tempo:
  - ALCANCE: meme com imagem é o que mais rende na conta dele e no nicho
  - DINHEIRO: o Original Content Rewards do X (07/08/2026) NÃO paga conteúdo
    republicado; arte própria paga, manchete traduzida não
  - INFORMAÇÃO: carrega o Medo & Ganância medido na hora

Roda no bot (Tóquio e GitHub), sem depender do Mac dele.
Usa só PIL e as fontes que o grafico.py já resolve em cada sistema.

    python -m src.termometro              gera e mostra o caminho
    python -m src.main --mode dado --tipo termometro
"""
from __future__ import annotations

import os
import random

from PIL import Image, ImageDraw

from .grafico import LOGO, PRETO, TEXTO, CINZA, _fonte, serie_fng

W, H = 1080, 1350
MOLDURA = (28, 28, 28)

# faixa do indice -> (cor, nome). A cor muda todo dia com o mercado.
FAIXAS = (
    (0, 24, (224, 81, 58), "MEDO EXTREMO"),
    (25, 44, (224, 138, 58), "MEDO"),
    (45, 55, (201, 201, 58), "NEUTRO"),
    (56, 74, (123, 201, 58), "GANÂNCIA"),
    (75, 100, (39, 201, 54), "GANÂNCIA EXTREMA"),
)

# A piada é da casa, não da IA: uma lista curta por faixa, sorteada no dia.
# Nenhuma faz previsão de preço nem promete resultado -- regra dele.
PIADAS = {
    "MEDO EXTREMO": [
        ("Todo mundo com medo ao mesmo tempo.", "E você: olhando ou fingindo que não viu?"),
        ("O mercado tá igual grupo de família às 3h.", "Você compra no vermelho ou espera acalmar?"),
        ("Pânico geral. Nada novo por aqui.", "Você já viu esse filme antes?"),
    ],
    "MEDO": [
        ("Mercado com o pé atrás.", "Você opera com medo ou espera o índice virar?"),
        ("Clima de quem já se queimou antes.", "Comprando na baixa ou de fora?"),
    ],
    "NEUTRO": [
        ("Mercado em cima do muro. Nem medo, nem festa.", "E você: comprando ou esperando passar?"),
        ("Dia de lado. O tédio também é posição.", "Você opera de lado ou fica de fora?"),
        ("Nem euforia, nem pânico. Raro.", "Dia de lado é dia de fazer o quê?"),
    ],
    "GANÂNCIA": [
        ("O pessoal voltou a ficar animado.", "Você entra na animação ou desconfia dela?"),
        ("Ganância batendo na porta de novo.", "Realiza lucro ou segura?"),
    ],
    "GANÂNCIA EXTREMA": [
        ("Todo mundo gênio de novo.", "Você realiza ou segura mais um pouco?"),
        ("Euforia no talo. Já vimos esse capítulo.", "Segurando ou tirando da mesa?"),
    ],
}


def faixa(n: int):
    for lo, hi, cor, nome in FAIXAS:
        if lo <= n <= hi:
            return cor, nome
    return CINZA, ""


def _quebrar(d, texto, fonte, largura):
    linhas, atual = [], ""
    for p in texto.split():
        teste = (atual + " " + p).strip()
        if d.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _espacado(d, xy, texto, fonte, cor, tracking=8):
    x, y = xy
    for ch in texto:
        d.text((x, y), ch, font=fonte, fill=cor)
        x += d.textlength(ch, font=fonte) + tracking


def gerar(saida: str, piada: str = "", pergunta: str = "") -> dict:
    pts, _ = serie_fng(90)
    vals = [int(v) for _, v in pts]
    n = vals[-1]
    ontem = vals[-2] if len(vals) > 1 else None
    cor, nome = faixa(n)
    if not piada:
        piada, pergunta = random.choice(PIADAS.get(nome, PIADAS["NEUTRO"]))

    img = Image.new("RGB", (W, H), PRETO)
    d = ImageDraw.Draw(img)
    X = 97

    d.rectangle([40, 40, W - 40, H - 40], outline=MOLDURA, width=2)
    _espacado(d, (X, 103), "TERMÔMETRO DA TROPA", _fonte(22, True), CINZA, 9)
    d.ellipse([W - 107, 101, W - 93, 115], fill=cor)

    # numero gigante
    fnum = _fonte(280, True)
    largura = d.textlength(str(n), font=fnum)
    d.text((X, 190), str(n), font=fnum, fill=cor)
    _espacado(d, (X + largura + 34, 320), nome, _fonte(26, True), cor, 7)
    d.text((X + largura + 34, 366), "medo & ganância", font=_fonte(25), fill=CINZA)

    # barra 0-100
    by = 540
    d.rounded_rectangle([X, by, W - X, by + 18], radius=9, fill=(26, 26, 26))
    d.rounded_rectangle([X, by, X + int((W - 2 * X) * n / 100), by + 18], radius=9, fill=cor)
    d.text((X, by + 32), "0 · medo", font=_fonte(21), fill=CINZA)
    d.text((W - X, by + 32), "ganância · 100", font=_fonte(21), fill=CINZA, anchor="ra")

    # a piada
    fp = _fonte(62, True)
    y = 680
    for linha in _quebrar(d, piada, fp, W - 2 * X)[:3]:
        d.text((X, y), linha, font=fp, fill=TEXTO)
        y += 76

    # a pergunta
    if pergunta:
        d.line([X, 1000, W - X, 1000], fill=(30, 38, 30), width=2)
        d.text((X, 1036), pergunta, font=_fonte(33, True), fill=cor)

    # rodape
    ontem_txt = f" · ontem {ontem}" if ontem is not None else ""
    d.text((X, 1120), f"Fonte: alternative.me{ontem_txt}", font=_fonte(20), fill=(110, 110, 110))
    d.text((X, 1148), "Não é recomendação de investimento.", font=_fonte(20), fill=(110, 110, 110))
    try:
        logo = Image.open(LOGO).convert("RGBA")
        logo.thumbnail((170, 56))
        img.paste(logo, (X, 1190), logo)
    except Exception:
        pass
    try:
        from .qr import gerar as gerar_qr
        qr = Image.open(gerar_qr()).convert("RGBA").resize((90, 90))
        img.paste(qr, (W - X - 90, 1175), qr)
    except Exception:
        pass

    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    img.save(saida, optimize=True)
    return {"arquivo": saida, "valor": n, "rotulo": nome, "ontem": ontem,
            "piada": piada, "pergunta": pergunta, "cor": cor}


if __name__ == "__main__":
    r = gerar(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "artes", "auto", "termometro.png"))
    print(r["arquivo"], "|", r["valor"], r["rotulo"], "|", r["piada"])
