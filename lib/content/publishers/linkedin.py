"""LinkedIn UGC Posts API client.

Scope: ``w_member_social`` (personal) or ``w_organization_social`` (page).

Required env vars
-----------------
* ``LINKEDIN_ACCESS_TOKEN`` — OAuth 2.0 3-legged access token.
* ``LINKEDIN_AUTHOR_URN`` — ``urn:li:person:{id}`` or ``urn:li:organization:{id}``.

Endpoint: ``POST https://api.linkedin.com/v2/ugcPosts``

Rate limits (2026-04): 500 posts / member / day on Developer tier; 100
calls / member / hour.  See ``docs/web-integrations.md`` for the current
ceiling — LinkedIn updates these quietly.

Images / media require a two-step register-upload dance; this client
posts text-only for now. ``media_asset_urn`` can be supplied by callers
that pre-registered a media asset.
"""

from __future__ import annotations

import os
from typing import Any

from .base import PublisherClient, PublishResult, _register


@_register
class LinkedInClient(PublisherClient):
    platform = "linkedin"
    credential_env = "LINKEDIN_ACCESS_TOKEN"

    _API = "https://api.linkedin.com/v2/ugcPosts"

    def _publish(
        self,
        *,
        text: str,
        visibility: str = "PUBLIC",
        media_asset_urn: str | None = None,
    ) -> PublishResult:
        token = os.getenv(self.credential_env, "")
        author = os.getenv("LINKEDIN_AUTHOR_URN", "")
        if not author:
            return PublishResult(
                platform=self.platform,
                ok=False,
                dry_run=False,
                error="missing LINKEDIN_AUTHOR_URN",
            )

        share: dict[str, Any] = {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "NONE",
        }
        if media_asset_urn:
            share["shareMediaCategory"] = "IMAGE"
            share["media"] = [
                {
                    "status": "READY",
                    "description": {"text": ""},
                    "media": media_asset_urn,
                    "title": {"text": ""},
                }
            ]

        body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {"com.linkedin.ugc.ShareContent": share},
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": visibility},
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }
        status, resp = self._http_json(self._API, method="POST", headers=headers, body=body)

        ok = 200 <= status < 300
        remote_id = resp.get("id") if isinstance(resp, dict) else None
        url = f"https://www.linkedin.com/feed/update/{remote_id}/" if ok and remote_id else None
        return PublishResult(
            platform=self.platform,
            ok=ok,
            dry_run=False,
            url=url,
            remote_id=remote_id,
            error=None if ok else f"HTTP {status}: {resp}",
            response_meta={"status": status},
        )
