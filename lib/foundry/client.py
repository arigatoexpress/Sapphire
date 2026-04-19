"""Palantir Foundry SDK client for Sapphire.

Wraps Foundry REST APIs for dataset operations, ontology object sync, and
health checks.  Supports token-based and OAuth client-credentials auth.

Configuration resolution order:
  1. Environment variables (PALANTIR_FOUNDRY_*, FOUNDRY_*)
  2. Files in ``$SAPPHIRE_SECRETS_DIR`` (default ``~/.config/sapphire-secrets``):
     - ``foundry_url`` — Foundry stack URL
     - ``foundry_token`` — bearer token
     - ``foundry_client_id`` / ``foundry_client_secret`` — OAuth

Env variables:
  PALANTIR_FOUNDRY_URL / FOUNDRY_URL          — Foundry stack URL
  PALANTIR_FOUNDRY_TOKEN / FOUNDRY_TOKEN      — bearer token (simplest)
  PALANTIR_FOUNDRY_CLIENT_ID + _SECRET        — OAuth client-credentials
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("foundry.client")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_URL_ENVS = ("PALANTIR_FOUNDRY_URL", "FOUNDRY_URL")
_TOKEN_ENVS = ("PALANTIR_FOUNDRY_TOKEN", "FOUNDRY_TOKEN", "FOUNDRY_API_TOKEN")
_CLIENT_ID_ENVS = ("PALANTIR_FOUNDRY_CLIENT_ID", "FOUNDRY_CLIENT_ID")
_CLIENT_SECRET_ENVS = ("PALANTIR_FOUNDRY_CLIENT_SECRET", "FOUNDRY_CLIENT_SECRET")

_DEFAULT_SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"


def _secrets_dir() -> Path:
    override = os.getenv("SAPPHIRE_SECRETS_DIR")
    return Path(override) if override else _DEFAULT_SECRETS_DIR


def _first_env(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


def _read_secret_file(name: str) -> str | None:
    """Read a single-value secret file from the sapphire-secrets dir.

    Returns the stripped contents, or None if the file doesn't exist or can't
    be read. Never raises — missing files are a normal fallback path.
    """
    path = _secrets_dir() / name
    try:
        if path.is_file():
            return path.read_text().strip() or None
    except OSError as exc:
        log.warning("Failed to read secret %s: %s", path, exc)
    return None


def _resolve_url() -> str | None:
    return _first_env(*_URL_ENVS) or _read_secret_file("foundry_url")


def _resolve_token() -> str | None:
    return _first_env(*_TOKEN_ENVS) or _read_secret_file("foundry_token")


def _resolve_client_id() -> str | None:
    return _first_env(*_CLIENT_ID_ENVS) or _read_secret_file("foundry_client_id")


def _resolve_client_secret() -> str | None:
    return (
        _first_env(*_CLIENT_SECRET_ENVS)
        or _read_secret_file("foundry_client_secret")
    )


@dataclass
class FoundryAuth:
    """Resolved auth bundle.  Token takes priority over OAuth."""

    base_url: str
    token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    _oauth_token: str | None = field(default=None, repr=False)
    _oauth_expiry: float = field(default=0.0, repr=False)

    # -- public ---------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "FoundryAuth":
        """Build auth from environment variables, falling back to secrets dir."""
        url = _resolve_url()
        if not url:
            raise FoundryConfigError(
                "No Foundry URL configured.  Set PALANTIR_FOUNDRY_URL, "
                f"FOUNDRY_URL, or write {_secrets_dir() / 'foundry_url'}."
            )
        url = url.rstrip("/")
        token = _resolve_token()
        client_id = _resolve_client_id()
        client_secret = _resolve_client_secret()
        if not token and not (client_id and client_secret):
            raise FoundryConfigError(
                "No Foundry credentials configured.  "
                "Set PALANTIR_FOUNDRY_TOKEN or both CLIENT_ID + CLIENT_SECRET, "
                f"or write {_secrets_dir() / 'foundry_token'}."
            )
        return cls(
            base_url=url,
            token=token,
            client_id=client_id,
            client_secret=client_secret,
        )

    def bearer_token(self) -> str:
        """Return a valid bearer token, refreshing OAuth if needed."""
        if self.token:
            return self.token
        if self._oauth_token and time.time() < self._oauth_expiry - 30:
            return self._oauth_token
        return self._refresh_oauth()

    @property
    def auth_mode(self) -> str:
        return "token" if self.token else "oauth"

    # -- private --------------------------------------------------------------

    def _refresh_oauth(self) -> str:
        url = f"{self.base_url}/multipass/api/oauth2/token"
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id or "",
            "client_secret": self.client_secret or "",
        }).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise FoundryAuthError(f"OAuth token refresh failed: {exc}") from exc

        self._oauth_token = data["access_token"]
        self._oauth_expiry = time.time() + data.get("expires_in", 3600)
        log.info("Foundry OAuth token refreshed, expires in %ds", data.get("expires_in", 3600))
        return self._oauth_token  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class FoundryError(Exception):
    """Base Foundry error."""


class FoundryConfigError(FoundryError):
    """Missing or invalid configuration."""


class FoundryAuthError(FoundryError):
    """Authentication failure."""


class FoundryAPIError(FoundryError):
    """HTTP-level API error."""

    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class FoundryClient:
    """Thin wrapper around Foundry REST APIs.

    Usage::

        client = FoundryClient.from_env()
        client.health()
        client.upsert_objects("ri.ontology..objectType.PaperTrade", rows)
    """

    def __init__(self, auth: FoundryAuth, *, timeout: int = 30):
        self.auth = auth
        self.timeout = timeout

    @classmethod
    def from_env(cls, **kwargs: Any) -> "FoundryClient":
        return cls(FoundryAuth.from_env(), **kwargs)

    # -- low-level HTTP -------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.auth.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)

        headers = {
            "Authorization": f"Bearer {self.auth.bearer_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode()[:2000]
            except Exception:
                pass
            raise FoundryAPIError(
                f"Foundry API {method} {path} → {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc
        except Exception as exc:
            raise FoundryAPIError(f"Foundry API {method} {path} failed: {exc}") from exc

    def _get(self, path: str, **kw: Any) -> dict[str, Any]:
        return self._request("GET", path, **kw)

    def _post(self, path: str, **kw: Any) -> dict[str, Any]:
        return self._request("POST", path, **kw)

    def _put(self, path: str, **kw: Any) -> dict[str, Any]:
        return self._request("PUT", path, **kw)

    # -- health ---------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Check Foundry stack health.  Returns ``{"ok": True/False, ...}``."""
        try:
            resp = self._get("/api/v2/datasets", params={"pageSize": "1"})
            return {"ok": True, "auth_mode": self.auth.auth_mode, "datasets_accessible": True}
        except FoundryAPIError as exc:
            return {
                "ok": False,
                "auth_mode": self.auth.auth_mode,
                "error": str(exc),
                "status": exc.status,
            }
        except FoundryError as exc:
            return {"ok": False, "auth_mode": self.auth.auth_mode, "error": str(exc)}

    # -- dataset operations ---------------------------------------------------

    def get_dataset(self, dataset_rid: str) -> dict[str, Any]:
        return self._get(f"/api/v2/datasets/{dataset_rid}")

    def list_datasets(self, *, page_size: int = 25) -> dict[str, Any]:
        return self._get("/api/v2/datasets", params={"pageSize": str(page_size)})

    def create_dataset(self, name: str, parent_folder_rid: str) -> dict[str, Any]:
        return self._post(
            "/api/v2/datasets",
            body={"name": name, "parentFolderRid": parent_folder_rid},
        )

    def upload_rows(
        self,
        dataset_rid: str,
        branch: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Upload NDJSON rows to a dataset branch via the batch upload API."""
        ndjson = "\n".join(json.dumps(r, default=str) for r in rows)
        url = f"{self.auth.base_url}/api/v2/datasets/{dataset_rid}/branches/{branch}/rows"
        headers = {
            "Authorization": f"Bearer {self.auth.bearer_token()}",
            "Content-Type": "application/x-ndjson",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=ndjson.encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {"rows_uploaded": len(rows)}
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode()[:2000]
            except Exception:
                pass
            raise FoundryAPIError(
                f"Row upload to {dataset_rid}/{branch} → {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc

    # -- ontology operations --------------------------------------------------

    def list_object_types(self) -> dict[str, Any]:
        return self._get("/api/v2/ontologies/ontology/objectTypes")

    def load_objects(
        self,
        object_type: str,
        *,
        page_size: int = 100,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"pageSize": str(page_size)}
        if page_token:
            params["pageToken"] = page_token
        return self._get(f"/api/v2/ontologies/ontology/objects/{object_type}", params=params)

    def upsert_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        primary_key: str = "id",
    ) -> dict[str, Any]:
        """Bulk-upsert ontology objects via the apply-action batch endpoint."""
        return self._post(
            "/api/v2/ontologies/ontology/actions/sapphire-upsert/apply",
            body={
                "parameters": {
                    "objectType": object_type,
                    "primaryKey": primary_key,
                    "objects": objects,
                },
            },
        )

    def search_objects(
        self,
        object_type: str,
        query: dict[str, Any],
        *,
        page_size: int = 100,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/v2/ontologies/ontology/objects/{object_type}/search",
            body={"query": query, "pageSize": page_size},
        )
