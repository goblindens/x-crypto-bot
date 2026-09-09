"""Publicacao no Threads (Meta).

API gratuita: a Meta nao cobra por chamada e nao tem plano pago. O limite
documentado e de 250 posts publicados por API a cada 24h por perfil -- muito
acima do que este bot usa.

Publicar tem duas etapas:
  1. cria um "container" com o texto      -> POST /{user-id}/threads
  2. publica o container                  -> POST /{user-id}/threads_publish
"""
from __future__ import annotations

import os
import time

import requests

from .publisher import PublishError

API = "https://graph.threads.net/v1.0"
TIMEOUT = 30
REQUIRED_ENV = ("THREADS_ACCESS_TOKEN",)


class ThreadsPublisher:
    name = "Threads"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.last_error = None
        self._user_id = None

    # ------------------------------------------------------------------ auth
    def _token(self) -> str:
        token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
        if not token:
            raise PublishError(
                "falta THREADS_ACCESS_TOKEN.\n"
                "Gere em developers.facebook.com -> seu app -> Threads -> "
                "User Token Generator, e coloque no .env (local) ou nos "
                "Secrets do GitHub."
            )
        return token

    def user_id(self) -> str:
        """Descobre o id do perfil a partir do proprio token -- assim voce so
        precisa guardar UMA credencial, nao duas."""
        if self._user_id:
            return self._user_id
        cached = os.environ.get("THREADS_USER_ID", "").strip()
        if cached:
            self._user_id = cached
            return cached
        data = self._get("/me", {"fields": "id,username"})
        self._user_id = str(data["id"])
        return self._user_id

    def whoami(self) -> dict:
        return self._get("/me", {"fields": "id,username"})

    # ------------------------------------------------------------------ http
    def _get(self, path: str, params: dict) -> dict:
        params = dict(params, access_token=self._token())
        try:
            response = requests.get(API + path, params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PublishError(f"falha de rede: {exc}") from exc
        return self._json_or_fail(response)

    def _post(self, path: str, params: dict) -> dict:
        params = dict(params, access_token=self._token())
        try:
            response = requests.post(API + path, params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PublishError(f"falha de rede: {exc}") from exc
        return self._json_or_fail(response)

    @staticmethod
    def _json_or_fail(response) -> dict:
        try:
            data = response.json()
        except ValueError:
            raise PublishError(f"HTTP {response.status_code}: resposta ilegivel") from None
        if response.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            msg = err.get("message", response.text[:300])
            code = err.get("code", response.status_code)
            hint = ""
            if code in (190, 102):
                hint = "\n   -> o token expirou ou foi revogado; gere um novo."
            elif "permission" in str(msg).lower():
                hint = "\n   -> falta a permissao threads_content_publish no app."
            raise PublishError(f"Threads recusou (codigo {code}): {msg}{hint}")
        return data

    # ------------------------------------------------------------- publicacao
    def post(self, text: str) -> str:
        if self.dry_run:
            print("\n----- DRY RUN (nada foi publicado) -----")
            print(text)
            print("----------------------------------------\n")
            return "dry-run"

        uid = self.user_id()
        container = self._post(f"/{uid}/threads", {"media_type": "TEXT", "text": text})
        creation_id = container.get("id")
        if not creation_id:
            raise PublishError(f"container sem id: {container}")

        # A Meta recomenda esperar antes de publicar. Para post de texto puro
        # costuma estar pronto na hora, entao tentamos rapido e insistimos.
        last_exc = None
        for espera in (2, 8, 20):
            time.sleep(espera)
            try:
                published = self._post(f"/{uid}/threads_publish", {"creation_id": creation_id})
            except PublishError as exc:
                last_exc = exc
                print(f"[threads] container ainda nao pronto, tentando de novo ({exc})")
                continue
            post_id = str(published.get("id", ""))
            print(f"[threads] publicado: https://www.threads.net/@_/post/{post_id}")
            return post_id

        raise PublishError(f"container criado mas nao publicou: {last_exc}")

    def post_image(self, image_url: str, text: str) -> str:
        """Publica uma IMAGEM com legenda.

        A API do Threads nao aceita upload de arquivo: a imagem precisa estar
        num endereco publico (https), de onde a Meta baixa. Por isso o Mac
        manda o PNG pro repositorio e o workflow passa a URL "raw" do GitHub.
        JPEG ou PNG, ate 8 MB, proporcao entre 10:1 e 1:10.
        """
        if not image_url.startswith("https://"):
            raise PublishError(f"image_url precisa ser https publico: {image_url}")
        if self.dry_run:
            print("\n----- DRY RUN (nada foi publicado) -----")
            print(f"[imagem] {image_url}")
            print(text)
            print("----------------------------------------\n")
            return "dry-run"

        uid = self.user_id()
        container = self._post(f"/{uid}/threads",
                               {"media_type": "IMAGE", "image_url": image_url, "text": text})
        creation_id = container.get("id")
        if not creation_id:
            raise PublishError(f"container sem id: {container}")

        # Imagem demora mais que texto: a Meta baixa e processa antes de liberar.
        # Consultamos o status ate ficar FINISHED (a doc sugere ~30 s de espera).
        last = ""
        for espera in (5, 10, 15, 30, 30):
            time.sleep(espera)
            st = self._get(f"/{creation_id}", {"fields": "status,error_message"})
            last = st.get("status", "")
            if last == "FINISHED":
                break
            if last == "ERROR":
                raise PublishError(f"a Meta recusou a imagem: {st.get('error_message', st)}")
            print(f"[threads] imagem ainda processando ({last or 'sem status'})...")
        if last != "FINISHED":
            raise PublishError(f"imagem nao ficou pronta a tempo (status {last})")

        published = self._post(f"/{uid}/threads_publish", {"creation_id": creation_id})
        post_id = str(published.get("id", ""))
        print(f"[threads] imagem publicada: https://www.threads.net/@_/post/{post_id}")
        return post_id
