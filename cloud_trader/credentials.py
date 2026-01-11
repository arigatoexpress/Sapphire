"""Credential loading for Aster."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

from .api_secrets import GcpSecretManager
from .config import get_settings

_secret_manager = GcpSecretManager()


@dataclass
class Credentials:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    # Vertex AI for Gemini 2.5
    vertex_api_key: Optional[str] = None
    # Notifications
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # Platform Keys
    solana_private_key: Optional[str] = None
    symphony_api_key: Optional[str] = None


class CredentialManager:
    _credentials: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        if self._credentials is None:
            self._credentials = load_credentials()
        return self._credentials


def load_credentials(gcp_secret_project: Optional[str] = None) -> Credentials:
    settings = get_settings()

    # Priority 1: Settings (Env Vars loaded by Pydantic)
    api_key = settings.aster_api_key
    api_secret = settings.aster_api_secret

    if not gcp_secret_project:
        gcp_secret_project = settings.gcp_project_id or "sapphire-479610"

    if not api_key and gcp_secret_project:
        print(
            f"DEBUG: Fetching ASTER_API_KEY from Secret Manager (project={gcp_secret_project})...",
            flush=True,
        )
        api_key = _secret_manager.get_secret("ASTER_API_KEY", gcp_secret_project)

    if not api_secret and gcp_secret_project:
        print(
            f"DEBUG: Fetching ASTER_SECRET_KEY from Secret Manager (project={gcp_secret_project})...",
            flush=True,
        )
        api_secret = _secret_manager.get_secret("ASTER_SECRET_KEY", gcp_secret_project)

    # It's possible the secret is base64-encoded
    if api_secret and len(api_secret) > 64:
        try:
            decoded = base64.b64decode(api_secret).decode("utf-8")
            if "PRIVATE KEY" in decoded:
                api_secret = decoded
        except (ValueError, UnicodeDecodeError):
            pass

    if api_key:
        api_key = api_key.strip()
        print(f"DEBUG: Loaded API Key: {api_key[:4]}... (len={len(api_key)})")

    if api_secret:
        api_secret = api_secret.strip()
        # Don't print secret parts for security, just length
        print(f"DEBUG: Loaded API Secret (len={len(api_secret)})")

    # Fetch Vertex API Key for Gemini 2.5
    vertex_key = os.environ.get("VERTEX_API_KEY")
    if not vertex_key and gcp_secret_project:
        print(
            f"DEBUG: Fetching VERTEX_API_KEY from Secret Manager (project={gcp_secret_project})..."
        )
        # Try both names to be safe
        vertex_key = _secret_manager.get_secret("vertex_api_key_v1", gcp_secret_project)
        if not vertex_key:
            vertex_key = _secret_manager.get_secret("VERTEX_API_KEY", gcp_secret_project)

    if vertex_key:
        print(f"DEBUG: Loaded Vertex API Key: {vertex_key[:4]}... (len={len(vertex_key)})")

    # Fetch Telegram & Platform Keys
    tg_token = settings.telegram_bot_token
    tg_chat = settings.telegram_chat_id
    solana_key = settings.solana_private_key
    symphony_key = settings.symphony_api_key

    if not tg_token and gcp_secret_project:
        tg_token = _secret_manager.get_secret("TELEGRAM_BOT_TOKEN", gcp_secret_project)
    if not tg_chat and gcp_secret_project:
        tg_chat = _secret_manager.get_secret("TELEGRAM_CHAT_ID", gcp_secret_project)
    if not solana_key and gcp_secret_project:
        solana_key = _secret_manager.get_secret("SOLANA_PRIVATE_KEY", gcp_secret_project)
    if not symphony_key and gcp_secret_project:
        symphony_key = _secret_manager.get_secret("SYMPHONY_API_KEY", gcp_secret_project)

    return Credentials(
        api_key=api_key,
        api_secret=api_secret,
        vertex_api_key=vertex_key,
        telegram_bot_token=tg_token,
        telegram_chat_id=tg_chat,
        solana_private_key=solana_key,
        symphony_api_key=symphony_key,
    )
