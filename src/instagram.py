"""Leitura do Instagram (Graph API) para o espelho Instagram -> X.

Copia enxuta do cliente do ig2yt. Le, nunca escreve.

O token vem, nesta ordem:
  1. IG_ACCESS_TOKEN no ambiente / .env deste projeto
  2. IG_TOKENS_FILE  -> o tokens.json do ig2yt (token renovado por ele)
  3. IG_ENV_FILE     -> o .env do ig2yt (token original)
Assim o espelho usa o mesmo token que o ig2yt ja mantem vivo, sem copiar
segredo de um lugar para outro.
"""
from __future__ import annotations

import json
import os
import time

import requests

MEDIA_FIELDS = "id,caption,media_type,media_product_type,media_url,permalink,timestamp,thumbnail_url"
CHILD_FIELDS = "id,media_type,media_url,thumbnail_url"


class InstagramError(RuntimeError):
    pass


def _read_env_file(path: str, key: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def resolve_token() -> tuple[str, str]:
    """Devolve (token, origem). Levanta InstagramError se nao achar."""
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if tok:
        return tok, "IG_ACCESS_TOKEN"
    tokens_file = os.environ.get("IG_TOKENS_FILE", "").strip()
    if tokens_file and os.path.exists(tokens_file):
        try:
            with open(tokens_file, "r", encoding="utf-8") as fh:
                tok = (json.load(fh) or {}).get("ig_access_token", "")
            if tok:
                return tok, f"tokens.json do ig2yt"
        except (OSError, ValueError):
            pass
    env_file = os.environ.get("IG_ENV_FILE", "").strip()
    if env_file:
        tok = _read_env_file(env_file, "IG_ACCESS_TOKEN")
        if tok:
            return tok, ".env do ig2yt"
    raise InstagramError(
        "sem token do Instagram: defina IG_ACCESS_TOKEN, ou IG_TOKENS_FILE / IG_ENV_FILE apontando para o ig2yt"
    )


class Instagram:
    def __init__(self, timeout: int = 30):
        self.token, self.token_origin = resolve_token()
        mode = os.environ.get("IG_API_MODE", "").strip() or _read_env_file(os.environ.get("IG_ENV_FILE", ""), "IG_API_MODE") or "instagram_login"
        version = os.environ.get("GRAPH_VERSION", "").strip() or _read_env_file(os.environ.get("IG_ENV_FILE", ""), "GRAPH_VERSION") or "v23.0"
        user_id = os.environ.get("IG_USER_ID", "").strip() or _read_env_file(os.environ.get("IG_ENV_FILE", ""), "IG_USER_ID") or "me"
        host = "graph.instagram.com" if mode == "instagram_login" else "graph.facebook.com"
        self.base = f"https://{host}/{version}"
        self.user_id = user_id
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, url: str, params: dict, retries: int = 3) -> dict:
        params = dict(params)
        params.setdefault("access_token", self.token)
        last = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last = exc
                time.sleep(2 * attempt)
                continue
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    time.sleep(3 * attempt)
                    continue
            try:
                err = resp.json().get("error", {})
            except ValueError:
                err = {}
            code = err.get("code")
            msg = err.get("message", resp.text[:200])
            if code in (190, 10, 102) or resp.status_code in (401, 403):
                raise InstagramError(f"Instagram rejeitou o token (codigo {code}): {msg}")
            if code in (4, 17, 613, 32) or resp.status_code == 429:
                time.sleep(30 * attempt)
                continue
            if resp.status_code >= 500:
                time.sleep(3 * attempt)
                continue
            raise InstagramError(f"Instagram respondeu {resp.status_code} (codigo {code}): {msg}")
        raise InstagramError(f"Instagram: esgotadas as tentativas ({last})")

    def me(self) -> dict:
        return self._get(f"{self.base}/me", {"fields": "id,username"})

    def recent(self, limit: int) -> list[dict]:
        """Midias mais recentes, da mais nova para a mais antiga."""
        data = self._get(f"{self.base}/{self.user_id}/media", {"fields": MEDIA_FIELDS, "limit": str(limit)})
        return data.get("data", [])

    def children(self, media_id: str) -> list[dict]:
        return self._get(f"{self.base}/{media_id}/children", {"fields": CHILD_FIELDS}).get("data", [])

    def download(self, url: str, dest: str) -> str:
        resp = self.session.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                fh.write(chunk)
        return dest
