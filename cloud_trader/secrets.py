"""GCP Secret Manager client."""
from __future__ import annotations

from typing import Optional

from google.cloud import secretmanager


class GcpSecretManager:
    """Lazy-loaded GCP Secret Manager client."""

    _client: Optional[secretmanager.SecretManagerServiceClient] = None

    def get_secret(self, secret_id: str, project_id: str, version: str = "latest") -> Optional[str]:
        if self._client is None:
            self._client = secretmanager.SecretManagerServiceClient()

        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
        try:
            response = self._client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            return None
