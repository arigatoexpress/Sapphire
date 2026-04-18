"""Base classes shared by every platform client.

A ``PublisherClient`` has one job: take a rendered post (markdown or a
list of tweets) and push it to a platform, returning a ``PublishResult``.
All clients honour three invariants:

1. **Env-driven auth** — no keys on disk, no keys in code.
2. **Dry-run by default** — a missing ``SAPPHIRE_PUBLISH_LIVE=1`` flag
   turns every client into a no-op that returns the request it *would*
   have sent. This is how ``auto_publish`` keeps itself from firing
   during local dev or a crashed credential store.
3. **Never raise** — network / auth errors become ``PublishResult(ok=False)``
   so the orchestrator can batch-publish without a single failure
   taking down the run.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Outcome of a single platform publish attempt."""

    platform: str
    ok: bool
    dry_run: bool
    url: str | None = None
    remote_id: str | None = None
    error: str | None = None
    request_preview: dict[str, Any] = field(default_factory=dict)
    response_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class PublisherClient:
    """Base publisher.

    Subclasses override :meth:`_publish` and set :attr:`platform`.
    """

    platform: str = "unknown"
    # Env var name that holds the primary credential (API key / token).
    # Checked by :meth:`configured` and used for friendly error messages.
    credential_env: str = ""

    def __init__(self, dry_run: bool | None = None, timeout: int = 20) -> None:
        if dry_run is None:
            dry_run = os.getenv("SAPPHIRE_PUBLISH_LIVE", "").lower() not in {"1", "true", "yes"}
        self.dry_run = dry_run
        self.timeout = timeout

    # --- public API -------------------------------------------------------

    def configured(self) -> bool:
        """Whether the client has credentials to make a live request."""
        return bool(self.credential_env and os.getenv(self.credential_env))

    def publish(self, **kwargs: Any) -> PublishResult:
        """Dispatch to the platform implementation, trapping any exception.

        Subclasses document their own kwargs.
        """
        if not self.dry_run and not self.configured():
            return PublishResult(
                platform=self.platform,
                ok=False,
                dry_run=False,
                error=f"missing credential env var: {self.credential_env}",
                request_preview=self._preview(**kwargs),
            )

        if self.dry_run:
            return PublishResult(
                platform=self.platform,
                ok=True,
                dry_run=True,
                url=None,
                remote_id="dry-run",
                request_preview=self._preview(**kwargs),
                response_meta={"note": "SAPPHIRE_PUBLISH_LIVE!=1 — payload validated, not sent"},
            )

        try:
            return self._publish(**kwargs)
        except Exception as exc:  # never raise to caller
            logger.exception("[%s] publish failed", self.platform)
            return PublishResult(
                platform=self.platform,
                ok=False,
                dry_run=False,
                error=f"{type(exc).__name__}: {exc}",
                request_preview=self._preview(**kwargs),
            )

    # --- hooks for subclasses --------------------------------------------

    def _publish(self, **kwargs: Any) -> PublishResult:  # pragma: no cover — abstract
        raise NotImplementedError

    def _preview(self, **kwargs: Any) -> dict[str, Any]:
        """A JSON-safe snapshot of the request the client would send."""
        out: dict[str, Any] = {}
        for k, v in kwargs.items():
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                out[k] = v
            else:
                out[k] = repr(v)
        return out

    # --- shared HTTP helper ----------------------------------------------

    def _http_json(
        self,
        url: str,
        *,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Minimal JSON HTTP client — stdlib only.

        Returns ``(status, body_dict)``. On non-JSON bodies, returns
        ``{"raw": "<text>"}``.
        """
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        hdrs = {"User-Agent": "sapphire-publisher/1.0", "Accept": "application/json"}
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    return resp.status, {"raw": raw}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            try:
                return e.code, json.loads(raw) if raw else {"error": str(e)}
            except json.JSONDecodeError:
                return e.code, {"raw": raw}


# Registry so auto_publish can look up a client by platform name.
_REGISTRY: dict[str, type[PublisherClient]] = {}


def _register(cls: type[PublisherClient]) -> type[PublisherClient]:
    _REGISTRY[cls.platform] = cls
    return cls


def load_client(platform: str, *, dry_run: bool | None = None) -> PublisherClient | None:
    """Return an instantiated client for ``platform`` or ``None``.

    ``typefully`` is treated as a fallback for ``x``: if ``x`` is requested
    but has no credentials, callers can fall through to ``typefully``.
    """
    cls = _REGISTRY.get(platform)
    if cls is None:
        return None
    return cls(dry_run=dry_run)
