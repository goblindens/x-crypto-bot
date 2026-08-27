"""Renova o token do Threads antes que ele expire.

O token de longa duracao da Meta vale 60 dias. Renovar devolve OUTRO token,
tambem de 60 dias -- ou seja, so serve se o novo valor for guardado em algum
lugar. Este script faz as duas coisas:

  1. chama o endpoint de refresh;
  2. se GH_PAT estiver definido, grava o token novo direto no Secret
     THREADS_ACCESS_TOKEN do repositorio, via API do GitHub.

Sem GH_PAT ele apenas avisa: nesse caso voce renova na mao a cada ~50 dias.

O token nunca e impresso na tela -- os logs do GitHub Actions sao legiveis por
quem tem acesso ao repositorio.
"""
import base64
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.main import load_dotenv  # noqa: E402

load_dotenv()

TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
if not TOKEN:
    print("FALTA THREADS_ACCESS_TOKEN")
    sys.exit(1)

# ------------------------------------------------------------------ refresh
resposta = requests.get(
    "https://graph.threads.net/refresh_access_token",
    params={"grant_type": "th_refresh_token", "access_token": TOKEN},
    timeout=30,
)
dados = resposta.json() if resposta.content else {}

if resposta.status_code >= 400 or "access_token" not in dados:
    erro = dados.get("error", {})
    print(f"FALHOU ao renovar: {erro.get('message', resposta.text[:300])}")
    print("\nCausas comuns:")
    print("  - o token tem menos de 24h (a Meta so renova depois disso)")
    print("  - o token ja expirou (passou de 60 dias) -- gere um novo no portal")
    sys.exit(1)

novo = dados["access_token"]
dias = int(dados.get("expires_in", 0)) // 86400
print(f"Token renovado com sucesso. Nova validade: {dias} dias.")

# ------------------------------------------------- grava no Secret do GitHub
PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()

if not PAT or not REPO:
    print("\nAVISO: GH_PAT nao configurado -- o token novo NAO foi salvo.")
    print("Sem isso o bot para de publicar quando o token atual expirar.")
    print("Configure GH_PAT (veja o README) ou renove manualmente a cada ~50 dias.")
    sys.exit(0)

try:
    from nacl import encoding, public
except ImportError:
    print("\nFALTA o pacote PyNaCl (pip install pynacl) para cifrar o Secret.")
    sys.exit(1)

cabecalho = {
    "Authorization": f"Bearer {PAT}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
base = f"https://api.github.com/repos/{REPO}/actions/secrets"

chave = requests.get(f"{base}/public-key", headers=cabecalho, timeout=30)
if chave.status_code >= 400:
    print(f"FALHOU ao ler a chave publica do repo ({chave.status_code}): {chave.text[:200]}")
    print("O GH_PAT precisa de permissao 'Secrets: Read and write' neste repositorio.")
    sys.exit(1)
chave = chave.json()

# Sealed box: so o GitHub consegue abrir
caixa = public.SealedBox(public.PublicKey(chave["key"].encode(), encoding.Base64Encoder()))
cifrado = base64.b64encode(caixa.encrypt(novo.encode("utf-8"))).decode("utf-8")

gravar = requests.put(
    f"{base}/THREADS_ACCESS_TOKEN",
    headers=cabecalho,
    json={"encrypted_value": cifrado, "key_id": chave["key_id"]},
    timeout=30,
)
if gravar.status_code >= 400:
    print(f"FALHOU ao gravar o Secret ({gravar.status_code}): {gravar.text[:200]}")
    sys.exit(1)

print("Secret THREADS_ACCESS_TOKEN atualizado no repositorio.")
print("O bot vai usar o token novo a partir da proxima execucao.")
