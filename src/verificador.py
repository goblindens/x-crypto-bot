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
             "patrocinado pela okx", "a okx patrocina",
             # Previsao de preco tambem entra pelo verbo, inclusive vinda de fonte seria
             # ("Estrategista projeta queda de 10% no S&P 500" escapou em 14/09/2026).
             # Regra dele, 13/09: "nao vamos mexer com previsao de preco, nao me venha com essa".
             "projeta", "projetam", "projecao", "projeção", "preve ", "prevê ", "preveem", "preveem",
             "estima que", "aposta em alta", "aposta em queda", "deve subir", "deve cair",
             "pode subir", "pode cair", "pode disparar", "pode despencar", "pode chegar a",
             "espera alta", "espera queda", "ve espaco para", "vê espaço para",
             "price target", "forecast", "predicts", "prediction"]

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


_ALIAS = {"BTC": r"(?:BTC|Bitcoin)", "ETH": r"(?:ETH|Ether|Ethereum)", "SOL": r"(?:SOL|Solana)"}


def checar_numeros(texto: str) -> list:
    problemas = []
    vivo = precos_ao_vivo()
    for sym0 in _MOEDAS:
        sym = _ALIAS[sym0]                      # "Bitcoin sobe para US$ 78 mil" tambem e preco do BTC (14/09)
        for m in re.finditer(rf"\b{sym}\b([^\d$\n]{{0,25}})((?:US\$|R\$|\$)?\s?\d[\d.,]*\s?(?:mil|k)?)(\s?(?:mi|bi|milh|bilh|%))?", texto, re.I):
            gap, bruto, sufixo = m.group(1), m.group(2).strip(), (m.group(3) or "")
            if sufixo:
                continue
            if re.search(r"etf|ganh|perd|fluxo|sa[ií]da|entrada|volume|domin|mi\b|compr|vend|hold|tesour|reserva", fold(gap)):
                continue
            if re.search(r"\d\s?%", bruto):
                continue
            try:
                val, unidade = _numero(bruto)
            except ValueError:
                continue
            if sym0 not in vivo:
                problemas.append(f"{sym0}: nao consegui conferir o preco ao vivo (fontes fora)"); continue
            p = vivo[sym0]["preco"]
            if val < p * 0.2:                   # "469 BTC comprados" nao e preco
                continue
            if unidade > p * 0.002:
                problemas.append(f"{sym0} '{bruto}': arredondado demais (ao vivo {p:,.0f}); escreva com precisao de {p*0.002:,.0f} ou melhor")
                continue
            if abs(val - p) > max(unidade, p * 0.004):
                problemas.append(f"{sym0} '{bruto}' nao bate com o preco ao vivo {p:,.2f} ({vivo[sym0]['fontes']} fontes)")
        for m in re.finditer(rf"\b{sym}\b[^\n(%]{{0,30}}\(([+\-−]?\s?\d+[.,]?\d*)\s?%", texto, re.I):
            try:
                v = float(m.group(1).replace("−", "-").replace(",", ".").replace(" ", ""))
            except ValueError:
                continue
            if sym0 in vivo and abs(v - vivo[sym0]["var"]) > 0.3:
                problemas.append(f"{sym0} variacao '{m.group(1)}%' nao bate com 24h ao vivo {vivo[sym0]['var']:+.2f}%")
    m = re.search(r"(medo\s*&\s*gan[aâ]ncia|m&g)([^\n.!?]{0,80})", texto, re.I)
    if m:
        nums = [int(x) for x in re.findall(r"\b(\d{1,3})\b", m.group(2))]
        val, rot = fng_ao_vivo()
        if val is None:
            problemas.append("Medo & Ganancia: nao consegui conferir ao vivo")
        elif nums and val not in nums:
            # a frase pode citar valores passados ("caiu de 74 pra 57"): o valor ao vivo tem que estar nela
            problemas.append(f"Medo & Ganancia: a frase cita {nums} mas o indice ao vivo e {val} ({rot})")
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


def checar_fontes(texto: str, config: dict, artigo=None) -> list:
    """`artigo` e a materia que ORIGINOU o post, quando o chamador a tem.

    Sem ela, a unica referencia era o RSS da fonte no momento da conferencia --
    e o feed rotaciona: materia de 3 h atras ja saiu do RSS, entao um post
    honesto era bloqueado por falta de lastro (visto em 17/09/2026: Bloomberg e
    CoinDesk barrados com noticia verdadeira). A materia de origem entra na
    comparacao com prioridade.
    """
    problemas = []
    recentes = _artigos_recentes(config)
    conhecidas = {k: v for k, v in recentes.items()}
    origem = fold(f"{artigo.title} {artigo.summary}") if artigo is not None else ""
    # citacao "via Fonte" ou "(Fonte)" no fim do trecho -- so conta se parecer nome de fonte conhecida
    # "via" so e citacao quando o nome seguinte E uma fonte conhecida. Sem isso
    # a preposicao comum virava fonte: "negociacao via blockchain" bloqueava o
    # post inteiro com "fonte 'blockchain' nao validada" (17/09/2026).
    cit = [m for m in re.finditer(r"\(?\bvia\s+([A-Za-zÀ-ÿ0-9][^()\n]*?)\)?(?=\n|$|\))", texto)
           if any(k in fold(m.group(1)) or fold(m.group(1)) in k for k in conhecidas)]
    for m in re.finditer(r"\(([A-Za-zÀ-ÿ][^()\n]{2,60})\)", texto):
        nome = fold(m.group(1))
        if any(k in nome or nome in k for k in conhecidas) and not any(c.start() == m.start() for c in cit):
            cit.append(m)
    cit.sort(key=lambda c: c.start())
    if not cit:
        return problemas
    for m in cit:
        nomes = [n.strip() for n in re.split(r",| e ", m.group(1)) if n.strip()]
        antes = texto[:m.start()]
        paragrafo = re.split(r"\n\s*\n", antes.strip())[-1] if antes.strip() else ""
        # "(via A e B)" no comeco de uma linha (sozinho) = fonte do post inteiro
        sozinho = antes.endswith("\n") or antes.endswith("\n(") or not paragrafo.strip() or len(paragrafo.strip()) < 15

        # PARAGRAFO POR PARAGRAFO, nunca o post em bloco (buraco achado em
        # 17/09/2026): conferindo tudo junto, uma frase inventada colada numa
        # manchete verdadeira PASSAVA, porque as ancoras da parte verdadeira
        # bastavam pro post inteiro. Sozinha, a mesma frase era bloqueada.
        if sozinho:
            trechos = [p.strip() for p in re.split(r"\n\s*\n", antes.strip()) if len(p.strip()) >= 15]
        else:
            trechos = [paragrafo]

        for nome in nomes:
            chave = fold(nome)
            fonte = next((k for k in conhecidas if k in chave or chave in k), None)
            if not fonte:
                problemas.append(f"fonte '{nome}' nao esta na lista de fontes validadas"); continue
            arts = conhecidas[fonte]
            if not arts:
                problemas.append(f"'{nome}': nada publicado nas ultimas 24h pra confirmar"); continue
            # DUAS REGRAS DIFERENTES, porque o post tem duas naturezas
            # (formato aprovado por ele em 17/09/2026: gancho · fato · provocacao).
            #
            # 1. NENHUM trecho pode INVENTAR entidade -- nome, orgao, pais,
            #    empresa ou numero que nao esta na materia. Vale pro post todo.
            # 2. Pelo menos UM trecho tem que estar ancorado numa materia real.
            #    Cobrar ancora de todo paragrafo cortava 6 de 6 opinioes boas:
            #    opiniao e leitura do fato, usa outras palavras, nunca bate
            #    ancora. Mas se NENHUM trecho bate, o post inteiro esta solto.
            algum_ancorado = False
            melhor_geral = 0
            for trecho in trechos:
                intruso = _entidade_inventada(trecho, origem, arts)
                if intruso:
                    problemas.append(f"o post cita '{intruso}', que nao esta na materia")
                    continue
                ancoras = _ancoras(trecho)
                if not ancoras:
                    continue
                melhor = 0
                if origem:
                    melhor = sum(1 for anc in ancoras
                                 if anc in origem or any(en in origem for en in _EN.get(anc, ())))
                for a in arts:
                    alvo = fold(a.title + " " + a.summary)
                    # fonte em ingles: cada ancora vale tambem pela traducao (radical PT -> termos EN)
                    acertos = sum(1 for anc in ancoras if anc in alvo or any(en in alvo for en in _EN.get(anc, ())))
                    if acertos > melhor:
                        melhor = acertos
                melhor_geral = max(melhor_geral, melhor)
                if melhor >= (2 if len(ancoras) >= 4 else 1):
                    algum_ancorado = True
            if trechos and not algum_ancorado:
                problemas.append(f"'{nome}': nada nas ultimas 24h sustenta este post "
                                 f"(melhor casamento: {melhor_geral} âncoras)")
    return problemas


# radical PT (5 letras) -> termos em ingles que valem como a mesma ancora (fontes CoinDesk/Cointelegraph)
_EN = {"acoes": ("stock",), "tecno": ("tech",), "corri": ("race",), "desac": ("slow",), "chefe": ("ceo", "chief", "head"),
       "juros": ("rate", "interest"), "banco": ("bank",), "regul": ("regul",), "camar": ("house",), "senad": ("senate",),
       "corre": ("exchange",), "fundo": ("fund",), "petro": ("oil",), "infla": ("inflat",), "dolar": ("dollar",),
       "ouro": ("gold",), "cripto": ("crypto",), "carte": ("wallet",), "golpe": ("scam", "hack"), "invas": ("hack", "breach"),
       "queda": ("drop", "fall", "selloff", "decline"), "subiu": ("climb", "rise", "gain", "up"), "sobe": ("climb", "rise"),
       "ganha": ("gain",), "perde": ("shed", "lose", "outflow"), "sangr": ("shed", "outflow"), "votac": ("vote",), "votam": ("vote",),
       "decid": ("decision", "decide"), "seman": ("week",), "pedir": ("call",), "pedid": ("call",), "pedir": ("call",), "peder": ("call",),
       "pediu": ("call",), "pediram": ("call",), "segur": ("safety",), "intel": ("ai", "intelligence"), "ether": ("ether",)}

_PARADAS = {"enquanto", "porque", "quando", "sobre", "entre", "depois", "antes", "ainda", "hoje", "ontem", "semana",
            "muito", "pouco", "outro", "outra", "mesmo", "mesma", "nesta", "neste", "ganhou", "ganhar", "chora", "bolha",
            "pesada", "comeco", "apenas", "todos", "todas", "pouco", "coisa", "algo"}


# Palavras que comecam frase ou sao comuns em portugues -- maiuscula nelas nao
# significa nome proprio.
_NAO_E_NOME = {"na", "o", "a", "os", "as", "um", "uma", "abre", "libera", "corretoras",
               "empresas", "investidores", "bolsas", "quem", "isso", "agora", "sem",
               "com", "para", "pode", "podem", "passa", "deixa", "vira", "fica", "cria",
               "muda", "tira", "poe", "poupa", "custa", "vale", "entra", "sai", "e", "de",
               "do", "da", "no", "em", "ao", "pelo", "pela", "mercado", "bolsa", "banco",
               "cripto", "bitcoin", "ethereum", "token", "tokenizadas", "tokenizados",
               # lugares e instituicoes que aparecem traduzidos ou por extenso na
               # materia e nao sao "entidade nova" -- bloquear isso derrubava 5 de
               # 6 posts bons em 17/09/2026 ("Congresso" x "Congress", "EUA" x "US")
               "eua", "brasil", "washington", "wall", "street", "congresso", "senado",
               "camara", "governo", "regulador", "reguladores", "estados", "unidos",
               "bolsas", "exchanges", "traders", "dolar", "real", "reais"}


def _entidade_inventada(trecho: str, origem: str, arts: list) -> str:
    """Nome proprio ou numero citado na opiniao que NAO aparece na materia.

    E a unica trava que a linha de opiniao precisa: ela pode interpretar o fato
    com as palavras que quiser, mas nao pode trazer para dentro do post uma
    empresa, um orgao, um pais ou um numero que a fonte nao publicou.
    """
    corpo = trecho.split(":", 1)[-1]
    alvo = origem + " " + " ".join(fold(a.title + " " + a.summary) for a in arts)

    for n in re.findall(r"\d[\d.,]*", corpo):
        # numero conta se aparecer na materia em QUALQUER formato: "3,6" e "3.6"
        # sao o mesmo numero em PT e EN.
        variantes = {n, n.replace(",", "."), n.replace(".", ","), n.replace(".", "").replace(",", "")}
        if len(n) > 1 and not any(v in alvo for v in variantes if v):
            return n

    # nome proprio = palavra com inicial maiuscula que nao abre a frase.
    # A comparacao usa RADICAL de 5 letras + traducao, igual as ancoras: a materia
    # pode estar em ingles ("Congress") e o post em portugues ("Congresso").
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-ZÀ-Ý][\wÀ-ÿ]{2,})", corpo):
        bruto = m.group(1)
        p = fold(bruto)
        if p in _NAO_E_NOME or len(p) < 4:
            continue
        radical = p[:5]
        if radical in alvo or any(en in alvo for en in _EN.get(radical, ())):
            continue
        return bruto
    return ""


def _ancoras(trecho: str) -> set:
    """Pedacos que tem que aparecer na materia: numeros e radicais (5 letras) de
    palavras longas. Radical casa inflexao ('descolou' ~ 'descola') e boa parte
    do ingles ('bitcoin', 'clarity', 'ether')."""
    t = fold(trecho)
    nums = set(re.findall(r"\d{2,}", t))
    rad = {w[:5] for w in re.findall(r"[a-z]{5,}", t) if w not in _PARADAS}
    return nums | rad


# Previsao de preco montada com palavras separadas: "deve FAZER O BITCOIN subir"
# passava, porque PROIBIDAS so pega frase colada ("deve subir"). Aqui o verbo e o
# movimento podem estar a ate 5 palavras de distancia. (buraco achado em 17/09/2026)
_VERBO_PREVISAO = r"(?:deve|devem|pode|podem|vai|vao|tende a|tendem a|espera-se|projeta|preve)"
_MOVIMENTO = r"(?:subir|cair|disparar|despencar|desabar|decolar|explodir|derreter|valorizar|desvalorizar|bater|chegar|atingir|alcancar)"
_PREVISAO_RE = re.compile(rf"\b{_VERBO_PREVISAO}\b(?:\W+\w+){{0,5}}\W+\b{_MOVIMENTO}\b")


def checar_proibidas(texto: str) -> list:
    t = fold(texto)
    problemas = [f"palavra proibida: '{p}'" for p in PROIBIDAS if fold(p) in t]
    m = _PREVISAO_RE.search(t)
    if m and not problemas:
        problemas.append(f"previsao de preco: '{m.group(0)}'")
    return problemas


# -------------------------------------------------------------------- tudo
def verificar(texto: str, config: dict | None = None, artigo=None) -> dict:
    problemas = (checar_proibidas(texto) + checar_numeros(texto)
                 + checar_fontes(texto, config or {}, artigo))
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
