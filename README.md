# Bot de notícias de cripto

Publica sozinho, todos os dias, sem servidor e **sem custo nenhum**:

- **Notícias** — lê feeds RSS de veículos brasileiros de cripto/mercado, pontua
  cada matéria por relevância, descarta publicidade e repetição, e posta as
  melhores com link para a fonte.
- **Resumo de mercado** — uma vez por dia: preços de BTC/ETH/SOL/XRP,
  dominância do Bitcoin e índice Medo & Ganância.

Roda no GitHub Actions no horário agendado. Seu computador pode estar desligado.

**Publica no Threads** (padrão). O X também é suportado, mas desde fevereiro de
2026 ele cobra por post — veja [X (opcional, pago)](#x-opcional-pago).

---

## Por que é grátis

| Peça | Plano | Custo |
|---|---|---|
| Threads API | Gratuita, sem tier pago — 250 posts/dia por perfil | R$ 0 |
| GitHub Actions | Grátis ilimitado em repositório público (2.000 min/mês no privado; o bot usa ~200) | R$ 0 |
| Feeds RSS | Públicos | R$ 0 |
| CoinGecko | API pública, sem chave | R$ 0 |
| Medo & Ganância (alternative.me) | API pública, sem chave | R$ 0 |
| Redação dos posts | Template em Python | R$ 0 |

O bot se limita a 8 posts/dia (`config.yaml`), bem abaixo dos 250/dia que a Meta
permite. Não há cartão, crédito nem cobrança em nenhuma etapa.

---

## Passo a passo (do zero)

### 1. Conta no Threads

Você precisa de um perfil no Threads — ele vem junto com uma conta do Instagram.
Se ainda não tiver, crie em threads.net.

### 2. Criar o app na Meta

1. Acesse **developers.facebook.com** → **My Apps** → **Create App**.
2. Em *Use case*, escolha **Access the Threads API**.
3. Dê um nome ao app (ex.: `bot-cripto`) e crie.
4. No painel do app, abra o caso de uso **Threads** → **Customize**.
5. Em **Permissions**, clique em **Add** nestas duas:
   - `threads_basic`
   - `threads_content_publish`

   Espere as duas mostrarem **Ready for testing**.

### 3. Gerar o token

Ainda no caso de uso Threads, aba **Settings** → painel **User Token Generator**
→ **Generate Access Token** no seu usuário → autorize.

Copie o token gerado. É um texto longo (centenas de caracteres) — é a **única**
credencial que o bot precisa.

> O token vale 60 dias. O bot renova sozinho toda segunda-feira (veja
> [Renovação do token](#renovação-do-token)).

### 4. Testar na sua máquina

```bash
cd "/Users/sinvalgomes/Claude Code/x-crypto-bot" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Copie `.env.example` para `.env`, cole o token em `THREADS_ACCESS_TOKEN=` e rode:

```bash
.venv/bin/python scripts/check_threads.py
```

Isso confirma a autenticação **sem publicar nada**. Depois, veja o que ele
publicaria:

```bash
.venv/bin/python -m src.main --mode news --dry-run
```

E, quando estiver satisfeito, publique de verdade:

```bash
.venv/bin/python -m src.main --mode news --max 1
```

### 5. Subir para o GitHub

Crie um repositório vazio no GitHub (sem README) e rode:

```bash
cd "/Users/sinvalgomes/Claude Code/x-crypto-bot" && git remote add origin https://github.com/SEU-USUARIO/SEU-REPO.git && git push -u origin main
```

Em **Settings → Secrets and variables → Actions → New repository secret**, crie:

| Nome | Valor |
|---|---|
| `THREADS_ACCESS_TOKEN` | o token do passo 3 |

O `.env` está no `.gitignore` — suas credenciais nunca vão para o repositório.

### 6. Ligar o agendamento

Aba **Actions** → workflow **bot-cripto** → **Run workflow** → `mode: news`,
`dry_run: true` para conferir. Depois rode com `dry_run: false` para valer.

A partir daí o cron assume:

| Horário (Brasília) | O que acontece |
|---|---|
| 08:05 | Resumo de mercado |
| 09:15, 12:15, 15:15, 18:15 | Até 2 notícias por execução |
| Segunda, 03:30 | Renovação do token |

Para mudar os horários, edite os `cron` em
[.github/workflows/bot.yml](.github/workflows/bot.yml) — lembrando que cron é
**sempre em UTC** e Brasília é UTC−3 (09:15 BRT = `15 12 * * *`).

---

## Renovação do token

O token do Threads vale 60 dias. Renovar gera um token **novo**, então não basta
chamar o endpoint: o valor precisa ser guardado de volta no Secret.

**Automático (recomendado).** Crie um Personal Access Token do GitHub com
permissão de escrita em Secrets:

1. github.com → **Settings** (da sua conta) → **Developer settings** →
   **Personal access tokens** → **Fine-grained tokens** → **Generate new token**
2. Em *Repository access*, escolha o repositório do bot
3. Em *Permissions → Repository permissions*, marque **Secrets: Read and write**
4. Gere, copie, e cadastre no repositório como o secret **`GH_PAT`**

Feito isso, toda segunda o bot renova o token e grava o novo sozinho. Você não
precisa fazer mais nada, para sempre.

**Manual.** Sem o `GH_PAT`, o job de renovação apenas avisa. Nesse caso você
gera um token novo no portal da Meta e atualiza o secret a cada ~50 dias. Se
passar de 60 dias sem uso, o token morre de vez e não dá para renovar.

---

## Ajustando o bot (`config.yaml`)

Tudo que importa está em [config.yaml](config.yaml) — não é preciso mexer no código.

- **`platform`** — `threads` (grátis) ou `x` (pago).
- **`limits`** — posts por execução, por dia e por mês; espaçamento mínimo.
- **`news.feeds`** — as fontes. Sete veículos brasileiros vêm ligados. As fontes
  em inglês vêm com `enabled: false`, porque o bot não traduz — a manchete
  sairia em inglês.
- **`news.keywords`** — o que aumenta a nota (`alta` = +3, `media` = +2, `baixa` = +1).
- **`news.min_score`** — nota de corte. Postando pouco? Baixe para 3. Postando
  irrelevância? Suba para 6.
- **`news.blocklist`** — manchete com esses termos é descartada.
- **`style.hashtag_pool`** — mapa de hashtag → termos que a acionam.

### Como a nota é calculada

```
peso da fonte  +  palavra-chave (por faixa)  +  recência (+3 se < 2h)
+ manchete curta (+1)  + já em português (+2)  − isca de clique (−2)
```

O log de cada execução mostra a conta inteira, matéria por matéria.

---

## Como ele evita repetição

- `state/state.json` guarda o hash de toda URL já vista (21 dias), com a URL
  normalizada — `?utm_source=...` não engana o bot.
- Manchetes com **45% ou mais de palavras em comum** com algo publicado nas
  últimas 72h são puladas: é a mesma notícia em outro veículo.
- No máximo **1 matéria por fonte** em cada execução.

O arquivo é commitado de volta pelo próprio workflow — é assim que o bot tem
memória mesmo rodando numa máquina nova toda vez.

---

## X (opcional, pago)

Em 6 de fevereiro de 2026 a X encerrou o plano gratuito. Publicar por API passou
a custar **$0,015 por post**, ou **$0,20 se o post tiver link**. Não existe cota
grátis.

O bot continua suportando o X: mude `platform` para `x` no `config.yaml`,
cadastre os secrets `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN` e
`X_ACCESS_TOKEN_SECRET`, e carregue créditos no portal da X.

Para gastar 13x menos, tire o link do post — edite `_news_template` em
[src/composer.py](src/composer.py) e remova `article.url` do rodapé.

---

## Problemas comuns

| Sintoma | Causa e solução |
|---|---|
| `codigo 190` ou `102` | Token expirado ou revogado. Gere um novo no User Token Generator. |
| Erro citando `permission` | Falta `threads_content_publish` no app, ou o token foi gerado antes de adicionar a permissão. Adicione e gere o token de novo. |
| `container criado mas nao publicou` | A Meta ainda estava processando. O bot já tenta 3 vezes; se persistir, é instabilidade do lado deles. |
| "nada passou no filtro de relevância" | `min_score` alto demais, ou madrugada sem notícia. Baixe `news.min_score`. |
| O agendamento parou | O GitHub desliga cron de repositório sem atividade por 60 dias. Como o bot commita o `state.json`, não deve acontecer; se acontecer, reative na aba Actions. |
| Um feed sumiu do log | O site mudou ou derrubou o RSS. O bot ignora e segue; troque a URL no `config.yaml`. |
| `402 Payment Required` | Você está com `platform: x` e sem créditos. Volte para `threads`. |

---

## Estrutura

```
config.yaml                    toda a configuração
src/sources.py                 RSS + CoinGecko + Medo & Ganância
src/ranker.py                  pontuação, filtro e escolha das matérias
src/composer.py                monta o texto do post
src/publisher_threads.py       publica no Threads
src/publisher.py               publica no X (opcional)
src/state.py                   memória: o que já foi postado, cotas
src/main.py                    orquestra tudo
scripts/check_threads.py       testa o token sem publicar
scripts/refresh_threads_token.py  renova o token e grava no Secret
.github/workflows/bot.yml      agendamento
```
