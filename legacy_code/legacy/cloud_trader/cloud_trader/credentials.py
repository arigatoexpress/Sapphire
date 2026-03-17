"""Credential loading for all trading platforms."""

from __future__ import annotations

import base64
import logging
import os
from dataclasses import dataclass
from typing import Dict, Optional

from .api_secrets import GcpSecretManager
from .config import get_settings

logger = logging.getLogger(__name__)
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

    # Solana / Aster / Jupiter
    solana_private_key: Optional[str] = None
    jupiter_api_key: Optional[str] = None

    # Aster (Monad)
    aster_api_key: Optional[str] = None

    # Lighter
    hl_private_key: Optional[str] = None
    hl_account_address: Optional[str] = None

    # Lighter
    lighter_pub_key: Optional[str] = None
    lighter_priv_key: Optional[str] = None
    lighter_account_index: int = 699444
    lighter_api_key_index: int = 0
    lighter_api_keys: Optional[Dict[int, str]] = None  # {api_key_index: private_key}

    # Aster Code (builder incentive)
    aster_code_builder_address: Optional[str] = None
    aster_code_fee_rate: Optional[str] = None


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
        logger.debug("Fetching ASTER_API_KEY from Secret Manager")
        api_key = _secret_manager.get_secret("ASTER_API_KEY", gcp_secret_project)

    if not api_secret and gcp_secret_project:
        logger.debug("Fetching ASTER_SECRET_KEY from Secret Manager")
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
        logger.debug("Loaded API Key (configured)")

    if api_secret:
        api_secret = api_secret.strip()
        logger.debug("Loaded API Secret (configured)")

    # ==========================================================================
    # AI MODEL API KEYS
    # ==========================================================================
    vertex_key = os.environ.get("VERTEX_API_KEY")
    if not vertex_key and gcp_secret_project:
        logger.debug("Fetching VERTEX_API_KEY from Secret Manager")
        vertex_key = _secret_manager.get_secret("vertex_api_key_v1", gcp_secret_project)
        if not vertex_key:
            vertex_key = _secret_manager.get_secret("VERTEX_API_KEY", gcp_secret_project)

    if vertex_key:
        logger.debug("Loaded Vertex API Key (configured)")

    # Gemini API Key
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_key and gcp_secret_project:
        logger.debug("Fetching GEMINI_API_KEY from Secret Manager")
        gemini_key = _secret_manager.get_secret("GEMINI_API_KEY", gcp_secret_project)
    
    if gemini_key:
        gemini_key = gemini_key.strip()
        logger.debug("Loaded Gemini API Key (configured)")

    # Grok API Key
    grok_key = os.environ.get("GROK_API_KEY")
    if not grok_key and gcp_secret_project:
        logger.debug("Fetching GROK_API_KEY from Secret Manager")
        grok_key = _secret_manager.get_secret("GROK_API_KEY", gcp_secret_project)
    
    if grok_key:
        grok_key = grok_key.strip()
        logger.debug("Loaded Grok API Key (configured)")

    # ==========================================================================
    # TELEGRAM NOTIFICATIONS
    # ==========================================================================
    tg_token = settings.telegram_bot_token
    tg_chat = settings.telegram_chat_id

    if not tg_token and gcp_secret_project:
        logger.debug("Fetching TELEGRAM_BOT_TOKEN from Secret Manager")
        tg_token = _secret_manager.get_secret("TELEGRAM_BOT_TOKEN", gcp_secret_project)
    if not tg_chat and gcp_secret_project:
        logger.debug("Fetching TELEGRAM_CHAT_ID from Secret Manager")
        tg_chat = _secret_manager.get_secret("TELEGRAM_CHAT_ID", gcp_secret_project)

    if tg_token:
        logger.debug("Loaded Telegram Bot Token (configured)")
    if tg_chat:
        logger.debug("Loaded Telegram Chat ID (configured)")

    # ==========================================================================
    # SOLANA / ASTER (Using ASTER_SOLANA_PRIVATE_KEY - original key compromised)
    # ==========================================================================
    solana_key = settings.solana_private_key
    if not solana_key and gcp_secret_project:
        logger.debug("Fetching ASTER_SOLANA_PRIVATE_KEY from Secret Manager")
        solana_key = _secret_manager.get_secret("ASTER_SOLANA_PRIVATE_KEY", gcp_secret_project)

    if solana_key:
        solana_key = solana_key.strip()
        logger.debug("Loaded Solana Private Key (configured)")

    # ==========================================================================
    # ASTER (MONAD)
    # ==========================================================================
    aster_key = settings.aster_api_key
    if not aster_key and gcp_secret_project:
        logger.debug("Fetching ASTER_API_KEY from Secret Manager")
        aster_key = _secret_manager.get_secret("ASTER_API_KEY", gcp_secret_project)
    
    if aster_key:
        aster_key = aster_key.strip()
        logger.debug("Loaded Aster API Key (configured)")

    # ==========================================================================
    # LIGHTER
    # ==========================================================================
    hl_private_key = os.environ.get("HL_SECRET_KEY")
    hl_account_address = os.environ.get("HL_ACCOUNT_ADDRESS")
    
    if not hl_private_key and gcp_secret_project:
        logger.debug("Fetching HL_SECRET_KEY from Secret Manager")
        hl_private_key = _secret_manager.get_secret("HL_SECRET_KEY", gcp_secret_project)
    
    if not hl_account_address and gcp_secret_project:
        logger.debug("Fetching HL_ACCOUNT_ADDRESS from Secret Manager")
        hl_account_address = _secret_manager.get_secret("HL_ACCOUNT_ADDRESS", gcp_secret_project)
    
    if hl_private_key:
        hl_private_key = hl_private_key.strip()
        logger.debug("Loaded Lighter Private Key (configured)")
    if hl_account_address:
        hl_account_address = hl_account_address.strip()
        logger.debug("Loaded Lighter Account (configured)")

    # ==========================================================================
    # LIGHTER (supports separate account_index and api_key_index)
    # ==========================================================================
    lighter_pub_key = os.environ.get("LIGHTER_PUB_KEY")
    lighter_priv_key = os.environ.get("LIGHTER_PRIV_KEY")

    if not lighter_pub_key and gcp_secret_project:
        logger.debug("Fetching LIGHTER_PUB_KEY from Secret Manager")
        lighter_pub_key = _secret_manager.get_secret("LIGHTER_PUB_KEY", gcp_secret_project)

    if not lighter_priv_key and gcp_secret_project:
        logger.debug("Fetching LIGHTER_PRIV_KEY from Secret Manager")
        lighter_priv_key = _secret_manager.get_secret("LIGHTER_PRIV_KEY", gcp_secret_project)

    if lighter_pub_key:
        lighter_pub_key = lighter_pub_key.strip()
        logger.debug("Loaded Lighter Pub Key (configured)")
    if lighter_priv_key:
        lighter_priv_key = lighter_priv_key.strip()
        logger.debug("Loaded Lighter Priv Key (configured)")

    # Lighter account_index / api_key_index from env
    lighter_account_index = int(os.environ.get("LIGHTER_ACCOUNT_INDEX", "699444"))
    lighter_api_key_index = int(os.environ.get("LIGHTER_API_KEY_INDEX", "0"))

    # Build api_keys dict: {api_key_index: private_key}
    lighter_api_keys: Optional[Dict[int, str]] = None
    if lighter_priv_key:
        lighter_api_keys = {lighter_api_key_index: lighter_priv_key}

    # ==========================================================================
    # ASTER CODE (Builder Incentive)
    # ==========================================================================
    aster_code_builder_address = os.environ.get("ASTER_CODE_BUILDER_ADDRESS")
    aster_code_fee_rate = os.environ.get("ASTER_CODE_FEE_RATE", "0")

    # ==========================================================================
    # JUPITER
    # ==========================================================================
    jupiter_api_key = os.environ.get("JUPITER_API_KEY", "")

    if not jupiter_api_key and gcp_secret_project:
        logger.debug("Fetching JUPITER_API_KEY from Secret Manager")
        jupiter_api_key = _secret_manager.get_secret("JUPITER_API_KEY", gcp_secret_project)

    if jupiter_api_key:
        jupiter_api_key = jupiter_api_key.strip()
        logger.debug("Loaded Jupiter API Key (configured)")

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
        jupiter_api_key=jupiter_api_key,
        aster_api_key=aster_key,
        hl_private_key=hl_private_key,
        hl_account_address=hl_account_address,
        lighter_pub_key=lighter_pub_key,
        lighter_priv_key=lighter_priv_key,
        lighter_account_index=lighter_account_index,
        lighter_api_key_index=lighter_api_key_index,
        lighter_api_keys=lighter_api_keys,
        aster_code_builder_address=aster_code_builder_address,
        aster_code_fee_rate=aster_code_fee_rate,
    )
