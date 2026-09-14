"""Memoria persistente do bot: o que ja foi publicado e quando.

O arquivo state/state.json e versionado no repositorio -- o workflow do GitHub
Actions faz commit dele a cada execucao. E assim que o bot lembra do que postou
mesmo rodando em uma maquina nova a cada vez.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

from .util import now_utc, url_hash

SEEN_TTL_DAYS = 21
POSTS_TTL_DAYS = 10


class State:
    def __init__(self, path: str):
        self.path = path
        self.data = {"seen": {}, "posts": [], "monthly": {}}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    loaded = json.load(fh)
                self.data["seen"] = loaded.get("seen", {}) or {}
                self.data["posts"] = loaded.get("posts", []) or []
                self.data["monthly"] = loaded.get("monthly", {}) or {}
                # blocos de outros modos (ex.: "espelho") sobrevivem ao load/save
                for key, value in loaded.items():
                    self.data.setdefault(key, value)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[state] arquivo ilegivel ({exc}); comecando do zero")

    # ---------------------------------------------------------------- leitura
    def has_seen(self, url: str) -> bool:
        return url_hash(url) in self.data["seen"]

    def recent_posts(self, hours: int):
        cutoff = now_utc() - timedelta(hours=hours)
        out = []
        for post in self.data["posts"]:
            when = _parse(post.get("ts"))
            if when and when >= cutoff:
                out.append(post)
        return out

    def posts_this_month(self) -> int:
        """Contador mensal proprio -- a lista de posts e podada, este numero nao.

        O plano free do X permite 500 posts por mes na conta; e este contador
        que impede o bot de estourar a cota e ficar mudo no fim do mes.
        """
        return int(self.data.get("monthly", {}).get(_month_key(), 0))

    def posts_last_24h(self) -> int:
        return len(self.recent_posts(24))

    def minutes_since_last_post(self):
        stamps = [_parse(p.get("ts")) for p in self.data["posts"]]
        stamps = [s for s in stamps if s]
        if not stamps:
            return None
        return (now_utc() - max(stamps)).total_seconds() / 60.0

    def recent_titles(self, hours: int = 72):
        return [p.get("title", "") for p in self.recent_posts(hours) if p.get("title")]

    def posted_kind_today(self, kind: str) -> bool:
        return any(p.get("kind") == kind for p in self.recent_posts(20))

    # -------------------------------------------------------------- escrita
    def mark_seen(self, url: str) -> None:
        self.data["seen"][url_hash(url)] = now_utc().isoformat()

    def record_post(self, kind: str, text: str, url: str = "", title: str = "", tweet_id: str = "") -> None:
        self.data["posts"].append(
            {
                "ts": now_utc().isoformat(),
                "kind": kind,
                "title": title,
                "url": url,
                "tweet_id": tweet_id,
                "text": text,
            }
        )
        month = _month_key()
        monthly = self.data.setdefault("monthly", {})
        monthly[month] = int(monthly.get(month, 0)) + 1
        if url:
            self.mark_seen(url)

    def prune(self) -> None:
        seen_cutoff = now_utc() - timedelta(days=SEEN_TTL_DAYS)
        self.data["seen"] = {
            key: ts for key, ts in self.data["seen"].items()
            if (_parse(ts) or now_utc()) >= seen_cutoff
        }
        months = sorted(self.data.get("monthly", {}).keys())[-4:]
        self.data["monthly"] = {m: self.data["monthly"][m] for m in months}
        posts_cutoff = now_utc() - timedelta(days=POSTS_TTL_DAYS)
        self.data["posts"] = [
            p for p in self.data["posts"] if (_parse(p.get("ts")) or now_utc()) >= posts_cutoff
        ]

    def _juntar_com_o_disco(self) -> None:
        """Dois processos usam o mesmo state.json (o espelho a cada 2 min e o loop de
        noticias, que fica horas de pe). Sem juntar, quem salva por ultimo apaga o
        trabalho do outro -- e post ja espelhado voltaria a sair no X, pagando de novo.
        Achado em 14/09/2026, depois que o loop continuo subiu em Toquio."""
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                disco = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        seen = dict(disco.get("seen") or {})
        seen.update(self.data.get("seen") or {})
        self.data["seen"] = seen

        vistos, posts = set(), []
        for post in (disco.get("posts") or []) + (self.data.get("posts") or []):
            chave = post.get("tweet_id") or f"{post.get('ts')}|{(post.get('text') or '')[:40]}"
            if chave in vistos:
                continue
            vistos.add(chave)
            posts.append(post)
        posts.sort(key=lambda p: p.get("ts") or "")
        self.data["posts"] = posts

        mensal = dict(disco.get("monthly") or {})
        for mes, n in (self.data.get("monthly") or {}).items():
            mensal[mes] = max(int(n or 0), int(mensal.get(mes, 0) or 0))
        self.data["monthly"] = mensal

        for chave, valor in disco.items():          # blocos de outros modos (espelho, etc.)
            self.data.setdefault(chave, valor)

    def save(self) -> None:
        self._juntar_com_o_disco()
        self.prune()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, self.path)


def _month_key() -> str:
    return now_utc().strftime("%Y-%m")


def _parse(value):
    if not value:
        return None
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            from datetime import timezone
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return None
