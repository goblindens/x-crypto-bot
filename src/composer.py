"""Transforma dado bruto em texto de tweet.

Dois caminhos:
  1. Template (padrao) -- puro Python, custo zero, sem chave de API.
  2. Claude (opcional) -- so entra se `composer.use_claude: true` no config E
     a variavel ANTHROPIC_API_KEY existir. Se qualquer coisa falhar, cai
     automaticamente no template. O bot nunca fica sem postar por causa disso.
"""
from __future__ import annotations

import os
import re
from datetime import timezone, timedelta

from .util import (fits, fold, fmt_pct, fmt_price, has_term, limit, now_utc,
                   truncate_to_fit, tweet_length)

BR_TZ = timezone(timedelta(hours=-3))

TOPIC_EMOJI = [
    (("hackeado", "hacker", "invasao", "roubo", "exploit", "golpe", "fraude"), "\U0001F6A8"),  # sirene
    (("etf", "blackrock", "aprova"), "\U0001F4C8"),                     # grafico subindo
    (("sec", "regulament", "lei", "processo", "justica", "cvm"), "\u2696\ufe0f"),  # balanca
    (("fed", "juros", "selic", "inflacao", "cpi", "banco central"), "\U0001F3E6"),     # banco
    (("bitcoin", "btc"), "\u20bf"),                                 # simbolo bitcoin
]


def pick_emoji(text: str) -> str:
    folded = fold(text)
    for needles, emoji in TOPIC_EMOJI:
        if any(has_term(folded, needle) for needle in needles):
            return emoji
    return "\U0001F4F0"  # jornal


def pick_hashtags(text: str, config: dict) -> str:
    """Escolhe hashtags a partir do TEXTO DO POST, nunca do resumo inteiro --
    senao qualquer mencao perdida vira hashtag fora de contexto."""
    style = config.get("style", {})
    pool = style.get("hashtag_pool", {}) or {}
    limit = int(style.get("hashtags_max", 2))
    default = style.get("hashtag_default", "#Cripto")
    folded = fold(text)

    chosen = []
    for tag, terms in pool.items():
        if any(has_term(folded, term) for term in terms):
            chosen.append(tag)
        if len(chosen) >= limit:
            break
    if default and default not in chosen and len(chosen) < limit:
        chosen.append(default)
    return " ".join(chosen[:limit])


# ------------------------------------------------------------------ noticia
def compose_news(article, config: dict) -> str:
    text = None
    if _claude_enabled(config):
        text = _compose_news_with_claude(article, config)
    if text == "SKIP":
        return text
    if not text:
        if article.lang != "pt":
            # sem a Claude nao ha traducao; manchete em ingles nao sai (regra: conteudo em PT)
            print(f"[composer] sem traducao disponivel para '{article.title[:50]}' -- pulando")
            return "SKIP"
        text = _news_template(article, config)
    # Fluxo parceiro (13/09/2026): OKX/Kraken/Ledger ganham a chamada pra comunidade.
    if getattr(article, "parceiro", False):
        chamada = (config.get("parceiros") or {}).get("chamada", "").strip()
        if chamada:
            candidato = text + "\n\n" + chamada
            if fits(candidato):
                text = candidato
    return text


def _first_sentence(summary: str, title: str) -> str:
    """Primeira frase do resumo, se acrescentar alguma coisa ao titulo.

    Muitos feeds repetem o titulo dentro do resumo -- nesse caso nao vale a
    pena ocupar espaco com ele.
    """
    import re
    texto = (summary or "").strip()
    if not texto:
        return ""
    frase = re.split(r"(?<=[.!?])\s+", texto)[0].strip()
    if len(frase) < 40 or len(frase) > 240:
        return ""
    if fold(frase)[:50] == fold(title)[:50]:
        return ""
    if not frase.endswith((".", "!", "?")):
        frase += "."
    return frase


def _news_template(article, config: dict) -> str:
    emoji = pick_emoji(article.title + " " + article.summary)
    hashtags = pick_hashtags(article.title, config)

    # Regra dele (13/09/2026): noticia sai so com o NOME da fonte, nunca com o
    # link. Link, so o da comunidade (e na 1a resposta).
    tail = f"\n\n({article.source})"
    if hashtags:
        tail += f"\n\n{hashtags}"
    reserved = tweet_length(tail)
    head = truncate_to_fit(f"{emoji} {article.title}", reserved=reserved)

    # Sobrou espaco (tipico no Threads, 500 caracteres)? Acrescenta contexto.
    frase = _first_sentence(article.summary, article.title)
    if frase:
        candidato = head + "\n\n" + frase + tail
        if fits(candidato):
            return candidato
    return head + tail


# ------------------------------------------------------------------ mercado
def compose_market(snapshot, config: dict) -> str:
    stamp = now_utc().astimezone(BR_TZ).strftime("%d/%m")
    lines = [f"\U0001F4CA Mercado cripto — {stamp}", ""]
    for coin in snapshot.coins:
        lines.append(f"{coin['symbol']} {fmt_price(coin['price'])} ({fmt_pct(coin['change24h'])})")

    extra = []
    if snapshot.btc_dominance is not None:
        extra.append(f"Dominância BTC: {snapshot.btc_dominance:.1f}".replace(".", ",") + "%")
    if snapshot.fear_greed:
        extra.append(f"Medo & Ganância: {snapshot.fear_greed['value']} ({snapshot.fear_greed['label']})")
    if extra:
        lines.append("")
        lines.extend(extra)

    hashtags = pick_hashtags("bitcoin mercado", config)
    if hashtags:
        lines.append("")
        lines.append(hashtags)

    text = "\n".join(lines)
    # Se estourar, remove moedas do fim ate caber
    while not fits(text) and len(snapshot.coins) > 1:
        snapshot.coins.pop()
        return compose_market(snapshot, config)
    return text


# ------------------------------------------------------- caminho opcional Claude
def _claude_enabled(config: dict) -> bool:
    if not config.get("composer", {}).get("use_claude", False):
        return False
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print("[composer] use_claude ligado mas ANTHROPIC_API_KEY ausente -- usando template")
        return False
    return True


# FORMATO APROVADO POR ELE EM 17/09/2026 -- posicao primeiro, manchete depois.
#
# Mudou porque a manchete seca nao rende: mediana de 479 impressoes contra 4.577
# do meme espelhado do Instagram, e 51 dos 60 ultimos posts sem UMA resposta.
# Pesquisa do nicho diz a mesma coisa: "manchete sem posicao" esta na lista do
# que o algoritmo ignora; o que rende e reacao rapida que nomeia o catalisador,
# toma posicao e convida discordancia.
#
# Ele aprovou este molde:
#     O Congresso travou e a SEC resolveu sozinha.        <- gancho (posicao)
#     Sem o Clarity Act aprovado, o regulador soltou...    <- fato
#     Regra feita por quem fiscaliza, nao por quem legisla.
#     Isso te deixa mais tranquilo ou menos?               <- provocacao
#     (Bloomberg)
_SCHEMA = {
    "type": "object",
    "properties": {
        "gancho": {
            "type": "string",
            "description": (
                "ATE 65 caracteres. A primeira linha, com ANGULO -- nao e a manchete. "
                "Diz o que aconteceu do jeito que um humano comentaria em voz alta. "
                "Ex.: 'O Congresso travou e a SEC resolveu sozinha.'"
            ),
        },
        "fato": {
            "type": "string",
            "description": (
                "ATE 105 caracteres. O que aconteceu, com quem/quanto/onde. E aqui que "
                "mora a informacao verificavel. Sem adjetivo, sem opiniao."
            ),
        },
        "provocacao": {
            "type": "string",
            "description": (
                "ATE 85 caracteres. Uma leitura curta do fato + uma pergunta que DIVIDE "
                "opiniao (nao 'o que voce acha?'). Ex.: 'Regra feita por quem fiscaliza, "
                "nao por quem legisla. Isso te deixa mais tranquilo ou menos?'. "
                "Deixe VAZIO se nao houver leitura concreta -- frase generica nao serve."
            ),
        },
        "publicar": {
            "type": "boolean",
            "description": "false se a materia for irrelevante, publicidade ou nao verificavel.",
        },
    },
    "required": ["gancho", "fato", "provocacao", "publicar"],
    "additionalProperties": False,
}

# Travas da linha de reacao. Se qualquer uma casar, a linha cai e o post sai
# so com manchete + resumo -- o fato nunca e perdido por causa da opiniao.
_PROIBIDO_NA_PRATICA = (
    # previsao de preco, em qualquer forma
    "vai subir", "vai cair", "vai bater", "vai chegar", "deve subir", "deve cair",
    "tende a subir", "tende a cair", "pode chegar a", "projeta", "preve", "previsao",
    "alvo de", "rumo aos", "rumo a us", "ate o fim do ano", "proximo alvo",
    # recomendacao
    "compre", "venda", "comprar agora", "vender agora", "aproveite", "nao perca",
    "oportunidade de compra", "hora de comprar", "hora de vender", "recomend",
    # acusacao sem decisao judicial
    "golpista", "e um golpe", "fraudador", "esta roubando", "criminoso", "picareta",
    # promessa
    "garantido", "lucro certo", "sem risco", "dinheiro facil",
)


def _compose_news_with_claude(article, config: dict):
    """Reescreve a manchete como post. Devolve None em qualquer falha."""
    try:
        import anthropic
    except ImportError:
        print("[composer] pacote anthropic nao instalado -- usando template")
        return None

    style = config.get("style", {})
    model = config.get("anthropic", {}).get("model", "claude-opus-5")
    effort = config.get("anthropic", {}).get("effort", "low")

    system = (
        "Voce escreve posts curtos de noticias de cripto e mercado financeiro para o X, "
        "em portugues do Brasil.\n"
        f"Tom: {style.get('voice', 'direto e informativo')}\n"
        "Regras rigidas:\n"
        "- Devolva TRES campos: 'gancho' (ate 65 caracteres), 'fato' (ate 105) e "
        "'provocacao' (ate 85). Somados, no maximo 250 caracteres.\n"
        "\n"
        "O MOLDE (aprovado por ele em 17/09/2026):\n"
        "  gancho     -> a primeira linha, com ANGULO. NAO repita a manchete: diga o que\n"
        "                aconteceu do jeito que uma pessoa comentaria em voz alta.\n"
        "                Bom:  'O Congresso travou e a SEC resolveu sozinha.'\n"
        "                Ruim: 'SEC publica orientacao sobre tokenizacao de acoes.'\n"
        "  fato       -> quem, quanto, onde. E aqui que mora a informacao verificavel.\n"
        "                Sem adjetivo seu.\n"
        "  provocacao -> uma leitura curta + uma pergunta que DIVIDE opiniao.\n"
        "                Bom:  'Regra feita por quem fiscaliza, nao por quem legisla. "
        "Isso te deixa mais tranquilo ou menos?'\n"
        "                Ruim: 'O que voce acha?' / 'Vale acompanhar.'\n"
        "\n"
        "- A posicao do gancho e da provocacao e sobre CONDUTA (de orgao, empresa, banco, "
        "projeto, governo) ou sobre o que MUDA de concreto. NUNCA sobre preco futuro.\n"
        "- Pode julgar conduta. Exemplo bom: 'Banco grande dizendo que uma moeda sobe 70x "
        "nao e analise, e folheto.'\n"
        "- PROIBIDO dizer para onde o preco vai, em qualquer forma ('vai subir', 'deve cair', "
        "'projeta', 'alvo de'). PROIBIDO recomendar compra ou venda. PROIBIDO chamar alguem de "
        "golpista ou criminoso sem decisao judicial. PROIBIDO prometer resultado.\n"
        "- PROIBIDO frase generica de encher linguica ('vale acompanhar', 'fique de olho', "
        "'o mercado reage', 'momento importante'). Sem leitura concreta, provocacao VAZIA.\n"
        "- Se um pais for central, comece com a bandeira dele (emoji), ex.: '🇺🇸 Senado vota...'.\n"
        "- Nao traduza nomes proprios; converta valores em ingles pra formato BR (US$ 463 mi, 85%).\n"
        "- NUNCA repita o preco atual de BTC/ETH/SOL que estiver na manchete (ele muda a cada minuto e "
        "o sistema confere ao vivo): diga 'sobe', 'cai', 'passa dos', sem o numero. Valores de fluxo, "
        "compra, liquidacao e ETF podem (e devem) aparecer.\n"
        "- Nao invente numeros, nomes ou fatos que nao estejam no material fornecido.\n"
        "- Nao use hashtags nem links (sao adicionados depois pelo sistema).\n"
        "- Nao de recomendacao de investimento.\n"
        "- Se o material for propaganda, especulacao de preco ou irrelevante, "
        "responda publicar=false."
    )
    user = (
        f"Fonte: {article.source}\n"
        f"Manchete: {article.title}\n"
        f"Resumo: {article.summary[:500]}"
    )
    params = {
        "model": model,
        "max_tokens": 2000,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"format": {"type": "json_schema", "schema": _SCHEMA}, "effort": effort},
    }

    client = anthropic.Anthropic()
    try:
        try:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
            )
        except TypeError:
            response = client.messages.create(**params)
        if getattr(response, "stop_reason", None) == "refusal":
            print("[composer] modelo recusou a materia -- usando template")
            return None
        import json
        raw = next(block.text for block in response.content if block.type == "text")
        data = json.loads(raw)
    except Exception as exc:  # rede, cota, schema -- nada disso pode derrubar o bot
        print(f"[composer] Claude indisponivel ({type(exc).__name__}: {exc}) -- usando template")
        return None

    if not data.get("publicar"):
        print(f"[composer] Claude marcou como nao publicavel: {article.title[:60]}")
        return "SKIP"

    gancho = (data.get("gancho") or "").strip()
    fato = (data.get("fato") or "").strip()
    provocacao = (data.get("provocacao") or "").strip()
    if not fato:
        return None

    # A opiniao (gancho e provocacao) passa pelas peneiras; o FATO nunca cai --
    # e ele que sustenta o post. Se a opiniao for reprovada, sai so o fato.
    gancho = _peneirar_reacao(gancho, article)
    provocacao = _peneirar_reacao(provocacao, article)

    hashtags = pick_hashtags(" ".join([gancho, fato]) or article.title, config)
    tail = f"\n\n({article.source})"   # so o nome da fonte, sem link (regra dele)
    if hashtags:
        tail += f"\n\n{hashtags}"

    # Ordem de sacrificio quando falta espaco: provocacao, depois gancho.
    # O FATO nunca e cortado.
    for _ in range(3):
        body = "\n\n".join(p for p in (gancho, fato, provocacao) if p)
        if tweet_length(body + tail) <= limit():
            return body + tail
        if provocacao:
            provocacao = ""
        elif gancho:
            gancho = ""
        else:
            break
    return None


def _peneirar_reacao(linha: str, article) -> str:
    """Devolve a linha de reacao, ou '' se ela nao passar nas travas dele.

    Duas peneiras locais, de graca:
      1. palavra proibida  -> previsao de preco, recomendacao, acusacao, promessa
      2. numero que nao esta na materia
    Depois disso o post inteiro ainda passa pelo `verificador.py` (que ja existia
    desde 14/09): cada paragrafo tem que se sustentar numa materia real das
    ultimas 24h. A reacao nao tem passe livre -- ela e conferida como o resto.

    Regra de 17/09/2026: "nao podemos correr risco de falar merda". Opiniao
    errada no ar vira print -- entao na duvida a linha cai e o post sai so com
    o fato, que e sempre defensavel.
    """
    if not linha:
        return ""
    plano = fold(linha)
    proibido = next((p for p in _PROIBIDO_NA_PRATICA if p in plano), None)
    if proibido:
        print(f"[composer] reacao barrada ('{proibido}'): {article.title[:50]}")
        return ""
    # numero que nao veio da materia nao entra na opiniao: o verificador so
    # confere o corpo do fato, e um numero inventado aqui passaria batido.
    numeros_fonte = set(re.findall(r"\d[\d.,]*", f"{article.title} {article.summary}"))
    for n in re.findall(r"\d[\d.,]*", linha):
        if n not in numeros_fonte and len(n) > 1:
            print(f"[composer] reacao barrada (numero {n} fora da materia): {article.title[:50]}")
            return ""
    return linha
