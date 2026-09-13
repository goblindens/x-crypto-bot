"""Tira um post do Instagram da lista de 'vistos' do espelho, para ele ser espelhado.

Uso: python scripts/desmarcar.py <permalink do Instagram>

Espera o ciclo do espelho terminar (ultima linha do log = '[bot] fim') antes
de mexer no estado, senao o processo em andamento salva por cima e a
desmarcacao se perde. O proximo ciclo (ate 2 min) publica o post.
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.util import url_hash  # noqa: E402

STATE = os.path.join(ROOT, "state", "state.json")
LOG = os.path.join(ROOT, "logs", "espelho.log")

permalink = sys.argv[1]
chave = url_hash(permalink)

last = ""
for _ in range(90):
    try:
        linhas = [l for l in open(LOG, encoding="utf-8", errors="ignore").read().splitlines() if l.strip()]
        last = linhas[-1] if linhas else ""
    except OSError:
        last = ""
    if "[bot] fim" in last:
        break
    time.sleep(2)

with open(STATE, encoding="utf-8") as fh:
    d = json.load(fh)
removido = d.get("seen", {}).pop(chave, None) is not None
with open(STATE, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
print(f"removido do visto: {removido} | chave {chave} | ultima linha do log: {last[:40]!r}")
