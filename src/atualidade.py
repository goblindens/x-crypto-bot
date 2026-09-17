"""A materia e de agora, ou e fato velho republicado hoje?

Regra dele, 17/09/2026: *"verifique primeiro se a noticia e atual"*.

O filtro de 6 h olha a hora de PUBLICACAO. Isso nao basta: jornal republica,
reaquece e faz retrospectiva o tempo todo, e a hora de publicacao fica nova
enquanto o fato continua velho.

O caso que abriu a trava, no feed de 17/09/2026:

    "Governo da Polonia perdeu US$ 230 milhoes em criptomoedas em operacao de
     petroleo, diz FT"
    publicada ha 2 h -- e o resumo diz "o caso aconteceu entre o fim de 2023 e
    marco de 2024 e ja havia sido noticiado".

Publicar isso como noticia de agora e o tipo de erro que custa credibilidade
sem nem ser mentira: cada frase esta certa, e mesmo assim o post engana.

Duas conferencias:
  1. IDADE -- quanto tempo desde a publicacao.
  2. FATO VELHO -- o texto aponta para um periodo que ja passou (ano anterior,
     mes com ano antigo, "ha dois anos"), ou se entrega como republicacao
     ("ja havia sido noticiado", "relembre", "retrospectiva").
"""
from __future__ import annotations

import re

from .util import fold, now_utc

# Entregam republicacao/retrospectiva mesmo sem data no texto.
_REAQUECIDO = (
    "ja havia sido noticiado", "ja havia sido divulgado", "ja tinha sido noticiado",
    "relembre", "relembra", "retrospectiva", "ha um ano", "ha dois anos", "ha tres anos",
    "no ano passado", "em retrospecto", "revisitando", "o caso aconteceu",
    "o caso ocorreu", "aconteceu entre", "ocorreu entre", "years ago", "a year ago",
    "last year", "previously reported", "had already been reported", "looking back",
)

_MESES = ("janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro", "january", "february", "march",
          "april", "may", "june", "july", "august", "september", "october", "november",
          "december")


def checar(article, max_horas: float = 6.0) -> dict:
    """{'ok': bool, 'motivo': str, 'idade_h': float|None}."""
    agora = now_utc()
    idade = None
    if getattr(article, "published", None):
        idade = (agora - article.published).total_seconds() / 3600
        if idade > max_horas:
            return {"ok": False, "idade_h": idade,
                    "motivo": f"materia tem {idade:.1f} h (teto {max_horas:g} h)"}
        # Hora adiantada e NORMAL, nao defeito: no feed de 17/09, 8 das 38
        # materias vinham do futuro (ate 2,1 h) -- embargo, fuso, agendamento.
        # Barrar isso derrubava CoinDesk, Bloomberg e The Block com noticia
        # verdadeira. So e defeito quando passa da propria janela.
        if idade < -max_horas:
            return {"ok": False, "idade_h": idade,
                    "motivo": f"publicada {-idade:.1f} h no futuro -- feed com hora errada"}

    texto = fold(f"{getattr(article, 'title', '')} {getattr(article, 'summary', '')}")

    for marca in _REAQUECIDO:
        if marca in texto:
            return {"ok": False, "idade_h": idade,
                    "motivo": f"fato velho republicado hoje: o texto diz '{marca}'"}

    # Ano anterior citado no corpo. Cuidado: quase todo texto de mercado cita
    # ano antigo como REFERENCIA ("primeira alta de juros desde julho de 2023",
    # "maior desde 2021") -- isso e contexto e tem que passar. So e fato velho
    # quando o ano marca QUANDO ACONTECEU.
    ano_atual = agora.year
    _REFERENCIA = r"(?:desde|since|from|apos|after|maior|menor|melhor|pior|primeir|ultim|recorde|high|low|record)"
    for m in re.finditer(r"\b(19|20)\d{2}\b", texto):
        ano = int(m.group(0))
        if ano >= ano_atual:
            continue
        trecho = texto[max(0, m.start() - 60):m.start()]
        if re.search(rf"\b{_REFERENCIA}\w*\b(?:\W+\w+){{0,6}}\W*$", trecho):
            continue                      # "desde julho de 2023" -- ponto de referencia
        if re.search(r"\b(aconteceu|ocorreu|comecou|durou|happened|occurred|began|entre)\b"
                     r"(?:\W+\w+){0,6}\W*$", trecho):
            return {"ok": False, "idade_h": idade,
                    "motivo": f"o fato e de {ano}, nao de agora"}

    return {"ok": True, "idade_h": idade, "motivo": ""}
