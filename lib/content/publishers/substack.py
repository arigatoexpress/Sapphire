"""Substack publisher.

Substack has no documented public "create post" API.  Two paths work:

1. **Email-to-post** — every Substack publication exposes a private
   ``post@<pub>.substack.com`` address. Emails sent to it become drafts.
   We go through Resend (which Sapphire already uses for THO) so we get
   delivery receipts and consistent SPF/DKIM.
2. **Internal draft endpoint** — a reverse-engineered
   ``POST https://substack.com/api/v1/drafts`` call, gated by a session
   cookie. Cookies expire and the endpoint is undocumented, so we
   treat it as best-effort and only enable it when
   ``SUBSTACK_SESSION_COOKIE`` is explicitly set.

Required env vars
-----------------
* ``SUBSTACK_POST_EMAIL`` — the publication's private submission address.
* ``RESEND_API_KEY`` — Resend token for sending the post email.
* ``RESEND_FROM_EMAIL`` — verified from-address (e.g. ``press@kadima.digital``).
* (optional) ``SUBSTACK_SESSION_COOKIE`` — enables the direct-draft path.

Once the email lands in Substack as a draft, Ari still needs to click
"Publish" in the web UI — deliberately — because copy-review is part
of the content quality gate.
"""

from __future__ import annotations

import os
from typing import Any

from .base import PublisherClient, PublishResult, _register


@_register
class SubstackClient(PublisherClient):
    platform = "substack"
    # Primary path is email-to-post through Resend; treat RESEND_API_KEY
    # as the credential because that's what we need to hit the network.
    credential_env = "RESEND_API_KEY"

    _RESEND_API = "https://api.resend.com/emails"

    def configured(self) -> bool:
        return all(
            os.getenv(var) for var in ("RESEND_API_KEY", "SUBSTACK_POST_EMAIL", "RESEND_FROM_EMAIL")
        )

    def _publish(
        self, *, title: str, body_html: str, body_text: str | None = None
    ) -> PublishResult:
        to_addr = os.getenv("SUBSTACK_POST_EMAIL", "")
        from_addr = os.getenv("RESEND_FROM_EMAIL", "")
        token = os.getenv("RESEND_API_KEY", "")

        payload: dict[str, Any] = {
            "from": from_addr,
            "to": [to_addr],
            "subject": title,
            "html": body_html,
        }
        if body_text:
            payload["text"] = body_text

        headers = {"Authorization": f"Bearer {token}"}
        status, resp = self._http_json(
            self._RESEND_API, method="POST", headers=headers, body=payload
        )
        ok = 200 <= status < 300
        remote_id = resp.get("id") if isinstance(resp, dict) else None
        return PublishResult(
            platform=self.platform,
            ok=ok,
            dry_run=False,
            url=None,
            remote_id=remote_id,
            error=None if ok else f"Resend HTTP {status}: {resp}",
            response_meta={"status": status, "via": "email-to-post"},
        )
