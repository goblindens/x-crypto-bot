"""Testa o token do Threads sem publicar nada.

    python scripts/check_threads.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import load_dotenv  # noqa: E402
from src.publisher_threads import PublishError, ThreadsPublisher  # noqa: E402

load_dotenv()

pub = ThreadsPublisher()
try:
    me = pub.whoami()
except PublishError as exc:
    print(f"FALHOU: {exc}")
    sys.exit(1)

print(f"OK -- autenticado como @{me.get('username')} (id {me.get('id')})")
print("O bot pode publicar nesse perfil.")
