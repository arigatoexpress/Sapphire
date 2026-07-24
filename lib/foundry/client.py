"""Palantir Foundry SDK client for Sapphire.

Wraps Foundry REST APIs for dataset operations, ontology object sync, and
health checks.  Supports token-based and OAuth client-credentials auth.

Configuration resolution order:
  1. Environment variables (PALANTIR_FOUNDRY_*, FOUNDRY_*)
  2. Files in ``$SAPPHIRE_SECRETS_DIR`` (default ``~/.config/sapphire-secrets``):
     - ``foundry_url`` — Foundry stack URL
     - ``foundry_token`` — bearer token
     - ``foundry_client_id`` / ``foundry_client_secret`` — OAuth
     - ``foundry_ontology`` — ontology API name or RID
     - ``foundry_upsert_action`` — action API name
     - ``foundry_write_mode`` — ``action`` (default) or ``dataset``
     - ``foundry_dataset_map`` — JSON object mapping object type → dataset RID

Env variables:
  PALANTIR_FOUNDRY_URL / FOUNDRY_URL          — Foundry stack URL
  PALANTIR_FOUNDRY_TOKEN / FOUNDRY_TOKEN      — bearer token (simplest)
  PALANTIR_FOUNDRY_CLIENT_ID + _SECRET        — OAuth client-credentials
  PALANTIR_FOUNDRY_ONTOLOGY / FOUNDRY_ONTOLOGY
                                                — ontology API name (default: ontology)
  PALANTIR_FOUNDRY_UPSERT_ACTION / FOUNDRY_UPSERT_ACTION
                                                — apply-action API name (default: sapphire-upsert)
  PALANTIR_FOUNDRY_WRITE_MODE / FOUNDRY_WRITE_MODE
                                                — action or dataset (default: action)
  PALANTIR_FOUNDRY_DATASET_MAP / FOUNDRY_DATASET_MAP
                                                — JSON mapping for dataset mode
"""

from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("foundry.client")

# Bearer tokens travel in Authorization headers — MITM-ing these calls leaks
# credentials. Prefer certifi's CA bundle (system Python can lag, and local
# cert-intercepting tools inject self-signed roots into the macOS keychain that
# default_context picks up). Fall back to the system store if certifi is absent;
# never disable verification.
_SSL_CTX = ssl.create_default_context()
try:
    import certifi

    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_URL_ENVS = ("PALANTIR_FOUNDRY_URL", "FOUNDRY_URL")
_TOKEN_ENVS = ("PALANTIR_FOUNDRY_TOKEN", "FOUNDRY_TOKEN", "FOUNDRY_API_TOKEN")
_CLIENT_ID_ENVS = ("PALANTIR_FOUNDRY_CLIENT_ID", "FOUNDRY_CLIENT_ID")
_CLIENT_SECRET_ENVS = ("PALANTIR_FOUNDRY_CLIENT_SECRET", "FOUNDRY_CLIENT_SECRET")
_ONTOLOGY_ENVS = ("PALANTIR_FOUNDRY_ONTOLOGY", "FOUNDRY_ONTOLOGY")
_UPSERT_ACTION_ENVS = ("PALANTIR_FOUNDRY_UPSERT_ACTION", "FOUNDRY_UPSERT_ACTION")
_WRITE_MODE_ENVS = ("PALANTIR_FOUNDRY_WRITE_MODE", "FOUNDRY_WRITE_MODE")
_DATASET_MAP_ENVS = ("PALANTIR_FOUNDRY_DATASET_MAP", "FOUNDRY_DATASET_MAP")
_DEFAULT_ONTOLOGY = "ontology"
_DEFAULT_UPSERT_ACTION = "sapphire-upsert"
_DEFAULT_WRITE_MODE = "action"
_VALID_WRITE_MODES = {"action", "dataset"}

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
            return path.read_text(encoding="utf-8").strip() or None
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
    return _first_env(*_CLIENT_SECRET_ENVS) or _read_secret_file("foundry_client_secret")


def _resolve_ontology_api_name() -> str:
    return _first_env(*_ONTOLOGY_ENVS) or _read_secret_file("foundry_ontology") or _DEFAULT_ONTOLOGY


def _resolve_upsert_action_api_name() -> str:
    return (
        _first_env(*_UPSERT_ACTION_ENVS)
        or _read_secret_file("foundry_upsert_action")
        or _DEFAULT_UPSERT_ACTION
    )


def _resolve_write_mode() -> str:
    mode = (
        (
            _first_env(*_WRITE_MODE_ENVS)
            or _read_secret_file("foundry_write_mode")
            or _DEFAULT_WRITE_MODE
        )
        .strip()
        .lower()
    )
    if mode not in _VALID_WRITE_MODES:
        known = ", ".join(sorted(_VALID_WRITE_MODES))
        raise FoundryConfigError(f"Invalid Foundry write mode {mode!r}; expected one of: {known}.")
    return mode


def _resolve_dataset_map() -> dict[str, str]:
    raw = _first_env(*_DATASET_MAP_ENVS) or _read_secret_file("foundry_dataset_map")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FoundryConfigError("Foundry dataset map must be valid JSON.") from exc
    if not isinstance(parsed, dict):
        raise FoundryConfigError("Foundry dataset map must be a JSON object.")

    dataset_map: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str) or not key or not value:
            raise FoundryConfigError(
                "Foundry dataset map entries must be non-empty string keys and values."
            )
        dataset_map[key] = value
    return dataset_map


def _quote_path_segment(value: str) -> str:
    return urllib.parse.quote(value.strip("/"), safe="")


def _quote_file_path(value: str) -> str:
    # Foundry's filePath route parameter is a single path segment. Some stacks
    # accept literal slashes, but Kadima routes nested paths only when "/" is
    # encoded as "%2F".
    return urllib.parse.quote(value.strip("/"), safe="._-")


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
    def from_env(cls) -> FoundryAuth:
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
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id or "",
                "client_secret": self.client_secret or "",
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
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

    def __init__(
        self,
        auth: FoundryAuth,
        *,
        timeout: int = 30,
        ontology: str | None = None,
        upsert_action: str | None = None,
        write_mode: str | None = None,
        dataset_map: dict[str, str] | None = None,
    ):
        self.auth = auth
        self.timeout = timeout
        self.ontology = (ontology or _resolve_ontology_api_name()).strip()
        self.upsert_action = (upsert_action or _resolve_upsert_action_api_name()).strip()
        self.write_mode = write_mode.strip().lower() if write_mode else _resolve_write_mode()
        if self.write_mode not in _VALID_WRITE_MODES:
            known = ", ".join(sorted(_VALID_WRITE_MODES))
            raise FoundryConfigError(
                f"Invalid Foundry write mode {self.write_mode!r}; expected one of: {known}."
            )
        self.dataset_map = dict(dataset_map) if dataset_map is not None else _resolve_dataset_map()

    @classmethod
    def from_env(cls, **kwargs: Any) -> FoundryClient:
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
            with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL_CTX) as resp:
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
            ontologies = self.list_ontologies()
            return {
                "ok": True,
                "auth_mode": self.auth.auth_mode,
                "ontologies_accessible": True,
                "ontology_count": len(ontologies.get("data") or []),
                "configured_ontology": self.ontology,
                "configured_upsert_action": self.upsert_action,
                "configured_write_mode": self.write_mode,
                "configured_dataset_types": sorted(self.dataset_map),
            }
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
            with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL_CTX) as resp:
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

    def upload_dataset_file(
        self,
        dataset_rid: str,
        file_path: str,
        content: bytes | str,
        *,
        branch: str = "master",
        transaction_type: str = "UPDATE",
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload a file to a Foundry dataset branch.

        The Kadima stack exposes dataset writes through the file upload
        endpoint, while the older row endpoint can 404.  The caller owns the
        file format; Sapphire uses newline-delimited JSON so each sync replaces
        one object-type snapshot file.
        """
        data = content.encode() if isinstance(content, str) else content
        dataset = _quote_path_segment(dataset_rid)
        path = _quote_file_path(file_path)
        url = f"{self.auth.base_url}/api/v2/datasets/{dataset}/files/{path}/upload"
        params = {
            "branchName": branch,
            "transactionType": transaction_type,
        }
        url += "?" + urllib.parse.urlencode(params)
        headers = {
            "Authorization": f"Bearer {self.auth.bearer_token()}",
            "Content-Type": content_type,
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=_SSL_CTX) as resp:
                raw = resp.read()
                return (
                    json.loads(raw)
                    if raw
                    else {
                        "bytes_uploaded": len(data),
                        "dataset_rid": dataset_rid,
                        "path": file_path,
                    }
                )
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode()[:2000]
            except Exception:
                pass
            raise FoundryAPIError(
                f"Dataset file upload to {dataset_rid}/{file_path} → {exc.code}",
                status=exc.code,
                body=err_body,
            ) from exc

    def upload_dataset_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        branch: str = "master",
    ) -> dict[str, Any]:
        """Write an object-type snapshot to its configured Foundry dataset."""
        dataset_rid = self.dataset_map.get(object_type)
        if not dataset_rid:
            raise FoundryConfigError(
                f"No Foundry dataset RID configured for object type {object_type!r}. "
                f"Set PALANTIR_FOUNDRY_DATASET_MAP or {_secrets_dir() / 'foundry_dataset_map'}."
            )
        ndjson = "".join(f"{json.dumps(obj, default=str)}\n" for obj in objects)
        path = f"sapphire_sync/{object_type}.jsonl"
        result = self.upload_dataset_file(dataset_rid, path, ndjson, branch=branch)
        result.setdefault("objects_uploaded", len(objects))
        result.setdefault("object_type", object_type)
        return result

    # -- ontology operations --------------------------------------------------

    def list_ontologies(self) -> dict[str, Any]:
        return self._get("/api/v2/ontologies")

    def list_object_types(self) -> dict[str, Any]:
        ontology = _quote_path_segment(self.ontology)
        return self._get(f"/api/v2/ontologies/{ontology}/objectTypes")

    def list_action_types(self) -> dict[str, Any]:
        ontology = _quote_path_segment(self.ontology)
        return self._get(f"/api/v2/ontologies/{ontology}/actionTypes")

    def list_actions(self) -> dict[str, Any]:
        return self.list_action_types()

    def _validate_ontology_exists(self) -> None:
        ontology_items = self.list_ontologies().get("data") or []
        ontology_names = {
            value
            for item in ontology_items
            if isinstance(item, dict)
            for value in (item.get("apiName"), item.get("rid"))
            if value
        }
        if self.ontology not in ontology_names:
            known = ", ".join(sorted(str(name) for name in ontology_names)[:5]) or "none"
            raise FoundryConfigError(
                f"Configured Foundry ontology {self.ontology!r} was not found. "
                f"Set PALANTIR_FOUNDRY_ONTOLOGY or {_secrets_dir() / 'foundry_ontology'} "
                f"to one of the deployed ontology API names/RIDs. Visible: {known}."
            )

    def validate_upsert_target(self) -> None:
        """Fail fast if the configured ontology/action cannot be found."""
        self._validate_ontology_exists()

        action_items = self.list_action_types().get("data") or []
        action_names = {
            value
            for item in action_items
            if isinstance(item, dict)
            for value in (item.get("apiName"), item.get("rid"))
            if value
        }
        if self.upsert_action not in action_names:
            known = ", ".join(sorted(str(name) for name in action_names)[:8]) or "none"
            raise FoundryConfigError(
                f"Configured Foundry upsert action {self.upsert_action!r} was not found "
                f"in ontology {self.ontology!r}. Set PALANTIR_FOUNDRY_UPSERT_ACTION "
                f"or {_secrets_dir() / 'foundry_upsert_action'} after the Sapphire action "
                f"is deployed. Visible actions: {known}."
            )

    def validate_dataset_target(
        self, object_types: list[str] | tuple[str, ...] | None = None
    ) -> None:
        """Fail fast if dataset-mode writes are missing required resources."""
        self._validate_ontology_exists()
        required = list(object_types or [])
        missing_datasets = [name for name in required if name not in self.dataset_map]
        if missing_datasets:
            raise FoundryConfigError(
                "Foundry dataset map is missing object type(s): "
                + ", ".join(sorted(missing_datasets))
                + f". Set PALANTIR_FOUNDRY_DATASET_MAP or {_secrets_dir() / 'foundry_dataset_map'}."
            )

        object_items = self.list_object_types().get("data") or []
        object_names = {
            value
            for item in object_items
            if isinstance(item, dict)
            for value in (item.get("apiName"), item.get("rid"))
            if value
        }
        missing_object_types = [name for name in required if name not in object_names]
        if missing_object_types:
            known = ", ".join(sorted(str(name) for name in object_names)[:8]) or "none"
            raise FoundryConfigError(
                "Configured Foundry object type(s) were not found: "
                + ", ".join(sorted(missing_object_types))
                + f". Visible object types: {known}."
            )

        for object_type in required:
            dataset_rid = self.dataset_map[object_type]
            try:
                self.get_dataset(dataset_rid)
            except FoundryAPIError as exc:
                if exc.status == 404:
                    raise FoundryConfigError(
                        f"Configured Foundry dataset for {object_type!r} was not found."
                    ) from exc
                raise

    def validate_write_target(
        self, object_types: list[str] | tuple[str, ...] | None = None
    ) -> None:
        """Validate the configured Foundry write target for the active mode."""
        if self.write_mode == "dataset":
            self.validate_dataset_target(object_types)
        else:
            self.validate_upsert_target()

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
        ontology = _quote_path_segment(self.ontology)
        obj = _quote_path_segment(object_type)
        return self._get(f"/api/v2/ontologies/{ontology}/objects/{obj}", params=params)

    def upsert_objects(
        self,
        object_type: str,
        objects: list[dict[str, Any]],
        *,
        primary_key: str = "id",
    ) -> dict[str, Any]:
        """Bulk-upsert ontology objects via the apply-action batch endpoint."""
        ontology = _quote_path_segment(self.ontology)
        action = _quote_path_segment(self.upsert_action)
        return self._post(
            f"/api/v2/ontologies/{ontology}/actions/{action}/apply",
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
        ontology = _quote_path_segment(self.ontology)
        obj = _quote_path_segment(object_type)
        return self._post(
            f"/api/v2/ontologies/{ontology}/objects/{obj}/search",
            body={"query": query, "pageSize": page_size},
        )
