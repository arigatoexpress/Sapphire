"""Typefully API client — scheduled X threads without the $200/mo X Basic tier.

Typefully is the cheapest way to post X threads programmatically today;
their free tier includes one scheduled thread per day and the paid tier
($12.50/mo) lifts that.

Required env vars
-----------------
* ``TYPEFULLY_API_KEY`` — from https://typefully.com/settings/integrations

Endpoint: ``POST https://api.typefully.com/v1/drafts/``

This is a fallback for :class:`XClient` — if the X API quartet isn't
present, the orchestrator tries ``typefully`` as platform ``x``.
"""

from __future__ import annotations

import os
from typing import Any

from .base import PublisherClient, PublishResult, _register


@_register
class TypefullyClient(PublisherClient):
    platform = "typefully"
    credential_env = "TYPEFULLY_API_KEY"

    _API = "https://api.typefully.com/v1/drafts/"

    def _publish(
        self,
        *,
        tweets: list[str],
        schedule: str = "next-free-slot",
        auto_publish: bool = True,
    ) -> PublishResult:
        """Create a Typefully draft from the thread.

        Args:
            tweets: list of tweet bodies.
            schedule: ISO-8601 timestamp, ``"next-free-slot"``, or
                ``None`` to leave as draft.
            auto_publish: if True + schedule set, Typefully posts it to
                X automatically at that time.
        """
        if not tweets:
            return PublishResult(
                platform=self.platform, ok=False, dry_run=False, error="empty thread"
            )

        content = "\n\n\n\n".join(tweets)  # quadruple newline = Typefully thread break
        payload: dict[str, Any] = {
            "content": content,
            "threadify": False,
            "auto_retweet_enabled": False,
        }
        if schedule:
            payload["schedule-date"] = schedule
            payload["auto-publish"] = auto_publish

        headers = {"X-API-KEY": os.getenv(self.credential_env, "")}
        status, resp = self._http_json(self._API, method="POST", headers=headers, body=payload)
        ok = 200 <= status < 300
        remote_id = resp.get("id") if isinstance(resp, dict) else None
        url = resp.get("share_url") if isinstance(resp, dict) else None
        return PublishResult(
            platform=self.platform,
            ok=ok,
            dry_run=False,
            url=url,
            remote_id=str(remote_id) if remote_id is not None else None,
            error=None if ok else f"Typefully HTTP {status}: {resp}",
            response_meta={"status": status, "schedule": schedule},
        )
