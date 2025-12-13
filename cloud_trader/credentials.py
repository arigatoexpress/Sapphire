"""Credential loading for Aster."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

from .config import get_settings
from .secrets import GcpSecretManager

_secret_manager = GcpSecretManager()


@dataclass
class Credentials:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None


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
        gcp_secret_project = settings.gcp_project_id

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

    return Credentials(api_key=api_key, api_secret=api_secret)
