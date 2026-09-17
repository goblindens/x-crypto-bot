"""Bateria de ataques contra as travas. Roda offline, sem gastar API.

Regra da casa (17/09/2026): trava nova nasce com a lista de ataques junto.
Testar se funciona nao e testar se quebra -- o que vale e o caso que DEVERIA
falhar e nao falha. Foi assim que descobrimos, no mesmo dia, que:

  - `checar_fontes` devolvia "sem problemas" na primeira linha quando o post
    nao citava fonte, e dois fatos inventados passaram;
  - `confirmacao._mesmo_assunto` nao reconhecia a MESMA noticia em 5 veiculos.

Uso:  ./.venv/bin/python scripts/testar_travas.py
Sai com codigo 1 se qualquer caso falhar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta                                  # noqa: E402

from src.atualidade import checar as checar_atualidade          # noqa: E402
from src.confirmacao import _mesmo_assunto                      # noqa: E402
from src.util import now_utc                                    # noqa: E402
from src.verificador import _conferir, checar_proibidas         # noqa: E402


class Art:
    """Materia de mentira, so com o que o verificador olha."""

    def __init__(self, title, summary=""):
        self.title, self.summary = title, summary


# As materias reais de 17/09/2026 que serviram de universo nos testes abaixo.
MATERIAS = [
    Art("SEC opens door to tokenized U.S. stock trading. Here's who could benefit"),
    Art("US securities regulator rolls out five-year exemption for tokenized stocks"),
    Art("Nos EUA, SEC cria isencao de cinco anos para negociacao de acoes tokenizadas"),
    Art("US sanctions Iranian crypto exchange BitBank over alleged bitcoin transfers to IRGC",
        "Treasury said the previously sanctioned Hormuz Safe platform used BitBank to transfer payments."),
    Art("Governo da Polonia perdeu US$ 230 milhoes em criptomoedas em operacao de petroleo, diz FT"),
    Art("Clarity Act failure may hamper U.S. crypto as industry seeks legal clarity"),
]

# (nome, texto, tem_que_passar)
CASOS = [
    # ---------------------------------------------------------------- devem PASSAR
    ("fato real, sem fonte no texto",
     "A SEC liberou negociacao de acoes tokenizadas nos EUA.", True),
    ("fato real com reacao curta",
     "A SEC liberou negociacao de acoes tokenizadas nos EUA.\n\nSem esperar o Congresso.", True),
    ("numero que esta na materia",
     "O governo da Polonia perdeu US$ 230 milhoes em cripto comprando petroleo.", True),
    ("materia em ingles, post em portugues",
     "Os EUA sancionaram a exchange iraniana BitBank.", True),

    # ---------------------------------------------------------------- devem BLOQUEAR
    ("fato inteiramente inventado",
     "O Banco Central do Japao proibiu todas as stablecoins hoje.", False),
    ("numero inventado colado em fato verdadeiro",
     "Os EUA sancionaram a BitBank e congelaram US$ 4,7 bilhoes.", False),
    ("entidade inventada colada em fato verdadeiro",
     "A SEC liberou acoes tokenizadas e a Nasdaq confirmou adesao imediata.", False),
    ("pais que nao esta em materia nenhuma",
     "Os EUA sancionaram a exchange BitBank a pedido da Coreia do Norte.", False),
    ("fato real em um paragrafo, mentira no outro",
     "A SEC liberou negociacao de acoes tokenizadas nos EUA.\n\n"
     "O Banco Central do Japao proibiu todas as stablecoins hoje.", False),
]

# Previsao de preco e recomendacao: `checar_proibidas`, que nao depende de materia.
PROIBIDAS = [
    ("previsao com palavras separadas", "Isso deve fazer o bitcoin subir forte."),
    ("previsao colada", "O bitcoin deve subir depois disso."),
    ("previsao com verbo no futuro", "O ether vai disparar com essa noticia."),
    ("projecao", "O banco projeta que o bitcoin pode bater novos patamares."),
]

# A MESMA noticia de 17/09 em 5 veiculos: a confirmacao TEM que juntar.
MESMO_FATO = [
    ("CoinDesk", "SEC opens door to tokenized U.S. stock trading. Here's who could benefit"),
    ("Reuters", "US securities regulator rolls out five-year exemption for tokenized stocks"),
    ("Cointelegraph", "SEC grants temporary exemption for tokenized US stock trading"),
    ("Livecoins", "SEC aprova lei temporaria que autoriza testes com acoes tokenizadas em plataformas blockchain"),
    ("Money Times", "Nos EUA, SEC cria isencao de cinco anos para negociacao de acoes tokenizadas"),
]
# Noticias DIFERENTES que nao podem ser confundidas entre si.
FATOS_DIFERENTES = [
    ("SEC opens door to tokenized U.S. stock trading",
     "US sanctions Iranian crypto exchange BitBank over alleged bitcoin transfers"),
    ("Governo da Polonia perdeu US$ 230 milhoes em criptomoedas",
     "DAC Awards reconhece jornalistas que se destacaram na cobertura do mercado"),
    ("Bitcoin ETFs register large outflows",
     "Clarity Act failure may hamper U.S. crypto"),
]


class Materia:
    """Materia de mentira com hora, pra trava de atualidade."""

    def __init__(self, title, summary="", horas=1.0):
        self.title, self.summary = title, summary
        self.published = now_utc() - timedelta(hours=horas)


# (nome, materia, tem_que_passar) -- "a noticia e de agora?" (regra dele, 17/09)
ATUALIDADE = [
    ("materia de 1 h, fato de agora",
     Materia("SEC libera negociacao de acoes tokenizadas nos EUA",
             "A decisao foi publicada hoje pela comissao.", horas=1), True),
    ("ano antigo como REFERENCIA ('desde julho de 2023')",
     Materia("Bitcoin coils near $76.5K as US stocks rebound from Fed rate hike",
             "The US Federal Reserve's first interest-rate hike since July 2023.", horas=1), True),
    ("hora adiantada (embargo/fuso) -- 8 de 38 materias reais vem assim",
     Materia("US sanctions Iranian crypto exchange BitBank",
             "Treasury designated the exchange today.", horas=-2), True),
    ("fato velho republicado hoje",
     Materia("Governo da Polonia perdeu US$ 230 milhoes em criptomoedas, diz FT",
             "O caso aconteceu entre o fim de 2023 e marco de 2024 e ja havia sido noticiado.",
             horas=1), False),
    ("retrospectiva",
     Materia("Relembre o maior hack de exchange da historia",
             "Relembre o que aconteceu naquele ano.", horas=1), False),
    ("materia velha demais",
     Materia("SEC libera negociacao de acoes tokenizadas", "", horas=30), False),
    ("feed com hora muito errada",
     Materia("SEC libera negociacao de acoes tokenizadas", "", horas=-48), False),
]


def main() -> int:
    falhas = []

    print("== VERIFICADOR: fato tem que se sustentar em materia real ==")
    for nome, texto, deve_passar in CASOS:
        trechos = [p.strip() for p in texto.split("\n\n") if len(p.strip()) >= 15]
        probs = _conferir(trechos, MATERIAS, "", "sem fonte citada", minimo=2)
        passou = not probs
        ok = passou == deve_passar
        marca = "ok  " if ok else "FALHA"
        esperado = "passar" if deve_passar else "bloquear"
        print(f"  {marca} [{esperado:>8}] {nome}")
        if not ok:
            falhas.append(nome)
            for p in probs:
                print(f"         -> {p}")
        elif probs:
            print(f"         ({probs[0]})")

    print("\n== VERIFICADOR: previsao de preco e recomendacao ==")
    for nome, texto in PROIBIDAS:
        probs = checar_proibidas(texto)
        ok = bool(probs)
        print(f"  {'ok  ' if ok else 'FALHA'} [bloquear] {nome}")
        if not ok:
            falhas.append(nome)

    print("\n== ATUALIDADE: a noticia e de agora, ou e fato velho de hoje? ==")
    for nome, mat, deve_passar in ATUALIDADE:
        r = checar_atualidade(mat, 6)
        ok = r["ok"] == deve_passar
        esperado = "passar" if deve_passar else "bloquear"
        print(f"  {'ok  ' if ok else 'FALHA'} [{esperado:>8}] {nome}")
        if not ok:
            falhas.append(nome)
            print(f"         -> {r['motivo'] or 'passou e nao devia'}")
        elif r["motivo"]:
            print(f"         ({r['motivo']})")

    print("\n== CONFIRMACAO: a mesma noticia em veiculos diferentes ==")
    for i in range(len(MESMO_FATO)):
        for j in range(i + 1, len(MESMO_FATO)):
            (f1, t1), (f2, t2) = MESMO_FATO[i], MESMO_FATO[j]
            ok = _mesmo_assunto(t1, t2)
            print(f"  {'ok  ' if ok else 'FALHA'} [ juntar ] {f1} x {f2}")
            if not ok:
                falhas.append(f"{f1} x {f2}")

    print("\n== CONFIRMACAO: noticias diferentes nao podem ser juntadas ==")
    for t1, t2 in FATOS_DIFERENTES:
        ok = not _mesmo_assunto(t1, t2)
        print(f"  {'ok  ' if ok else 'FALHA'} [separar ] {t1[:42]}... x {t2[:42]}...")
        if not ok:
            falhas.append("juntou noticias diferentes")

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + " | ".join(falhas[:6]))
        return 1
    print("todos os ataques foram barrados e todo post honesto passou")
    return 0


if __name__ == "__main__":
    sys.exit(main())
