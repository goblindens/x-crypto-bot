"""Metricas dos proprios posts no X (leitura propria: $0,001 por post).

Uso: python scripts/metricas.py <id> [<id> ...]   -> JSON {id: {...}}
Traz impressoes, likes, respostas, reposts, quotes, bookmarks e -- por serem
posts da propria conta -- cliques no link e no perfil (non_public_metrics).
A Formula chama isto pelo venv do bot, em lote, com cache de horas: nunca em
loop. Regra da casa (12/09/2026): nenhuma leitura paga sem o Sinval pedir --
o dash le no maximo a cada 6 h e no botao "atualizar metricas".
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.main import load_dotenv  # noqa: E402

load_dotenv()
import tweepy  # noqa: E402

ids = [i for i in sys.argv[1:] if i.isdigit()]
if not ids:
    print("{}"); sys.exit(0)

client = tweepy.Client(
    consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
    access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
)
out = {}
for i in range(0, len(ids), 100):
    lote = ids[i:i + 100]
    try:
        r = client.get_tweets(ids=lote, tweet_fields=["created_at", "public_metrics", "non_public_metrics", "text"], user_auth=True)
    except tweepy.HTTPException as exc:
        # non_public_metrics so vale ate 30 dias; se recusar, tenta so as publicas
        r = client.get_tweets(ids=lote, tweet_fields=["created_at", "public_metrics", "text"], user_auth=True)
    for t in (r.data or []):
        pm = t.public_metrics or {}
        npm = getattr(t, "non_public_metrics", None) or {}
        out[str(t.id)] = {
            "criado": str(t.created_at), "texto": t.text,
            "imp": pm.get("impression_count", 0), "like": pm.get("like_count", 0), "resp": pm.get("reply_count", 0),
            "rt": pm.get("retweet_count", 0), "quote": pm.get("quote_count", 0), "book": pm.get("bookmark_count", 0),
            "cliques_link": npm.get("url_link_clicks"), "cliques_perfil": npm.get("user_profile_clicks"),
        }
    for e in (r.errors or []):
        out[str(e.get("value", ""))] = {"erro": e.get("title", "erro")}
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(json.dumps(out, ensure_ascii=False))
