"""Credential loading for Aster."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Credentials:
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    # Vertex AI for Gemini 2.5
    vertex_api_key: Optional[str] = None


class CredentialManager:
    _credentials: Optional[Credentials] = None

    def get_credentials(self) -> Credentials:
        if self._credentials is None:
            self._credentials = load_credentials()
        return self._credentials


def load_credentials(gcp_secret_project: Optional[str] = None) -> Credentials:
    # Simplified version for bot-aster service that relies on env vars provided by Cloud Run
    api_key = os.getenv("ASTER_API_KEY")
    api_secret = os.getenv("ASTER_SECRET_KEY") or os.getenv("ASTER_API_SECRET")
    vertex_key = os.getenv("VERTEX_API_KEY")

    return Credentials(api_key=api_key, api_secret=api_secret, vertex_api_key=vertex_key)
