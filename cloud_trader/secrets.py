"""GCP Secret Manager client."""
from __future__ import annotations

from typing import Optional

try:
    from google.cloud import secretmanager
except ImportError:
    secretmanager = None


class GcpSecretManager:
    """Lazy-loaded GCP Secret Manager client."""

    _client = None

    def get_secret(self, secret_id: str, project_id: str, version: str = "latest") -> Optional[str]:
        if secretmanager is None:
            print("⚠️ Secret Manager not available (missing dependency)")
            return None

        if self._client is None:
            try:
                self._client = secretmanager.SecretManagerServiceClient()
            except Exception as e:
                print(f"⚠️ Failed to initialize Secret Manager client: {e}")
                return None

        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
        try:
            response = self._client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception:
            return None
