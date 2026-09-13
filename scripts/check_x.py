"""Confere as chaves do X do .env: imprime so o @ da conta. Custa $0,01 (1 leitura de usuario)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.main import load_dotenv  # noqa: E402

load_dotenv()
import tweepy  # noqa: E402

client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)
me = client.get_me().data
print(f"X OK: @{me.username} | tweepy {tweepy.__version__} | python {sys.version.split()[0]}")
