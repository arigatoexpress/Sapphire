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

from .decorator import requires_admin
from .routes import build_blueprint, register_blueprint
from .session import SessionManager
from .store import (
    CredentialRecord,
    CredentialStore,
    FirestoreCredentialStore,
    InMemoryCredentialStore,
)

__all__ = [
    "CredentialRecord",
    "CredentialStore",
    "FirestoreCredentialStore",
    "InMemoryCredentialStore",
    "SessionManager",
    "build_blueprint",
    "register_blueprint",
    "requires_admin",
]
