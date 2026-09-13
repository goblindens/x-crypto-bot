"""Fila de posts agendados para o X.

Arquivo: state/fila.json -- lista de itens:
  {"id": "2026-09-12-comunidade", "quando": "2026-09-12T19:30", "texto": "...",
   "resposta": "texto da 1a resposta (pode ter o link)", "tipo": "comunidade"}

"quando" e horario de Brasilia (BRT, UTC-3). O espelho, que roda a cada 40 s
na VPS, chama run_fila(); tudo que estiver vencido e ainda nao enviado sai.
Depois de enviado o item ganha "enviado" (ISO), "tweet_id" e "resposta_id".

Regra da casa: link so na resposta, nunca no corpo -- e so nos posts de
comunidade/parceria. Se "texto" tiver URL, o item e recusado e marcado
com "erro" para nao gastar $0,20 sem querer.

Excecao controlada (teste A/B de 12/09 a 26/09/2026): dias impares o link vai
na resposta; dias pares vai no corpo, com "link_no_corpo": true no item. O
tipo gravado no estado ("comunidade/resposta" ou "comunidade/corpo") e o que
permite comparar cliques depois (non_public_metrics.url_link_clicks).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

from .publisher import PublishError

BR_TZ = timezone(timedelta(hours=-3))
_URL = re.compile(r"https?://\S+|\b[a-z0-9-]+\.(com|com\.br|net|io|ai|app)\b", re.I)


def _load(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError) as exc:
        print(f"[fila] arquivo ilegivel ({exc}); ignorando")
        return []


def _save(path: str, itens: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(itens, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _quando(item: dict) -> datetime | None:
    try:
        dt = datetime.fromisoformat(item["quando"])
    except (KeyError, ValueError):
        return None
    return dt.replace(tzinfo=BR_TZ) if dt.tzinfo is None else dt


def run_fila(path: str, state, publisher, force: bool = False) -> int:
    itens = _load(path)
    if not itens:
        return 0
    agora = datetime.now(BR_TZ)
    enviados = 0
    mudou = False
    for item in itens:
        if item.get("enviado") or item.get("erro"):
            continue
        quando = _quando(item)
        if quando is None:
            item["erro"] = "campo 'quando' invalido"; mudou = True
            continue
        if quando > agora and not force:
            continue
        texto = (item.get("texto") or "").strip()
        if not texto:
            item["erro"] = "texto vazio"; mudou = True
            continue
        # Teste A/B (decisao dele, 12/09/2026): link na resposta vs link no
        # corpo, alternando por dia, medido em cliques e entradas no grupo.
        # So passa URL no corpo quando o item declara "link_no_corpo": true.
        if _URL.search(texto) and not item.get("link_no_corpo"):
            item["erro"] = "URL no corpo do post sem 'link_no_corpo': true (regra: link so na resposta)"; mudou = True
            print(f"[fila] recusado {item.get('id')}: {item['erro']}")
            continue
        print(f"[fila] enviando {item.get('id')} (agendado {quando:%d/%m %H:%M}, agora {agora:%H:%M})")
        try:
            tweet_id = publisher.post(texto)
            item["tweet_id"] = tweet_id
            resposta = (item.get("resposta") or "").strip()
            if resposta and tweet_id and tweet_id != "dry-run":
                item["resposta_id"] = publisher.post_reply(resposta, tweet_id)
            elif resposta:
                print(f"[fila] (dry-run) resposta: {resposta}")
        except PublishError as exc:
            item["erro"] = str(exc); mudou = True
            publisher.last_error = str(exc)
            print(f"[erro] {exc}")
            break
        item["enviado"] = datetime.now(timezone.utc).isoformat()
        mudou = True
        enviados += 1
        if not publisher.dry_run:
            variante = "corpo" if item.get("link_no_corpo") else ("resposta" if item.get("resposta") else "sem-link")
            state.record_post(f"{item.get('tipo', 'fila')}/{variante}", texto, title=item.get("id", ""), tweet_id=item.get("tweet_id", ""))
    if mudou and not publisher.dry_run:
        _save(path, itens)
    return enviados
