# Bot de notícias de cripto para o X

Publica sozinho, todos os dias, sem servidor e **sem custo nenhum**:

- **Notícias** — lê feeds RSS de veículos brasileiros de cripto/mercado, pontua
  cada matéria por relevância, descarta publicidade e repetição, e posta as
  melhores.
- **Resumo de mercado** — uma vez por dia, preços de BTC/ETH/SOL/XRP,
  dominância do Bitcoin e índice Medo & Ganância.

Roda no GitHub Actions no horário agendado. Seu computador pode estar desligado.

---

## Por que é 100% grátis

| Peça | Plano usado | Custo |
|---|---|---|
| X API | **Free** — 500 posts/mês | R$ 0 |
| GitHub Actions | Grátis ilimitado em repositório público (2.000 min/mês no privado; o bot usa ~200) | R$ 0 |
| Feeds RSS | Públicos | R$ 0 |
| CoinGecko | API pública, sem chave | R$ 0 |
| Medo & Ganância (alternative.me) | API pública, sem chave | R$ 0 |
| Redação dos posts | Template em Python | R$ 0 |

O bot se limita a **8 posts/dia e 400/mês** (`config.yaml`), com folga dentro
dos 500/mês do plano Free do X. Ele conta os posts do mês no `state/state.json`
e simplesmente para quando chega no teto — nunca gera cobrança nem bloqueio.

> Existe um modo opcional em que a **Claude** reescreve cada manchete como post
> (fica bem melhor). Esse modo **é pago** e vem **desligado**. Veja o final deste
> arquivo.

---

## Passo a passo (do zero)

### 1. Crie a conta de desenvolvedor no X

1. Acesse **developer.x.com** → *Sign up for Free Account*.
2. Descreva o uso em inglês (ex.: *"Automated account that posts Brazilian
   crypto and financial news headlines from public RSS feeds."*).
3. Em **Projects & Apps**, abra o seu App → **User authentication settings** →
   *Set up*:
   - **App permissions:** `Read and write`
   - **Type of App:** `Web App, Automated App or Bot`
   - **Callback URI:** `https://example.com` · **Website URL:** qualquer URL sua
   - Salve.
4. Vá em **Keys and tokens** e gere:
   - `API Key` e `API Key Secret`
   - `Access Token` e `Access Token Secret`

> ⚠️ **O erro mais comum:** gerar os Access Tokens **antes** de mudar a permissão
> para *Read and write*. Nesse caso o token continua só-leitura e o post falha
> com `403 Forbidden`. Se isso acontecer, clique em **Regenerate** nos Access
> Tokens depois de salvar a permissão.

### 2. Suba o projeto para o GitHub

Já existe um commit pronto nesta pasta. Crie um repositório vazio no GitHub
(sem README) e rode:

```bash
cd "/Users/sinvalgomes/Claude Code/x-crypto-bot" && git remote add origin https://github.com/SEU-USUARIO/SEU-REPO.git && git branch -M main && git push -u origin main
```

### 3. Cadastre as chaves como Secrets

No repositório: **Settings → Secrets and variables → Actions → New repository
secret**. Crie os quatro:

| Nome | Valor |
|---|---|
| `X_API_KEY` | API Key |
| `X_API_SECRET` | API Key Secret |
| `X_ACCESS_TOKEN` | Access Token |
| `X_ACCESS_TOKEN_SECRET` | Access Token Secret |

Nunca coloque essas chaves em arquivo do repositório.

### 4. Teste sem publicar

Aba **Actions** → workflow **bot-x-cripto** → **Run workflow** →
`mode: news`, `dry_run: true` → **Run**.

Abra o log do passo *Rodar o bot*: ele mostra a nota de cada matéria e o texto
exato que seria publicado. Nada vai para o X.

### 5. Publique de verdade

Mesmo caminho, agora com `dry_run: false`. Confira o post na sua conta.

Feito isso, o agendamento assume sozinho:

| Horário (Brasília) | O que publica |
|---|---|
| 08:05 | Resumo de mercado |
| 09:15, 12:15, 15:15, 18:15 | Até 2 notícias por execução |

Para mudar os horários, edite os `cron` em
[.github/workflows/bot.yml](.github/workflows/bot.yml) — **lembrando que cron é
sempre em UTC**, e Brasília é UTC−3 (09:15 BRT = `15 12 * * *`).

---

## Rodar na sua máquina (opcional)

```bash
cd "/Users/sinvalgomes/Claude Code/x-crypto-bot" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Copie `.env.example` para `.env`, preencha as chaves, e:

```bash
.venv/bin/python -m src.main --mode news --dry-run
```

Outros comandos:

```bash
.venv/bin/python scripts/check_auth.py
```

```bash
.venv/bin/python -m src.main --mode market --dry-run
```

```bash
.venv/bin/python -m src.main --mode news --max 1
```

---

## Ajustando o bot (`config.yaml`)

Tudo que importa está em [config.yaml](config.yaml) — não é preciso mexer no código.

- **`limits`** — quantos posts por execução, por dia e por mês; espaçamento
  mínimo entre posts.
- **`news.feeds`** — as fontes. Sete veículos brasileiros vêm ligados. As fontes
  em inglês (CoinDesk, The Block, Decrypt…) vêm com `enabled: false`, porque no
  modo template o bot **não traduz** — a manchete sairia em inglês.
- **`news.keywords`** — o que aumenta a nota de uma matéria (`alta` = +3,
  `media` = +2, `baixa` = +1).
- **`news.min_score`** — a nota de corte. Postando pouco? Baixe para 3. Postando
  coisa irrelevante? Suba para 6.
- **`news.blocklist`** — manchete que contiver qualquer um desses termos é
  descartada (publieditorial, "melhores corretoras", previsão de preço…).
- **`style.hashtag_pool`** — mapa de hashtag → termos que a acionam.

### Como a nota é calculada

```
peso da fonte  +  palavra-chave (por faixa)  +  recência (+3 se < 2h)
+ manchete curta (+1)  + já em português (+2)  − isca de clique (−2)
```

O log de cada execução mostra a conta inteira, matéria por matéria.

---

## Como ele evita repetição

- `state/state.json` guarda o hash de toda URL já vista (21 dias). A URL é
  normalizada antes — `?utm_source=...` não engana o bot.
- Manchetes com **45% ou mais de palavras em comum** com algo publicado nas
  últimas 72h são puladas: é a mesma notícia em outro veículo.
- No máximo **1 matéria por fonte** em cada execução.

O arquivo é commitado de volta pelo próprio workflow a cada rodada — é assim que
o bot tem memória mesmo rodando numa máquina nova toda vez.

---

## Modo opcional com a Claude (pago)

No modo padrão o post é a manchete original + link. Com a Claude ligada, ela
reescreve a manchete como post, em português, e ainda **veta** matérias
irrelevantes ou publicitárias que passaram pelo filtro.

Isso usa a API da Anthropic, que **é cobrada por uso** (centavos por post, mas
não é zero). Para ligar:

1. Descomente `anthropic>=1.0.0` em `requirements.txt`.
2. Em `config.yaml`, mude `composer.use_claude` para `true`.
3. Crie o secret `ANTHROPIC_API_KEY` no GitHub.

Se a chave faltar ou a chamada falhar por qualquer motivo, o bot volta sozinho
para o template — ele nunca deixa de postar por causa disso.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `403 Forbidden` ao publicar | Token gerado antes de mudar para *Read and write*. Regenere os Access Tokens. |
| `403` com texto duplicado | O X recusa dois posts idênticos. Normal; a próxima execução pega outra matéria. |
| `401 Unauthorized` | Chave copiada errada ou com espaço sobrando no Secret. |
| `429 Too Many Requests` | Cota do X estourada. O bot para sozinho; espere a virada da janela. |
| "nada passou no filtro de relevância" | `min_score` alto demais, ou madrugada sem notícia. Baixe `news.min_score`. |
| O agendamento parou | O GitHub desliga cron de repositório sem atividade por 60 dias. Como o bot commita o `state.json` a cada rodada, isso não deve acontecer — mas se acontecer, é só reativar na aba Actions. |
| Um feed sumiu do log | O site mudou/derrubou o RSS. O bot ignora e segue com os outros; troque a URL no `config.yaml`. |

---

## Estrutura

```
config.yaml               toda a configuração
src/sources.py            RSS + CoinGecko + Medo & Ganância
src/ranker.py             pontuação, filtro e escolha das matérias
src/composer.py           monta o texto do tweet
src/publisher.py          publica no X (e o modo dry-run)
src/state.py              memória: o que já foi postado, cotas
src/main.py               orquestra tudo
scripts/check_auth.py     testa as credenciais sem publicar
.github/workflows/bot.yml agendamento
```
