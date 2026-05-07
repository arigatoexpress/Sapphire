"""@requires_admin decorator gating views behind a valid session cookie.

Looks up the active SessionManager attached to the current Flask app
(``current_app.extensions['sapphire_admin_session']``) and validates the
session cookie. On failure:
    - JSON / XHR requests get 401 + {"error": "unauthorized"}.
    - Browser navigations get a 302 redirect to /admin/login.

We deliberately fail fast (no DB call, no slow-paths) so the endpoint is
safe to expose under any rate-limit-friendly scenario.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps

from flask import current_app, g, jsonify, redirect, request

from .session import SESSION_COOKIE_NAME


def _wants_json() -> bool:
    """Distinguish XHR / fetch from real browser navigations."""
    accept = request.headers.get("Accept", "")
    if "application/json" in accept:
        return True
    if request.path.startswith("/api/"):
        return True
    requested = request.headers.get("X-Requested-With", "").lower()
    return requested == "xmlhttprequest"


def admin_session_payload() -> dict | None:
    """Return the verified admin session payload for the current request."""
    sm = current_app.extensions.get("sapphire_admin_session")
    if sm is None:
        return None
    return sm.verify_session(request.cookies.get(SESSION_COOKIE_NAME))


def has_admin_session() -> bool:
    """Return true when the request has a valid admin session cookie."""
    return admin_session_payload() is not None


def admin_required_response():
    """Return the standard response for a missing admin session."""
    if _wants_json():
        return jsonify({"error": "unauthorized"}), 401
    return redirect("/admin/login")


def requires_admin(view_func: Callable):
    """Block access unless a valid admin session cookie is present."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        sm = current_app.extensions.get("sapphire_admin_session")
        if sm is None:
            # Misconfiguration — bail with a clean 503 instead of crashing.
            return jsonify({"error": "admin_auth_not_configured"}), 503
        payload = sm.verify_session(request.cookies.get(SESSION_COOKIE_NAME))
        if not payload:
            return admin_required_response()
        g.admin_user = payload.get("user_id", "admin")
        g.admin_session = payload
        return view_func(*args, **kwargs)

    return wrapped
