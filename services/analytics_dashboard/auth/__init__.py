"""WebAuthn passkey authentication for the Sapphire analytics dashboard.

Public surface:
    register_blueprint(app, *, credential_store=None)
        Register the /api/admin/* + /admin/* routes on a Flask app.
    requires_admin
        Decorator gating any view behind a valid admin session cookie.
    SessionManager
        Sign / verify the session cookie. Exposed for tests.
    CredentialStore (abstract), FirestoreCredentialStore, InMemoryCredentialStore
        Pluggable persistence. Production uses Firestore (collection
        ``admin_credentials`` in project ``tho-ai-agent``); tests use the
        in-memory variant.

The module is deliberately self-contained — `services/analytics_dashboard/app.py`
calls one helper (`register_blueprint`) and everything else lives here.
"""

from __future__ import annotations

from .decorator import (
    admin_required_response,
    admin_session_payload,
    has_admin_session,
    requires_admin,
)
from .session import SessionManager
from .store import (
    CredentialRecord,
    CredentialStore,
    FirestoreCredentialStore,
    InMemoryCredentialStore,
)

try:
    from .routes import build_blueprint, register_blueprint
except Exception as _routes_exc:  # noqa: BLE001
    _ROUTES_IMPORT_ERROR = _routes_exc

    def build_blueprint(*args, _exc=_ROUTES_IMPORT_ERROR, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"admin auth routes unavailable: {_exc}") from _exc

    def register_blueprint(*args, _exc=_ROUTES_IMPORT_ERROR, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError(f"admin auth routes unavailable: {_exc}") from _exc


__all__ = [
    "CredentialRecord",
    "CredentialStore",
    "FirestoreCredentialStore",
    "InMemoryCredentialStore",
    "SessionManager",
    "admin_required_response",
    "admin_session_payload",
    "build_blueprint",
    "has_admin_session",
    "register_blueprint",
    "requires_admin",
]
