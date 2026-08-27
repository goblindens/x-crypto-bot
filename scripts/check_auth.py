"""Testa as credenciais do X sem publicar nada.

    python scripts/check_auth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import load_dotenv  # noqa: E402
from src.publisher import REQUIRED_ENV  # noqa: E402

load_dotenv()

missing = [name for name in REQUIRED_ENV if not os.environ.get(name, "").strip()]
if missing:
    print("FALTANDO: " + ", ".join(missing))
    sys.exit(1)

import tweepy  # noqa: E402

client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"],
    consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"],
    access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)

try:
    me = client.get_me()
except tweepy.TweepyException as exc:
    print(f"FALHOU: {exc}")
    print("\nCheque se o App tem permissao 'Read and write' e se voce gerou os")
    print("Access Token DEPOIS de mudar a permissao (senao ele continua read-only).")
    sys.exit(1)

print(f"OK -- autenticado como @{me.data.username} ({me.data.name})")
print("O bot pode publicar nessa conta.")
