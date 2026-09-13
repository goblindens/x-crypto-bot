"""Publicacao no X via API v2 (OAuth 1.0a, conta propria)."""
from __future__ import annotations

import os

REQUIRED_ENV = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


class PublishError(RuntimeError):
    pass


class Publisher:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.last_error = None   # main() usa isto para decidir o codigo de saida
        self._client = None

    def _client_or_fail(self):
        if self._client is not None:
            return self._client
        missing = [name for name in REQUIRED_ENV if not os.environ.get(name, "").strip()]
        if missing:
            raise PublishError(
                "faltam credenciais do X: " + ", ".join(missing)
                + "\nDefina como secrets no GitHub (ou no .env local)."
            )
        import tweepy

        self._client = tweepy.Client(
            consumer_key=os.environ["X_API_KEY"],
            consumer_secret=os.environ["X_API_SECRET"],
            access_token=os.environ["X_ACCESS_TOKEN"],
            access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        )
        return self._client

    def post(self, text: str) -> str:
        """Publica e devolve o id do tweet. Em dry-run so imprime.

        Levanta PublishError em qualquer falha; quem chama registra o erro em
        self.last_error para o processo terminar com codigo != 0 e a execucao
        aparecer vermelha no GitHub Actions.
        """
        if self.dry_run:
            print("\n----- DRY RUN (nada foi publicado) -----")
            print(text)
            print("----------------------------------------\n")
            return "dry-run"

        import tweepy

        client = self._client_or_fail()
        try:
            response = client.create_tweet(text=text)
        except tweepy.TooManyRequests as exc:
            raise PublishError(f"limite de requisicoes do X atingido: {exc}") from exc
        except tweepy.Forbidden as exc:
            # tipico: texto duplicado, ou app sem permissao de escrita
            raise PublishError(f"X recusou o post (duplicado ou permissao read-only?): {exc}") from exc
        except tweepy.Unauthorized as exc:
            raise PublishError(f"credenciais invalidas do X: {exc}") from exc
        except tweepy.TweepyException as exc:
            raise PublishError(f"erro ao publicar: {exc}") from exc

        tweet_id = str((response.data or {}).get("id", ""))
        print(f"[x] publicado: https://x.com/i/web/status/{tweet_id}")
        return tweet_id

    def post_reply(self, text: str, in_reply_to: str) -> str:
        """Responde a um post proprio (e onde o link vai, quando vai)."""
        if self.dry_run:
            print(f"----- DRY RUN resposta a {in_reply_to} -----\n{text}\n")
            return "dry-run"
        import tweepy

        client = self._client_or_fail()
        try:
            response = client.create_tweet(text=text, in_reply_to_tweet_id=in_reply_to)
        except tweepy.TweepyException as exc:
            raise PublishError(f"erro ao responder {in_reply_to}: {exc}") from exc
        reply_id = str((response.data or {}).get("id", ""))
        print(f"[x] resposta publicada: https://x.com/i/web/status/{reply_id}")
        return reply_id

    def post_with_media(self, text: str, image_path: str, video: bool = False) -> str:
        """Publica texto (pode ser vazio) com uma imagem ou um video. Em dry-run so imprime.

        O upload usa o endpoint v1.1 (media/upload), que o tweepy 4.14 expoe em
        API.media_upload e que segue aceito pelas chaves desta conta (testado
        em 12/09/2026). Video vai em pedaços (chunked) e espera o X terminar
        de processar antes de publicar. Se o X desligar o v1.1, a troca e so aqui.
        """
        if self.dry_run:
            print("\n----- DRY RUN (nada foi publicado) -----")
            print(text if text else "(so a midia)")
            print(f"[{'video' if video else 'imagem'}] {image_path}")
            print("----------------------------------------\n")
            return "dry-run"

        import tweepy

        client = self._client_or_fail()
        auth = tweepy.OAuth1UserHandler(
            os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
            os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_TOKEN_SECRET"],
        )
        try:
            api = tweepy.API(auth)
            if video:
                media = api.media_upload(image_path, chunked=True, media_category="tweet_video",
                                         wait_for_async_finalize=True)
                estado = getattr(getattr(media, "processing_info", None), "state", None) or \
                    (media.processing_info or {}).get("state") if hasattr(media, "processing_info") else None
                if estado and estado not in ("succeeded", None):
                    raise PublishError(f"X nao terminou de processar o video (estado: {estado})")
            else:
                media = api.media_upload(image_path)
            response = client.create_tweet(text=text or None, media_ids=[media.media_id_string])
        except tweepy.TooManyRequests as exc:
            raise PublishError(f"limite de requisicoes do X atingido: {exc}") from exc
        except tweepy.Forbidden as exc:
            raise PublishError(f"X recusou o post (duplicado, sem credito ou read-only?): {exc}") from exc
        except tweepy.Unauthorized as exc:
            raise PublishError(f"credenciais invalidas do X: {exc}") from exc
        except tweepy.TweepyException as exc:
            raise PublishError(f"erro ao publicar com imagem: {exc}") from exc

        tweet_id = str((response.data or {}).get("id", ""))
        print(f"[x] publicado com imagem: https://x.com/i/web/status/{tweet_id}")
        return tweet_id
