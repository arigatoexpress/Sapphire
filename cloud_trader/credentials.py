"""Credential loading for all trading platforms."""

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
    # Aster (CEX)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # AI Models
    vertex_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    grok_api_key: Optional[str] = None
    
    # Notifications
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    
    # Solana / Drift
    solana_private_key: Optional[str] = None
    
    # Symphony (Monad)
    symphony_api_key: Optional[str] = None
    
    # Hyperliquid
    hl_private_key: Optional[str] = None
    hl_account_address: Optional[str] = None


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

    # ==========================================================================
    # ASTER CREDENTIALS
    # ==========================================================================
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
        print(f"DEBUG: Loaded API Secret (len={len(api_secret)})")

    # ==========================================================================
    # AI MODEL API KEYS
    # ==========================================================================
    vertex_key = os.environ.get("VERTEX_API_KEY")
    if not vertex_key and gcp_secret_project:
        print(f"DEBUG: Fetching VERTEX_API_KEY from Secret Manager...")
        vertex_key = _secret_manager.get_secret("vertex_api_key_v1", gcp_secret_project)
        if not vertex_key:
            vertex_key = _secret_manager.get_secret("VERTEX_API_KEY", gcp_secret_project)

    if vertex_key:
        print(f"DEBUG: Loaded Vertex API Key: {vertex_key[:4]}... (len={len(vertex_key)})")

    # Gemini API Key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key and gcp_secret_project:
        print(f"DEBUG: Fetching GEMINI_API_KEY from Secret Manager...")
        gemini_key = _secret_manager.get_secret("GEMINI_API_KEY", gcp_secret_project)
    
    if gemini_key:
        gemini_key = gemini_key.strip()
        print(f"DEBUG: Loaded Gemini API Key: {gemini_key[:4]}... (len={len(gemini_key)})")

    # Grok API Key
    grok_key = os.environ.get("GROK_API_KEY")
    if not grok_key and gcp_secret_project:
        print(f"DEBUG: Fetching GROK_API_KEY from Secret Manager...")
        grok_key = _secret_manager.get_secret("GROK_API_KEY", gcp_secret_project)
    
    if grok_key:
        grok_key = grok_key.strip()
        print(f"DEBUG: Loaded Grok API Key: {grok_key[:4]}... (len={len(grok_key)})")

    # ==========================================================================
    # TELEGRAM NOTIFICATIONS
    # ==========================================================================
    tg_token = settings.telegram_bot_token
    tg_chat = settings.telegram_chat_id

    if not tg_token and gcp_secret_project:
        print(f"DEBUG: Fetching TELEGRAM_BOT_TOKEN from Secret Manager...")
        tg_token = _secret_manager.get_secret("TELEGRAM_BOT_TOKEN", gcp_secret_project)
    if not tg_chat and gcp_secret_project:
        print(f"DEBUG: Fetching TELEGRAM_CHAT_ID from Secret Manager...")
        tg_chat = _secret_manager.get_secret("TELEGRAM_CHAT_ID", gcp_secret_project)

    if tg_token:
        print(f"DEBUG: Loaded Telegram Bot Token (len={len(tg_token)})")
    if tg_chat:
        print(f"DEBUG: Loaded Telegram Chat ID: {tg_chat}")

    # ==========================================================================
    # SOLANA / DRIFT
    # ==========================================================================
    solana_key = settings.solana_private_key
    if not solana_key and gcp_secret_project:
        print(f"DEBUG: Fetching SOLANA_PRIVATE_KEY from Secret Manager...")
        solana_key = _secret_manager.get_secret("SOLANA_PRIVATE_KEY", gcp_secret_project)
    
    if solana_key:
        solana_key = solana_key.strip()
        print(f"DEBUG: Loaded Solana Private Key (len={len(solana_key)})")

    # ==========================================================================
    # SYMPHONY (MONAD)
    # ==========================================================================
    symphony_key = settings.symphony_api_key
    if not symphony_key and gcp_secret_project:
        print(f"DEBUG: Fetching SYMPHONY_API_KEY from Secret Manager...")
        symphony_key = _secret_manager.get_secret("SYMPHONY_API_KEY", gcp_secret_project)
    
    if symphony_key:
        symphony_key = symphony_key.strip()
        print(f"DEBUG: Loaded Symphony API Key (len={len(symphony_key)})")

    # ==========================================================================
    # HYPERLIQUID
    # ==========================================================================
    hl_private_key = os.environ.get("HL_SECRET_KEY")
    hl_account_address = os.environ.get("HL_ACCOUNT_ADDRESS")
    
    if not hl_private_key and gcp_secret_project:
        print(f"DEBUG: Fetching HL_SECRET_KEY from Secret Manager...")
        hl_private_key = _secret_manager.get_secret("HL_SECRET_KEY", gcp_secret_project)
    
    if not hl_account_address and gcp_secret_project:
        print(f"DEBUG: Fetching HL_ACCOUNT_ADDRESS from Secret Manager...")
        hl_account_address = _secret_manager.get_secret("HL_ACCOUNT_ADDRESS", gcp_secret_project)
    
    if hl_private_key:
        hl_private_key = hl_private_key.strip()
        print(f"DEBUG: Loaded Hyperliquid Private Key (len={len(hl_private_key)})")
    if hl_account_address:
        hl_account_address = hl_account_address.strip()
        print(f"DEBUG: Loaded Hyperliquid Account: {hl_account_address[:10]}...")

    # ==========================================================================
    # RETURN CREDENTIALS
    # ==========================================================================
    return Credentials(
        api_key=api_key,
        api_secret=api_secret,
        vertex_api_key=vertex_key,
        gemini_api_key=gemini_key,
        grok_api_key=grok_key,
        telegram_bot_token=tg_token,
        telegram_chat_id=tg_chat,
        solana_private_key=solana_key,
        symphony_api_key=symphony_key,
        hl_private_key=hl_private_key,
        hl_account_address=hl_account_address,
    )
