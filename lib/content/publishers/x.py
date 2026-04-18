"""X (Twitter) API v2 client — posts a thread in one shot.

Required env vars
-----------------
* ``X_BEARER_TOKEN`` — app-only token, OR
* ``X_ACCESS_TOKEN`` + ``X_ACCESS_SECRET`` + ``X_API_KEY`` + ``X_API_SECRET`` for
  user-context OAuth 1.0a (required to actually post).

Because X's Free tier no longer lets you post programmatically (Basic at
$200/mo does), this client is configured via ``X_BEARER_TOKEN`` for
read-only validation during dry-run, and the full OAuth 1.0a quartet for
live posting. If only the bearer token is present, :meth:`configured`
returns False for live mode — callers fall through to ``typefully`` or
leave the thread for manual posting.

Endpoint: ``POST https://api.x.com/2/tweets``  (one request per tweet,
chained via ``reply.in_reply_to_tweet_id``).
"""

from __future__ import annotations

import os
from typing import Any

from .base import PublisherClient, PublishResult, _register


@_register
class XClient(PublisherClient):
    platform = "x"
    credential_env = "X_ACCESS_TOKEN"  # user-context token is what actually lets us post

    _API = "https://api.x.com/2/tweets"

    def configured(self) -> bool:
        return all(
            os.getenv(var)
            for var in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")
        )

    def _publish(self, *, tweets: list[str]) -> PublishResult:
        if not tweets:
            return PublishResult(
                platform=self.platform, ok=False, dry_run=False, error="empty thread"
            )

        # OAuth 1.0a signing is ~80 lines; we import lazily so stdlib-only
        # test paths don't need requests-oauthlib installed.
        try:
            from requests_oauthlib import OAuth1Session  # type: ignore[import-not-found]
        except ImportError:
            return PublishResult(
                platform=self.platform,
                ok=False,
                dry_run=False,
                error="requests_oauthlib not installed — `pip install requests_oauthlib`",
            )

        oauth = OAuth1Session(
            os.getenv("X_API_KEY"),
            client_secret=os.getenv("X_API_SECRET"),
            resource_owner_key=os.getenv("X_ACCESS_TOKEN"),
            resource_owner_secret=os.getenv("X_ACCESS_SECRET"),
        )

        posted_ids: list[str] = []
        parent_id: str | None = None
        for text in tweets:
            payload: dict[str, Any] = {"text": text}
            if parent_id:
                payload["reply"] = {"in_reply_to_tweet_id": parent_id}
            r = oauth.post(self._API, json=payload, timeout=self.timeout)
            if r.status_code >= 300:
                return PublishResult(
                    platform=self.platform,
                    ok=False,
                    dry_run=False,
                    error=f"HTTP {r.status_code}: {r.text[:200]}",
                    remote_id=parent_id,
                    response_meta={"posted_before_failure": posted_ids},
                )
            data = r.json().get("data", {})
            tid = data.get("id")
            if not tid:
                return PublishResult(
                    platform=self.platform,
                    ok=False,
                    dry_run=False,
                    error=f"no tweet id in response: {r.text[:200]}",
                )
            posted_ids.append(tid)
            parent_id = tid

        first_id = posted_ids[0]
        return PublishResult(
            platform=self.platform,
            ok=True,
            dry_run=False,
            url=f"https://x.com/i/status/{first_id}",
            remote_id=first_id,
            response_meta={"thread_ids": posted_ids, "count": len(posted_ids)},
        )
