"""WebAuthn registration + assertion endpoints + admin pages.

Endpoints (mounted on the main Flask app via ``register_blueprint``):

    POST /api/admin/register/begin     → registration options + signed handle
    POST /api/admin/register/complete  → verify attestation, store credential
    POST /api/admin/login/begin        → assertion options + signed handle
    POST /api/admin/login/complete     → verify assertion, mint session cookie
    POST /api/admin/logout             → clear session cookie
    GET  /api/admin/whoami             → JSON identity probe (gated)

    GET  /admin/login                  → login + register UI
    GET  /admin                        → admin landing (gated)

Design notes
------------
- Challenges are one-shot 32-byte nonces signed via SessionManager
  (``challenge_ttl`` = 5 min). They are returned to the client through the
  ``handle`` field — clients pass them straight back to /complete. The raw
  challenge bytes never leave the server unsigned.
- Errors return JSON, not HTML, and never 500 on user-controlled input.
  Generic ``invalid_request``/``unauthorized`` codes avoid leaking which
  step failed (rate-limit-friendly, no probe oracle).
- ``user_id`` is always literal ``"admin"`` — single-user setup.
- Origin is computed from ``rp_id`` at request time (https://<rp_id> in
  prod, http://localhost:<port> in dev). It can be overridden via the
  ``ADMIN_EXPECTED_ORIGIN`` env var if you front the service behind a
  non-standard hostname.
"""

from __future__ import annotations

import json
import logging
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Iterable
from datetime import UTC, datetime

from flask import (
    Blueprint,
    Flask,
    g,
    jsonify,
    make_response,
    render_template,
    request,
)
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .decorator import requires_admin
from .session import SESSION_COOKIE_NAME, SessionManager
from .store import CredentialRecord, CredentialStore, default_store

log = logging.getLogger("sapphire.admin_auth")

ADMIN_USER_ID = "admin"
RP_NAME_DEFAULT = "Sapphire Alpha Admin"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return urlsafe_b64decode(s + padding)


def _b64url_encode(b: bytes) -> str:
    return urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _expected_origin(rp_id: str) -> str:
    """Resolve the expected origin for WebAuthn verification.

    Order of precedence:
        1. ``ADMIN_EXPECTED_ORIGIN`` env var (single value or comma-list).
        2. ``http://localhost:<PORT>`` when rp_id == "localhost".
        3. ``https://<rp_id>`` otherwise.
    """
    override = os.environ.get("ADMIN_EXPECTED_ORIGIN")
    if override:
        # Comma-separated list works because verify_*_response accepts
        # Union[str, List[str]] for expected_origin.
        parts = [p.strip() for p in override.split(",") if p.strip()]
        return parts[0] if len(parts) == 1 else parts  # type: ignore[return-value]
    if rp_id == "localhost":
        port = os.environ.get("PORT", "8080")
        return f"http://localhost:{port}"
    return f"https://{rp_id}"


def _allow_descriptors(records: Iterable[CredentialRecord]) -> list[PublicKeyCredentialDescriptor]:
    return [PublicKeyCredentialDescriptor(id=r.credential_id) for r in records]


def _err(code: str, status: int = 400, **extra):
    payload = {"error": code, **extra}
    return jsonify(payload), status


# ---------------------------------------------------------------------------
# Flask wiring
# ---------------------------------------------------------------------------


def build_blueprint(
    *,
    rp_id: str | None = None,
    rp_name: str | None = None,
    credential_store: CredentialStore | None = None,
    session_manager: SessionManager | None = None,
    cookie_secure: bool | None = None,
) -> tuple[Blueprint, dict]:
    """Build a Flask blueprint plus a context dict the caller can stash on the
    app. The context is exposed so tests can flip the credential store or
    session manager mid-test.
    """
    rp_id = rp_id or os.environ.get("RP_ID", "localhost")
    rp_name = rp_name or os.environ.get("RP_NAME", RP_NAME_DEFAULT)
    credential_store = credential_store or default_store(
        os.environ.get("GCP_PROJECT", "sapphire-479610")
    )
    session_manager = session_manager or SessionManager()
    if cookie_secure is None:
        cookie_secure = rp_id != "localhost"

    bp = Blueprint("sapphire_admin", __name__, template_folder="../templates")

    ctx = {
        "rp_id": rp_id,
        "rp_name": rp_name,
        "credential_store": credential_store,
        "session_manager": session_manager,
        "cookie_secure": cookie_secure,
    }

    # ---- WebAuthn: registration ----

    @bp.post("/api/admin/register/begin")
    def register_begin():
        # Single-user lockout: refuse to register a second credential unless
        # the caller is already authenticated. This prevents an attacker from
        # registering their own passkey before Ari does.
        existing = ctx["credential_store"].list_for_user(ADMIN_USER_ID)
        if existing:
            token = request.cookies.get(SESSION_COOKIE_NAME)
            if not ctx["session_manager"].verify_session(token):
                log.info("register_begin denied: credentials exist + no session")
                return _err("registration_locked", status=403)

        challenge = SessionManager.new_challenge_bytes()
        try:
            options = generate_registration_options(
                rp_id=ctx["rp_id"],
                rp_name=ctx["rp_name"],
                user_id=ADMIN_USER_ID.encode("utf-8"),
                user_name=ADMIN_USER_ID,
                user_display_name="Sapphire Admin",
                challenge=challenge,
                exclude_credentials=_allow_descriptors(existing),
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.PREFERRED,
                    user_verification=UserVerificationRequirement.PREFERRED,
                ),
            )
        except Exception as exc:  # noqa: BLE001 — defensive, log + clean error
            log.exception("register_begin failed: %s", exc)
            return _err("internal_error", status=500)

        handle = ctx["session_manager"].wrap_challenge(challenge, flow="register")
        return jsonify(
            {
                "options": json.loads(options_to_json(options)),
                "handle": handle,
            }
        )

    @bp.post("/api/admin/register/complete")
    def register_complete():
        body = request.get_json(silent=True) or {}
        handle = body.get("handle")
        credential = body.get("credential")
        if not isinstance(handle, str) or not isinstance(credential, dict):
            return _err("invalid_request")

        challenge = ctx["session_manager"].unwrap_challenge(handle, flow="register")
        if challenge is None:
            return _err("challenge_expired", status=400)

        try:
            verified = verify_registration_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=ctx["rp_id"],
                expected_origin=_expected_origin(ctx["rp_id"]),
                require_user_verification=False,
            )
        except InvalidRegistrationResponse as exc:
            log.info("register_complete rejected: %s", exc)
            return _err("invalid_attestation", status=400)
        except Exception as exc:  # noqa: BLE001
            log.exception("register_complete error: %s", exc)
            return _err("internal_error", status=500)

        record = CredentialRecord(
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            user_id=ADMIN_USER_ID,
            aaguid=str(getattr(verified, "aaguid", "") or ""),
        )
        ctx["credential_store"].add(record)
        log.info("registered passkey aaguid=%s", record.aaguid or "?")

        # First registration auto-logs-in; subsequent re-registrations
        # (already authenticated) get a fresh session too.
        token = ctx["session_manager"].issue_session(ADMIN_USER_ID)
        resp = make_response(
            jsonify(
                {
                    "ok": True,
                    "credential_id": record.credential_id_b64,
                    "aaguid": record.aaguid,
                }
            )
        )
        resp.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            max_age=ctx["session_manager"].session_ttl,
            httponly=True,
            secure=ctx["cookie_secure"],
            samesite="Lax",
            path="/",
        )
        return resp

    # ---- WebAuthn: login ----

    @bp.post("/api/admin/login/begin")
    def login_begin():
        records = ctx["credential_store"].list_for_user(ADMIN_USER_ID)
        if not records:
            return _err("no_credentials_registered", status=404)
        challenge = SessionManager.new_challenge_bytes()
        try:
            options = generate_authentication_options(
                rp_id=ctx["rp_id"],
                challenge=challenge,
                allow_credentials=_allow_descriptors(records),
                user_verification=UserVerificationRequirement.PREFERRED,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("login_begin failed: %s", exc)
            return _err("internal_error", status=500)

        handle = ctx["session_manager"].wrap_challenge(challenge, flow="login")
        return jsonify(
            {
                "options": json.loads(options_to_json(options)),
                "handle": handle,
            }
        )

    @bp.post("/api/admin/login/complete")
    def login_complete():
        body = request.get_json(silent=True) or {}
        handle = body.get("handle")
        credential = body.get("credential")
        if not isinstance(handle, str) or not isinstance(credential, dict):
            return _err("invalid_request")

        challenge = ctx["session_manager"].unwrap_challenge(handle, flow="login")
        if challenge is None:
            return _err("challenge_expired", status=400)

        # Look up the credential the client claims to be using.
        raw_id = credential.get("rawId") or credential.get("id")
        if not isinstance(raw_id, str):
            return _err("invalid_request")
        try:
            cred_id_bytes = _b64url_decode(raw_id)
        except Exception:
            return _err("invalid_request")
        record = ctx["credential_store"].get(cred_id_bytes)
        if record is None:
            log.info("login_complete: unknown credential")
            return _err("unauthorized", status=401)

        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=ctx["rp_id"],
                expected_origin=_expected_origin(ctx["rp_id"]),
                credential_public_key=record.public_key,
                credential_current_sign_count=record.sign_count,
                require_user_verification=False,
            )
        except InvalidAuthenticationResponse as exc:
            log.info("login_complete rejected: %s", exc)
            return _err("unauthorized", status=401)
        except Exception as exc:  # noqa: BLE001
            log.exception("login_complete error: %s", exc)
            return _err("internal_error", status=500)

        ctx["credential_store"].update_usage(
            record.credential_id, sign_count=verified.new_sign_count
        )
        token = ctx["session_manager"].issue_session(ADMIN_USER_ID)
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie(
            SESSION_COOKIE_NAME,
            token,
            max_age=ctx["session_manager"].session_ttl,
            httponly=True,
            secure=ctx["cookie_secure"],
            samesite="Lax",
            path="/",
        )
        return resp

    @bp.post("/api/admin/logout")
    def logout():
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie(
            SESSION_COOKIE_NAME,
            "",
            max_age=0,
            httponly=True,
            secure=ctx["cookie_secure"],
            samesite="Lax",
            path="/",
        )
        return resp

    @bp.get("/api/admin/whoami")
    @requires_admin
    def whoami():
        return jsonify({"user_id": g.admin_user, "issued_at": datetime.now(UTC).isoformat()})

    @bp.get("/api/admin/status")
    def status():
        """Public status: tells the login UI whether to show 'register' or
        'sign in'. Detailed auth metadata is only returned to an active admin
        session so the public login screen cannot enumerate the boundary.
        """
        try:
            count = ctx["credential_store"].count()
        except Exception as exc:  # noqa: BLE001
            log.info("admin_status count failed: %s", exc)
            count = 0
        registered = count > 0
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        try:
            is_admin = bool(ctx["session_manager"].verify_session(session_token))
        except Exception as exc:  # noqa: BLE001
            log.info("admin_status session check failed: %s", exc)
            is_admin = False
        if not is_admin:
            return jsonify({"mode": "public_admin_status", "registered": registered})
        return jsonify(
            {
                "mode": "admin_admin_status",
                "rp_id": ctx["rp_id"],
                "registered": registered,
                "credentials": count,
            }
        )

    # ---- HTML pages ----

    @bp.get("/admin/login")
    def admin_login_page():
        return render_template("admin_login.html", rp_id=ctx["rp_id"])

    @bp.get("/admin")
    @requires_admin
    def admin_landing_page():
        return render_template("admin.html", user_id=g.admin_user, rp_id=ctx["rp_id"])

    return bp, ctx


def register_blueprint(app: Flask, **kwargs) -> dict:
    """Build the admin blueprint and register it on ``app``. Returns the
    context dict so callers can introspect rp_id, swap stores in tests, etc.
    """
    bp, ctx = build_blueprint(**kwargs)
    app.register_blueprint(bp)
    app.extensions = getattr(app, "extensions", {})
    app.extensions["sapphire_admin_session"] = ctx["session_manager"]
    app.extensions["sapphire_admin_ctx"] = ctx
    return ctx
