"""Publicacao no X via API v2 (OAuth 1.0a, conta propria)."""
from __future__ import annotations

import os

REQUIRED_ENV = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")


class PublishError(RuntimeError):
    pass


class Publisher:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
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
        """Publica e devolve o id do tweet. Em dry-run so imprime."""
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
