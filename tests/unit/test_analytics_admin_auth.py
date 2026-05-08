"""Tests for services/analytics_dashboard/auth — WebAuthn passkey scaffold.

Covers:
    * SessionManager   issue/verify, ttl, challenge wrap/unwrap, flow tag
    * InMemoryCredentialStore CRUD
    * @requires_admin  (401 JSON, 302 HTML, 503 missing config, allow valid)
    * /api/admin/status
    * /api/admin/register/begin       (challenge handle round-trip)
    * /api/admin/register/complete    (mocked verify → credential persisted +
                                       session cookie minted)
    * /api/admin/login/begin/complete (mocked verify → cookie + sign_count++)
    * Single-user lockout: register_begin blocked once a credential exists
    * /api/admin/logout

We mock ``webauthn.verify_registration_response`` and
``verify_authentication_response`` so no real CTAP attestation is needed —
the spec contract under test is the routing + persistence + cookie wiring,
not the cryptographic verification (that's the upstream library's job).
"""

from __future__ import annotations

import importlib.util
import sys
import types
from base64 import urlsafe_b64encode
from pathlib import Path

import pytest

# The whole suite needs the optional `webauthn` + `itsdangerous` packages.
# When CI is missing them (e.g. early pip-cache misses, partial installs),
# skip cleanly rather than corrupting sys.modules with a half-loaded
# _sapphire_test_auth_pkg that breaks every subsequent test.
pytest.importorskip("webauthn")
pytest.importorskip("itsdangerous")

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTH_DIR = REPO_ROOT / "services" / "analytics_dashboard" / "auth"
TEMPLATE_DIR = REPO_ROOT / "services" / "analytics_dashboard" / "templates"


# ---------------------------------------------------------------------------
# module loader — load services/analytics_dashboard/auth/* under a unique name
# so we don't collide with the production package import path.
# ---------------------------------------------------------------------------


def _load_pkg():
    pkg_name = "_sapphire_test_auth_pkg"
    if pkg_name in sys.modules:
        return sys.modules[pkg_name]
    spec = importlib.util.spec_from_file_location(
        pkg_name,
        AUTH_DIR / "__init__.py",
        submodule_search_locations=[str(AUTH_DIR)],
    )
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[pkg_name] = pkg
    try:
        spec.loader.exec_module(pkg)
    except Exception:
        # Tear down the half-loaded package so a retry (or another test
        # importing it) doesn't see a corrupted module with missing
        # attributes. Without this, the first failure cascades into
        # AttributeError noise across the whole suite.
        sys.modules.pop(pkg_name, None)
        raise
    return pkg


@pytest.fixture
def auth_pkg():
    return _load_pkg()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _b64url(b: bytes) -> str:
    return urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _make_app(auth_pkg, store=None, session=None, rp_id="localhost"):
    """Build a fresh Flask app with the admin blueprint mounted."""
    from flask import Flask

    bp, ctx = auth_pkg.build_blueprint(
        rp_id=rp_id,
        rp_name="Sapphire Test",
        credential_store=store or auth_pkg.InMemoryCredentialStore(),
        session_manager=session or auth_pkg.SessionManager(secret_key="test-secret"),
        cookie_secure=False,
    )
    app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
    app.register_blueprint(bp)
    app.extensions = getattr(app, "extensions", {}) or {}
    app.extensions["sapphire_admin_session"] = ctx["session_manager"]
    app.extensions["sapphire_admin_ctx"] = ctx
    return app, ctx


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


def test_session_manager_round_trips_user_id(auth_pkg):
    sm = auth_pkg.SessionManager(secret_key="k")
    token = sm.issue_session("admin")
    payload = sm.verify_session(token)
    assert payload is not None
    assert payload["user_id"] == "admin"


def test_session_manager_rejects_bad_signature(auth_pkg):
    sm = auth_pkg.SessionManager(secret_key="k")
    sm2 = auth_pkg.SessionManager(secret_key="different")
    token = sm.issue_session("admin")
    assert sm2.verify_session(token) is None


def test_session_manager_rejects_expired_token(auth_pkg):
    # ttl=-1 means any cookie reads as expired
    sm = auth_pkg.SessionManager(secret_key="k", session_ttl=-1)
    token = sm.issue_session("admin")
    assert sm.verify_session(token) is None


def test_session_manager_rejects_empty_token(auth_pkg):
    sm = auth_pkg.SessionManager(secret_key="k")
    assert sm.verify_session(None) is None
    assert sm.verify_session("") is None


def test_challenge_wrap_unwrap_round_trip(auth_pkg):
    sm = auth_pkg.SessionManager(secret_key="k")
    raw = auth_pkg.SessionManager.new_challenge_bytes()
    handle = sm.wrap_challenge(raw, flow="register")
    assert sm.unwrap_challenge(handle, flow="register") == raw


def test_challenge_unwrap_rejects_wrong_flow_tag(auth_pkg):
    """A handle minted for register must not validate against login."""
    sm = auth_pkg.SessionManager(secret_key="k")
    raw = auth_pkg.SessionManager.new_challenge_bytes()
    handle = sm.wrap_challenge(raw, flow="register")
    assert sm.unwrap_challenge(handle, flow="login") is None


def test_challenge_bytes_are_32_bytes_random(auth_pkg):
    a = auth_pkg.SessionManager.new_challenge_bytes()
    b = auth_pkg.SessionManager.new_challenge_bytes()
    assert len(a) == 32
    assert a != b  # random


# ---------------------------------------------------------------------------
# InMemoryCredentialStore
# ---------------------------------------------------------------------------


def test_in_memory_store_add_and_get(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore()
    rec = auth_pkg.CredentialRecord(
        credential_id=b"c1",
        public_key=b"pk1",
        sign_count=0,
        user_id="admin",
        aaguid="a-1",
    )
    store.add(rec)
    assert store.get(b"c1") is rec
    assert store.count() == 1
    assert store.list_for_user("admin") == [rec]
    assert store.list_for_user("other") == []


def test_in_memory_store_update_usage_bumps_sign_count(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore()
    store.add(
        auth_pkg.CredentialRecord(
            credential_id=b"c1", public_key=b"pk", sign_count=0, user_id="admin"
        )
    )
    store.update_usage(b"c1", sign_count=5)
    rec = store.get(b"c1")
    assert rec.sign_count == 5
    assert rec.last_used_at is not None


def test_in_memory_store_missing_credential_returns_none(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore()
    assert store.get(b"nope") is None


# ---------------------------------------------------------------------------
# @requires_admin decorator
# ---------------------------------------------------------------------------


def test_requires_admin_returns_401_json_when_no_cookie(auth_pkg):
    app, _ = _make_app(auth_pkg)
    client = app.test_client()
    r = client.get("/api/admin/whoami")
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_requires_admin_returns_401_when_cookie_signature_bad(auth_pkg):
    app, _ = _make_app(auth_pkg)
    client = app.test_client()
    client.set_cookie("sapphire_admin", "tampered.value")
    r = client.get("/api/admin/whoami")
    assert r.status_code == 401


def test_requires_admin_redirects_browser_navigations(auth_pkg):
    app, _ = _make_app(auth_pkg)
    client = app.test_client()
    # /admin (HTML) without cookie should 302
    r = client.get("/admin", headers={"Accept": "text/html"})
    assert r.status_code in (301, 302)
    assert "/admin/login" in r.headers.get("Location", "")


def test_requires_admin_passes_with_valid_cookie(auth_pkg):
    app, ctx = _make_app(auth_pkg)
    token = ctx["session_manager"].issue_session("admin")
    client = app.test_client()
    client.set_cookie("sapphire_admin", token)
    r = client.get("/api/admin/whoami")
    assert r.status_code == 200
    body = r.get_json()
    assert body["user_id"] == "admin"
    assert "issued_at" in body


def test_requires_admin_503_when_session_extension_missing(auth_pkg):
    """If something has stripped the SessionManager off the app, decorator
    returns a clean 503 instead of crashing.
    """
    from flask import Flask, jsonify

    app = Flask(__name__)

    @app.get("/p")
    @auth_pkg.requires_admin
    def _protected():
        return jsonify({"ok": True})

    # No session extension at all → 503
    r = app.test_client().get("/p")
    assert r.status_code == 503
    assert r.get_json() == {"error": "admin_auth_not_configured"}


# ---------------------------------------------------------------------------
# /api/admin/status
# ---------------------------------------------------------------------------


def test_status_reports_unregistered_initially(auth_pkg):
    app, _ = _make_app(auth_pkg)
    r = app.test_client().get("/api/admin/status")
    assert r.status_code == 200
    body = r.get_json()
    assert body["mode"] == "public_admin_status"
    assert body["registered"] is False
    assert "credentials" not in body
    assert "rp_id" not in body


def test_status_reports_registered_after_credential_added(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"c1", public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, _ = _make_app(auth_pkg, store=store)
    body = app.test_client().get("/api/admin/status").get_json()
    assert body["mode"] == "public_admin_status"
    assert body["registered"] is True
    assert "credentials" not in body


def test_status_reports_admin_metadata_for_authenticated_admin(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"c1", public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    token = ctx["session_manager"].issue_session("admin")
    client = app.test_client()
    client.set_cookie("sapphire_admin", token)

    body = client.get("/api/admin/status").get_json()

    assert body["mode"] == "admin_admin_status"
    assert body["registered"] is True
    assert body["credentials"] == 1
    assert body["rp_id"] == "localhost"


# ---------------------------------------------------------------------------
# /api/admin/register/* (with patched webauthn verify)
# ---------------------------------------------------------------------------


def test_register_begin_returns_options_and_handle(auth_pkg, monkeypatch):
    app, ctx = _make_app(auth_pkg)
    r = app.test_client().post("/api/admin/register/begin")
    assert r.status_code == 200
    body = r.get_json()
    assert "options" in body
    assert "handle" in body
    # rp_id propagated to options
    assert body["options"]["rp"]["id"] == "localhost"
    # challenge in options is base64url string and decodes to 32 bytes
    chall = body["options"]["challenge"]
    assert isinstance(chall, str)
    # And the handle round-trips through SessionManager
    raw = ctx["session_manager"].unwrap_challenge(body["handle"], flow="register")
    assert raw is not None and len(raw) == 32


def test_register_begin_locked_when_existing_credential_and_no_session(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"c1", public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, _ = _make_app(auth_pkg, store=store)
    r = app.test_client().post("/api/admin/register/begin")
    assert r.status_code == 403
    assert r.get_json()["error"] == "registration_locked"


def test_register_begin_allowed_for_authenticated_admin_when_credential_exists(
    auth_pkg,
):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"c1", public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    token = ctx["session_manager"].issue_session("admin")
    client = app.test_client()
    client.set_cookie("sapphire_admin", token)
    r = client.post("/api/admin/register/begin")
    assert r.status_code == 200


def test_register_complete_persists_credential_and_sets_cookie(auth_pkg, monkeypatch):
    """End-to-end: client posts attestation, server verifies (mocked),
    credential is persisted, session cookie is set.
    """
    app, ctx = _make_app(auth_pkg)
    sm = ctx["session_manager"]
    store = ctx["credential_store"]

    # Forge a "valid" challenge handle the server has just issued.
    challenge = auth_pkg.SessionManager.new_challenge_bytes()
    handle = sm.wrap_challenge(challenge, flow="register")

    # Mock the upstream webauthn verify_registration_response.
    fake_credential_id = b"cred-abc123"
    fake_pub_key = b"public-key-bytes"

    def fake_verify(**kwargs):
        # Sanity: server passed our challenge and rp_id through.
        assert kwargs["expected_challenge"] == challenge
        assert kwargs["expected_rp_id"] == "localhost"
        return types.SimpleNamespace(
            credential_id=fake_credential_id,
            credential_public_key=fake_pub_key,
            sign_count=0,
            aaguid="00000000-0000-0000-0000-000000000001",
        )

    # Patch the symbol the routes module bound at import time.
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]
    monkeypatch.setattr(routes_mod, "verify_registration_response", fake_verify)

    r = app.test_client().post(
        "/api/admin/register/complete",
        json={
            "handle": handle,
            "credential": {
                "id": _b64url(fake_credential_id),
                "rawId": _b64url(fake_credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _b64url(b"{}"),
                    "attestationObject": _b64url(b"\x00"),
                },
                "clientExtensionResults": {},
            },
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["credential_id"] == _b64url(fake_credential_id)

    # Credential persisted
    rec = store.get(fake_credential_id)
    assert rec is not None
    assert rec.public_key == fake_pub_key
    assert rec.user_id == "admin"

    # Session cookie minted
    cookies = r.headers.getlist("Set-Cookie")
    assert any("sapphire_admin=" in c for c in cookies)


def test_register_complete_rejects_bad_challenge_handle(auth_pkg, monkeypatch):
    app, _ = _make_app(auth_pkg)
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]
    monkeypatch.setattr(
        routes_mod,
        "verify_registration_response",
        lambda **kw: pytest.fail("verify should not be called"),
    )
    r = app.test_client().post(
        "/api/admin/register/complete",
        json={"handle": "not-a-real-handle", "credential": {"id": "x"}},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "challenge_expired"


def test_register_complete_rejects_invalid_attestation(auth_pkg, monkeypatch):
    app, ctx = _make_app(auth_pkg)
    sm = ctx["session_manager"]
    handle = sm.wrap_challenge(b"\x00" * 32, flow="register")
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]

    def boom(**kw):
        from webauthn.helpers.exceptions import InvalidRegistrationResponse

        raise InvalidRegistrationResponse("bad attestation")

    monkeypatch.setattr(routes_mod, "verify_registration_response", boom)

    r = app.test_client().post(
        "/api/admin/register/complete",
        json={"handle": handle, "credential": {"id": "x"}},
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_attestation"


def test_register_complete_rejects_malformed_body(auth_pkg):
    app, _ = _make_app(auth_pkg)
    r = app.test_client().post("/api/admin/register/complete", json={})
    assert r.status_code == 400
    assert r.get_json()["error"] == "invalid_request"


# ---------------------------------------------------------------------------
# /api/admin/login/* (with patched verify)
# ---------------------------------------------------------------------------


def test_login_begin_404_when_no_credentials(auth_pkg):
    app, _ = _make_app(auth_pkg)
    r = app.test_client().post("/api/admin/login/begin")
    assert r.status_code == 404
    assert r.get_json()["error"] == "no_credentials_registered"


def test_login_begin_returns_options_when_credential_registered(auth_pkg):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"cid-1",
                public_key=b"pk",
                sign_count=0,
                user_id="admin",
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    r = app.test_client().post("/api/admin/login/begin")
    assert r.status_code == 200
    body = r.get_json()
    assert body["options"]["rpId"] == "localhost"
    assert "handle" in body
    # allowCredentials lists our registered cred (b64url of b"cid-1")
    assert body["options"]["allowCredentials"][0]["id"] == _b64url(b"cid-1")


def test_login_complete_happy_path(auth_pkg, monkeypatch):
    cred_id = b"cid-1"
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=cred_id,
                public_key=b"pk",
                sign_count=3,
                user_id="admin",
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    sm = ctx["session_manager"]
    challenge = auth_pkg.SessionManager.new_challenge_bytes()
    handle = sm.wrap_challenge(challenge, flow="login")

    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]

    def fake_verify(**kwargs):
        assert kwargs["expected_challenge"] == challenge
        assert kwargs["credential_public_key"] == b"pk"
        assert kwargs["credential_current_sign_count"] == 3
        return types.SimpleNamespace(new_sign_count=4)

    monkeypatch.setattr(routes_mod, "verify_authentication_response", fake_verify)

    r = app.test_client().post(
        "/api/admin/login/complete",
        json={
            "handle": handle,
            "credential": {
                "id": _b64url(cred_id),
                "rawId": _b64url(cred_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _b64url(b"{}"),
                    "authenticatorData": _b64url(b"\x00"),
                    "signature": _b64url(b"\x00"),
                    "userHandle": None,
                },
                "clientExtensionResults": {},
            },
        },
    )
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}
    # sign_count bumped
    assert store.get(cred_id).sign_count == 4
    # cookie set
    assert any("sapphire_admin=" in c for c in r.headers.getlist("Set-Cookie"))


def test_login_complete_unknown_credential_returns_401(auth_pkg, monkeypatch):
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=b"known", public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    handle = ctx["session_manager"].wrap_challenge(b"\x00" * 32, flow="login")
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]
    monkeypatch.setattr(
        routes_mod,
        "verify_authentication_response",
        lambda **kw: pytest.fail("must not be called"),
    )

    r = app.test_client().post(
        "/api/admin/login/complete",
        json={
            "handle": handle,
            "credential": {
                "id": _b64url(b"unknown"),
                "rawId": _b64url(b"unknown"),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _b64url(b"{}"),
                    "authenticatorData": _b64url(b"\x00"),
                    "signature": _b64url(b"\x00"),
                    "userHandle": None,
                },
            },
        },
    )
    assert r.status_code == 401


def test_login_complete_invalid_assertion_returns_401(auth_pkg, monkeypatch):
    cred_id = b"cid"
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=cred_id, public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    handle = ctx["session_manager"].wrap_challenge(b"\x00" * 32, flow="login")
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]

    def boom(**kw):
        from webauthn.helpers.exceptions import InvalidAuthenticationResponse

        raise InvalidAuthenticationResponse("nope")

    monkeypatch.setattr(routes_mod, "verify_authentication_response", boom)
    r = app.test_client().post(
        "/api/admin/login/complete",
        json={
            "handle": handle,
            "credential": {
                "id": _b64url(cred_id),
                "rawId": _b64url(cred_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _b64url(b"{}"),
                    "authenticatorData": _b64url(b"\x00"),
                    "signature": _b64url(b"\x00"),
                    "userHandle": None,
                },
            },
        },
    )
    assert r.status_code == 401
    assert r.get_json()["error"] == "unauthorized"


def test_login_complete_rejects_register_flow_handle(auth_pkg, monkeypatch):
    """A challenge handle minted for /register must be unusable on /login.

    This is the cross-flow replay defense in SessionManager.unwrap_challenge.
    """
    cred_id = b"cid"
    store = auth_pkg.InMemoryCredentialStore(
        seed=[
            auth_pkg.CredentialRecord(
                credential_id=cred_id, public_key=b"pk", sign_count=0, user_id="admin"
            )
        ]
    )
    app, ctx = _make_app(auth_pkg, store=store)
    # handle is for `register` flow but client is calling /login/complete
    bad_handle = ctx["session_manager"].wrap_challenge(b"\x00" * 32, flow="register")
    routes_mod = sys.modules[auth_pkg.__name__ + ".routes"]
    monkeypatch.setattr(
        routes_mod,
        "verify_authentication_response",
        lambda **kw: pytest.fail("must not be called"),
    )

    r = app.test_client().post(
        "/api/admin/login/complete",
        json={
            "handle": bad_handle,
            "credential": {
                "id": _b64url(cred_id),
                "rawId": _b64url(cred_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": _b64url(b"{}"),
                    "authenticatorData": _b64url(b"\x00"),
                    "signature": _b64url(b"\x00"),
                    "userHandle": None,
                },
            },
        },
    )
    assert r.status_code == 400
    assert r.get_json()["error"] == "challenge_expired"


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


def test_logout_clears_cookie(auth_pkg):
    app, ctx = _make_app(auth_pkg)
    token = ctx["session_manager"].issue_session("admin")
    client = app.test_client()
    client.set_cookie("sapphire_admin", token)
    # logged in
    assert client.get("/api/admin/whoami").status_code == 200
    # logout
    r = client.post("/api/admin/logout")
    assert r.status_code == 200
    # cookie clear directive present
    cleared = [c for c in r.headers.getlist("Set-Cookie") if "sapphire_admin=" in c]
    assert cleared
    # And after the cookie is dropped the next call is unauthorized.
    # (The Werkzeug test client honors Set-Cookie so this should work.)
    r2 = client.get("/api/admin/whoami")
    assert r2.status_code == 401


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def test_admin_login_page_renders(auth_pkg):
    app, _ = _make_app(auth_pkg)
    r = app.test_client().get("/admin/login")
    assert r.status_code == 200
    assert b"Sapphire Admin" in r.data
    assert b"passkey" in r.data.lower()


def test_admin_landing_requires_session(auth_pkg):
    app, _ = _make_app(auth_pkg)
    r = app.test_client().get("/admin", headers={"Accept": "text/html"})
    # browser request → redirect (not 401)
    assert r.status_code in (301, 302)


def test_admin_landing_renders_with_valid_session(auth_pkg):
    app, ctx = _make_app(auth_pkg)
    token = ctx["session_manager"].issue_session("admin")
    client = app.test_client()
    client.set_cookie("sapphire_admin", token)
    r = client.get("/admin")
    assert r.status_code == 200
    # Cards link to the passkey-gated data suites plus public surfaces.
    assert b"System Health Detail" in r.data
    assert b"Failover Readiness" in r.data
    assert b"Brain Full Synthesis" in r.data
    assert b"Signals And Forecasts" in r.data
    assert b"Decision Queue" in r.data
    assert b"Public Sapphire OS" in r.data
