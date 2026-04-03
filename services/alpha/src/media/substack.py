import asyncio
import email.utils
import os
import smtplib
import time
from email.message import EmailMessage

import aiohttp
from loguru import logger


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class SubstackClient:
    """
    Substack publishing client.

    Supports two delivery modes:
    1) Email publishing (recommended baseline): SMTP -> publication ingest email
    2) Webhook publishing: POST to `SAPPHIRE_MEDIA_SUBSTACK_POST_URL`
    """

    def __init__(self):
        self.enabled = _is_true(os.getenv("SAPPHIRE_MEDIA_SUBSTACK_ENABLED", "false"))

        self.publication_url = (
            os.getenv("SAPPHIRE_SUBSTACK_PUBLICATION_URL", "").strip()
            or os.getenv("SAPPHIRE_SUBSTACK_URL", "").strip()
        )
        self.api_key = (
            os.getenv("SAPPHIRE_SUBSTACK_API_TOKEN", "").strip()
            or os.getenv("SAPPHIRE_SUBSTACK_API_KEY", "").strip()
        )

        self.post_url = os.getenv("SAPPHIRE_MEDIA_SUBSTACK_POST_URL", "").strip()
        self.publication_email = os.getenv("SAPPHIRE_SUBSTACK_PUBLICATION_EMAIL", "").strip()
        self.from_email = os.getenv("SAPPHIRE_SUBSTACK_FROM_EMAIL", "").strip()
        self.from_name = os.getenv("SAPPHIRE_SUBSTACK_FROM_NAME", "Sapphire Inc. 🤖").strip()
        self.smtp_host = os.getenv("SAPPHIRE_SUBSTACK_SMTP_HOST", "").strip()
        self.smtp_port = int(os.getenv("SAPPHIRE_SUBSTACK_SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SAPPHIRE_SUBSTACK_SMTP_USERNAME", "").strip()
        self.smtp_password = os.getenv("SAPPHIRE_SUBSTACK_SMTP_PASSWORD", "").strip()
        self.smtp_use_tls = _is_true(os.getenv("SAPPHIRE_SUBSTACK_SMTP_USE_TLS", "true"))
        self.ready = False
        self.mode = "disabled"

    async def start(self):
        """Initialize client and resolve active publishing mode."""
        if not self.enabled:
            logger.info("🚫 Substack automation disabled via config.")
            self.mode = "disabled"
            return

        if self.post_url:
            self.mode = "webhook"
            self.ready = True
            logger.info(f"✅ SubstackClient initialized in webhook mode: {self.post_url}")
            return

        has_email_mode = all([self.publication_email, self.from_email, self.smtp_host])
        if has_email_mode:
            self.mode = "email"
            self.ready = True
            logger.info(f"✅ SubstackClient initialized in email mode: {self.publication_email}")
            return

        self.mode = "misconfigured"
        self.ready = False
        logger.warning(
            "⚠️ Substack config incomplete. Set either "
            "`SAPPHIRE_MEDIA_SUBSTACK_POST_URL` or SMTP + publication email vars."
        )

    async def post(self, title: str, body: str) -> str | None:
        """
        Publish to Substack via configured mode.

        Returns a message id / external id.
        """
        if not self.ready:
            raise RuntimeError("SubstackClient not ready")

        clean_title = str(title or "").strip() or "Sapphire Update"
        clean_body = str(body or "").strip()
        if not clean_body:
            raise RuntimeError("Substack body is empty")

        if self.mode == "webhook":
            return await self._post_via_webhook(clean_title, clean_body)
        if self.mode == "email":
            return await asyncio.to_thread(self._post_via_email_sync, clean_title, clean_body)
        raise RuntimeError(f"Unsupported Substack mode: {self.mode}")

    async def _post_via_webhook(self, title: str, body: str) -> str:
        assert self.post_url
        payload = {
            "title": title,
            "body": body,
            "publication_url": self.publication_url,
            "source": "sapphire_alpha_engine",
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self.post_url, json=payload, headers=headers) as resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"substack_webhook_http_{resp.status}: {text[:240]}")
                logger.info(f"📝 Substack webhook publish accepted ({resp.status})")
                # Prefer external id if webhook returns one, else synthesize.
                return f"webhook:{resp.status}:{hash(text) % 10_000_000}"

    def _post_via_email_sync(self, title: str, body: str) -> str:
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = email.utils.formataddr((self.from_name, self.from_email))
        msg["To"] = self.publication_email
        msg["X-Sapphire-Source"] = "alpha-engine"
        if self.publication_url:
            msg["X-Sapphire-Publication"] = self.publication_url
        msg.set_content(body)

        if self.smtp_use_tls:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=20)
            smtp.ehlo()

        try:
            if self.smtp_username:
                smtp.login(self.smtp_username, self.smtp_password)
            smtp.send_message(msg)
            logger.info(f"📝 Substack email publish sent to {self.publication_email}")
            return msg.get("Message-ID") or f"email:{int(time.time())}"
        finally:
            try:
                smtp.quit()
            except Exception:
                smtp.close()
