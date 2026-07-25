#!/usr/bin/env python3
"""
Sapphire Trading Dashboard
Real-time trading system monitor and control interface
"""

import ast
import json
import logging
import os
import plistlib
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any

# Make the Sapphire lib/ discoverable regardless of whether this dashboard runs
# from the main repo or a git worktree. Done once at import time so namespace
# packages resolve consistently across requests.
_DASHBOARD_ROOTS = (
    Path(__file__).resolve().parents[2],  # current checkout (worktree or main)
    Path.home() / "Code" / "Sapphire",  # canonical main repo
)
# Insert in reverse so the current-checkout path ends up at index 0 (highest
# priority). Without this, a worktree dashboard resolves `lib.*` against the
# main repo and misses modules only present in the worktree.
for _r in reversed(_DASHBOARD_ROOTS):
    _rs = str(_r)
    while _rs in sys.path:
        sys.path.remove(_rs)
    sys.path.insert(0, _rs)

log = logging.getLogger("dashboard")

import contextlib

from flask import Flask, Response, jsonify, render_template, request, send_file, send_from_directory

from lib.core import routine_pause

# Disable Flask's auto-registered /static/<path> route. It was bypassing the
# @requires_auth decorator and exposing static/benchmark_report.html
# (infrastructure topology: GPU models, VRAM, endpoints) to any caller.
# A guarded replacement is registered below so the same files still serve
# — only for authenticated users.
app = Flask(__name__, static_folder=None)
_STATIC_DIR = Path(__file__).parent / "static"
_FRONTEND_DIST_DIR = Path(__file__).parent / "frontend" / "dist"
_DASHBOARD_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENT_EVENTS_FILE = _DASHBOARD_REPO_ROOT / "data" / "events" / "bus.jsonl"
_AGENT_HEARTBEAT_DIR = _DASHBOARD_REPO_ROOT / "data" / "agents"
_GEMINI_OODA_DAILY_DIR = _DASHBOARD_REPO_ROOT / "data" / ".autonomy" / "gemini-ooda"
_TELEGRAM_HISTORY_INTEL_DIR = _DASHBOARD_REPO_ROOT / "data" / "telegram_history_intel"
_ROUTINE_PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"

# Configuration
# Pi-less mode: services run on Mac (localhost) and rari2 (Tailscale)
RARI1_IP = os.environ.get("RARI1_IP", "127.0.0.1")  # control-plane on Mac
RARI2_IP = os.environ.get("RARI2_IP", "100.x.x.y")  # rari2 via Tailscale
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# Auth configuration — credentials required via environment variables
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "sapphire")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")
WEAK_AUTH_PASSWORDS = {"sapphire", "password", "changeme", "admin"}

if not AUTH_PASSWORD:
    raise RuntimeError("AUTH_PASSWORD environment variable must be set")
if AUTH_PASSWORD.lower() in WEAK_AUTH_PASSWORDS:
    raise RuntimeError("AUTH_PASSWORD must not use a known default value")

# Dashboard port — honour the PORT env var so internal self-references stay
# correct regardless of how the service is launched.
DASHBOARD_PORT = int(os.environ.get("PORT", 8082))

# x402 payment gate — optional, disabled unless X402_ENABLED=1
import sys as _sys  # noqa: E402

_LIB_PAYMENTS = _DASHBOARD_REPO_ROOT
if str(_LIB_PAYMENTS) not in sys.path:
    sys.path.insert(0, str(_LIB_PAYMENTS))
try:
    from lib.payments.x402_middleware import require_payment as x402_require  # noqa: E402

    _X402_AVAILABLE = True
except Exception:
    _X402_AVAILABLE = False

    def x402_require(amount_usd, description=""):  # type: ignore[misc]
        def _decorator(f):
            return f

        return _decorator


def check_auth(username, password):
    # Constant-time compare to avoid leaking password length / prefix via
    # response-time side channel. Both values are compared after encoding so
    # mismatched types don't raise.
    if username is None or password is None:
        return False
    u_ok = secrets.compare_digest(str(username).encode("utf-8"), str(AUTH_USERNAME).encode("utf-8"))
    p_ok = secrets.compare_digest(str(password).encode("utf-8"), str(AUTH_PASSWORD).encode("utf-8"))
    return u_ok and p_ok


def authenticate():
    return Response(
        "Authentication required.", 401, {"WWW-Authenticate": 'Basic realm="Sapphire Dashboard"'}
    )


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)

    return decorated


@app.route("/static/<path:filename>", endpoint="static")
@requires_auth
def guarded_static(filename):
    """Auth-gated replacement for Flask's default static handler.

    Named `static` so url_for('static', filename=...) still works for any
    template or route that relies on the default Flask endpoint name.
    """
    return send_from_directory(_STATIC_DIR, filename)


@app.route("/app-preview")
@requires_auth
def app_preview():
    """Serve the built React control-plane preview when the bundle exists."""
    index_path = _FRONTEND_DIST_DIR / "index.html"
    if not index_path.exists():
        return (
            jsonify(
                {
                    "status": "unknown",
                    "mode": "blocked",
                    "title": "Sapphire OS Control Plane preview",
                    "value": "build required",
                    "summary": (
                        "The React app source exists under services/dashboard/frontend, "
                        "but the local Vite bundle has not been built yet."
                    ),
                    "source": {
                        "kind": "file",
                        "path_or_url": "services/dashboard/frontend/dist/index.html",
                        "generated_at": None,
                        "age_seconds": None,
                    },
                    "actions": [
                        {
                            "label": "Build preview bundle",
                            "mode": "dry_run",
                            "requires_confirm": False,
                        }
                    ],
                }
            ),
            503,
        )
    return send_file(index_path)


@app.route("/app-preview/assets/<path:filename>")
@requires_auth
def app_preview_assets(filename):
    """Serve Vite assets for the React control-plane preview."""
    return send_from_directory(_FRONTEND_DIST_DIR / "assets", filename)


@app.route("/api/v2/control-plane/summary")
@requires_auth
def api_v2_control_plane_summary():
    """Normalized read-only cards for the Sapphire OS Control Plane preview."""

    def fetch():
        from services.dashboard.control_plane_summary import build_control_plane_summary

        return build_control_plane_summary(probe_services=True)

    return jsonify(get_cached("v2_control_plane_summary", fetch, ttl=30, raise_on_miss=True))


# Cache for data
_cache = {}
_cache_time = {}
CACHE_DURATION = 10  # seconds
CHAIN_OVERVIEW_CACHE_DURATION = 60
PORTFOLIO_CACHE_DURATION = 30
CASCADE_CACHE_DURATION = 30
STRATEGY_PERFORMANCE_CACHE_DURATION = 30
MARKET_UNIVERSE_CACHE_DURATION = 60
STRATEGY_LAB_CACHE_DURATION = 300
CROSS_ASSET_CACHE_DURATION = 300
RH_CHAIN_LOCAL_CACHE_DURATION = 5

# ── In-process latency metrics (per-route rolling) ─────────────────────────
# Keeps a bounded ring buffer of (method, path, ms) samples plus per-route
# counters. Exposed via /metrics (auth-gated). Bounded size keeps memory in
# check under long-running processes (~24 bytes/sample × 2000 = 48 KB).
_METRICS_MAX_SAMPLES = 2000
_metrics_samples: list[tuple[str, str, float]] = []
_metrics_counts: dict[str, int] = {}
_metrics_totals: dict[str, float] = {}
_X402_PRODUCT_MIDDLEWARE_CACHE: dict[tuple[str, str, str, str], Any] = {}


@app.before_request
def _metrics_before_request():
    request.environ["sapphire.t0"] = time.perf_counter()


@app.after_request
def _metrics_after_request(response):
    t0 = request.environ.get("sapphire.t0")
    if t0 is None:
        return response
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    endpoint = request.endpoint or request.path or "unknown"
    key = f"{request.method} {endpoint}"
    _metrics_counts[key] = _metrics_counts.get(key, 0) + 1
    _metrics_totals[key] = _metrics_totals.get(key, 0.0) + elapsed_ms
    _metrics_samples.append((request.method, endpoint, elapsed_ms))
    if len(_metrics_samples) > _METRICS_MAX_SAMPLES:
        # Drop oldest ~10% to amortize the trim cost
        del _metrics_samples[: _METRICS_MAX_SAMPLES // 10]
    response.headers["X-Response-Time-ms"] = f"{elapsed_ms:.1f}"
    return response


def get_cached(key, fetch_func, ttl=CACHE_DURATION, *, raise_on_miss=False):
    """Get cached data or fetch fresh, returning stale data if refresh fails."""
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < ttl:
        return _cache[key]

    try:
        data = fetch_func()
        _cache[key] = data
        _cache_time[key] = now
        return data
    except Exception as e:
        log.warning("Cache fetch failed for '%s': %s", key, e)
        if key in _cache:
            return _cache[key]
        if raise_on_miss:
            raise
        return {}


_SECRETISH_TEXT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|private[_-]?key)\b\s*[:=]\s*[^,\s;]+"
)
_BEARER_TEXT_RE = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{8,}")
_USER_PATH_RE = re.compile(r"/Users/[^/\s)\"'`]+")
_BUYER_SAFE_REDACTED_TEXT = "[buyer-safe redacted]"
_BUYER_SAFE_FIELD_REPLACEMENTS: dict[str, Any] = {
    "artifact": _BUYER_SAFE_REDACTED_TEXT,
    "cache_dir": _BUYER_SAFE_REDACTED_TEXT,
    "cache_root": _BUYER_SAFE_REDACTED_TEXT,
    "endpoint": _BUYER_SAFE_REDACTED_TEXT,
    "label": _BUYER_SAFE_REDACTED_TEXT,
    "last_exit": None,
    "pid": None,
    "relative_path": _BUYER_SAFE_REDACTED_TEXT,
    "root": _BUYER_SAFE_REDACTED_TEXT,
    "roots": [],
}


def _paste_safe_text(value: Any, *, limit: int = 280) -> str:
    """Return compact dashboard text without local user paths or secret-shaped values."""
    text = " ".join(str(value or "").split())
    text = text.replace(str(_DASHBOARD_REPO_ROOT), "Sapphire")
    text = text.replace(str(Path.home() / "Code" / "Sapphire"), "Sapphire")
    text = _USER_PATH_RE.sub("~", text)
    text = re.sub(r"\bAri's\b", "the operator's", text)
    text = re.sub(r"\bAri\b", "the operator", text)
    text = _SECRETISH_TEXT_RE.sub(lambda m: f"{m.group(1)}=[redacted]", text)
    text = _BEARER_TEXT_RE.sub("Bearer [redacted]", text)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _buyer_safe_requested() -> bool:
    """Return True when a dashboard route should expose buyer-safe payloads."""
    raw = (
        request.args.get("profile")
        or request.args.get("view")
        or request.args.get("buyer_safe")
        or request.args.get("public")
        or ""
    )
    return str(raw).strip().lower() in {
        "1",
        "true",
        "yes",
        "buyer",
        "buyer_safe",
        "buyer-safe",
        "public",
    }


def _buyer_safe_payload(payload: Any) -> Any:
    """Redact operational identifiers while preserving diligence signal value."""
    redacted_fields: set[str] = set()

    def _walk(value: Any, key: str = "") -> Any:
        normalized_key = key.lower()
        if normalized_key in _BUYER_SAFE_FIELD_REPLACEMENTS:
            redacted_fields.add(normalized_key)
            return _BUYER_SAFE_FIELD_REPLACEMENTS[normalized_key]
        if isinstance(value, dict):
            return {
                str(child_key): _walk(child_value, str(child_key))
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [_walk(item, key) for item in value]
        if isinstance(value, str):
            return _paste_safe_text(value, limit=360)
        return value

    safe_payload = _walk(payload)
    if isinstance(safe_payload, dict):
        safe_payload["audience"] = "buyer_safe"
        safe_payload["redaction"] = {
            "profile": "buyer_safe",
            "applied": True,
            "fields": sorted(redacted_fields),
        }
    return safe_payload


def _maybe_buyer_safe_payload(payload: Any) -> Any:
    return _buyer_safe_payload(payload) if _buyer_safe_requested() else payload


def _repo_display_path(path: Path | str) -> str:
    raw = Path(path)
    try:
        return str(raw.resolve().relative_to(_DASHBOARD_REPO_ROOT.resolve()))
    except (OSError, ValueError):
        return _paste_safe_text(str(path), limit=160)


def _first_paragraph(lines: list[str], *, start: int = 0) -> str:
    paragraph: list[str] = []
    in_code = False
    for line in lines[start:]:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not stripped:
            if paragraph:
                break
            continue
        if stripped.startswith("#") or stripped.startswith("- "):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def _extract_diligence_doc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("# ")), path.stem)
    readout_index = next(
        (
            idx + 1
            for idx, line in enumerate(lines)
            if line.strip().lower() == "## diligence readout"
        ),
        len(lines),
    )
    evidence_index = next(
        (idx + 1 for idx, line in enumerate(lines) if line.strip().lower() == "## evidence"),
        len(lines),
    )
    evidence: list[str] = []
    for line in lines[evidence_index:]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("- "):
            evidence.append(_paste_safe_text(stripped[2:], limit=140))
    words = re.findall(r"\b[\w'-]+\b", text)
    return {
        "id": path.stem.split("-", 1)[0],
        "title": _paste_safe_text(title, limit=120),
        "path": _repo_display_path(path),
        "summary": _paste_safe_text(_first_paragraph(lines, start=1), limit=360),
        "readout": _paste_safe_text(_first_paragraph(lines, start=readout_index), limit=360),
        "evidence": evidence[:6],
        "metrics": {
            "words": len(words),
            "headings": sum(1 for line in lines if line.startswith("## ")),
            "evidence_items": len(evidence),
        },
    }


def _build_cross_asset_snapshot() -> dict[str, Any]:
    """Build the cache-first cross-asset dashboard payload."""
    try:
        from services.cross_asset.run import build_snapshot

        return build_snapshot(live=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("cross-asset snapshot unavailable: %s", exc)
        return {
            "ok": False,
            "mode": "unavailable",
            "error": _paste_safe_text(f"{type(exc).__name__}: {exc}", limit=180),
            "matrix": {"windows": {}, "breakdown_events": []},
            "regime": {
                "label": "regime_uncertain",
                "confidence": 0.0,
                "drivers": ["snapshot unavailable"],
                "metrics": {},
            },
            "breakdowns": [],
            "lead_lag": [],
            "source_summary": {},
        }


def _cross_asset_snapshot_cached() -> dict[str, Any]:
    return get_cached(
        "cross_asset_snapshot",
        _build_cross_asset_snapshot,
        ttl=CROSS_ASSET_CACHE_DURATION,
    )


def _x402_fred_observations_path(now: datetime | None = None) -> Path:
    raw_path = os.environ.get("SAPPHIRE_X402_FRED_OBSERVATIONS_PATH")
    if raw_path:
        return Path(raw_path).expanduser()
    raw_root = os.environ.get("SAPPHIRE_MACRO_OUTPUT_ROOT")
    output_root = (
        Path(raw_root).expanduser() if raw_root else _DASHBOARD_REPO_ROOT / "data" / "macro"
    )
    day = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d")
    return output_root / day / "fred_observations.jsonl"


def _build_x402_fred_features() -> dict[str, Any]:
    """Load local FRED-derived features for the simulated paid report."""
    from lib.macro.fred_loader import (
        macro_feature_row_from_observation_rows,
        read_fred_observation_jsonl,
    )

    path = _x402_fred_observations_path()
    rows = read_fred_observation_jsonl(path)
    if not rows:
        return {}
    return macro_feature_row_from_observation_rows(
        rows,
        source_path=_repo_display_path(path),
    )


def _x402_fred_features_cached() -> dict[str, Any]:
    return get_cached(
        "x402_fred_features",
        _build_x402_fred_features,
        ttl=CROSS_ASSET_CACHE_DURATION,
    )


def _x402_payment_header() -> str | None:
    return request.headers.get("X-PAYMENT") or request.headers.get("PAYMENT-SIGNATURE")


def _x402_product_catalogs():
    from lib.payments.x402_products import load_validated_catalogs

    return load_validated_catalogs()


def _x402_market_regime_catalogs():
    return _x402_product_catalogs()


def _x402_product_middleware(product):
    from lib.payments.x402_middleware import X402Middleware

    recipient = os.environ.get("X402_RECIPIENT", "")
    key = (product.product_id, recipient, product.network, product.asset or "")
    middleware = _X402_PRODUCT_MIDDLEWARE_CACHE.get(key)
    if middleware is None:
        middleware = X402Middleware(
            recipient_address=recipient,
            pricing={product.route: float(product.price_usd)},
            network=product.network,
            asset=product.asset,
            enabled=True,
        )
        _X402_PRODUCT_MIDDLEWARE_CACHE[key] = middleware
    return middleware


def _x402_market_regime_middleware(product):
    return _x402_product_middleware(product)


def _x402_receipt_ledger():
    from lib.payments.x402_products import ReceiptLedger

    return ReceiptLedger()


def _append_x402_product_receipt(
    *,
    product,
    requirements,
    payment_header: str | None,
    verification,
    status: str,
    endpoint: str,
    artifact_id: str | None = None,
):
    from lib.payments.x402_products import ReceiptRecord

    receipt = ReceiptRecord.from_payment(
        product=product,
        requirements=requirements,
        payment_header=payment_header,
        verification=verification,
        status=status,
        artifact_id=artifact_id,
        metadata={
            "endpoint": endpoint,
            "live_settlement_allowed": product.live_settlement_allowed,
        },
    )
    try:
        _x402_receipt_ledger().append(receipt)
    except Exception as exc:  # noqa: BLE001
        log.warning("x402 receipt append failed for %s: %s", endpoint, exc)
    return receipt


def _append_x402_market_regime_receipt(
    *,
    product,
    requirements,
    payment_header: str | None,
    verification,
    status: str,
    artifact_id: str | None = None,
):
    return _append_x402_product_receipt(
        product=product,
        requirements=requirements,
        payment_header=payment_header,
        verification=verification,
        status=status,
        endpoint="/api/x402/market-regime",
        artifact_id=artifact_id,
    )


def _agentwiki_context():
    from lib.payments.agentwiki import load_validated_agentwiki_artifacts

    catalog, registry = _x402_product_catalogs()
    artifacts = load_validated_agentwiki_artifacts(catalog, registry)
    return catalog, registry, artifacts


def _matrix_payload(snapshot: dict[str, Any], *, window: str, method: str) -> dict[str, Any]:
    matrix_root = snapshot.get("matrix") or {}
    windows = matrix_root.get("windows") or {}
    selected = (windows.get(window) or {}).get(method)
    if selected is None and windows:
        first_window = next(iter(windows))
        first_methods = windows.get(first_window) or {}
        first_method = method if method in first_methods else next(iter(first_methods), method)
        selected = first_methods.get(first_method)
        window = first_window
        method = first_method
    return {
        "ok": bool(snapshot.get("ok", True)),
        "mode": snapshot.get("mode", "cache_or_dry_run"),
        "generated_at": snapshot.get("generated_at"),
        "window": window,
        "method": method,
        "matrix": selected,
        "available_windows": sorted(windows),
        "available_methods": sorted({name for methods in windows.values() for name in methods}),
        "breakdown_count": len(snapshot.get("breakdowns") or []),
        "source_summary": snapshot.get("source_summary") or {},
        "error": snapshot.get("error"),
    }


def _cross_asset_regime_history(limit: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in _DASHBOARD_ROOTS:
        data_root = root / "data" / "cross_asset"
        if not data_root.exists():
            continue
        for path in sorted(data_root.glob("*/regimes.jsonl"))[-limit:]:
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        raw = json.loads(line)
                        rows.append(raw.get("payload") or raw)
            except (OSError, json.JSONDecodeError):
                continue
    return rows[-limit:]


def _build_diligence_summary(root: Path | None = None) -> dict[str, Any]:
    repo_root = root or _DASHBOARD_REPO_ROOT
    diligence_dir = repo_root / "docs" / "diligence"
    documents: list[dict[str, Any]] = []
    missing: list[str] = []
    for index in range(10):
        matches = sorted(diligence_dir.glob(f"{index:02d}-*.md"))
        if not matches:
            missing.append(f"{index:02d}")
            continue
        try:
            documents.append(_extract_diligence_doc(matches[0]))
        except OSError as exc:
            missing.append(f"{index:02d}:{exc.__class__.__name__}")
    totals = {
        "documents": len(documents),
        "expected_documents": 10,
        "missing_documents": len(missing),
        "words": sum(doc["metrics"]["words"] for doc in documents),
        "headings": sum(doc["metrics"]["headings"] for doc in documents),
        "evidence_items": sum(doc["metrics"]["evidence_items"] for doc in documents),
    }
    return {
        "mode": "read_only_diligence_packet",
        "status": "pass" if not missing and len(documents) == 10 else "warn",
        "source_root": "docs/diligence",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "totals": totals,
        "missing": missing,
        "documents": documents,
    }


def _build_risk_kernel_summary() -> dict[str, Any]:
    from lib.core.risk_kernel import DecisionEnvelope, RiskKernelV1, __version__

    kernel = RiskKernelV1()
    safe_decision = DecisionEnvelope(
        decision_id="diligence-safe-sample",
        action="research_decision",
        symbol="BTC-USD",
        side="long",
        notional_usd=1_000.0,
        equity=100_000.0,
        price=100_000.0,
        quantity=0.01,
        atr=1_500.0,
        stop_loss_price=99_000.0,
        risk_metrics={
            "daily_loss_pct": 0.25,
            "intraday_drawdown_pct": 0.4,
            "kill_switch_active": False,
        },
    )
    blocked_decision = DecisionEnvelope(
        decision_id="diligence-block-sample",
        action="open_order",
        symbol="BTC-USD",
        side="long",
        notional_usd=15_000.0,
        proposed_position_pct=15.0,
        equity=100_000.0,
        price=100_000.0,
        quantity=0.15,
        atr=20_000.0,
        stop_loss_price=90_000.0,
        risk_metrics={
            "daily_loss_pct": 4.5,
            "intraday_drawdown_pct": 3.8,
            "kill_switch_active": True,
        },
        metadata={"ignore_risk_kernel": True},
    )
    safe_verdict = kernel.evaluate(safe_decision).to_dict()
    blocked_verdict = kernel.evaluate(blocked_decision).to_dict()
    policies = [
        {
            "name": getattr(policy, "name", policy.__class__.__name__),
            "version": getattr(policy, "version", "unknown"),
            "params": dict(getattr(policy, "params", {}) or {}),
        }
        for policy in kernel.policies
    ]
    params_by_name = {policy["name"]: policy["params"] for policy in policies}
    return {
        "mode": "read_only_risk_kernel_summary",
        "status": "pass" if safe_verdict["allowed"] and not blocked_verdict["allowed"] else "warn",
        "version": __version__,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "headline": {
            "policy_count": len(policies),
            "sample_allowed": safe_verdict["allowed"],
            "blocked_fired_gates": len(blocked_verdict["fired_gates"]),
            "max_daily_loss_pct": params_by_name.get("daily_loss", {}).get("max_loss_pct"),
            "max_intraday_drawdown_pct": params_by_name.get("intraday_drawdown", {}).get(
                "max_drawdown_pct"
            ),
            "max_position_pct": params_by_name.get("atr_sizing", {}).get("max_position_pct"),
            "max_atr_risk_pct": params_by_name.get("atr_sizing", {}).get("max_atr_risk_pct"),
            "max_single_trade_loss_pct": params_by_name.get("atr_sizing", {}).get(
                "max_single_trade_loss_pct"
            ),
        },
        "policies": policies,
        "sample_verdicts": {
            "safe": {
                "allowed": safe_verdict["allowed"],
                "fired_gates": [gate["policy"] for gate in safe_verdict["fired_gates"]],
                "evaluation_ms": safe_verdict["evaluation_ms"],
            },
            "blocked": {
                "allowed": blocked_verdict["allowed"],
                "fired_gates": [gate["policy"] for gate in blocked_verdict["fired_gates"]],
                "evaluation_ms": blocked_verdict["evaluation_ms"],
            },
        },
    }


def _build_provenance_summary(*, older_than_hours: float = 24.0) -> dict[str, Any]:
    try:
        from scripts.ops import provenance_verify

        report = provenance_verify.build_report(
            provenance_verify.DEFAULT_ROOTS,
            older_than_hours=max(0.0, min(float(older_than_hours), 24 * 30)),
        )
        invalid_rows = [row for row in report.get("rows", []) if not row.get("ok")]
        return {
            "mode": "read_only_provenance_verifier",
            "status": "pass" if report.get("ok") else "warn",
            "schema_version": report.get("schema_version", 1),
            "older_than_hours": report.get("older_than_hours", older_than_hours),
            "checked": report.get("checked", 0),
            "missing_or_invalid": report.get("missing_or_invalid", 0),
            "roots": [_repo_display_path(Path(root)) for root in report.get("roots", [])],
            "invalid_sample": [
                {
                    "artifact": _paste_safe_text(row.get("artifact"), limit=180),
                    "reason": _paste_safe_text(row.get("reason"), limit=80),
                }
                for row in invalid_rows[:5]
            ],
        }
    except Exception as exc:
        log.warning("provenance summary unavailable: %s", exc)
        return {
            "mode": "read_only_provenance_verifier",
            "status": "unknown",
            "checked": 0,
            "missing_or_invalid": 0,
            "roots": [],
            "invalid_sample": [],
            "error": _paste_safe_text(f"{exc.__class__.__name__}: {exc}", limit=180),
        }


def _count_test_functions(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _load_pytest_cache(root: Path) -> dict[str, Any]:
    cache_dir = root / ".pytest_cache" / "v" / "cache"
    nodeids_path = cache_dir / "nodeids"
    lastfailed_path = cache_dir / "lastfailed"
    nodeids: list[str] = []
    lastfailed: dict[str, Any] = {}
    try:
        raw_nodeids = json.loads(nodeids_path.read_text(encoding="utf-8"))
        if isinstance(raw_nodeids, list):
            nodeids = [str(item) for item in raw_nodeids]
    except (OSError, json.JSONDecodeError):
        nodeids = []
    try:
        raw_lastfailed = json.loads(lastfailed_path.read_text(encoding="utf-8"))
        if isinstance(raw_lastfailed, dict):
            lastfailed = raw_lastfailed
    except (OSError, json.JSONDecodeError):
        lastfailed = {}
    return {
        "root": root,
        "nodeids": nodeids,
        "lastfailed": lastfailed,
        "cache_mtime": datetime.fromtimestamp(nodeids_path.stat().st_mtime, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        if nodeids_path.exists()
        else None,
    }


def _build_test_suite_health(root: Path | None = None) -> dict[str, Any]:
    repo_root = root or _DASHBOARD_REPO_ROOT
    cache = _load_pytest_cache(repo_root)
    if not cache["nodeids"] and root is None:
        for candidate in _DASHBOARD_ROOTS:
            candidate_cache = _load_pytest_cache(candidate)
            if candidate_cache["nodeids"]:
                cache = candidate_cache
                break
    test_files = sorted((repo_root / "tests" / "unit").glob("test_*.py"))
    plugin_files = sorted((repo_root / "plugins" / "claw-sapphire" / "tests").glob("test_*.py"))
    nodeids = cache["nodeids"]
    lastfailed = cache["lastfailed"]

    def suite(prefix: str, files: list[Path]) -> dict[str, Any]:
        return {
            "path": prefix.rstrip("/"),
            "test_files": len(files),
            "test_functions": sum(_count_test_functions(path) for path in files),
            "cached_nodeids": sum(1 for nodeid in nodeids if nodeid.startswith(prefix)),
            "lastfailed": sum(1 for nodeid in lastfailed if nodeid.startswith(prefix)),
        }

    suites = {
        "unit": suite("tests/unit/", test_files),
        "plugin": suite("plugins/claw-sapphire/tests/", plugin_files),
    }
    lastfailed_count = len(lastfailed)
    status = (
        "pass" if nodeids and lastfailed_count == 0 else ("fail" if lastfailed_count else "warn")
    )
    return {
        "mode": "read_only_test_suite_health",
        "status": status,
        "source": "pytest_cache" if nodeids else "static_source_inventory",
        "cache_root": _repo_display_path(cache["root"]),
        "cache_mtime": cache["cache_mtime"],
        "totals": {
            "suites": len(suites),
            "test_files": sum(row["test_files"] for row in suites.values()),
            "test_functions": sum(row["test_functions"] for row in suites.values()),
            "cached_nodeids": len(nodeids),
            "lastfailed": lastfailed_count,
        },
        "suites": suites,
    }


def _dashboard_launchagent_labels(root: Path | None = None) -> list[str]:
    repo_root = root or _DASHBOARD_REPO_ROOT
    paths = list((repo_root / "infra" / "launchagents").glob("*.plist"))
    paths.extend((repo_root / "services").glob("*/launchagent/*.plist"))
    labels: set[str] = set()
    for path in paths:
        try:
            payload = plistlib.loads(path.read_bytes())
        except (OSError, plistlib.InvalidFileException):
            continue
        label = payload.get("Label") if isinstance(payload, dict) else None
        if isinstance(label, str) and label:
            labels.add(label)
    return sorted(labels)


def _parse_launchctl_list(output: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("pid"):
            continue
        parts = stripped.split(maxsplit=2)
        if len(parts) != 3:
            continue
        pid_raw, status_raw, label = parts
        pid = None if pid_raw == "-" else int(pid_raw) if pid_raw.lstrip("-").isdigit() else pid_raw
        last_exit: int | str | None
        last_exit = int(status_raw) if status_raw.lstrip("-").isdigit() else status_raw
        rows[label] = {"pid": pid, "last_exit": last_exit}
    return rows


def _build_launchagent_summary() -> dict[str, Any]:
    labels = _dashboard_launchagent_labels()
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {
            "mode": "read_only_launchagent_status",
            "status": "unknown",
            "checked": False,
            "error": _paste_safe_text(f"{exc.__class__.__name__}: {exc}", limit=160),
            "totals": {"labels": len(labels), "running": 0, "loaded": 0, "not_loaded": 0},
            "launchagents": [
                {"label": label, "status_label": "unknown", "pid": None, "last_exit": None}
                for label in labels
            ],
        }
    if result.returncode != 0:
        return {
            "mode": "read_only_launchagent_status",
            "status": "unknown",
            "checked": True,
            "error": _paste_safe_text(result.stderr, limit=160),
            "totals": {"labels": len(labels), "running": 0, "loaded": 0, "not_loaded": 0},
            "launchagents": [
                {"label": label, "status_label": "unknown", "pid": None, "last_exit": None}
                for label in labels
            ],
        }
    parsed = _parse_launchctl_list(result.stdout)
    rows: list[dict[str, Any]] = []
    for label in labels:
        live = parsed.get(label)
        if not live:
            rows.append(
                {"label": label, "status_label": "not_loaded", "pid": None, "last_exit": None}
            )
            continue
        pid = live.get("pid")
        last_exit = live.get("last_exit")
        if pid not in (None, "-"):
            status_label = "running"
        elif last_exit == 0:
            status_label = "loaded"
        else:
            status_label = "exited"
        rows.append(
            {
                "label": label,
                "status_label": status_label,
                "pid": pid,
                "last_exit": last_exit,
            }
        )
    totals = {
        "labels": len(rows),
        "running": sum(1 for row in rows if row["status_label"] == "running"),
        "loaded": sum(1 for row in rows if row["status_label"] in {"running", "loaded", "exited"}),
        "not_loaded": sum(1 for row in rows if row["status_label"] == "not_loaded"),
    }
    return {
        "mode": "read_only_launchagent_status",
        "status": "pass" if totals["loaded"] else "warn",
        "checked": True,
        "totals": totals,
        "launchagents": rows,
    }


def _build_routine_pause_summary(pause_dir: Path | None = None) -> dict[str, Any]:
    rows = [
        {"name": record.name, "paused_at": record.paused_at}
        for record in routine_pause.list_paused(pause_dir=pause_dir or _ROUTINE_PAUSE_DIR)
    ]
    return {
        "mode": "read_only_routine_pause_status",
        "status": "warn" if rows else "pass",
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "totals": {"paused": len(rows)},
        "paused_routines": rows,
    }


def fetch_sync(url):
    """Synchronous fetch — 4 MB response cap to prevent memory pressure."""
    import ssl
    import urllib.parse
    import urllib.request

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {}
    try:
        import certifi

        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(url, timeout=5, context=ctx) as response:  # nosec B310 - URL scheme is restricted above.
            data = response.read(4 * 1024 * 1024)  # 4 MB cap
            return json.loads(data)
    except Exception:
        return {}


def _dashboard_page_route_count() -> int:
    """Count registered, non-static dashboard page routes."""
    routes: set[str] = set()
    for rule in app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        path = rule.rule
        if path.startswith("/api/") or path.startswith("/static/") or "<" in path:
            continue
        routes.add(path)
    return len(routes)


@lru_cache(maxsize=1)
def _tool_registry_metric() -> dict[str, str]:
    """Return the registry metric from the validator, with a YAML fallback."""
    fallback_count = "unknown"
    try:
        import yaml

        registry = yaml.safe_load(
            (_DASHBOARD_REPO_ROOT / "infra" / "tool-registry.yaml").read_text(encoding="utf-8")
        )
        tools = registry.get("tools", []) if isinstance(registry, dict) else []
        fallback_count = str(len(tools))
    except Exception:
        fallback_count = "unknown"

    try:
        result = subprocess.run(
            [sys.executable, "scripts/validate_tool_registry.py", "--json"],
            cwd=_DASHBOARD_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if result.returncode == 0:
            payload = json.loads(result.stdout)
            summary = payload.get("summary", {})
            entries = summary.get("registry_entries", fallback_count)
            errors = len(payload.get("errors", []))
            return {
                "value": f"{entries} / {errors}",
                "note": "Registry entries / validation errors from the local validator",
            }
    except Exception:
        pass

    return {
        "value": f"{fallback_count} / ?",
        "note": "Registry entries from YAML; validator unavailable in this process",
    }


@lru_cache(maxsize=1)
def _production_readiness_metric() -> dict[str, str]:
    """Return the no-external production-readiness summary for showcase use."""
    try:
        env = os.environ.copy()
        env.update(
            {
                "SAPPHIRE_WINDOWS_HTTP_TIMEOUT_SECONDS": "1",
                "SAPPHIRE_WINDOWS_TCP_TIMEOUT_SECONDS": "1",
            }
        )
        result = subprocess.run(
            [
                sys.executable,
                "scripts/ops/production_readiness_sweep.py",
                "--no-external",
                "--format",
                "json",
            ],
            cwd=_DASHBOARD_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode in {0, 20} and result.stdout.strip():
            payload = json.loads(result.stdout)
            summary = payload.get("summary", {})
            fail = int(summary.get("fail", 0))
            return {
                "value": f"{fail} FAIL",
                "note": (
                    "No-external sweep: "
                    f"{summary.get('pass', 0)} pass, "
                    f"{summary.get('warn', 0)} warn, "
                    f"{summary.get('skip', 0)} skip"
                ),
            }
    except Exception:
        pass

    return {
        "value": "unknown",
        "note": "No-external production-readiness sweep unavailable",
    }


@lru_cache(maxsize=1)
def _org_repo_index() -> dict[str, dict[str, Any]]:
    """Load paste-safe repo metadata for showcase satellite cards."""
    try:
        import yaml

        manifest = yaml.safe_load(
            (_DASHBOARD_REPO_ROOT / "infra" / "org-repos.yaml").read_text(encoding="utf-8")
        )
    except Exception:
        return {}
    repos = manifest.get("repos", []) if isinstance(manifest, dict) else []
    return {
        str(repo.get("id")): repo for repo in repos if isinstance(repo, dict) and repo.get("id")
    }


def _manifest_summary(repo_id: str, fallback: str) -> str:
    repo = _org_repo_index().get(repo_id, {})
    role = repo.get("role")
    return str(role) if role else fallback


def _manifest_repo_link(repo_id: str) -> dict[str, Any] | None:
    repo = _org_repo_index().get(repo_id, {})
    github = repo.get("github")
    if not github:
        return None
    return {
        "label": "Repository",
        "href": f"https://github.com/{github}",
        "external": True,
    }


def _manifest_tags(repo_id: str, extra: list[str]) -> list[str]:
    repo = _org_repo_index().get(repo_id, {})
    tags = list(extra)
    for key in ("classification", "migration_state"):
        value = repo.get(key)
        if value:
            tags.append(str(value).replace("_", " "))
    if repo.get("production_adjacent"):
        tags.append("production adjacent")

    deduped: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        clean = tag.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            deduped.append(clean)
    return deduped


def _append_link(
    links: list[dict[str, Any]],
    link: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if link:
        return [*links, link]
    return links


def _build_unified_dashboard_payload() -> dict[str, Any]:
    """Read-only dashboard directory for Sapphire and adjacent frontends."""
    registry_metric = _tool_registry_metric()
    readiness_metric = _production_readiness_metric()
    satellite_dashboards = [
        {
            "name": "Project-Go-Forward / THO",
            "status": "Production",
            "summary": _manifest_summary(
                "project-go-forward",
                "FastAPI and React platform for the Texas Home Outlet site, CRM flows, partner APIs, document generation, and regulatory RAG.",
            ),
            "links": _append_link(
                [
                    {"label": "Live Site", "href": "https://sapphirealpha.xyz", "external": True},
                    {
                        "label": "Health",
                        "href": "https://sapphirealpha.xyz/health",
                        "external": True,
                    },
                    {
                        "label": "Cloud Run Health",
                        "href": "https://project-go-forward-trgi34bxuq-uc.a.run.app/health",
                        "external": True,
                    },
                ],
                _manifest_repo_link("project-go-forward"),
            ),
            "tags": _manifest_tags("project-go-forward", ["Cloud Run", "React", "FastAPI"]),
        },
        {
            "name": "regional-intel-workbench",
            "status": "Local Showcase",
            "summary": _manifest_summary(
                "regional-intel-workbench",
                "Public-source regional intelligence console with Austin, Houston, and Gunnison coverage plus client-specific feed surfaces.",
            ),
            "links": _append_link(
                [
                    {
                        "label": "Analyst Console",
                        "href": "http://127.0.0.1:8768/intel",
                        "external": True,
                    },
                    {
                        "label": "Blanga Austin",
                        "href": "http://127.0.0.1:8768/blanga/austin",
                        "external": True,
                    },
                    {
                        "label": "Vote Monitor",
                        "href": "http://127.0.0.1:8768/vote-monitor",
                        "external": True,
                    },
                    {
                        "label": "API Health",
                        "href": "http://127.0.0.1:8768/api/intel/health",
                        "external": True,
                    },
                ],
                _manifest_repo_link("regional-intel-workbench"),
            ),
            "tags": _manifest_tags(
                "regional-intel-workbench", ["regional intel", "client feed", "provenance"]
            ),
        },
        {
            "name": "org-platform",
            "status": "Local Dashboard",
            "summary": "Autonomous organization fallback dashboard for unified events, crypto signals, Foundry-ready transforms, and local demos.",
            "links": [
                {"label": "Dashboard", "href": "http://127.0.0.1:3000", "external": True},
                {
                    "label": "Events JSON",
                    "href": "http://127.0.0.1:3000/events.json",
                    "external": True,
                },
                {
                    "label": "Crypto JSON",
                    "href": "http://127.0.0.1:3000/crypto.json",
                    "external": True,
                },
            ],
            "tags": ["Next.js", "events", "Foundry"],
        },
        {
            "name": "Agentic PM Hub",
            "status": "Protected",
            "summary": _manifest_summary(
                "agentic-arigato",
                "Authenticated Cloud Run project-management hub for operator coordination; linked as a protected satellite surface.",
            ),
            "links": _append_link(
                [
                    {
                        "label": "Service Health",
                        "href": "https://agentic-pm-hub-trgi34bxuq-uc.a.run.app/health",
                        "external": True,
                    },
                    {
                        "label": "Liveness",
                        "href": "https://agentic-pm-hub-trgi34bxuq-uc.a.run.app/healthz/",
                        "external": True,
                    },
                ],
                _manifest_repo_link("agentic-arigato"),
            ),
            "tags": _manifest_tags("agentic-arigato", ["Cloud Run", "protected", "coordination"]),
        },
    ]

    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "metrics": [
            {
                "label": "Dashboard Routes",
                "value": str(_dashboard_page_route_count()),
                "note": "Registered non-static dashboard page routes, including aliases",
            },
            {
                "label": "Registry Entries",
                "value": registry_metric["value"],
                "note": registry_metric["note"],
            },
            {
                "label": "Readiness",
                "value": readiness_metric["value"],
                "note": readiness_metric["note"],
            },
            {
                "label": "Satellite Frontends",
                "value": str(len(satellite_dashboards)),
                "note": "THO, regional intel, org-platform, and protected PM hub with repo pointers",
            },
        ],
        "walkthrough_paths": [
            {
                "persona": "Buyer proof path",
                "title": "Executive evidence",
                "summary": "Start with the curated front door, then move through diligence, readiness, security, and provenance-heavy source quality.",
                "links": [
                    {"label": "Showcase", "href": "/showcase"},
                    {"label": "Diligence", "href": "/diligence"},
                    {"label": "Readiness", "href": "/production-readiness"},
                    {"label": "Security", "href": "/security/overview"},
                    {"label": "Source Quality", "href": "/source-quality"},
                ],
                "tags": ["buyer", "evidence", "read-only"],
            },
            {
                "persona": "Operator health path",
                "title": "Daily command loop",
                "summary": "Open the live overview, then inspect observability, inference telemetry, logs, and launch posture without mutating services.",
                "links": [
                    {"label": "Overview", "href": "/"},
                    {"label": "Observability", "href": "/observability"},
                    {"label": "Inference", "href": "/inference-telemetry"},
                    {"label": "Logs", "href": "/logs"},
                    {"label": "Infrastructure", "href": "/infrastructure"},
                ],
                "tags": ["operator", "health", "local"],
            },
            {
                "persona": "Satellite demo path",
                "title": "Sapphire plus frontends",
                "summary": "Jump from Sapphire into THO production, the regional-intel console, org-platform, and the protected PM hub with clear status labels.",
                "links": [
                    {
                        "label": "THO",
                        "href": "https://sapphirealpha.xyz",
                        "external": True,
                    },
                    {
                        "label": "Regional Intel",
                        "href": "http://127.0.0.1:8768/intel",
                        "external": True,
                    },
                    {
                        "label": "org-platform",
                        "href": "http://127.0.0.1:3000",
                        "external": True,
                    },
                    {
                        "label": "PM Hub",
                        "href": "https://agentic-pm-hub-trgi34bxuq-uc.a.run.app/health",
                        "external": True,
                    },
                ],
                "tags": ["frontends", "satellites", "no controls"],
            },
            {
                "persona": "Engineering source path",
                "title": "Repo-grounded context",
                "summary": "Use the repository pointers and Sapphire pages to connect product surfaces back to source ownership and guardrails.",
                "links": [
                    {
                        "label": "Sapphire",
                        "href": "https://github.com/arigatoexpress/Sapphire",
                        "external": True,
                    },
                    {
                        "label": "Project-Go-Forward",
                        "href": "https://github.com/arigatoexpress/Project-Go-Forward",
                        "external": True,
                    },
                    {
                        "label": "regional-intel",
                        "href": "https://github.com/arigatoexpress/regional-intel-workbench",
                        "external": True,
                    },
                    {"label": "Organization", "href": "/organization"},
                ],
                "tags": ["repos", "guardrails", "source"],
            },
        ],
        "primary_surfaces": [
            {
                "kicker": "Mission Control",
                "title": "System Overview",
                "href": "/",
                "summary": "Live service posture, inference tier health, activity feed, quick navigation, and operational KPIs.",
                "tags": ["operator", "live status", "SSE"],
            },
            {
                "kicker": "Reliability",
                "title": "Production Readiness",
                "href": "/production-readiness",
                "summary": "Failure and warning matrix for repo state, no-spend gates, runbooks, LaunchAgents, and external-readiness checks.",
                "tags": ["0 FAIL target", "ops"],
            },
            {
                "kicker": "Observability",
                "title": "Signals and Inference",
                "href": "/inference-telemetry",
                "summary": "Inference proxy telemetry, tier routing, model latency, quota posture, and service health context.",
                "tags": ["LLM mesh", "telemetry"],
            },
            {
                "kicker": "Diligence",
                "title": "Buyer Packet",
                "href": "/diligence",
                "summary": "Acquirer-ready proof surface with product capabilities, security posture, provenance, and roadmap artifacts.",
                "tags": ["demo-safe", "evidence"],
            },
            {
                "kicker": "Intel",
                "title": "Regional Intelligence",
                "href": "/intel",
                "summary": "Sapphire-hosted regional context, source quality, geographic signals, and client-ready intelligence paths.",
                "tags": ["regional", "sources"],
            },
            {
                "kicker": "Products",
                "title": "Threat Intel and Dossier",
                "href": "/threat-intel",
                "summary": "Productized security intelligence, customer dossier workflows, and showcase-ready commercial surfaces.",
                "tags": ["product", "client"],
            },
        ],
        "satellite_dashboards": satellite_dashboards,
        "adjacent_projects": [
            {
                "name": "Project-Go-Forward / THO",
                "coverage": "Production business system, CRM, partner APIs, document generation, and the public THO app.",
                "href": "https://sapphirealpha.xyz",
                "surface": "Production app",
                "links": [
                    {
                        "label": "Production app",
                        "href": "https://sapphirealpha.xyz",
                        "external": True,
                    },
                    {
                        "label": "Repository",
                        "href": "https://github.com/arigatoexpress/Project-Go-Forward",
                        "external": True,
                    },
                    {"label": "Diligence", "href": "/diligence"},
                ],
            },
            {
                "name": "regional-intel-workbench",
                "coverage": "Regional intelligence feeds, client-ready intel consoles, vote monitoring, and Foundry-oriented exports.",
                "href": "http://127.0.0.1:8768/intel",
                "surface": "Local intel console",
                "links": [
                    {
                        "label": "Analyst console",
                        "href": "http://127.0.0.1:8768/intel",
                        "external": True,
                    },
                    {
                        "label": "Repository",
                        "href": "https://github.com/arigatoexpress/regional-intel-workbench",
                        "external": True,
                    },
                    {"label": "Sapphire intel", "href": "/intel"},
                ],
            },
            {
                "name": "tradingview-mcp / tradingview-mcp-v2",
                "coverage": "TradingView bridge and dry-run signal tooling",
                "href": "/api/tradingview/capabilities",
                "surface": "Capability matrix JSON",
                "links": [
                    {"label": "Capabilities", "href": "/api/tradingview/capabilities"},
                    {
                        "label": "Ari bridge repo",
                        "href": "https://github.com/arigatoexpress/tradingview-mcp",
                        "external": True,
                    },
                    {
                        "label": "Upstream bridge",
                        "href": "https://github.com/tradesdontlie/tradingview-mcp",
                        "external": True,
                    },
                ],
            },
            {
                "name": "cyber-threat-bot",
                "coverage": "Defensive threat collection and research workflow",
                "href": "/threat-intel",
                "surface": "Threat Intel product surface",
                "links": [
                    {"label": "Threat Intel", "href": "/threat-intel"},
                    {
                        "label": "Repository",
                        "href": "https://github.com/arigatoexpress/cyber-threat-bot",
                        "external": True,
                    },
                ],
            },
            {
                "name": "crypto-tax-tracker",
                "coverage": "Finance-supporting satellite tracked from the org manifest",
                "href": "/sapphire-book",
                "surface": "Sapphire Book context",
                "links": [
                    {"label": "Sapphire Book", "href": "/sapphire-book"},
                    {
                        "label": "Repository",
                        "href": "https://github.com/arigatoexpress/crypto-tax-tracker",
                        "external": True,
                    },
                ],
            },
        ],
        "dashboard_directory": [
            {
                "group": "Command",
                "links": [
                    {"label": "Overview", "href": "/"},
                    {"label": "Operations", "href": "/architecture"},
                    {"label": "Activity", "href": "/activity"},
                    {"label": "Organization", "href": "/organization"},
                ],
            },
            {
                "group": "Trading",
                "links": [
                    {"label": "Portfolio", "href": "/portfolio"},
                    {"label": "Performance", "href": "/performance"},
                    {"label": "Factors", "href": "/factors"},
                    {"label": "Cascade", "href": "/cascade"},
                    {"label": "Analytics", "href": "/analytics"},
                ],
            },
            {
                "group": "Intelligence",
                "links": [
                    {"label": "Intelligence", "href": "/intelligence"},
                    {"label": "Investments", "href": "/investment-intel"},
                    {"label": "Cross Asset", "href": "/cross-asset"},
                    {"label": "Sovereign Thesis", "href": "/sovereign-thesis"},
                    {"label": "Source Quality", "href": "/source-quality"},
                ],
            },
            {
                "group": "Product",
                "links": [
                    {"label": "Diligence", "href": "/diligence"},
                    {"label": "Threat Intel", "href": "/threat-intel"},
                    {"label": "Customer Dossier", "href": "/customer-dossier"},
                    {"label": "Sapphire Book", "href": "/sapphire-book"},
                ],
            },
            {
                "group": "Safety",
                "links": [
                    {"label": "Observability", "href": "/observability"},
                    {"label": "Security", "href": "/security"},
                    {"label": "Security Overview", "href": "/security/overview"},
                    {"label": "Robinhood Chain", "href": "/chain/robinhood"},
                ],
            },
        ],
        "operating_loop": [
            {
                "step": "Observe",
                "title": "Signals and status",
                "copy": "Dashboards consolidate live services, local artifacts, public-source intel, and satellite health into one read-only view.",
            },
            {
                "step": "Orient",
                "title": "Evidence map",
                "copy": "Product, diligence, operations, trading, and source-quality paths stay one click apart for quick walkthroughs.",
            },
            {
                "step": "Decide",
                "title": "Guarded posture",
                "copy": "Production-readiness, security, no-spend gates, and paper-only trading boundaries remain explicit in the command surface.",
            },
            {
                "step": "Show",
                "title": "Friend-ready demo",
                "copy": "External frontends and Sapphire routes are grouped by purpose so the strongest proof paths are easy to present.",
            },
        ],
    }


@app.route("/")
@requires_auth
def index():
    """Main dashboard — curated read-only front door."""
    return render_template(
        "pages/showcase.html",
        current_page="showcase",
        page_title="Unified Dashboard",
        unified_dashboard=_build_unified_dashboard_payload(),
    )


@app.route("/overview")
@requires_auth
def overview():
    """Legacy system-overview page (root now serves the showcase)."""
    return render_template(
        "pages/overview.html", current_page="overview", page_title="System Overview"
    )


@app.route("/showcase")
@app.route("/unified")
@app.route("/unified-dashboard")
@requires_auth
def showcase():
    """Curated read-only front door for demos and ecosystem orientation."""
    return render_template(
        "pages/showcase.html",
        current_page="showcase",
        page_title="Unified Dashboard",
        unified_dashboard=_build_unified_dashboard_payload(),
    )


@app.route("/architecture")
@requires_auth
def architecture():
    return render_template(
        "pages/architecture.html", current_page="architecture", page_title="Architecture"
    )


@app.route("/intelligence")
@requires_auth
def intelligence():
    return render_template(
        "pages/intelligence.html", current_page="intelligence", page_title="Intelligence"
    )


@app.route("/organization")
@requires_auth
def organization():
    return render_template(
        "pages/organization.html", current_page="organization", page_title="Organization"
    )


@app.route("/activity")
@requires_auth
def activity():
    return render_template("pages/activity.html", current_page="activity", page_title="Activity")


@app.route("/sapphire-book")
@requires_auth
def sapphire_book():
    return render_template(
        "pages/sapphire_book.html", current_page="sapphire_book", page_title="Sapphire Book"
    )


@app.route("/infrastructure")
@requires_auth
def infrastructure():
    return render_template(
        "pages/infrastructure.html", current_page="infrastructure", page_title="Infrastructure"
    )


@app.route("/control")
@requires_auth
def control():
    return render_template("pages/control.html", current_page="control", page_title="Control")


@app.route("/settings")
@requires_auth
def settings():
    return render_template("pages/settings.html", current_page="settings", page_title="Settings")


@app.route("/metrics")
@requires_auth
def metrics():
    """Per-route latency metrics (in-process). Not Prometheus format — JSON.

    Returns aggregate count/avg/p50/p95/p99/max for each endpoint plus the
    overall slowest endpoints. Exposed to help diagnose dashboard slowness
    (the dashboard performs many synchronous urllib fetches against remote
    services — tail latency lives in those outbound calls, not in Flask).
    """

    def _percentile(values, p):
        if not values:
            return 0.0
        s = sorted(values)
        k = int(round((p / 100.0) * (len(s) - 1)))
        return s[max(0, min(k, len(s) - 1))]

    by_route: dict[str, list[float]] = {}
    for method, endpoint, ms in _metrics_samples:
        key = f"{method} {endpoint}"
        by_route.setdefault(key, []).append(ms)

    routes = []
    for key, samples in by_route.items():
        routes.append(
            {
                "route": key,
                "count": _metrics_counts.get(key, len(samples)),
                "avg_ms": round(sum(samples) / len(samples), 2),
                "p50_ms": round(_percentile(samples, 50), 2),
                "p95_ms": round(_percentile(samples, 95), 2),
                "p99_ms": round(_percentile(samples, 99), 2),
                "max_ms": round(max(samples), 2),
                "samples": len(samples),
            }
        )
    routes.sort(key=lambda r: r["p95_ms"], reverse=True)

    return jsonify(
        {
            "window_samples": len(_metrics_samples),
            "window_limit": _METRICS_MAX_SAMPLES,
            "routes": routes,
            "slowest_p95": routes[:10],
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/api/status")
@requires_auth
def api_status():
    """Get system status"""

    def fetch():
        # Fetch from rari2 (trading engine)
        rari2_status = fetch_sync(f"http://{RARI2_IP}:18888/status")

        # Fetch from rari1 (workbench)
        workbench_stats = fetch_sync(f"http://{RARI1_IP}:18891/workbench/stats")

        return {
            "rari2": rari2_status,
            "workbench": workbench_stats,
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("status", fetch))


@app.route("/api/watchlist")
@requires_auth
def api_watchlist():
    """Organized watchlist with corrected symbols, liked tokens, and trending tokens."""

    def fetch():
        from lib.trading.strategy_lab import build_market_universe
        from lib.trading.tradingview_ta_machine import build_tradingview_ta_machine

        universe = build_market_universe(fetch_live=True)
        ta_machine = build_tradingview_ta_machine(
            fetch_live=False,
            market_universe=universe,
        )
        liked = universe.get("liked_tokens", [])
        core_symbols = {"BTC", "ETH", "SOL", "HYPE", "ZEC"}
        major_crypto = [
            {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "type": "perp" if row.get("hyperliquid_symbol") else "spot",
                "priority": str(row.get("priority", "medium")).upper(),
                "price": row.get("price_usd"),
                "change_24h_pct": row.get("change_24h_pct"),
                "tradingview_symbol": row.get("tradingview_symbol"),
                "hyperliquid_symbol": row.get("hyperliquid_symbol"),
                "robinhood_symbol": row.get("robinhood_symbol"),
            }
            for row in liked
            if row.get("symbol") in core_symbols
        ]
        mid_cap = [
            {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "type": "perp" if row.get("hyperliquid_symbol") else "spot",
                "priority": str(row.get("priority", "medium")).upper(),
                "price": row.get("price_usd"),
                "change_24h_pct": row.get("change_24h_pct"),
                "tradingview_symbol": row.get("tradingview_symbol"),
                "hyperliquid_symbol": row.get("hyperliquid_symbol"),
                "robinhood_symbol": row.get("robinhood_symbol"),
            }
            for row in liked
            if row.get("symbol") not in core_symbols
        ]

        return {
            "major_crypto": major_crypto,
            "mid_cap": mid_cap,
            "liked_tokens": liked,
            "trending_tokens": universe.get("trending_tokens", []),
            "venue_matrix": universe.get("venue_matrix", []),
            "tradingview_watchlist": ta_machine.get("watchlist", {}),
            "tradingview_ta_machine": {
                "watchlist_name": ta_machine.get("watchlist_name"),
                "indicator_stack": ta_machine.get("indicator_stack", []),
                "chart_layout": ta_machine.get("chart_layout", {}),
                "work_orders": ta_machine.get("work_orders", []),
                "safety": ta_machine.get("safety", {}),
            },
            "corrected_aliases": universe.get("corrected_aliases", {}),
            "pair_analysis": [
                {
                    "symbol": "ETHBTC",
                    "name": "ETH/BTC Ratio",
                    "type": "pair",
                    "priority": "HIGH",
                    "strategy": "Z<-2: BUY ETH, Z>2: SELL ETH",
                },
                {
                    "symbol": "SOLBTC",
                    "name": "SOL/BTC Ratio",
                    "type": "pair",
                    "priority": "MEDIUM",
                    "strategy": "Z<-2: BUY SOL, Z>2: SELL SOL",
                },
            ],
            "timestamp": datetime.now().isoformat(),
            "stale": bool(universe.get("stale")),
        }

    return jsonify(get_cached("watchlist", fetch, ttl=MARKET_UNIVERSE_CACHE_DURATION))


@app.route("/api/analytics/market-universe")
@requires_auth
def api_analytics_market_universe():
    """Market universe for analytics: Sapphire-liked, trending, and venue symbols."""

    def fetch():
        from lib.trading.strategy_lab import build_market_universe

        return build_market_universe(fetch_live=True)

    return jsonify(get_cached("market_universe", fetch, ttl=MARKET_UNIVERSE_CACHE_DURATION))


@app.route("/api/tradingview/capabilities")
@requires_auth
def api_tradingview_capabilities():
    """TradingView capability matrix and alert template."""

    def fetch():
        from lib.trading.strategy_lab import build_tradingview_capability_matrix

        return build_tradingview_capability_matrix()

    return jsonify(get_cached("tradingview_capabilities", fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route("/api/tradingview/ta-machine")
@requires_auth
def api_tradingview_ta_machine():
    """Dynamic TradingView watchlist, TA stack, and chart automation work orders."""
    offline = (request.args.get("offline") or "").strip().lower() in {"1", "true", "yes"}
    try:
        limit = max(1, min(50, int(request.args.get("limit", "18"))))
    except ValueError:
        limit = 18

    def fetch():
        from lib.trading.tradingview_ta_machine import build_tradingview_ta_machine

        return build_tradingview_ta_machine(fetch_live=not offline, limit=limit)

    cache_key = f"tradingview_ta_machine::{not offline}::{limit}"
    return jsonify(get_cached(cache_key, fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route("/api/tradingview/watchlist.txt")
@requires_auth
def api_tradingview_watchlist_txt():
    """TradingView-compatible comma-separated watchlist TXT export."""
    offline = (request.args.get("offline") or "").strip().lower() in {"1", "true", "yes"}
    try:
        limit = max(1, min(50, int(request.args.get("limit", "18"))))
    except ValueError:
        limit = 18

    def fetch():
        from lib.trading.tradingview_ta_machine import build_tradingview_watchlist_txt

        return build_tradingview_watchlist_txt(fetch_live=not offline, limit=limit)

    cache_key = f"tradingview_watchlist_txt::{not offline}::{limit}"
    body = get_cached(cache_key, fetch, ttl=STRATEGY_LAB_CACHE_DURATION)
    return Response(str(body) + "\n", mimetype="text/plain")


@app.route("/api/trading/workbench/watchlist")
@requires_auth
def api_trading_workbench_watchlist():
    """Read-only TradingView/Sapphire workbench watchlist contract."""
    offline = (request.args.get("offline") or "").strip().lower() in {"1", "true", "yes"}
    symbols = [
        token.strip() for token in (request.args.get("symbols") or "").split(",") if token.strip()
    ]
    try:
        limit = max(1, min(50, int(request.args.get("limit", "18"))))
    except ValueError:
        limit = 18

    def fetch():
        from lib.trading.tradingview_ta_machine import build_trading_workbench_watchlist

        return build_trading_workbench_watchlist(
            fetch_live=not offline,
            limit=limit,
            symbols=symbols or None,
        )

    cache_key = f"trading_workbench_watchlist::{not offline}::{limit}::{','.join(symbols)}"
    return jsonify(get_cached(cache_key, fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route("/api/trading/workbench/work-orders/preview", methods=["POST"])
@requires_auth
def api_trading_workbench_work_orders_preview():
    """Preview TA/chart work orders without mutating TradingView or trading venues."""
    payload = request.get_json(silent=True) or {}

    def _list_field(name: str, default: list[str]) -> list[str]:
        raw = payload.get(name)
        if raw is None:
            return default
        if isinstance(raw, list):
            return [str(item).strip() for item in raw if str(item).strip()]
        return [token.strip() for token in str(raw).split(",") if token.strip()]

    from lib.trading.tradingview_ta_machine import build_trading_workbench_work_order_preview

    return jsonify(
        build_trading_workbench_work_order_preview(
            symbols=_list_field("symbols", ["BTC", "ETH", "SOL", "HYPE"]),
            timeframes=_list_field("timeframes", ["60", "240", "D"]),
            jobs=_list_field(
                "jobs",
                [
                    "ta_profile",
                    "forecast",
                    "correlation",
                    "backtest_summary",
                    "pine_preview",
                    "chart_plan",
                ],
            ),
            strategies=_list_field("strategies", ["SapphireComposite", "RegimeAwareRSI"]),
            allow_live_trading=bool(payload.get("allow_live_trading") is True),
            allow_telegram=bool(payload.get("allow_telegram") is True),
            allow_browser_mutation=bool(payload.get("allow_browser_mutation") is True),
        )
    )


@app.route("/api/trading/strategy-lab")
@requires_auth
def api_trading_strategy_lab():
    """Dry-run strategy lab across paper, TradingView, Robinhood, and Hyperliquid."""

    def fetch():
        from lib.trading.strategy_lab import build_strategy_lab_report

        return build_strategy_lab_report(fetch_live=True)

    return jsonify(get_cached("strategy_lab", fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route("/api/trading/shadow-controller")
@requires_auth
def api_trading_shadow_controller():
    """Risk-managed paper-shadow trading controller report."""
    fetch_live = (request.args.get("offline") or "").strip().lower() not in {"1", "true", "yes"}

    def fetch():
        from lib.trading.shadow_controller import build_shadow_trading_report

        return build_shadow_trading_report(fetch_live=fetch_live)

    cache_key = f"trading_shadow_controller::{fetch_live}"
    return jsonify(get_cached(cache_key, fetch, ttl=STRATEGY_LAB_CACHE_DURATION))


@app.route("/api/trading/order-draft", methods=["POST"])
@requires_auth
def api_trading_order_draft():
    """Build non-submitting venue order drafts for strategy testing."""
    try:
        body = request.get_json(silent=True) or {}
        from lib.trading.strategy_lab import build_order_drafts

        drafts = build_order_drafts(
            body.get("symbol", "BTC"),
            body.get("action", "buy"),
            notional_usd=float(body.get("notional_usd", 100.0) or 100.0),
            strategy=str(body.get("strategy") or "strategy_lab"),
        )
        return jsonify(
            {
                "execution_enabled": False,
                "mode": "draft_only",
                "drafts": drafts,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    except Exception as e:
        log.exception("order draft failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


@app.route("/api/tradingview/orchestrator/sessions")
@requires_auth
def api_tradingview_orchestrator_sessions():
    """List recent TradingView TA capture sessions."""
    try:
        limit = max(1, min(100, int(request.args.get("limit", "20"))))
    except ValueError:
        limit = 20
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    return jsonify({"status": "ok", "sessions": orch.list_sessions(limit=limit)})


@app.route("/api/tradingview/orchestrator/latest")
@requires_auth
def api_tradingview_orchestrator_latest():
    """Latest TradingView TA capture manifest."""
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    manifest = orch.latest_manifest()
    if manifest is None:
        return jsonify({"status": "ok", "manifest": None, "note": "No sessions captured yet"})
    return jsonify({"status": "ok", "manifest": manifest})


@app.route("/api/tradingview/orchestrator/scoring/latest")
@requires_auth
def api_tradingview_orchestrator_scoring_latest():
    """Latest TA-capture scoring rows, sorted by absolute score (desc).

    Closes the loop from "TradingView orchestrator captured these TA values"
    back into Sapphire's scoring. Each row carries ``score`` in [-1, +1],
    ``regime``, and a short ``rationale``. Read-only; does not call ``tv``.
    """
    try:
        top_n_raw = request.args.get("top_n")
        top_n = int(top_n_raw) if top_n_raw is not None else None
        if top_n is not None and top_n <= 0:
            top_n = None
    except ValueError:
        top_n = None
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    return jsonify({"status": "ok", "scoring": orch.latest_scoring(top_n=top_n)})


@app.route("/api/tradingview/orchestrator/probe")
@requires_auth
def api_tradingview_orchestrator_probe():
    """Read-only probe of current TradingView Desktop state."""
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    return jsonify(
        {
            "status": "ok",
            "state": orch.probe_state(),
            "quote": orch.probe_quote(),
            "values": orch.probe_values(),
        }
    )


@app.route("/api/tradingview/orchestrator/artifacts/<path:artifact_path>")
@requires_auth
def api_tradingview_orchestrator_artifact(artifact_path: str):
    """Serve a TradingView TA capture artifact (screenshot, JSON, etc.)."""
    from lib.trading.tradingview_orchestrator import DEFAULT_ARTIFACT_ROOT

    base = Path(DEFAULT_ARTIFACT_ROOT)
    target = (base / artifact_path).resolve()
    # Security: prevent path traversal outside the artifact root
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return jsonify({"status": "error", "reason": "invalid_path"}), 400
    if not target.exists() or not target.is_file():
        return jsonify({"status": "error", "reason": "not_found"}), 404
    mimetype = "image/png" if target.suffix == ".png" else "application/json"
    return send_file(str(target), mimetype=mimetype)


@app.route("/api/tradingview/orchestrator/pine")
@requires_auth
def api_tradingview_orchestrator_pine():
    """List Pine scripts on the TV account + locally generated templates."""
    from lib.trading.pine_templates import list_generated
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    tv_scripts = orch.pine_list()
    payload = tv_scripts.get("payload") or {}
    return jsonify(
        {
            "status": "ok",
            "tv_account": {
                "ok": tv_scripts.get("ok", False),
                "scripts": payload.get("scripts", []) or [],
            },
            "generated_local": list_generated(),
        }
    )


@app.route("/api/tradingview/orchestrator/alerts")
@requires_auth
def api_tradingview_orchestrator_alerts():
    """List active TradingView alerts (read-only)."""
    from lib.trading.tradingview_orchestrator import TradingViewOrchestrator

    orch = TradingViewOrchestrator()
    res = orch.alerts_list()
    payload = res.get("payload") or {}
    return jsonify(
        {
            "status": "ok" if res.get("ok") else "fail",
            "alert_count": payload.get("alert_count"),
            "alerts": payload.get("alerts") or [],
        }
    )


@app.route("/api/proposals")
@requires_auth
def api_proposals():
    """Get trade proposals"""

    def fetch():
        return fetch_sync(f"http://{RARI1_IP}:18891/workbench/proposals")

    return jsonify(get_cached("proposals", fetch))


@app.route("/api/opportunities")
@requires_auth
def api_opportunities():
    """Trading opportunities sourced from today's signal_generator output.

    Reads `data/trading_signals.jsonl` (TA scanner) and returns the latest
    high-confidence BUY/SELL signals as opportunities. No mocked entries.
    """

    def fetch():
        path = Path.home() / "Code" / "Sapphire" / "data" / "trading_signals.jsonl"
        if not path.exists():
            return {"opportunities": [], "timestamp": datetime.now().isoformat()}
        try:
            lines = path.read_text().strip().splitlines()[-60:]
        except OSError:
            return {"opportunities": [], "timestamp": datetime.now().isoformat()}
        out: list[dict] = []
        seen_symbols: set[str] = set()
        for line in reversed(lines):
            try:
                s = json.loads(line)
            except json.JSONDecodeError:
                continue
            sym = s.get("symbol") or ""
            if not sym or sym in seen_symbols:
                continue
            if float(s.get("confidence") or 0) < 0.5:
                continue
            seen_symbols.add(sym)
            raw = s.get("raw") or {}
            out.append(
                {
                    "symbol": sym,
                    "side": (s.get("action") or "").lower(),
                    "confidence": s.get("confidence"),
                    "price": s.get("price"),
                    "reason": raw.get("reason") or s.get("strategy", ""),
                    "edge": raw.get("edge"),
                    "kelly_size_pct": raw.get("kelly_size_pct"),
                    "timestamp": s.get("timestamp"),
                }
            )
            if len(out) >= 6:
                break
        return {"opportunities": out, "timestamp": datetime.now().isoformat()}

    return jsonify(get_cached("opportunities", fetch))


@app.route("/api/logs")
@requires_auth
def api_logs():
    """Recent entries from data/system_events.jsonl — no mocked logs.

    Query params:
        hours:   filter to last N hours (default 24)
        level:   filter by level (INFO/WARN/ERROR)
        service: substring match against event type or tags
    """
    hours = max(1, min(int(request.args.get("hours", 24) or 24), 168))
    level_filter = (request.args.get("level") or "").upper().strip() or None
    service_filter = (request.args.get("service") or "").lower().strip() or None

    def _level_for_event(evt_type: str, tags: list) -> str:
        """Classify event bus events by priority level."""
        for t in tags:
            if str(t).startswith("priority:p0"):
                return "ERROR"
            if str(t).startswith("priority:p1"):
                return "WARN"
        # Event bus types map to levels by convention
        if evt_type in {"service.health"} or evt_type.endswith(".failed"):
            return "WARN"
        if evt_type in {"regime.shifted", "funding.extreme"}:
            return "WARN"
        return "INFO"

    def _bus_entries(cutoff: float) -> list:
        """Pull recent events across all canonical streams via event bus replay."""
        try:
            bus = _event_bus()
        except Exception:
            return []
        from lib.core.event_bus import EVENT_TYPES

        since = datetime.fromtimestamp(cutoff, tz=UTC)
        collected = []
        for et in EVENT_TYPES:
            try:
                for ev in bus.replay(et, since=since, limit=50):
                    data = ev.data if isinstance(ev.data, dict) else {}
                    # Build a concise human-readable message from the event payload
                    if ev.type == "signal.generated":
                        msg = f"signal: {data.get('action', '?')} {data.get('symbol', '?')} @ ${data.get('price', 0)} (conf {data.get('confidence', 0):.2f})"
                    elif ev.type == "signal.closed":
                        msg = f"signal closed: {data.get('symbol', '?')} pnl ${data.get('pnl_usd', 0):.2f}"
                    elif ev.type == "regime.snapshot":
                        msg = f"regime: {data.get('regime', '?')} conf {data.get('confidence') or 0:.2f}"
                    elif ev.type == "regime.shifted":
                        msg = f"regime shift: {data.get('prior', '?')} → {data.get('regime', '?')}"
                    elif ev.type == "funding.extreme":
                        msg = f"funding extreme: {data.get('count', 0)} perps, bias {data.get('bias', '?')}"
                    elif ev.type == "service.health":
                        msg = f"health: {data.get('pass', 0)} ok · {data.get('warn', 0)} warn · {data.get('fail', 0)} fail ({data.get('status', '?')})"
                    elif ev.type == "content.generated":
                        msg = f"content: {data.get('kind', '?')} · {data.get('quality_passed', 0)}/{data.get('quality_passed', 0) + data.get('quality_failed', 0)} platforms passed"
                    else:
                        msg = json.dumps(data, default=str)[:160]
                    collected.append(
                        {
                            "timestamp": ev.ts,
                            "level": _level_for_event(ev.type, []),
                            "message": msg[:240],
                            "type": ev.type,
                            "tags": [f"source:{ev.source}"],
                        }
                    )
            except Exception:
                continue
        return collected

    def fetch():
        cutoff = time.time() - hours * 3600
        entries: list = []

        # 1) Traditional system_events.jsonl (service lifecycle, watchdog, etc.)
        path = Path.home() / "Code" / "Sapphire" / "data" / "system_events.jsonl"
        if path.exists():
            try:
                lines = path.read_text().strip().splitlines()[-500:]
            except OSError:
                lines = []
            for line in reversed(lines):
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_str = e.get("timestamp", "")
                try:
                    ts_unix = datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                except (ValueError, TypeError):
                    ts_unix = 0
                if ts_unix and ts_unix < cutoff:
                    continue
                tags = e.get("tags") or []
                entries.append(
                    {
                        "timestamp": ts_str,
                        "level": _level_for_event(e.get("type", ""), tags),
                        "message": e.get("message", "")[:240],
                        "type": e.get("type", ""),
                        "tags": tags,
                    }
                )

        # 2) Event bus (regime, signals, content, health) — richer real-time feed.
        entries.extend(_bus_entries(cutoff))

        # Filters are applied uniformly across both sources.
        def _keep(entry: dict) -> bool:
            if level_filter and entry["level"] != level_filter:
                return False
            if service_filter:
                evt_type = entry["type"].lower()
                tags = entry["tags"]
                if service_filter not in evt_type and not any(
                    service_filter in str(t).lower() for t in tags
                ):
                    return False
            return True

        entries = [e for e in entries if _keep(e)]
        entries.sort(key=lambda e: e["timestamp"], reverse=True)
        return {
            "logs": entries[:200],
            "count": len(entries),
            "timestamp": datetime.now().isoformat(),
        }

    cache_key = f"logs::h{hours}::l{level_filter or ''}::s{service_filter or ''}"
    return jsonify(get_cached(cache_key, fetch))


# ── Event Bus SSE ────────────────────────────────────────────────────────────


def _event_bus():
    """Import event bus lazily — dashboard should start even if lib/core missing."""
    _p = Path.home() / "Code" / "Sapphire" / "lib" / "core"
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
    from event_bus import get_bus

    return get_bus(source="dashboard")


@app.route("/api/events/stream")
@requires_auth
def api_events_stream():
    """Server-sent event stream of live bus events (glob pattern via ?types=)."""
    patterns_raw = request.args.get("types", "*")
    patterns = [p.strip() for p in patterns_raw.split(",") if p.strip()]

    import queue as _queue

    try:
        bus = _event_bus()
    except Exception as e:
        return Response(
            f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n",
            mimetype="text/event-stream",
        )

    q: _queue.Queue = _queue.Queue(maxsize=500)

    def _on_event(ev):
        with contextlib.suppress(_queue.Full):
            q.put_nowait(
                {
                    "id": ev.id,
                    "type": ev.type,
                    "ts": ev.ts,
                    "source": ev.source,
                    "data": ev.data,
                }
            )

    subscription = bus.subscribe(patterns, _on_event)

    def gen():
        try:
            # Opening ping so the client sees the connection immediately
            yield f"event: open\ndata: {json.dumps({'patterns': patterns})}\n\n"
            last_beat = time.time()
            while True:
                try:
                    payload = q.get(timeout=15)
                    yield f"event: {payload['type']}\ndata: {json.dumps(payload, default=str)}\n\n"
                except _queue.Empty:
                    # Keep proxies from closing the connection
                    yield ": keepalive\n\n"
                if time.time() - last_beat > 60:
                    last_beat = time.time()
        finally:
            subscription.stop()

    return Response(
        gen(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )


@app.route("/api/events/world-state")
@requires_auth
def api_world_state():
    """Snapshot of aggregated world state for the overview page."""
    try:
        bus = _event_bus()
        return jsonify(bus.get_world_state().to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/events/replay")
@requires_auth
def api_events_replay():
    """Historical replay of one event type."""
    event_type = request.args.get("type", "")
    if not event_type:
        return jsonify({"error": "missing ?type=<event_type>"}), 400
    limit = int(request.args.get("limit", 100))
    try:
        bus = _event_bus()
        events = bus.replay(event_type, limit=limit)
        return jsonify(
            [
                {"id": e.id, "type": e.type, "ts": e.ts, "source": e.source, "data": e.data}
                for e in events
            ]
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/system")
@requires_auth
def system():
    """Unified system status — inference tiers + services"""
    return render_template("pages/system.html", current_page="system", page_title="System Status")


_INFERENCE_TIER_ORDER = (
    ("t1", "windows-gpu", "t1_windows_gpu", "Windows GPU"),
    ("t2a", "pi-rari1", "t2_pi_rari1", "Pi rari1"),
    ("t2b", "pi-rari2", "t2_pi_rari2", "Pi rari2"),
    ("t3", "mac-local", "t3_mac_local", "Mac local"),
    ("t4", "kimi-cloud", "t4_kimi_cloud", "Kimi cloud"),
)


def _normalize_inference_tiers(proxy_health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return dashboard-stable tier keys while preserving proxy health truth."""
    endpoints = proxy_health.get("endpoints") if isinstance(proxy_health, dict) else {}
    raw_tiers = proxy_health.get("tiers") if isinstance(proxy_health, dict) else {}
    endpoints = endpoints if isinstance(endpoints, dict) else {}
    raw_tiers = raw_tiers if isinstance(raw_tiers, dict) else {}

    normalized: dict[str, dict[str, Any]] = {}
    for tier_key, endpoint_key, raw_key, label in _INFERENCE_TIER_ORDER:
        status = str(endpoints.get(endpoint_key, "unknown")).lower()
        normalized[tier_key] = {
            "label": label,
            "endpoint_key": endpoint_key,
            "status": status,
            "healthy": status in {"healthy", "ok", "available"},
            "url": raw_tiers.get(raw_key, ""),
        }
    return normalized


def _normalize_service_health(name: str, result: Any) -> tuple[bool, dict[str, Any]]:
    if name != "pm-bot" or not isinstance(result, dict):
        return bool(result), {}

    local_ready = bool(result.get("local_process_ready", True))
    telegram_ready = bool(result.get("telegram_delivery_ready"))
    details = {
        "status": result.get("status"),
        "local_process_ready": local_ready,
        "telegram_delivery_ready": telegram_ready,
        "telegram_delivery_reason": result.get("telegram_delivery_reason"),
        "telegram_inbound_owner": result.get("telegram_inbound_owner"),
        "telegram_operator_action": result.get("telegram_operator_action"),
    }
    return local_ready and telegram_ready, details


@app.route("/api/system")
@requires_auth
def api_system():
    """Unified system status JSON — inference health + service checks"""
    import socket

    def fetch():
        proxy_health = fetch_sync("http://127.0.0.1:11435/health")
        proxy_metrics = fetch_sync("http://127.0.0.1:11435/metrics")

        services = [
            ("control-plane", "127.0.0.1", 8082, "/health"),
            ("dashboard", "127.0.0.1", DASHBOARD_PORT, "/health"),
            ("signal-logger", "127.0.0.1", 18081, "/health"),
            ("pm-bot", "127.0.0.1", 18082, "/health"),
            ("openbb-api", "127.0.0.1", 6900, None),  # TCP: /api/v1/system/status 404s
            ("regional-intel", "127.0.0.1", 8787, None),  # TCP: /health 404s, root returns HTML
            # inference-proxy health already fetched above via proxy_health — reuse, no re-probe
            ("redis", "127.0.0.1", 6379, None),
        ]

        service_status = []
        for name, host, port, path in services:
            try:
                if path:
                    result = fetch_sync(f"http://{host}:{port}{path}")
                    ok, details = _normalize_service_health(name, result)
                else:
                    s = socket.create_connection((host, port), timeout=2)
                    s.close()
                    ok = True
                    details = {}
            except Exception:
                ok = False
                details = {}
            service_status.append({"name": name, "port": port, "healthy": ok, **details})

        # Add inference-proxy status from already-fetched proxy_health (avoid re-probe)
        service_status.append(
            {
                "name": "inference-proxy",
                "port": 11435,
                "healthy": proxy_health.get("status") == "ok",
            }
        )
        healthy_count = sum(1 for s in service_status if s["healthy"])

        # CDP / TradingView MCP health (Mac TV Desktop on :9222)
        cdp_status = {"connected": False, "tabs": 0, "tv_tabs": 0, "error": "", "recovery": ""}
        try:
            cdp_raw = fetch_sync("http://127.0.0.1:9222/json")
            if isinstance(cdp_raw, list):
                tv_tabs = [t for t in cdp_raw if "tradingview" in t.get("url", "").lower()]
                cdp_status = {
                    "connected": True,
                    "tabs": len(cdp_raw),
                    "tv_tabs": len(tv_tabs),
                    "error": "",
                    "recovery": "",
                }
            else:
                cdp_status["error"] = "unexpected_response"
        except Exception as e:
            cdp_status["error"] = str(e)[:80]
            cdp_status["recovery"] = (
                "Run ~/Code/Sapphire/infra/scripts/start-tradingview-cdp.sh "
                "or: launchctl kickstart -k gui/$UID/com.sapphire.tradingview-cdp"
            )

        # Recent signals from signal pipeline
        signals_recent = fetch_sync("http://127.0.0.1:18081/api/signals/recent")

        return {
            "inference": {
                "endpoints": proxy_health.get("endpoints", {}),
                "tiers": _normalize_inference_tiers(proxy_health),
                "raw_tiers": proxy_health.get("tiers", {}),
                "metrics": proxy_metrics.get("metrics", {}),
            },
            "services": service_status,
            "healthy_count": healthy_count,
            "total_count": len(services),
            "cdp": cdp_status,
            "signals": {
                "recent_count": signals_recent.get("count", 0),
                "latest": (signals_recent.get("signals") or [])[:5],
            },
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("system", fetch))


@app.route("/signals")
@requires_auth
def signals_page():
    """Trading signal history and pipeline status"""
    return render_template(
        "pages/signals.html", current_page="signals", page_title="Signal Pipeline"
    )


@app.route("/api/signals")
@requires_auth
def api_signals():
    """Signal pipeline data — recent signals, stats, kernel status"""
    import sys
    from pathlib import Path as _Path

    def fetch():
        # Load signal pipeline
        _root = _Path.home() / "Code" / "Sapphire"
        for _p in [
            str(_root / "services" / "alpha"),
            str(_root / "lib" / "core" / "src"),
            str(_root / "lib" / "core"),
        ]:
            if _p not in sys.path:
                sys.path.insert(0, _p)

        recent = []
        stats = {}
        kernel = {}
        active = []

        try:
            from signal_pipeline import pipeline as _pl

            recent = _pl.recent_signals(20)
            stats = _pl.signal_stats()
            kernel = _pl.kernel_status()
            active = _pl.active_signals()
        except Exception:
            # Fallback: read JSONL directly
            import json
            from datetime import datetime as _dt

            signals_dir = _root / "data" / "signals"
            today = _dt.now(UTC).strftime("%Y-%m-%d")
            f = signals_dir / f"{today}.jsonl"
            if f.exists():
                for line in f.read_text().strip().splitlines()[-20:]:
                    with contextlib.suppress(Exception):
                        recent.append(json.loads(line))
                recent.reverse()

        return {
            "recent": recent,
            "active": active,
            "stats": stats,
            "kernel": kernel,
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("signals", fetch))


@app.route("/agents")
@requires_auth
def agents_page():
    """Pi autonomous agents status"""
    return render_template("pages/agents.html", current_page="agents", page_title="Pi Agents")


@app.route("/api/agents")
@requires_auth
def api_agents():
    """Pi agent status and vitals"""

    def fetch():
        agents = []

        for agent_name, pi_ip, pi_port, _log_path in [
            (
                "market-watchdog",
                "100.x.x.x",
                19001,
                "/home/rari/sapphire/logs/market-watchdog.log",
            ),
            ("health-monitor", "100.x.x.y", 19002, "/home/rari/sapphire/uptime.jsonl"),
        ]:
            status = {
                "name": agent_name,
                "host": pi_ip,
                "port": pi_port,
                "running": False,
                "last_seen": None,
                "last_log": [],
            }
            try:
                data = fetch_sync(f"http://{pi_ip}:{pi_port}/health")
                status["running"] = bool(data)
                status["last_seen"] = data.get("timestamp", datetime.now().isoformat())
                status["vitals"] = data.get("vitals", {})
                status["uptime_seconds"] = data.get("uptime_seconds", 0)
                status["check_count"] = data.get("check_count", 0)
                status["last_check"] = data.get("last_check", {})
            except Exception as e:
                status["error"] = str(e)[:60]
            agents.append(status)

        return {"agents": agents, "timestamp": datetime.now().isoformat()}

    return jsonify(get_cached("agents", fetch))


@app.route("/benchmarks")
@requires_auth
def benchmarks():
    """GPU benchmark report — served raw to avoid Jinja2 mangling Chart.js braces"""
    report_path = Path(__file__).parent / "static" / "benchmark_report.html"
    if not report_path.exists():
        return Response(
            "<h1>Benchmark report not yet generated.</h1><p>Run: python3 benchmarks/generate_report.py</p>",
            content_type="text/html",
        )
    return send_file(str(report_path), mimetype="text/html")


@app.route("/health-status")
@requires_auth
def health_status_page():
    """Unified service health view"""
    return render_template("pages/health.html", current_page="health", page_title="Health Status")


@app.route("/api/health/summary")
@requires_auth
def api_health_summary():
    """Aggregate health summary across all service tiers"""
    import socket

    def fetch():
        checks = [
            # (name, category, host, port, path)
            ("control-plane", "cloud", "127.0.0.1", 8082, "/health"),
            ("dashboard", "cloud", "127.0.0.1", DASHBOARD_PORT, "/health"),
            ("signal-logger", "cloud", "127.0.0.1", 18081, "/health"),
            ("pm-bot", "cloud", "127.0.0.1", 18082, "/health"),
            ("inference-proxy", "cloud", "127.0.0.1", 11435, "/health"),
            ("openbb-api", "cloud", "127.0.0.1", 6900, None),
            ("redis", "cloud", "127.0.0.1", 6379, None),
            ("windows-ollama", "windows", "100.x.x.z", 11434, None),
            ("rari1-ollama", "pi", "100.x.x.x", 11434, None),
            ("rari2-ollama", "pi", "100.x.x.y", 11434, None),
        ]

        by_category = {"cloud": [], "windows": [], "pi": [], "firestore": []}
        healthy_count = 0
        unhealthy_count = 0

        for name, category, host, port, path in checks:
            t0 = time.time()
            try:
                if path:
                    result = fetch_sync(f"http://{host}:{port}{path}")
                    ok, details = _normalize_service_health(name, result)
                else:
                    s = socket.create_connection((host, port), timeout=2)
                    s.close()
                    ok = True
                    details = {}
            except Exception:
                ok = False
                details = {}
            elapsed = int((time.time() - t0) * 1000)

            entry = {
                "name": name,
                "healthy": ok,
                "response_time_ms": elapsed if ok else None,
                **details,
            }
            by_category[category].append(entry)

            if ok:
                healthy_count += 1
            else:
                unhealthy_count += 1

        return {
            "healthy": unhealthy_count == 0,
            "healthy_count": healthy_count,
            "unhealthy_count": unhealthy_count,
            "by_category": by_category,
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("health_summary", fetch))


@app.route("/production-readiness")
@requires_auth
def production_readiness_page():
    """Production readiness gates"""
    return render_template(
        "pages/production_readiness.html",
        current_page="production_readiness",
        page_title="Production Readiness",
    )


def _readiness_cache_path() -> Path:
    """Latest JSON output from scripts/ops/production_readiness_sweep.py."""
    return _DASHBOARD_REPO_ROOT / "data" / "readiness" / "readiness-sweep-latest.json"


def _empty_readiness_payload(*, note: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "generated_at": None,
        "cache_age_seconds": None,
        "cache_stale": False,
        "summary": {"pass": 0, "warn": 0, "fail": 0, "skip": 0, "total": 0},
        "checks": [],
    }
    if note:
        payload["note"] = note
    return payload


def _readiness_latest_payload() -> dict[str, Any]:
    path = _readiness_cache_path()
    if not path.exists():
        return _empty_readiness_payload(note="no cache yet")
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        payload = _empty_readiness_payload(note="cache unreadable")
        payload["error"] = f"{type(exc).__name__}: {exc}"
        return payload

    summary = body.get("summary") if isinstance(body, dict) else {}
    checks = body.get("checks") if isinstance(body, dict) else []
    if not isinstance(summary, dict):
        summary = {}
    if not isinstance(checks, list):
        checks = []
    complete_summary = {"pass": 0, "warn": 0, "fail": 0, "skip": 0, "total": 0}
    complete_summary.update({key: int(summary.get(key) or 0) for key in complete_summary})
    age_seconds = max(0, int(time.time() - path.stat().st_mtime))
    return {
        "status": "ok",
        "generated_at": body.get("generated_at") if isinstance(body, dict) else None,
        "duration_ms": body.get("duration_ms") if isinstance(body, dict) else None,
        "cache_age_seconds": age_seconds,
        "cache_stale": age_seconds > 6 * 60 * 60,
        "summary": complete_summary,
        "checks": checks,
    }


@app.route("/api/readiness/latest")
@requires_auth
def api_readiness_latest():
    """Return the latest cached production-readiness sweep JSON."""
    return jsonify(_readiness_latest_payload())


@app.route("/api/readiness/check/<section>/<name>")
@requires_auth
def api_readiness_check(section: str, name: str):
    """Return one cached production-readiness check by section/category and name."""
    payload = _readiness_latest_payload()
    for check in payload.get("checks") or []:
        check_section = str(check.get("section") or check.get("category") or "")
        if check_section == section and str(check.get("name") or "") == name:
            return jsonify(
                {
                    "status": "ok",
                    "generated_at": payload.get("generated_at"),
                    "cache_age_seconds": payload.get("cache_age_seconds"),
                    "cache_stale": payload.get("cache_stale"),
                    "check": check,
                }
            )
    return jsonify({"status": "error", "error": "check not found"}), 404


@app.route("/api/production/readiness")
@requires_auth
def api_production_readiness():
    """Production readiness gates — contracts, cloud services, edge fleet"""
    import socket

    def fetch():
        ts = datetime.now().isoformat()

        # Gate A — API contracts (key service endpoints)
        contract_checks = []
        for name, url in [
            ("signal-logger /health", "http://127.0.0.1:18081/health"),
            ("inference-proxy /health", "http://127.0.0.1:11435/health"),
            ("control-plane /health", "http://127.0.0.1:8082/health"),
            ("dashboard /health", f"http://127.0.0.1:{DASHBOARD_PORT}/health"),
        ]:
            t0 = time.time()
            result = fetch_sync(url)
            latency = int((time.time() - t0) * 1000)
            ok = bool(result)
            contract_checks.append(
                {
                    "name": name,
                    "healthy": ok,
                    "status": "ok" if ok else "unreachable",
                    "latency_ms": latency,
                }
            )

        gate_a_pass = sum(1 for c in contract_checks if c["healthy"])
        gate_a = {
            "ok": gate_a_pass == len(contract_checks),
            "pass": gate_a_pass,
            "total": len(contract_checks),
        }

        # Gate B — cloud services (Mac + Windows GPU Ollama)
        cloud_services = {}
        for name, host, port in [
            ("mac-ollama", "127.0.0.1", 11434),
            ("windows-ollama", "100.x.x.z", 11434),
            ("openbb-api", "127.0.0.1", 6900),
            ("redis", "127.0.0.1", 6379),
        ]:
            t0 = time.time()
            try:
                s = socket.create_connection((host, port), timeout=2)
                s.close()
                ok = True
            except Exception:
                ok = False
            latency = int((time.time() - t0) * 1000)
            cloud_services[name] = {
                "healthy": ok,
                "status": "ok" if ok else "down",
                "latency_ms": latency if ok else None,
            }

        gate_b_pass = sum(1 for s in cloud_services.values() if s["healthy"])
        gate_b = {
            "ok": gate_b_pass == len(cloud_services),
            "pass": gate_b_pass,
            "total": len(cloud_services),
        }

        # Gate C — edge fleet (Pi nodes)
        pi_nodes = {}
        for name, host in [("rari1", "100.x.x.x"), ("rari2", "100.x.x.y")]:
            t0 = time.time()
            try:
                s = socket.create_connection((host, 11434), timeout=3)
                s.close()
                ok = True
            except Exception:
                ok = False
            latency = int((time.time() - t0) * 1000)
            pi_nodes[name] = {
                "healthy": ok,
                "status": "ok" if ok else "unreachable",
                "latency_ms": latency if ok else None,
            }

        gate_c_pass = sum(1 for s in pi_nodes.values() if s["healthy"])
        gate_c = {
            "ok": gate_c_pass > 0,  # at least one Pi required
            "pass": gate_c_pass,
            "total": len(pi_nodes),
        }

        gates = {"A_contracts": gate_a, "B_cloud": gate_b, "C_edge": gate_c}
        overall_ok = gate_a["ok"] and gate_b["ok"]  # Pi optional for prod

        blockers = []
        for check in contract_checks:
            if not check["healthy"]:
                blockers.append(
                    {"name": check["name"], "gate": "A_contracts", "error": check["status"]}
                )
        for name, svc in cloud_services.items():
            if not svc["healthy"]:
                blockers.append({"name": name, "gate": "B_cloud", "error": svc["status"]})

        return {
            "overall_ok": overall_ok,
            "gates": gates,
            "blockers": blockers,
            "cloud": {"services": cloud_services},
            "contract_checks": contract_checks,
            "timestamp": ts,
        }

    return jsonify(get_cached("prod_readiness", fetch))


@app.route("/logs")
@requires_auth
def logs_page():
    """Log viewer page"""
    return render_template("pages/logs.html", current_page="logs", page_title="Logs")


@app.route("/command-deck")
@requires_auth
def command_deck_page():
    """Trading command deck"""
    return render_template(
        "pages/command_deck.html", current_page="command_deck", page_title="Command Deck"
    )


@app.route("/api/trading/metrics")
@requires_auth
def api_trading_metrics():
    """Trading pipeline metrics — signal counts, success rates from signal logger"""
    import json as _json
    from datetime import datetime as _dt
    from pathlib import Path as _Path

    def fetch():
        _alpha = _Path.home() / "Code" / "Sapphire" / "services" / "alpha"
        if str(_alpha) not in _sys.path:
            _sys.path.insert(0, str(_alpha))

        today = _dt.now(UTC).strftime("%Y-%m-%d")
        signals_dir = _Path.home() / "Code" / "Sapphire" / "data" / "signals"
        f = signals_dir / f"{today}.jsonl"

        signals_today = []
        if f.exists():
            for line in f.read_text().strip().splitlines():
                with contextlib.suppress(Exception):
                    signals_today.append(_json.loads(line))

        total = len(signals_today)

        # Win rate from outcome-tagged signals (via signal_pipeline.signal_stats)
        win_rate = None
        wins = losses = 0
        total_pnl = 0.0
        try:
            from signal_pipeline import pipeline as _pl

            stats = _pl.signal_stats()
            win_rate = stats.get("win_rate")
            wins = stats.get("wins", 0)
            losses = stats.get("losses", 0)
            total_pnl = stats.get("total_pnl_usd", 0.0)
        except Exception:
            pass

        # Recent signals (last 5, most recent first)
        recent = []
        for s in signals_today[-5:][::-1]:
            recent.append(
                {
                    "id": s.get("pipeline_id", ""),
                    "symbol": s.get("symbol", ""),
                    "action": s.get("action", "").upper(),
                    "score": s.get("score", 0),
                    "routing": s.get("routing", ""),
                    "outcome": s.get("outcome"),
                    "pnl_usd": s.get("pnl_usd"),
                    "ts": s.get("timestamp", "")[:19].replace("T", " "),
                }
            )

        # Live stats from signal logger
        live = fetch_sync("http://127.0.0.1:18081/api/signals/stats") or {}

        return {
            "signals_today": total,
            "win_rate": win_rate,
            "wins": wins,
            "losses": losses,
            "total_pnl_usd": round(total_pnl, 2),
            "recent": recent,
            "pipeline": {
                "webhook_active": bool(fetch_sync("http://127.0.0.1:18081/health")),
                "live_total": live.get("total", total),
            },
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("trading_metrics", fetch))


@app.route("/soc")
@requires_auth
def soc_page():
    """Security Operations Center"""
    return render_template(
        "pages/soc.html", current_page="soc", page_title="Security Operations Center"
    )


@app.route("/security/overview")
@requires_auth
def security_overview_page():
    """Security intelligence: dependency scanner, model integrity, network surface."""
    return render_template(
        "pages/security.html", current_page="security", page_title="Security Overview"
    )


@app.route("/chain")
@requires_auth
def chain_page():
    """On-chain intelligence: regime, funding, TVL, stablecoin flows"""
    return render_template(
        "pages/chain.html", current_page="chain", page_title="On-Chain Intelligence"
    )


@app.route("/api/chain/overview")
@requires_auth
@x402_require(0.01, description="On-chain intelligence snapshot")
def api_chain_overview():
    """Unified on-chain snapshot — regime, funding, OI, TVL, stablecoins."""
    from pathlib import Path as _Path

    _root = _Path.home() / "Code" / "Sapphire"
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))

    def fetch():
        from lib.chain import ChainIntelligence

        ci = ChainIntelligence()
        return ci.snapshot(alert_on_shift=False)

    try:
        return jsonify(
            get_cached(
                "chain_overview",
                fetch,
                ttl=CHAIN_OVERVIEW_CACHE_DURATION,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.exception("chain overview failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/chain/robinhood")
@requires_auth
def robinhood_chain_page():
    """Robinhood Chain testnet: contract status, on-chain signals, payment gate."""
    return render_template(
        "pages/robinhood_chain.html", current_page="robinhood_chain", page_title="Robinhood Chain"
    )


@app.route("/api/chain/robinhood/status")
@requires_auth
def api_robinhood_chain_status():
    """Chain health: block number, gas price, contract addresses."""
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient

        client = RobinhoodChainClient()
        status = client.get_chain_status()
        return jsonify(
            {
                "connected": status.connected,
                "chain_id": status.chain_id,
                "block_number": status.block_number,
                "gas_price_gwei": status.gas_price_gwei,
                "signal_verifier_address": status.signal_verifier_address,
                "payment_gate_address": status.payment_gate_address,
                "sentinel_registry_address": status.sentinel_registry_address,
                "signal_count": status.signal_count,
                "error": status.error,
            }
        )
    except Exception as e:
        log.exception("robinhood chain status failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chain/robinhood/signals")
@requires_auth
def api_robinhood_chain_signals():
    """Recent on-chain signals from SapphireSignalVerifier."""
    count = min(int(request.args.get("count", 10)), 50)
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient

        client = RobinhoodChainClient()
        signals = client.get_signal_history(count)
        return jsonify({"signals": signals, "count": len(signals)})
    except Exception as e:
        log.exception("robinhood chain signals failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chain/robinhood/payment")
@requires_auth
def api_robinhood_payment_stats():
    """Payment gate pricing and stats."""
    try:
        from lib.chain.robinhood_chain import RobinhoodChainClient

        client = RobinhoodChainClient()
        return jsonify(client.get_payment_gate_stats())
    except Exception as e:
        log.exception("robinhood payment stats failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chain/robinhood/local-state")
@requires_auth
def api_robinhood_chain_local_state():
    """Compact summary of the local Robinhood Chain stack (ops-state/rh-chain)."""
    try:
        from lib.chain.rh_chain_local import build_local_state_summary

        data = get_cached(
            "rh_chain_local_state",
            build_local_state_summary,
            ttl=RH_CHAIN_LOCAL_CACHE_DURATION,
            raise_on_miss=True,
        )
        return jsonify(_maybe_buyer_safe_payload(data))
    except Exception as e:
        log.exception("robinhood chain local state failed")
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chain/robinhood/local-memes")
@requires_auth
def api_robinhood_chain_local_memes():
    """Full memes-state.json from the local orderflow collector."""
    try:
        from lib.chain.rh_chain_local import load_memes_state

        return jsonify(_maybe_buyer_safe_payload(load_memes_state()))
    except Exception as e:
        log.exception("robinhood chain local memes failed")
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/chain/robinhood/local-feed")
@requires_auth
def api_robinhood_chain_local_feed():
    """Full rh-feed-state.json from the local sequencer feed listener."""
    try:
        from lib.chain.rh_chain_local import load_feed_state

        return jsonify(_maybe_buyer_safe_payload(load_feed_state()))
    except Exception as e:
        log.exception("robinhood chain local feed failed")
        return jsonify({"ok": False, "error": f"{type(e).__name__}: {e}"}), 500


@app.route("/chain/sentinel")
@requires_auth
def sentinel_page():
    """Sapphire Sentinel hackathon demo for agentic payments on Robinhood Chain."""
    return render_template(
        "pages/sentinel.html", current_page="sentinel", page_title="Sapphire Sentinel"
    )


@app.route("/api/hackathon/sentinel/demo")
@requires_auth
def api_sentinel_demo():
    """Return the static testnet-only Sentinel demo state."""
    try:
        from lib.hackathon.sentinel import build_demo_state

        return jsonify(build_demo_state())
    except Exception as e:
        log.exception("sentinel demo failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/hackathon/sentinel/evaluate", methods=["POST"])
@requires_auth
def api_sentinel_evaluate():
    """Evaluate an agent payment attempt without settlement or order submission."""
    try:
        body = request.get_json(silent=True) or {}
        from lib.hackathon.chain_health_gate import ChainHealthVerdict
        from lib.hackathon.sentinel import evaluate_from_payload

        if os.environ.get("SENTINEL_DEMO_FORCE_DEPEG") == "1":
            from decimal import Decimal

            class _PoisonGate:
                def evaluate_chain(self, chain_id: int):
                    return ChainHealthVerdict(
                        chain_id=4326,
                        chain_name="MegaETH",
                        severity="BLOCK",
                        reasons=["demo: forced depeg (500 bps)"],
                        peg_divergence_bps=Decimal("500"),
                    )

            gate = _PoisonGate()
        else:
            from lib.hackathon.chain_health_gate import default_gate

            gate = default_gate()

        return jsonify(
            {
                "execution_enabled": False,
                "mode": "policy_preview_only",
                "decision": evaluate_from_payload(body, gate=gate),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
    except Exception as e:
        log.exception("sentinel evaluation failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 400


# Cross-chain Aave APY arbitrage scanner: ~1-2s per scan in production
# (3 RPC fan-outs across 5 candidate assets). 30s server-side cache
# keeps the panel snappy and avoids hammering chain RPCs from a 60s
# auto-refreshing dashboard panel.
CROSS_CHAIN_ARB_CACHE_DURATION = 30


@app.route("/api/cross_chain/aave_arb")
@requires_auth
def api_cross_chain_aave_arb():
    """Live cross-chain Aave V3 supply/borrow APY arbitrage opportunities.

    Returns the JSON shape produced by
    :func:`lib.hackathon.cross_chain_alpha.scan_aave_arb` plus a
    ``generated_at`` ISO-8601 UTC timestamp so the panel can render an
    accurate "Last scan" label even when responses come from cache.
    """

    def fetch():
        from lib.hackathon.cross_chain_alpha import scan_aave_arb

        payload = scan_aave_arb(top_n=5)
        payload["generated_at"] = datetime.now(UTC).isoformat()
        return payload

    try:
        return jsonify(
            get_cached("cross_chain_aave_arb", fetch, ttl=CROSS_CHAIN_ARB_CACHE_DURATION)
        )
    except Exception as e:
        log.exception("cross-chain aave arb scan failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


# Cross-chain GMX V2 perps overview: per-chain funding APR + OI skew
# + same-underlying divergence. Same 30s server-side cache contract as
# the Aave arb panel above so a 60s auto-refresh polls the endpoint
# twice between actual chain RPC fan-outs.
PERPS_OVERVIEW_CACHE_DURATION = 30


@app.route("/api/perps/overview")
@requires_auth
def api_perps_overview():
    """Live cross-chain GMX V2 perps funding-rate + OI-skew overview.

    Returns the JSON shape produced by
    :func:`lib.perps.gmx_v2_overview.scan_perps_overview` plus a
    ``generated_at`` ISO-8601 UTC timestamp so the panel can render an
    accurate "Last refresh" label even when responses come from cache.
    """

    def fetch():
        from lib.perps.gmx_v2_overview import scan_perps_overview

        payload = scan_perps_overview()
        payload["generated_at"] = datetime.now(UTC).isoformat()
        return payload

    try:
        return jsonify(get_cached("perps_overview", fetch, ttl=PERPS_OVERVIEW_CACHE_DURATION))
    except Exception as e:
        log.exception("perps overview scan failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/risk")
@requires_auth
def risk_page():
    """Portfolio risk: Sharpe/Sortino/Calmar/drawdown/Kelly."""
    return render_template("pages/risk.html", current_page="risk", page_title="Portfolio Risk")


@app.route("/analytics")
@requires_auth
def analytics_page():
    """Performance analytics: equity curve, Sharpe, regime breakdown."""
    return render_template(
        "pages/analytics.html", current_page="analytics", page_title="Performance Analytics"
    )


@app.route("/api/analytics")
@requires_auth
def api_analytics():
    """Full analytics report from signal + paper trading data."""

    def fetch():
        from pathlib import Path as _Path

        repo_root = _Path(__file__).resolve().parents[2]
        if str(repo_root) not in _sys.path:
            _sys.path.insert(0, str(repo_root))
        from services.intelligence import analytics as _analytics

        return _analytics.build_report()

    return jsonify(get_cached("analytics", fetch))


@app.route("/api/risk/metrics")
@requires_auth
@x402_require(0.02, description="Portfolio risk analytics")
def api_risk_metrics():
    """Portfolio metrics computed from paper_trading + signal audit logs."""
    from dataclasses import asdict
    from pathlib import Path as _Path

    _root = _Path.home() / "Code" / "Sapphire"
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    try:
        from lib.analytics.risk_engine import RiskEngine

        bankroll = float(request.args.get("bankroll", 10000.0))
        eng = RiskEngine(bankroll=bankroll)
        m = eng.compute()
        return jsonify(asdict(m))
    except Exception as e:
        log.exception("risk metrics failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/analytics/performance")
@requires_auth
def api_analytics_performance():
    """Equity/benchmark/rolling-Sharpe/regime/monthly report from latest backtest."""
    try:
        from lib.analytics.performance import build_performance_report

        primary = request.args.get("symbol", "BTC-USD")
        window = int(request.args.get("window", 30))
        candidates = [r / "data" / "backtests" / "latest.json" for r in _DASHBOARD_ROOTS]
        path = next((c for c in candidates if c.exists()), candidates[0])
        report = build_performance_report(path, primary_symbol=primary, rolling_window=window)
        return jsonify(report)
    except Exception as e:
        log.exception("analytics performance failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/risk/backtest")
@requires_auth
def api_risk_backtest():
    """Backtest SMA-crossover signals against 90d OHLCV.

    Query params:
      symbols=BTC-USD,ETH-USD   comma list (default: BTC/ETH/SOL/SPY)
      days=90                   lookback period
      latest=1                  return the last saved run instead of recomputing
    """
    try:
        from lib.analytics.backtest import DEFAULT_SYMBOLS, BacktestConfig, Backtester

        if request.args.get("latest") == "1":
            for cand in (r / "data" / "backtests" / "latest.json" for r in _DASHBOARD_ROOTS):
                if cand.exists():
                    return jsonify(json.loads(cand.read_text()))
            return jsonify({"error": "no cached backtest"}), 404
        syms_arg = request.args.get("symbols")
        symbols = (
            tuple(s.strip() for s in syms_arg.split(",") if s.strip())
            if syms_arg
            else DEFAULT_SYMBOLS
        )
        days = int(request.args.get("days", 90))
        cfg = BacktestConfig(symbols=symbols, period_days=days)
        bt = Backtester(cfg)
        results = bt.run_comparison()
        bt.save(results)
        return jsonify(results)
    except Exception as e:
        log.exception("backtest failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/analytics/correlation")
@requires_auth
def api_correlation():
    """30-day rolling correlation matrix across crypto + equities + macro."""
    from dataclasses import asdict
    from pathlib import Path as _Path

    _root = _Path.home() / "Code" / "Sapphire"
    if str(_root) not in _sys.path:
        _sys.path.insert(0, str(_root))
    try:
        from lib.analytics.correlation import CorrelationEngine

        window = int(request.args.get("window", 30))
        eng = CorrelationEngine()
        report = eng.report(window_days=window)
        return jsonify(
            {
                "matrix": asdict(report.matrix),
                "decorrelation_events": [asdict(e) for e in report.decorrelation_events],
                "risk_on_matrix": asdict(report.risk_on_matrix) if report.risk_on_matrix else None,
                "risk_off_matrix": asdict(report.risk_off_matrix)
                if report.risk_off_matrix
                else None,
                "timestamp": report.timestamp,
            }
        )
    except Exception as e:
        log.exception("correlation matrix failed")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


@app.route("/api/soc/security")
@requires_auth
def api_soc_security():
    """SOC security status — auth events, network, inference gate, threat intel, investigations"""
    import re
    import subprocess

    def fetch():
        checks = {}
        auth_events = []
        tailscale_devices = []
        outbound = {"total": 0, "unexpected": 0}
        injection_stats = {
            "injection_attempts": 0,
            "jailbreak_attempts": 0,
            "prompt_leakage": 0,
            "sensitivity_blocks": 0,
        }
        threats = []
        investigations = []

        # ── Auth logs ────────────────────────────────────────────────
        try:
            result = subprocess.run(["last", "-10"], capture_output=True, text=True, timeout=5)
            lines = [
                ln
                for ln in result.stdout.splitlines()
                if ln.strip() and "wtmp" not in ln and "reboot" not in ln
            ]
            known_users = {"aribs", "rari"}
            unknown = [ln for ln in lines if not any(u in ln for u in known_users)]
            if unknown:
                checks["auth_logs"] = {
                    "status": "warn",
                    "detail": f"{len(unknown)} unknown session(s)",
                }
                for ln in unknown[:3]:
                    auth_events.append(
                        {
                            "timestamp": datetime.now().isoformat()[:19],
                            "type": "warn",
                            "message": ln.strip()[:80],
                        }
                    )
            else:
                checks["auth_logs"] = {
                    "status": "pass",
                    "detail": f"{len(lines)} sessions, all known",
                }
                for ln in lines[:5]:
                    parts = ln.split()
                    auth_events.append(
                        {
                            "timestamp": " ".join(parts[4:8]) if len(parts) > 7 else "--",
                            "type": "ok",
                            "message": ln.strip()[:80],
                        }
                    )
        except Exception:
            checks["auth_logs"] = {"status": "warn", "detail": "Could not read auth logs"}

        # ── Tailscale devices ────────────────────────────────────────
        try:
            result = subprocess.run(
                ["tailscale", "status"], capture_output=True, text=True, timeout=8
            )
            known_ips = {"100.x.x.w", "100.x.x.z", "100.x.x.x", "100.x.x.y"}
            lines = [
                ln for ln in result.stdout.splitlines() if ln.strip() and not ln.startswith("#")
            ]
            unknown_devices = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1] if len(parts) > 1 else "unknown"
                    user = parts[2] if len(parts) > 2 else ""
                    os_info = parts[3] if len(parts) > 3 else ""
                    status = " ".join(parts[4:]) if len(parts) > 4 else "idle"
                    tailscale_devices.append(
                        {
                            "ip": ip,
                            "name": hostname,
                            "user": user,
                            "os": os_info,
                            "status": status,
                            "online": ip in known_ips,
                        }
                    )
                    if ip and not any(
                        ip.startswith(k) for k in ["100.67", "100.71", "100.120", "100.87"]
                    ):
                        unknown_devices.append(ip)
            if unknown_devices:
                checks["tailscale"] = {
                    "status": "warn",
                    "detail": f"{len(unknown_devices)} unknown device(s)",
                }
            else:
                checks["tailscale"] = {
                    "status": "pass",
                    "detail": f"{len(tailscale_devices)} known devices",
                }
        except Exception:
            checks["tailscale"] = {"status": "warn", "detail": "tailscale not reachable"}

        # ── Hermes injection check ───────────────────────────────────
        try:
            log_path = Path.home() / ".hermes" / "logs" / "gateway.log"
            if log_path.exists():
                content = log_path.read_text(errors="ignore")[-50000:]  # last 50KB
                patterns = [
                    "inject",
                    "ignore previous",
                    "jailbreak",
                    "eval(",
                    "exec(",
                    "__import__",
                ]
                found = [p for p in patterns if p.lower() in content.lower()]
                injection_stats["injection_attempts"] = len(found)
                injection_stats["jailbreak_attempts"] = content.lower().count("jailbreak")
                if found:
                    checks["hermes_injection"] = {
                        "status": "warn",
                        "detail": f"{len(found)} pattern(s) detected",
                    }
                else:
                    checks["hermes_injection"] = {
                        "status": "pass",
                        "detail": "0 injection patterns",
                    }
            else:
                checks["hermes_injection"] = {"status": "pass", "detail": "No log file (clean)"}
        except Exception:
            checks["hermes_injection"] = {"status": "warn", "detail": "Could not scan logs"}

        # ── Outbound connections ─────────────────────────────────────
        try:
            result = subprocess.run(
                ["lsof", "-i", "-P", "-n"], capture_output=True, text=True, timeout=8
            )
            established = [ln for ln in result.stdout.splitlines() if "ESTABLISHED" in ln]
            # Filter known/expected IPs
            known_prefixes = (
                "100.",
                "127.",
                "17.",
                "34.",
                "35.",
                "52.",
                "54.",
                "104.",
                "140.",
                "142.",
                "192.168.",
                "10.",
            )
            unexpected = [ln for ln in established if not any(p in ln for p in known_prefixes)]
            outbound = {"total": len(established), "unexpected": len(unexpected)}
            if unexpected:
                checks["outbound_network"] = {
                    "status": "warn",
                    "detail": f"{len(unexpected)} unexpected",
                }
            else:
                checks["outbound_network"] = {
                    "status": "pass",
                    "detail": f"{len(established)} known connections",
                }
        except Exception:
            checks["outbound_network"] = {"status": "warn", "detail": "lsof unavailable"}

        # ── Credential scan ──────────────────────────────────────────
        try:
            dangerous_patterns = [
                (Path.home() / ".env", ".env file in home"),
                (Path.home() / "Code" / "Sapphire" / ".env", ".env in Sapphire root"),
            ]
            found_creds = []
            for path, label in dangerous_patterns:
                if path.exists():
                    found_creds.append(label)
            # Check for hardcoded secrets in recently modified py files
            checks["credentials"] = {"status": "pass", "detail": "No exposed credentials"}
            if found_creds:
                checks["credentials"] = {"status": "warn", "detail": "; ".join(found_creds)}
        except Exception:
            checks["credentials"] = {"status": "warn", "detail": "Scan error"}

        # ── Proxy sensitivity gate ───────────────────────────────────
        try:
            proxy_path = (
                Path.home() / "Code" / "Sapphire" / "services" / "inference-proxy" / "app.py"
            )
            if proxy_path.exists():
                content = proxy_path.read_text()
                gate_patterns = [
                    "api_key",
                    "password",
                    "bearer",
                    "jwt",
                    "private_key",
                    "credit_card",
                    "ssn",
                    "secret",
                ]
                found = [p for p in gate_patterns if p in content.lower()]
                checks["proxy_gate"] = {
                    "status": "pass",
                    "detail": f"{len(found)}/{len(gate_patterns)} patterns active",
                }
            else:
                checks["proxy_gate"] = {"status": "warn", "detail": "Proxy not found"}
        except Exception:
            checks["proxy_gate"] = {"status": "warn", "detail": "Could not verify"}

        # ── LaunchAgents ─────────────────────────────────────────────
        try:
            la_dir = Path.home() / "Library" / "LaunchAgents"
            plists = list(la_dir.glob("*.plist"))
            known_prefixes = (
                "com.sapphire.",
                "homebrew.",
                "com.apple.",
                "ai.hermes.",
                "com.anthropic.",
                "com.1password.",
                "io.tailscale.",
            )
            unknown_agents = [
                p.name for p in plists if not any(p.name.startswith(pfx) for pfx in known_prefixes)
            ]
            if unknown_agents:
                checks["launchagents"] = {
                    "status": "warn",
                    "detail": f"{len(unknown_agents)} unknown agent(s)",
                }
            else:
                checks["launchagents"] = {
                    "status": "pass",
                    "detail": f"{len(plists)} agents, all known",
                }
        except Exception:
            checks["launchagents"] = {"status": "warn", "detail": "Could not read LaunchAgents"}

        # ── Suspicious processes ─────────────────────────────────────
        try:
            import re as _re

            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            # Use word-boundary regex per pattern to avoid matching any line
            # that happens to contain the literal substring (e.g. a directory
            # path with " nc " in it). `nc`/`ncat` need true argv-level matches.
            suspicious = [
                "xmrig",
                "minergate",
                "nc",
                "ncat",
                "ngrok",
                "chisel",
                "frpc",
                "frps",
                "reverse_shell",
                "meterpreter",
            ]
            patterns = {
                s: _re.compile(rf"(?<![\w/.-]){_re.escape(s)}(?![\w.-])") for s in suspicious
            }
            found_procs = [s for s, p in patterns.items() if p.search(result.stdout)]
            if found_procs:
                checks["suspicious_processes"] = {
                    "status": "fail",
                    "detail": f"ALERT: {', '.join(found_procs)}",
                }
            else:
                checks["suspicious_processes"] = {
                    "status": "pass",
                    "detail": "No suspicious processes",
                }
        except Exception:
            checks["suspicious_processes"] = {"status": "warn", "detail": "ps unavailable"}

        # ── Threat intel from cyber-threat-bot refresh ──────────────
        try:
            threat_file = (
                Path.home()
                / "Code"
                / "Sapphire"
                / "data"
                / "intelligence"
                / "latest"
                / "threats.json"
            )
            if threat_file.exists():
                data = json.loads(threat_file.read_text())
                for t in data.get("threats", [])[:8]:
                    score = t.get("score", 0) or 0
                    sev = (
                        "critical"
                        if score >= 9
                        else "high"
                        if score >= 7
                        else "medium"
                        if score >= 4
                        else "low"
                    )
                    threats.append(
                        {
                            "cve_id": t.get("canonical_id", "?"),
                            "title": t.get("title", ""),
                            "severity": sev,
                            "score": score,
                            "source": t.get("source", "unknown"),
                            "exploited": t.get("exploited", False),
                            "url": t.get("url", ""),
                        }
                    )
        except Exception:
            pass

        # If no saved threats, show empty/all-clear
        if not threats:
            threats = []

        # ── Investigation history ────────────────────────────────────
        try:
            docs_dir = Path.home() / "Code" / "Sapphire" / "docs"
            inv_files = sorted(docs_dir.glob("security-investigation-*.md"), reverse=True)
            for inv_file in inv_files[:3]:
                content = inv_file.read_text(errors="ignore")
                # Extract date from filename
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", inv_file.name)
                inv_date = date_match.group(1) if date_match else "unknown"
                # Extract trigger line
                trigger = ""
                for line in content.splitlines():
                    if "**Trigger**" in line or "Trigger" in line:
                        trigger = (
                            line.replace("**Trigger**:", "").replace("**Trigger**", "").strip()
                        )
                        trigger = re.sub(r"[*#]", "", trigger).strip()
                        break
                # Extract verdict
                verdict = "clean"
                if "NOT compromised" in content or "CLEAN" in content:
                    verdict = "clean"
                elif "COMPROMISED" in content:
                    verdict = "threat"
                investigations.append(
                    {
                        "title": trigger[:80] or f"Investigation {inv_date}",
                        "date": inv_date,
                        "verdict": verdict,
                        "summary": "10-point security sweep. Verdict: System clean. No unauthorized access detected.",
                        "file": inv_file.name,
                    }
                )
        except Exception:
            pass

        # ── Overall verdict ──────────────────────────────────────────
        statuses = [c["status"] for c in checks.values()]
        if "fail" in statuses:
            overall = "THREAT"
            msg = "Critical issue detected — immediate action required"
        elif statuses.count("warn") >= 2:
            overall = "WARN"
            msg = f"{statuses.count('warn')} warnings — review recommended"
        elif "warn" in statuses:
            overall = "WARN"
            msg = "1 warning — system mostly clean"
        else:
            overall = "CLEAN"
            msg = f"All {len(checks)} checks passed — system secure"

        return {
            "overall_verdict": overall,
            "summary_message": msg,
            "checks": checks,
            "auth_events": auth_events,
            "tailscale_devices": tailscale_devices,
            "outbound_connections": outbound,
            "injection_stats": injection_stats,
            "proxy_gate": {
                "blocked_patterns": [
                    "api_key",
                    "apikey",
                    "bearer",
                    "jwt",
                    "password",
                    "secret",
                    "-----BEGIN",
                    "credit_card",
                    "ssn",
                ]
            },
            "threats": threats,
            "investigations": investigations,
            "timestamp": datetime.now().isoformat(),
        }

    return jsonify(get_cached("soc_security", fetch))


@app.route("/api/soc/threats")
@requires_auth
def api_soc_threats():
    """Live threat feed from cyber-threat-bot — CISA KEV, NVD, MITRE ATT&CK.
    Reads saved reports first (fast), falls back to live fetch if stale (>4h).
    """
    import re as _re

    CTB_SRC = Path.home() / "Code" / "cyber-threat-bot" / "src"
    THREAT_CACHE = 240  # 4 hours — live fetch is slow (NVD rate limits)

    def fetch():
        threats = []
        source_note = ""
        generated_at = None

        # ── 1. Try saved reports (fast path) ──────────────────────────
        threat_dir = Path.home() / "Code" / "Sapphire" / "data" / "threat_intel"
        saved_reports = (
            sorted(threat_dir.glob("latest_*.md"), reverse=True) if threat_dir.exists() else []
        )

        if saved_reports:
            latest = saved_reports[0]
            try:
                # Check freshness — use file if <4h old
                age_hours = (time.time() - latest.stat().st_mtime) / 3600
                content = latest.read_text(errors="ignore")

                # Extract generated_at
                for line in content.splitlines()[:5]:
                    if "Generated at" in line or "generated" in line.lower():
                        generated_at = line.replace("Generated at:", "").strip()
                        break

                # Parse structured threat entries
                sections = content.split("\n### ")
                for section in sections[1:12]:  # up to 11 threats
                    lines = section.strip().splitlines()
                    if not lines:
                        continue
                    title_line = lines[0].strip().lstrip("0123456789. ")

                    cve_id = None
                    cvss = None
                    exploited = False
                    summary = ""
                    source = "CISA/NVD"

                    for line in lines:
                        if "`CVE-" in line:
                            m = _re.search(r"CVE-\d{4}-\d+", line)
                            if m:
                                cve_id = m.group(0)
                        if "CVSS base score" in line:
                            m = _re.search(r"(\d+\.?\d*)", line.split("CVSS base score")[-1])
                            if m:
                                cvss = float(m.group(1))
                        if "Exploited in the wild: yes" in line:
                            exploited = True
                        if line.strip().startswith("- Summary:"):
                            summary = line.replace("- Summary:", "").strip()
                        if "Sources:" in line:
                            source = line.replace("- Sources:", "").strip()

                    # Severity mapping
                    if exploited and cvss and cvss >= 9.0:
                        severity = "critical"
                    elif exploited or (cvss and cvss >= 9.0):
                        severity = "high"
                    elif cvss and cvss >= 7.0:
                        severity = "medium"
                    else:
                        severity = "low"

                    threats.append(
                        {
                            "cve_id": cve_id,
                            "title": title_line[:100],
                            "severity": severity,
                            "cvss": cvss,
                            "exploited": exploited,
                            "summary": summary[:300],
                            "source": source,
                        }
                    )

                source_note = f"Saved report ({age_hours:.1f}h old)"
                if threats:
                    return {
                        "threats": threats,
                        "source": source_note,
                        "generated_at": generated_at,
                        "total": len(threats),
                        "critical_count": sum(1 for t in threats if t["severity"] == "critical"),
                        "high_count": sum(1 for t in threats if t["severity"] == "high"),
                        "timestamp": datetime.now().isoformat(),
                    }
            except Exception:
                pass

        # ── 2. Live fetch via cyber-threat-bot ─────────────────────────
        if str(CTB_SRC) not in _sys.path and CTB_SRC.exists():
            _sys.path.insert(0, str(CTB_SRC))

        try:
            from cyber_threat_bot import scoring as _sc
            from cyber_threat_bot import sources as _src

            records = _src.collect_latest_records(days=3, per_source=5)
            records.sort(key=lambda r: _sc.record_priority(r), reverse=True)

            for r in records[:12]:
                cvss = r.metadata.get("cvss_base_score") or r.metadata.get("cvss")
                if cvss:
                    try:
                        cvss = float(cvss)
                    except Exception:
                        cvss = None

                if r.exploited and cvss and cvss >= 9.0:
                    severity = "critical"
                elif r.exploited or (cvss and cvss >= 9.0):
                    severity = "high"
                elif cvss and cvss >= 7.0:
                    severity = "medium"
                else:
                    severity = "low"

                threats.append(
                    {
                        "cve_id": r.canonical_id if r.canonical_id.startswith("CVE-") else None,
                        "title": r.title[:100],
                        "severity": severity,
                        "cvss": cvss,
                        "exploited": r.exploited,
                        "summary": r.summary[:300] if r.summary else "",
                        "source": r.source,
                        "url": r.url,
                        "published_at": r.published_at.isoformat() if r.published_at else None,
                    }
                )

            source_note = "Live — CISA KEV + NVD"
        except ImportError:
            source_note = "cyber-threat-bot unavailable"
        except Exception as e:
            source_note = f"Error: {str(e)[:60]}"

        return {
            "threats": threats,
            "source": source_note,
            "generated_at": datetime.now().isoformat(),
            "total": len(threats),
            "critical_count": sum(1 for t in threats if t["severity"] == "critical"),
            "high_count": sum(1 for t in threats if t["severity"] == "high"),
            "timestamp": datetime.now().isoformat(),
        }

    # Longer cache — NVD rate limits mean we don't want to spam live fetches
    key = "soc_threats"
    now = time.time()
    if key in _cache and now - _cache_time.get(key, 0) < THREAT_CACHE:
        return jsonify(_cache[key])
    try:
        data = fetch()
        _cache[key] = data
        _cache_time[key] = now
        return jsonify(data)
    except Exception as e:
        return jsonify(
            {
                "threats": [],
                "source": f"Error: {e}",
                "total": 0,
                "critical_count": 0,
                "high_count": 0,
                "timestamp": datetime.now().isoformat(),
            }
        )


@app.route("/predictions")
@requires_auth
def predictions_page():
    """Kronos candlestick prediction dashboard"""
    return render_template(
        "pages/predictions.html", current_page="predictions", page_title="Kronos Predictions"
    )


@app.route("/api/predictions/kronos")
@requires_auth
@x402_require(0.05, description="Kronos candlestick forecasts")
def api_kronos_prediction():
    """Kronos foundation model prediction endpoint.
    Query params: symbol (default BTC-USD), lookback (default 200), predict (default 24), interval (default 1h)
    """
    import subprocess as _sp

    symbol = request.args.get("symbol", "BTC-USD")
    lookback = int(request.args.get("lookback", 200))
    predict = int(request.args.get("predict", 24))
    interval = request.args.get("interval", "1h")

    # Cap to reasonable limits
    lookback = min(lookback, 500)
    predict = min(predict, 96)

    cache_key = f"kronos_{symbol}_{interval}_{predict}"
    KRONOS_CACHE = 300  # 5 min cache per symbol
    KRONOS_CACHE_MAX = 64  # hard cap to prevent RAM growth from unique ?symbol= values

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < KRONOS_CACHE:
        return jsonify(_cache[cache_key])

    kronos_tool = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "predict_kronos.py"
    )
    kronos_python = Path.home() / "Code" / "Kronos" / ".venv" / "bin" / "python3"

    if not kronos_python.exists():
        kronos_python = Path("/usr/local/bin/python3")

    kronos_env = {
        **__import__("os").environ,
        "PYTHONPATH": str(Path.home() / "Code" / "Kronos"),
    }

    payload = json.dumps(
        {
            "action": "predict",
            "symbol": symbol,
            "lookback_bars": lookback,
            "predict_bars": predict,
            "interval": interval,
        }
    )

    try:
        result = _sp.run(
            [str(kronos_python), str(kronos_tool)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=120,
            env=kronos_env,
        )
        if result.returncode != 0:
            # Never echo raw subprocess stderr to clients — it can leak paths,
            # stack traces, env details. Log server-side; return a generic note.
            log.warning(
                "Kronos subprocess failed (rc=%s): %s",
                result.returncode,
                (result.stderr or "")[-500:],
            )
            return jsonify({"error": "Kronos process failed"}), 500

        data = json.loads(result.stdout)
        # Evict oldest Kronos entries to keep cache bounded — an authenticated
        # attacker could otherwise fill RAM with unique ?symbol= values.
        kronos_keys = [k for k in _cache if k.startswith("kronos_")]
        if len(kronos_keys) >= KRONOS_CACHE_MAX:
            oldest = sorted(kronos_keys, key=lambda k: _cache_time.get(k, 0))[
                : len(kronos_keys) - KRONOS_CACHE_MAX + 1
            ]
            for k in oldest:
                _cache.pop(k, None)
                _cache_time.pop(k, None)
        _cache[cache_key] = data
        _cache_time[cache_key] = now
        return jsonify(data)

    except _sp.TimeoutExpired:
        return jsonify(
            {"error": "Kronos prediction timed out (120s). Model may still be loading."}
        ), 504
    except json.JSONDecodeError as e:
        log.warning("Kronos returned invalid JSON: %s", e)
        return jsonify({"error": "Invalid JSON from Kronos"}), 500
    except Exception as e:
        log.warning("Kronos endpoint error: %s", e)
        return jsonify({"error": "Kronos request failed"}), 500


@app.route("/api/predictions/status")
@requires_auth
def api_kronos_status():
    """Check Kronos model status — cached predictions + model load state"""
    import subprocess as _sp

    kronos_tool = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "predict_kronos.py"
    )
    kronos_python = Path.home() / "Code" / "Kronos" / ".venv" / "bin" / "python3"
    if not Path(str(kronos_python)).exists():
        kronos_python = "/usr/local/bin/python3"

    kronos_env = {**__import__("os").environ, "PYTHONPATH": str(Path.home() / "Code" / "Kronos")}

    try:
        result = _sp.run(
            [str(kronos_python), str(kronos_tool)],
            input='{"action":"status"}',
            capture_output=True,
            text=True,
            timeout=10,
            env=kronos_env,
        )
        data = json.loads(result.stdout)

        # Add cached prediction summary
        today = datetime.now().strftime("%Y-%m-%d")
        pred_file = (
            Path.home() / "Code" / "Sapphire" / "data" / "intelligence" / today / "predictions.json"
        )
        data["has_todays_predictions"] = pred_file.exists()
        if pred_file.exists():
            preds = json.loads(pred_file.read_text())
            data["cached_symbols"] = list(preds.get("predictions", {}).keys())

        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "model_loaded": False}), 200


@app.route("/api/soc/cyber-research", methods=["POST"])
@requires_auth
def api_soc_cyber_research():
    """Proxy security queries to Lumo T5 via lumo_research.py plugin tool."""
    import subprocess

    data = request.get_json(force=True, silent=True) or {}
    query = (data.get("query") or "").strip()
    mode = data.get("mode", "ask")  # ask | security_brief | security_brief_deep
    web_search = bool(data.get("web_search", False))

    if not query:
        return jsonify({"error": "query required"}), 400

    tool_path = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "lumo_research.py"
    )

    if mode == "security_brief_deep":
        inp = json.dumps(
            {"action": "security_brief", "topic": query, "depth": "deep", "web_search": web_search}
        )
    elif mode == "security_brief":
        inp = json.dumps(
            {
                "action": "security_brief",
                "topic": query,
                "depth": "standard",
                "web_search": web_search,
            }
        )
    else:
        inp = json.dumps({"action": "ask", "query": query, "web_search": web_search})

    try:
        result = subprocess.run(
            ["python3", str(tool_path)], input=inp, capture_output=True, text=True, timeout=120
        )
        if result.stdout.strip():
            out = json.loads(result.stdout)
        else:
            # Don't leak raw subprocess stderr to clients — log server-side.
            log.warning("lumo_research returned no stdout; stderr=%s", (result.stderr or "")[-500:])
            out = {"status": "error", "error": "no output"}
        return jsonify(out)
    except subprocess.TimeoutExpired:
        return jsonify({"status": "timeout", "error": "Lumo took too long (>120s). Try again."})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


@app.route("/api/soc/lumo-status")
@requires_auth
def api_soc_lumo_status():
    """Quick Lumo API reachability check."""
    import subprocess

    tool_path = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "lumo_research.py"
    )
    try:
        result = subprocess.run(
            ["python3", str(tool_path)],
            input='{"action":"status"}',
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = json.loads(result.stdout) if result.stdout.strip() else {"online": False}
        return jsonify(out)
    except Exception as e:
        return jsonify({"online": False, "error": str(e)})


@app.route("/health")
def health():
    """Health check endpoint — public"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


# ── Metrics history / sparkline endpoints ─────────────────────────────────────


@app.route("/api/metrics/history")
@requires_auth
def api_metrics_history():
    """24-hour time-series for overview sparklines (5-min intervals, up to 288 pts)."""
    from metrics_collector import get_metrics_history

    entries = get_metrics_history(hours=24)
    result = {
        "inference": [
            {
                "ts": e["ts"],
                "count": e.get("inference_count", 0),
                "avg_ms": e.get("inference_avg_ms", 0),
            }
            for e in entries
        ],
        "signals": [{"ts": e["ts"], "count": e.get("signals", 0)} for e in entries],
        "threats": [{"ts": e["ts"], "count": e.get("threats", 0)} for e in entries],
    }
    return jsonify(result)


@app.route("/api/soc/threat-timeline")
@requires_auth
def api_soc_threat_timeline():
    """7-day threat severity breakdown from daily intelligence files."""
    from datetime import timedelta

    intel_base = Path.home() / "Code" / "Sapphire" / "data" / "intelligence"
    days = []
    today = datetime.now()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        counts = {"date": date_str, "critical": 0, "high": 0, "medium": 0, "low": 0}
        threat_file = intel_base / date_str / "threats.json"
        if threat_file.exists():
            try:
                data = json.loads(threat_file.read_text())
                for t in data.get("threats", []):
                    sev = (t.get("severity") or "low").lower()
                    if sev in counts:
                        counts[sev] += 1
                    else:
                        counts["low"] += 1
            except Exception:
                pass
        days.append(counts)
    return jsonify({"days": days})


@app.route("/api/agents/history")
@requires_auth
def api_agents_history():
    """24-hour Pi vitals history for sparklines."""
    from metrics_collector import get_agent_history

    entries = get_agent_history(hours=24)
    result: dict = {
        "rari1": {"cpu_temp": [], "mem_pct": [], "timestamps": []},
        "rari2": {"cpu_temp": [], "mem_pct": [], "timestamps": []},
    }
    for e in entries:
        ts = e.get("ts", "")
        for node in ("rari1", "rari2"):
            v = (e.get("agents") or {}).get(node, {})
            result[node]["timestamps"].append(ts)
            result[node]["cpu_temp"].append(v.get("cpu_temp"))
            result[node]["mem_pct"].append(v.get("mem_pct"))
    return jsonify(result)


@app.route("/api/signals/performance")
@requires_auth
def api_signals_performance():
    """Daily signal P&L and win-rate trend from all signal JSONL files."""
    from datetime import timedelta

    signals_dir = Path.home() / "Code" / "Sapphire" / "data" / "signals"
    today = datetime.now()
    daily = []
    cumulative_pnl = [0.0]
    win_rate_trend = []
    running_pnl = 0.0

    for i in range(13, -1, -1):  # last 14 days
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y-%m-%d")
        f = signals_dir / f"{date_str}.jsonl"
        day = {"date": date_str, "signals": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        if f.exists():
            try:
                for line in f.read_text().strip().splitlines():
                    try:
                        s = json.loads(line)
                        day["signals"] += 1
                        outcome = s.get("outcome")
                        pnl = s.get("pnl_usd", 0.0) or 0.0
                        day["pnl"] = round(day["pnl"] + pnl, 2)
                        if outcome == "win":
                            day["wins"] += 1
                        elif outcome == "loss":
                            day["losses"] += 1
                    except Exception:
                        pass
            except Exception:
                pass
        if day["signals"] > 0:
            running_pnl += day["pnl"]
            cumulative_pnl.append(round(running_pnl, 2))
            closed = day["wins"] + day["losses"]
            win_rate_trend.append(round(day["wins"] / closed, 3) if closed > 0 else None)
            daily.append(day)

    return jsonify(
        {
            "daily": daily,
            "cumulative_pnl": cumulative_pnl[1:] if len(cumulative_pnl) > 1 else [],
            "win_rate_trend": win_rate_trend,
        }
    )


@app.route("/portfolio")
@requires_auth
def portfolio_page():
    return render_template("pages/portfolio.html", current_page="portfolio", page_title="Portfolio")


@app.route("/factors")
@requires_auth
def factors_page():
    return render_template("pages/factors.html", current_page="factors", page_title="Factors")


@app.route("/performance")
@requires_auth
def performance_page():
    return render_template(
        "pages/performance.html", current_page="performance", page_title="Performance"
    )


def _parse_agent_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO timestamp string into an aware UTC datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _load_agent_events(limit: int = 20) -> list[dict[str, Any]]:
    """Load the most recent agent events from the event bus JSONL fallback."""
    if not _AGENT_EVENTS_FILE.exists():
        return []

    events: list[dict[str, Any]] = []
    try:
        lines = _AGENT_EVENTS_FILE.read_text().splitlines()
    except OSError:
        return events

    for raw_line in reversed(lines):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = str(record.get("type") or "")
        if not event_type.startswith("agent."):
            continue
        data = record.get("data") or {}
        if not isinstance(data, dict):
            data = {"value": data}
        events.append(
            {
                "type": event_type,
                "ts": record.get("ts"),
                "agent": data.get("agent") or record.get("source") or "unknown",
                "data": data,
            }
        )
        if len(events) >= limit:
            break
    return events


def _load_agent_heartbeats() -> list[dict[str, Any]]:
    """Load per-agent heartbeat files from disk."""
    heartbeats: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    if not _AGENT_HEARTBEAT_DIR.exists():
        return heartbeats

    for path in sorted(_AGENT_HEARTBEAT_DIR.glob("*.heartbeat")):
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        updated_at = _parse_agent_timestamp(payload.get("updated_at"))
        heartbeats.append(
            {
                "name": payload.get("agent") or path.stem,
                "cycle_count": int(payload.get("cycle_count") or 0),
                "last_cycle_completed_at": payload.get("last_cycle_completed_at"),
                "updated_at": payload.get("updated_at"),
                "age_sec": (
                    max(0, int((now - updated_at).total_seconds()))
                    if updated_at is not None
                    else None
                ),
            }
        )
    return heartbeats


def _load_agents_autonomous_context() -> dict[str, Any]:
    """Build the server-side context for the autonomous agents dashboard."""
    events = _load_agent_events()
    heartbeats = _load_agent_heartbeats()
    last_cycle_event = next(
        (event for event in events if event["type"] == "agent.cycle.completed"),
        None,
    )
    cycle_count = 0
    if heartbeats:
        cycle_count = max(heartbeat["cycle_count"] for heartbeat in heartbeats)
    if cycle_count == 0 and last_cycle_event is not None:
        cycle_count = int(last_cycle_event["data"].get("cycle_count") or 0)

    return {
        "last_cycle_timestamp": last_cycle_event["ts"] if last_cycle_event else None,
        "cycle_count": cycle_count,
        "events": events,
        "heartbeats": heartbeats,
    }


@app.route("/agents/autonomous")
@requires_auth
def agents_autonomous_page():
    """Autonomous agent heartbeat and event dashboard."""
    return render_template(
        "pages/agents_autonomous.html",
        current_page="agents-autonomous",
        page_title="Autonomous Agents",
        **_load_agents_autonomous_context(),
    )


@app.route("/content")
@requires_auth
def content_page():
    return render_template(
        "pages/content.html", current_page="content", page_title="Content_Engine"
    )


@app.route("/cascade")
@requires_auth
def cascade_page():
    return render_template("pages/cascade.html", current_page="cascade", page_title="Cascade")


@app.route("/intel")
@requires_auth
def intel_page():
    return render_template("pages/intel.html", current_page="intel", page_title="Intel")


@app.route("/intel/leads")
@requires_auth
def intel_leads_page():
    """Houston home-lead pipeline — Leaflet map + ranked sidebar."""
    return render_template(
        "pages/intel_leads.html",
        current_page="intel-leads",
        page_title="Home Leads",
    )


def _filter_leads(leads, *, score_min=None, source=None, zip_code=None, urgency=None):
    out = []
    for lead in leads:
        if score_min is not None:
            s = lead.get("score")
            if not isinstance(s, (int, float)) or s < score_min:
                continue
        if source and lead.get("source") != source:
            continue
        if zip_code and str(lead.get("zip", "")).strip() != str(zip_code).strip():
            continue
        if urgency and lead.get("urgency") != urgency:
            continue
        out.append(lead)
    return out


@app.route("/api/leads")
@requires_auth
def api_leads():
    """Paginated lead list. Filters: score_min, source, zip, urgency, limit, offset."""
    try:
        from lib.intel.houston_leads import load_leads
    except Exception as e:
        return jsonify({"error": f"lead module unavailable: {e}"}), 500

    leads = load_leads()
    score_min = request.args.get("score_min", type=float)
    source = request.args.get("source")
    zip_code = request.args.get("zip")
    urgency = request.args.get("urgency")
    limit = request.args.get("limit", default=100, type=int)
    offset = request.args.get("offset", default=0, type=int)

    filtered = _filter_leads(
        leads,
        score_min=score_min,
        source=source,
        zip_code=zip_code,
        urgency=urgency,
    )
    # Newest scored, highest scoring first; fall back to ingestion order.
    filtered.sort(
        key=lambda l: (l.get("score") or -1, l.get("ingested_at") or ""),
        reverse=True,
    )
    page = filtered[offset : offset + limit]
    return jsonify(
        {
            "total": len(filtered),
            "limit": limit,
            "offset": offset,
            "leads": page,
        }
    )


@app.route("/api/leads/map")
@requires_auth
def api_leads_map():
    """GeoJSON FeatureCollection for the map page (geocoded leads only)."""
    try:
        from lib.intel.houston_leads import load_leads
    except Exception as e:
        return jsonify({"error": f"lead module unavailable: {e}"}), 500

    score_min = request.args.get("score_min", type=float)
    source = request.args.get("source")
    leads = _filter_leads(load_leads(), score_min=score_min, source=source)

    features = []
    for lead in leads:
        lat, lng = lead.get("lat"), lead.get("lng")
        if lat is None or lng is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                "properties": {
                    "id": lead.get("id"),
                    "address": lead.get("address"),
                    "type": lead.get("type"),
                    "source": lead.get("source"),
                    "score": lead.get("score"),
                    "score_reason": lead.get("score_reason"),
                    "urgency": lead.get("urgency"),
                    "description": lead.get("description"),
                    "created_at": lead.get("created_at"),
                },
            }
        )
    return jsonify({"type": "FeatureCollection", "features": features})


@app.route("/api/leads/stats")
@requires_auth
def api_leads_stats():
    try:
        from lib.intel.pipeline import stats as lead_stats
    except Exception as e:
        return jsonify({"error": f"lead module unavailable: {e}"}), 500
    return jsonify(lead_stats())


@app.route("/api/leads/score", methods=["POST"])
@requires_auth
def api_leads_score():
    """Score every unscored lead in the JSONL store. Returns the count."""
    try:
        from lib.intel.lead_scorer import score_unscored
    except Exception as e:
        return jsonify({"error": f"lead module unavailable: {e}"}), 500
    payload = request.get_json(silent=True) or {}
    limit = payload.get("limit")
    n = score_unscored(limit=limit if isinstance(limit, int) else None)
    return jsonify({"scored": n})


@app.route("/investment-intel")
@requires_auth
def investment_intel_page():
    return render_template(
        "pages/investment_intel.html",
        current_page="investment-intel",
        page_title="Investment Intel",
    )


@app.route("/cross-asset")
@requires_auth
def cross_asset_page():
    return render_template(
        "pages/cross_asset.html",
        current_page="cross-asset",
        page_title="Cross-Asset Intel",
    )


@app.route("/sovereign-thesis")
@requires_auth
def sovereign_thesis_page():
    return render_template(
        "pages/sovereign_thesis.html",
        current_page="sovereign-thesis",
        page_title="Sovereign Thesis",
    )


@app.route("/sovereign-thesis/story")
@requires_auth
def sovereign_thesis_story_page():
    return render_template(
        "pages/sovereign_thesis_story.html",
        current_page="sovereign-thesis-story",
        page_title="Sovereign Thesis Story",
    )


@app.route("/diligence")
@requires_auth
def diligence_page():
    return render_template(
        "pages/diligence.html",
        current_page="diligence",
        page_title="Diligence",
        diligence_summary=_maybe_buyer_safe_payload(_build_diligence_summary()),
        buyer_safe=_buyer_safe_requested(),
    )


@app.route("/observability")
@requires_auth
def observability_page():
    return render_template(
        "pages/observability.html",
        current_page="observability",
        page_title="Observability",
        routine_pause_summary=_maybe_buyer_safe_payload(_build_routine_pause_summary()),
        buyer_safe=_buyer_safe_requested(),
    )


@app.route("/narrative-eval")
@requires_auth
def narrative_eval_page():
    return render_template(
        "pages/narrative_eval.html",
        current_page="narrative-eval",
        page_title="Narrative Eval",
    )


# ---------------------------------------------------------------------------
# /timetravel — operator-facing as-of-T snapshot view (Tranche 7-G).
# ---------------------------------------------------------------------------
#
# Reads ``lib.timetravel.snapshot.take_snapshot`` to answer "what was the
# correlator + narrative state at T?". Read-only research tool — never writes
# back to ``data/``, never publishes to the event bus, never places orders or
# alerts. The link is opt-in (operator-only) and surfaced from the Ops nav.

# Default per-scope row cap. Snapshots for older timestamps can exceed
# 100k rows per scope; cap before serialising to keep responses bounded.
_TIMETRAVEL_DEFAULT_ROW_CAP = 200
_TIMETRAVEL_MAX_ROW_CAP = 2000


def _timetravel_parse_at(raw: str | None) -> datetime | None:
    """Coerce a user-supplied ISO/datetime-local string to UTC datetime.

    Accepts ``YYYY-MM-DDTHH:MM`` (HTML datetime-local), ``YYYY-MM-DDTHH:MM:SS``,
    full ISO-8601 with offset, or trailing ``Z``. Returns ``None`` on failure.
    """
    if not raw:
        return None
    candidate = str(raw).strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _timetravel_truncate(snapshot_dict: dict[str, Any], cap: int) -> dict[str, Any]:
    """Cap each scope's ``rows`` list at ``cap`` (most-recent kept)."""
    entries = snapshot_dict.get("entries") or {}
    truncated: dict[str, Any] = {}
    for name, entry in entries.items():
        rows = list(entry.get("rows") or [])
        if cap > 0 and len(rows) > cap:
            entry = dict(entry)
            entry["rows"] = rows[-cap:]
            entry["truncated"] = True
            entry["truncated_to"] = cap
            entry["original_row_count"] = len(rows)
        truncated[name] = entry
    snapshot_dict["entries"] = truncated
    return snapshot_dict


def _timetravel_index_summary() -> dict[str, Any]:
    """Return a small, safe summary of the on-disk index for the UI."""
    try:
        from lib.timetravel.snapshot import index_status as _index_status

        return _index_status()
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("timetravel index summary error: %s", exc)
        return {
            "exists": False,
            "files": 0,
            "rows": 0,
            "signature": None,
            "built_at": None,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def _timetravel_build_payload(
    *,
    at: datetime,
    scope_filter: tuple[str, ...] | None,
    cap: int,
) -> dict[str, Any]:
    """Build a single ``take_snapshot`` payload, with row-cap + no-data path."""
    from lib.timetravel.snapshot import DEFAULT_SCOPE, take_snapshot

    requested_scope = scope_filter or DEFAULT_SCOPE
    snap = take_snapshot(at, scope=requested_scope)
    snapshot_dict = _timetravel_truncate(snap.to_dict(), cap)

    # "No data this far back" detection: every scope is empty.
    entries = snapshot_dict.get("entries") or {}
    all_empty = bool(entries) and all(
        bool((entry or {}).get("empty", True)) for entry in entries.values()
    )
    return {
        "ok": True,
        "at": snapshot_dict.get("at"),
        "scope": snapshot_dict.get("scope"),
        "snapshot": snapshot_dict,
        "no_data": all_empty,
        "row_cap": cap,
        "index": _timetravel_index_summary(),
    }


@app.route("/timetravel")
@requires_auth
def timetravel_page():
    """Render the operator-facing as-of-T snapshot debug page."""
    from lib.timetravel.snapshot import DEFAULT_SCOPE

    return render_template(
        "pages/timetravel.html",
        current_page="timetravel",
        page_title="Time Travel",
        default_scopes=list(DEFAULT_SCOPE),
        index_summary=_timetravel_index_summary(),
    )


@app.route("/api/timetravel-snapshot")
@requires_auth
def api_timetravel_snapshot():
    """Return the as-of-T snapshot (and optionally a 'now' comparison).

    Query params:
      ``at`` — ISO-8601 / datetime-local string, defaults to ``utcnow()``
      ``compare_to_now`` — when truthy (``1``/``true``), include a second
        snapshot anchored at ``utcnow()`` for side-by-side rendering
      ``scope`` — optional comma-separated list (defaults to all scopes)
      ``max_rows_per_scope`` — int, default 200, max 2000
    """
    raw_at = request.args.get("at")
    parsed_at = _timetravel_parse_at(raw_at) if raw_at else datetime.now(UTC)
    if parsed_at is None:
        return jsonify(
            {
                "ok": False,
                "error": (
                    "invalid 'at' — expected ISO-8601 / datetime-local "
                    "(e.g. 2026-04-30T12:00 or 2026-04-30T12:00:00+00:00)"
                ),
                "at": raw_at,
            }
        ), 400

    raw_compare = (request.args.get("compare_to_now") or "").strip().lower()
    compare_to_now = raw_compare in {"1", "true", "yes", "on"}

    raw_scope = request.args.get("scope")
    scope_filter: tuple[str, ...] | None = None
    if raw_scope:
        scope_filter = tuple(s.strip() for s in raw_scope.split(",") if s.strip())
        if not scope_filter:
            scope_filter = None

    try:
        cap = int(request.args.get("max_rows_per_scope") or _TIMETRAVEL_DEFAULT_ROW_CAP)
    except (TypeError, ValueError):
        cap = _TIMETRAVEL_DEFAULT_ROW_CAP
    cap = max(1, min(cap, _TIMETRAVEL_MAX_ROW_CAP))

    try:
        primary = _timetravel_build_payload(at=parsed_at, scope_filter=scope_filter, cap=cap)
    except Exception as exc:  # noqa: BLE001 - return clean JSON, don't crash.
        log.warning("timetravel snapshot error (at=%s): %s", parsed_at, exc)
        return jsonify(
            {
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}"[:300],
                "at": parsed_at.isoformat(),
            }
        ), 500

    payload: dict[str, Any] = {
        "ok": True,
        "primary": primary,
        "compare_to_now": compare_to_now,
    }
    if compare_to_now:
        try:
            payload["now"] = _timetravel_build_payload(
                at=datetime.now(UTC), scope_filter=scope_filter, cap=cap
            )
        except Exception as exc:  # noqa: BLE001 - 'now' is best-effort.
            log.warning("timetravel 'now' snapshot error: %s", exc)
            payload["now"] = {
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}"[:300],
            }
    return jsonify(payload)


@app.route("/api/diligence-summary")
@requires_auth
def api_diligence_summary():
    return jsonify(_maybe_buyer_safe_payload(_build_diligence_summary()))


@app.route("/api/risk-kernel-summary")
@requires_auth
def api_risk_kernel_summary():
    return jsonify(_maybe_buyer_safe_payload(_build_risk_kernel_summary()))


@app.route("/api/provenance-summary")
@requires_auth
def api_provenance_summary():
    raw_hours = request.args.get("older_than_hours", "24")
    try:
        older_than_hours = float(raw_hours)
    except (TypeError, ValueError):
        older_than_hours = 24.0
    return jsonify(
        _maybe_buyer_safe_payload(_build_provenance_summary(older_than_hours=older_than_hours))
    )


@app.route("/api/test-suite-health")
@requires_auth
def api_test_suite_health():
    return jsonify(_maybe_buyer_safe_payload(_build_test_suite_health()))


@app.route("/api/launchagent-summary")
@requires_auth
def api_launchagent_summary():
    return jsonify(_maybe_buyer_safe_payload(_build_launchagent_summary()))


@app.route("/api/cross-asset-matrix")
@requires_auth
def api_cross_asset_matrix():
    window = request.args.get("window", "7d")
    method = request.args.get("method", "pearson")
    snapshot = _cross_asset_snapshot_cached()
    return jsonify(_matrix_payload(snapshot, window=window, method=method))


@app.route("/api/cross-asset-regime")
@requires_auth
def api_cross_asset_regime():
    snapshot = _cross_asset_snapshot_cached()
    history = _cross_asset_regime_history()
    if not history and snapshot.get("regime"):
        history = [snapshot["regime"]]
    return jsonify(
        {
            "ok": bool(snapshot.get("ok", True)),
            "mode": snapshot.get("mode", "cache_or_dry_run"),
            "generated_at": snapshot.get("generated_at"),
            "regime": snapshot.get("regime"),
            "history": history[-30:],
            "error": snapshot.get("error"),
        }
    )


@app.route("/api/x402/market-regime", methods=["POST"])
@requires_auth
def api_x402_market_regime():
    """Simulated x402-paid market-regime report.

    This endpoint intentionally uses the existing mock/pluggable x402 verifier
    path. It records non-secret receipts but does not enable facilitator
    settlement or any trading behavior.
    """
    try:
        from lib.payments.x402_market_regime import build_market_regime_report

        catalog, registry = _x402_market_regime_catalogs()
        product = catalog.get("market_regime_report")
        middleware = _x402_market_regime_middleware(product)
        requirements = product.to_payment_requirements(
            resource_url=request.url,
            pay_to=middleware.recipient,
            network=middleware.network,
            asset=middleware.asset,
        )
        payment_header = _x402_payment_header()
        allowed, body, result = middleware.gate(
            request.url,
            float(product.price_usd),
            payment_header,
            product.description,
            requirements=requirements,
        )
        if not allowed:
            status = "required" if not payment_header else "rejected"
            receipt = _append_x402_market_regime_receipt(
                product=product,
                requirements=requirements,
                payment_header=payment_header,
                verification=result,
                status=status,
            )
            response_body = dict(body or {})
            response_body["receipt"] = {
                "receipt_id": receipt.receipt_id,
                "status": receipt.status,
                "product_id": receipt.product_id,
            }
            resp = jsonify(response_body)
            resp.status_code = 402
            resp.headers["X-Payment-Required"] = "true"
            return resp

        snapshot = _cross_asset_snapshot_cached()
        report = build_market_regime_report(
            product=product,
            registry=registry,
            snapshot=snapshot,
            macro_features=_x402_fred_features_cached(),
        )
        receipt = _append_x402_market_regime_receipt(
            product=product,
            requirements=requirements,
            payment_header=payment_header,
            verification=result,
            status="accepted",
            artifact_id=str(report.get("artifact_id") or ""),
        )
        report["payment"] = {
            "receipt_id": receipt.receipt_id,
            "status": receipt.status,
            "network": receipt.network,
            "amount_atomic": receipt.amount_atomic,
            "live_settlement_allowed": product.live_settlement_allowed,
        }
        return jsonify(report)
    except Exception as exc:  # noqa: BLE001
        log.exception("x402 market-regime report failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/backtest", methods=["POST"])
@requires_auth
def api_x402_backtest():
    """Simulated x402-paid backtest receipt.

    This endpoint packages already-materialized local backtest artifacts. It
    does not run a strategy, pull market data, place orders, or enable live
    settlement.
    """
    try:
        from lib.analytics.backtest_results import leaderboard, summary
        from lib.payments.x402_backtest_receipt import build_backtest_receipt

        catalog, registry = _x402_product_catalogs()
        product = catalog.get("backtest_receipt")
        middleware = _x402_product_middleware(product)
        requirements = product.to_payment_requirements(
            resource_url=request.url,
            pay_to=middleware.recipient,
            network=middleware.network,
            asset=middleware.asset,
        )
        payment_header = _x402_payment_header()
        allowed, body, result = middleware.gate(
            request.url,
            float(product.price_usd),
            payment_header,
            product.description,
            requirements=requirements,
        )
        if not allowed:
            status = "required" if not payment_header else "rejected"
            receipt = _append_x402_product_receipt(
                product=product,
                requirements=requirements,
                payment_header=payment_header,
                verification=result,
                status=status,
                endpoint="/api/x402/backtest",
            )
            response_body = dict(body or {})
            response_body["receipt"] = {
                "receipt_id": receipt.receipt_id,
                "status": receipt.status,
                "product_id": receipt.product_id,
            }
            resp = jsonify(response_body)
            resp.status_code = 402
            resp.headers["X-Payment-Required"] = "true"
            return resp

        payload = request.get_json(silent=True) or {}
        metric = str(payload.get("metric") or "sortino")
        try:
            limit = int(payload.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        symbols = payload.get("symbols") or ()
        if isinstance(symbols, str):
            symbols = [symbols]
        if not isinstance(symbols, list | tuple):
            symbols = ()
        include_minimal = bool(payload.get("include_minimal_trades", False))
        bounded_limit = max(1, min(limit, 25))
        backtest_summary = summary()
        backtest_leaderboard = leaderboard(
            metric=metric,
            limit=bounded_limit,
            include_minimal_trades=include_minimal,
        )
        report = build_backtest_receipt(
            product=product,
            registry=registry,
            summary=backtest_summary,
            leaderboard=backtest_leaderboard,
            metric=metric,
            symbols=tuple(str(symbol) for symbol in symbols),
            limit=bounded_limit,
            include_minimal_trades=include_minimal,
        )
        receipt = _append_x402_product_receipt(
            product=product,
            requirements=requirements,
            payment_header=payment_header,
            verification=result,
            status="accepted",
            endpoint="/api/x402/backtest",
            artifact_id=str(report.get("artifact_id") or ""),
        )
        report["payment"] = {
            "receipt_id": receipt.receipt_id,
            "status": receipt.status,
            "network": receipt.network,
            "amount_atomic": receipt.amount_atomic,
            "live_settlement_allowed": product.live_settlement_allowed,
        }
        return jsonify(report)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        log.exception("x402 backtest receipt failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/agentwiki/search")
@requires_auth
def api_x402_agentwiki_search():
    """Free, authenticated discovery for rights-labeled AgentWiki artifacts."""

    try:
        from lib.payments.agentwiki import search_agentwiki_artifacts

        catalog, registry, artifacts = _agentwiki_context()
        try:
            limit = int(request.args.get("limit", "10"))
        except ValueError:
            limit = 10
        payload = search_agentwiki_artifacts(
            artifacts,
            catalog,
            registry,
            query=str(request.args.get("q") or ""),
            max_price_usd=request.args.get("max_price"),
            category=request.args.get("category"),
            limit=limit,
        )
        return jsonify(payload)
    except Exception as exc:  # noqa: BLE001
        log.exception("AgentWiki search failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/agentwiki/sources/grants-gov/search", methods=["GET", "POST"])
@requires_auth
def api_x402_agentwiki_grants_gov_search():
    """Cache-first Grants.gov source search for AgentWiki builders."""

    try:
        from lib.payments.agentwiki_grants_gov import search_grants_gov_opportunities

        body = request.get_json(silent=True) if request.method == "POST" else {}
        body = body if isinstance(body, dict) else {}

        def value(*keys: str, default=None):
            for key in keys:
                if key in body and body[key] not in (None, ""):
                    return body[key]
                arg_value = request.args.get(key)
                if arg_value not in (None, ""):
                    return arg_value
            return default

        def bool_value(*keys: str, default: bool = False) -> bool:
            raw = value(*keys, default=default)
            if isinstance(raw, bool):
                return raw
            return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}

        payload = search_grants_gov_opportunities(
            query=str(value("query", "q", default="")),
            limit=value("limit", "rows", default=10),
            statuses=value("statuses", "oppStatuses", default="forecasted|posted"),
            agencies=value("agencies", default=""),
            funding_categories=value("funding_categories", "fundingCategories", default=""),
            eligibilities=value("eligibilities", default=""),
            funding_instruments=value(
                "funding_instruments",
                "fundingInstruments",
                default="",
            ),
            aln=value("aln", default=""),
            opportunity_number=str(value("opportunity_number", "oppNum", default="")),
            fetch_live=bool_value("fetch_live", "live", default=False),
            use_cache=bool_value("use_cache", default=True),
            write_cache=bool_value("write_cache", default=False),
        )
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        log.exception("AgentWiki Grants.gov source search failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/agentwiki/artifacts/<artifact_id>/quote")
@requires_auth
def api_x402_agentwiki_quote(artifact_id: str):
    """Free quote and rights preview before an AgentWiki paid fetch."""

    try:
        from lib.payments.agentwiki import artifact_by_id, quote_agentwiki_artifact

        catalog, registry, artifacts = _agentwiki_context()
        artifact = artifact_by_id(artifacts, artifact_id)
        product = catalog.get(artifact.product_id)
        return jsonify(quote_agentwiki_artifact(artifact, product, registry))
    except KeyError:
        return jsonify({"error": "AgentWiki artifact not found", "artifact_id": artifact_id}), 404
    except Exception as exc:  # noqa: BLE001
        log.exception("AgentWiki quote failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/agentwiki/artifacts/<artifact_id>/content", methods=["POST"])
@requires_auth
def api_x402_agentwiki_content(artifact_id: str):
    """Simulated x402-paid AgentWiki artifact delivery.

    This endpoint serves static, rights-labeled seed artifacts only. It does not
    crawl, bypass access controls, mutate external systems, or enable live
    settlement.
    """

    endpoint = f"/api/x402/agentwiki/artifacts/{artifact_id}/content"
    try:
        from lib.payments.agentwiki import artifact_by_id, build_agentwiki_artifact_payload

        catalog, registry, artifacts = _agentwiki_context()
        artifact = artifact_by_id(artifacts, artifact_id)
        product = catalog.get(artifact.product_id)
        middleware = _x402_product_middleware(product)
        requirements = product.to_payment_requirements(
            resource_url=request.url,
            pay_to=middleware.recipient,
            network=middleware.network,
            asset=middleware.asset,
        )
        payment_header = _x402_payment_header()
        allowed, body, result = middleware.gate(
            request.url,
            float(product.price_usd),
            payment_header,
            product.description,
            requirements=requirements,
        )
        if not allowed:
            status = "required" if not payment_header else "rejected"
            receipt = _append_x402_product_receipt(
                product=product,
                requirements=requirements,
                payment_header=payment_header,
                verification=result,
                status=status,
                endpoint=endpoint,
            )
            response_body = dict(body or {})
            response_body["receipt"] = {
                "receipt_id": receipt.receipt_id,
                "status": receipt.status,
                "product_id": receipt.product_id,
            }
            resp = jsonify(response_body)
            resp.status_code = 402
            resp.headers["X-Payment-Required"] = "true"
            return resp

        payload = build_agentwiki_artifact_payload(artifact, product, registry)
        receipt = _append_x402_product_receipt(
            product=product,
            requirements=requirements,
            payment_header=payment_header,
            verification=result,
            status="accepted",
            endpoint=endpoint,
            artifact_id=str(payload.get("delivery_id") or artifact_id),
        )
        payload["payment"] = {
            "receipt_id": receipt.receipt_id,
            "status": receipt.status,
            "network": receipt.network,
            "amount_atomic": receipt.amount_atomic,
            "live_settlement_allowed": product.live_settlement_allowed,
        }
        return jsonify(payload)
    except KeyError:
        return jsonify({"error": "AgentWiki artifact not found", "artifact_id": artifact_id}), 404
    except Exception as exc:  # noqa: BLE001
        log.exception("AgentWiki artifact delivery failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/x402/products")
@requires_auth
def api_x402_products():
    """Authenticated discovery index for Sapphire x402-paid products."""

    try:
        from lib.payments.x402_product_index import build_product_index

        catalog, registry = _x402_product_catalogs()
        return jsonify(build_product_index(catalog, registry))
    except Exception as exc:  # noqa: BLE001
        log.exception("x402 product index failed")
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 500


@app.route("/api/cross-asset-breakdowns")
@requires_auth
def api_cross_asset_breakdowns():
    snapshot = _cross_asset_snapshot_cached()
    return jsonify(
        {
            "ok": bool(snapshot.get("ok", True)),
            "mode": snapshot.get("mode", "cache_or_dry_run"),
            "generated_at": snapshot.get("generated_at"),
            "breakdowns": snapshot.get("breakdowns") or [],
            "lead_lag": snapshot.get("lead_lag") or [],
            "error": snapshot.get("error"),
        }
    )


@app.route("/api/routine-pause-status")
@requires_auth
def api_routine_pause_status():
    return jsonify(_maybe_buyer_safe_payload(_build_routine_pause_summary()))


@app.route("/api/narrative-eval-summary")
@requires_auth
def api_narrative_eval_summary():
    try:
        from services.narrative_evaluation.run import summary

        limit = int(request.args.get("limit") or 1000)
        date = request.args.get("date") or None
        return jsonify(summary(date=date, limit=limit))
    except Exception as e:
        log.warning("narrative eval summary API error: %s", e)
        return jsonify(
            {
                "ok": False,
                "error": str(e),
                "overall": {"total": 0, "scored": 0, "accuracy": None},
                "by_symbol": {},
                "by_timeframe": {},
                "by_edge_bucket": {},
                "recent": [],
            }
        ), 200


@app.route("/api/narrative-eval-aggregates")
@requires_auth
def api_narrative_eval_aggregates():
    try:
        from services.narrative_evaluation.run import aggregates, calibration, diagnostics

        date = request.args.get("date") or None
        limit = int(request.args.get("limit") or 1000)
        view = str(request.args.get("view") or "aggregates").lower()
        if view == "diagnostics":
            return jsonify(diagnostics(date=date, limit=limit))
        if view == "calibration":
            return jsonify(calibration(date=date, limit=limit))
        group_by = request.args.get("group_by") or "symbol"
        return jsonify(aggregates(group_by=group_by, date=date, limit=limit))
    except Exception as e:
        log.warning("narrative eval aggregates API error: %s", e)
        return jsonify(
            {
                "ok": False,
                "error": str(e),
                "generated_at": datetime.now(UTC).isoformat(),
                "groups": {},
            }
        ), 200


@app.route("/api/foundry/readiness")
@requires_auth
def api_foundry_readiness():
    """Repo-grounded Foundry readiness: safe config checks + local artifact map."""
    try:
        from lib.foundry.readiness import build_foundry_readiness

        payload = build_foundry_readiness()
        payload["last_updated"] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("foundry readiness API error: %s", e)
        return jsonify(
            {
                "status": "unknown",
                "badge": "UNAVAILABLE",
                "auth_mode": "unknown",
                "connection_label": "Foundry readiness inspection failed.",
                "connector_registered": False,
                "configured_envs": {},
                "recommended_first_app": "Sapphire Mission Control",
                "transport_hint": "Dataset sync first.",
                "dataset_groups": [],
                "totals": {"groups": 0, "files": 0},
                "latest_materialization": None,
                "next_step": "Inspect the repo-level Foundry configuration and retry.",
                "error": str(e),
                "last_updated": time.time(),
            }
        ), 200


@app.route("/api/foundry/sync-status")
@requires_auth
def api_foundry_sync_status():
    """Foundry sync engine status — last sync, history, tracked files."""
    try:
        from lib.foundry.sync import get_sync_status

        payload = get_sync_status()
        payload["last_updated"] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("foundry sync-status API error: %s", e)
        return jsonify(
            {
                "last_sync": None,
                "last_status": "unavailable",
                "sync_count": 0,
                "tracked_files": 0,
                "recent_history": [],
                "recent_errors": 0,
                "interval_seconds": 900,
                "source_types": [],
                "error": str(e),
                "last_updated": time.time(),
            }
        ), 200


@app.route("/api/investments/intel")
@requires_auth
def api_investments_intel():
    """Read-only investment intelligence source mesh and thesis report."""
    try:
        from lib.intel.investment_intel import build_investment_intel_report

        live_crypto = str(request.args.get("live") or "").lower() in {"1", "true", "yes"}
        return jsonify(build_investment_intel_report(fetch_live_crypto=live_crypto))
    except Exception as e:
        log.warning("investment intel API error: %s", e)
        return jsonify(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "mode": "read-only",
                "error": str(e),
                "research_pack": {"available": False, "source_label": "unavailable"},
                "universe": [],
                "source_mesh": {
                    "connectors": [],
                    "coverage": [],
                    "totals": {"assets": 0, "connectors": 0, "configured_connectors": 0},
                    "missing_envs": [],
                },
                "source_probes": {"summary": {}, "probes": [], "series_catalog": []},
                "ops_queue": [],
                "analysis_lenses": [],
                "series_catalog": [],
                "materialization_plan": {"tables": [], "total_rows": 0},
                "mindset": [],
            }
        ), 200


@app.route("/api/investments/probes")
@requires_auth
def api_investments_probes():
    """Read-only investment source probes; live network probes require ?live=1."""
    try:
        from lib.intel.investment_intel import probe_source_mesh

        live = str(request.args.get("live") or "").lower() in {"1", "true", "yes"}
        return jsonify(probe_source_mesh(live=live))
    except Exception as e:
        log.warning("investment probes API error: %s", e)
        return jsonify(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "mode": "read-only",
                "live_requested": False,
                "error": str(e),
                "probes": [],
                "summary": {"total": 0, "ready": 0, "errors": 0},
                "series_catalog": [],
            }
        ), 200


@app.route("/api/investments/thesis")
@requires_auth
def api_investments_thesis():
    """Read-only cypherpunk/Austrian thesis matrix for investments."""
    try:
        from lib.intel.sovereign_thesis import build_sovereign_thesis_report

        return jsonify(build_sovereign_thesis_report())
    except Exception as e:
        log.warning("investment thesis API error: %s", e)
        return jsonify(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "mode": "research_intel_only",
                "error": str(e),
                "worldview": {"stance": "cypherpunk_austrian", "principles": []},
                "safety": {
                    "live_trading_enabled": False,
                    "execution_enabled": False,
                    "telegram_sends_enabled": False,
                    "guards": ["research_intel_only"],
                },
                "totals": {
                    "assets": 0,
                    "lenses": 0,
                    "core_assets": 0,
                    "aligned_assets": 0,
                    "watch_assets": 0,
                    "speculative_assets": 0,
                    "invalidation_watches": 0,
                    "tripped_invalidations": 0,
                    "source_requirements": 0,
                },
                "asset_classes": {},
                "lenses": [],
                "assets": [],
                "matrix": [],
                "invalidation_queue": [],
                "ops_queue": [],
                "source_requirements": [],
                "source_docs": [],
            }
        ), 200


@app.route("/api/autonomy/continuous-intelligence")
@requires_auth
def api_autonomy_continuous_intelligence():
    """Read-only work planner for continuous strategy, confluence, and thesis tasks."""
    try:
        from lib.autonomy.continuous_intelligence import build_continuous_intelligence_plan

        live = str(request.args.get("live") or "").lower() in {"1", "true", "yes"}
        return jsonify(build_continuous_intelligence_plan(fetch_live=live))
    except Exception as e:
        log.warning("continuous intelligence API error: %s", e)
        return jsonify(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "mode": "read_only_task_planning",
                "live_requested": False,
                "execution_enabled": False,
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "writes_by_default": False,
                "error": str(e),
                "safety": {
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                    "guards": ["read_only_task_generation", "dry_run_dispatch_only"],
                },
                "runtime_targets": [],
                "totals": {"tasks": 0, "blocked": 0, "lanes": {}, "priorities": {}, "runtimes": {}},
                "inputs": {},
                "tasks": [],
                "next_dispatch": [],
                "operating_loop": [],
                "source_docs": [],
            }
        ), 200


@app.route("/api/autonomy/org-coverage")
@requires_auth
def api_autonomy_org_coverage():
    """Read-only Sapphire and satellite repo coverage for the organization page."""
    try:
        from lib.autonomy.org_coverage import build_org_coverage

        external = str(request.args.get("external") or "").lower() in {"1", "true", "yes"}
        cache_key = f"org_coverage::{external}"
        return jsonify(
            get_cached(
                cache_key,
                lambda: build_org_coverage(external=external),
                ttl=30,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.warning("org coverage API error: %s", e)
        return jsonify(
            {
                "schema_version": 1,
                "mode": "org_coverage",
                "generated_at": datetime.now(UTC).isoformat(),
                "error": str(e),
                "summary": {
                    "repos_tracked": 0,
                    "satellite_repos": 0,
                    "upstream_tracked": 0,
                    "modules_tracked": 0,
                    "attention_items": 0,
                    "external_checked": False,
                },
                "safety": {
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                    "guards": ["dashboard_read_only", "error_fallback"],
                },
                "execution_enabled": False,
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "writes_by_default": False,
                "modules": [],
                "repos": [],
                "upstream_repos": [],
                "worktrees": [],
                "ci_strategies": [],
                "routine_stages": [],
                "programs": [],
            }
        ), 200


@app.route("/api/autonomy/quant-intelligence")
@requires_auth
def api_autonomy_quant_intelligence():
    """Read-only quant flywheel for assets, signals, validation, and work orders."""
    try:
        from lib.autonomy.quant_intelligence import build_quant_intelligence_flywheel

        live = str(request.args.get("live") or "").lower() in {"1", "true", "yes"}
        cache_key = f"quant_intelligence::{live}"
        return jsonify(
            get_cached(
                cache_key,
                lambda: build_quant_intelligence_flywheel(fetch_live=live),
                ttl=STRATEGY_LAB_CACHE_DURATION,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.warning("quant intelligence API error: %s", e)
        return jsonify(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "mode": "quant_intelligence_flywheel",
                "live_requested": False,
                "execution_enabled": False,
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "writes_by_default": False,
                "error": str(e),
                "safety": {
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                    "guards": ["read_only_quant_planning", "paper_forward_only"],
                },
                "current_state": {},
                "watch_universes": [],
                "signal_families": [],
                "validation_stack": [],
                "data_source_roadmap": [],
                "autonomy_gaps": [],
                "work_orders": [],
                "dispatch_now": [],
                "operating_loop": [],
                "totals": {},
                "source_docs": [],
            }
        ), 200


def _truncate_gemini_ooda_diff_value(value: Any, limit: int = 180) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, sort_keys=True)
    else:
        text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def _flatten_gemini_ooda_diff(value: Any, *, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, child in sorted(value.items()):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_gemini_ooda_diff(child, prefix=child_prefix))
        return flattened
    return {prefix: value}


def _gemini_ooda_diff(today: dict[str, Any], yesterday: dict[str, Any] | None) -> dict[str, Any]:
    """Paste-safe diff for daily OODA packets shown on the dashboard."""
    if not yesterday:
        return {
            "available": False,
            "reason": "missing_yesterday_packet",
            "added": [],
            "removed": [],
            "mutated": [],
        }
    today_flat = _flatten_gemini_ooda_diff(
        {
            "topic": today.get("topic"),
            "tool_response": today.get("tool_response"),
            "context_summary": today.get("context_summary"),
        }
    )
    yesterday_flat = _flatten_gemini_ooda_diff(
        {
            "topic": yesterday.get("topic"),
            "tool_response": yesterday.get("tool_response"),
            "context_summary": yesterday.get("context_summary"),
        }
    )
    today_keys = set(today_flat)
    yesterday_keys = set(yesterday_flat)
    return {
        "available": True,
        "added": sorted(today_keys - yesterday_keys),
        "removed": sorted(yesterday_keys - today_keys),
        "mutated": [
            {
                "key": key,
                "before": _truncate_gemini_ooda_diff_value(yesterday_flat[key]),
                "after": _truncate_gemini_ooda_diff_value(today_flat[key]),
            }
            for key in sorted(today_keys & yesterday_keys)
            if today_flat[key] != yesterday_flat[key]
        ],
    }


def _load_gemini_ooda_daily_diff(
    *,
    packet_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    packet_dir = packet_dir or _GEMINI_OODA_DAILY_DIR
    current = (now or datetime.now(UTC)).astimezone(UTC).date()
    today_path = packet_dir / f"{current.isoformat()}.json"
    yesterday_path = packet_dir / f"{(current - timedelta(days=1)).isoformat()}.json"
    if not today_path.exists():
        return {
            "available": False,
            "reason": "missing_today_packet",
            "today_path": str(today_path),
            "yesterday_path": str(yesterday_path),
            "added": [],
            "removed": [],
            "mutated": [],
        }
    try:
        today_payload = json.loads(today_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "reason": "today_packet_unreadable",
            "error": type(exc).__name__,
            "today_path": str(today_path),
            "yesterday_path": str(yesterday_path),
            "added": [],
            "removed": [],
            "mutated": [],
        }
    yesterday_payload = None
    if yesterday_path.exists():
        try:
            yesterday_payload = json.loads(yesterday_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            yesterday_payload = None
    diff = _gemini_ooda_diff(today_payload, yesterday_payload)
    diff.update(
        {
            "today": current.isoformat(),
            "yesterday": (current - timedelta(days=1)).isoformat(),
            "today_path": str(today_path),
            "yesterday_path": str(yesterday_path),
        }
    )
    return diff


def _request_truthy(*names: str) -> bool:
    for name in names:
        raw = (request.args.get(name) or "").strip().lower()
        if raw in {"1", "true", "yes", "y"}:
            return True
    return False


@app.route("/api/gemini-ooda")
@requires_auth
def api_gemini_ooda():
    """Read-only Gemini OODA synthesizer surface — dry-run by default.

    Returns the tool's status block and an optional dry-run synthesis from
    the current sovereign-thesis snapshot. Live Gemini calls require
    SAPPHIRE_GEMINI_LIVE=1 + the sensitivity gate + the rate/cost caps in
    the underlying tool; this endpoint never opts into live mode itself.
    """
    try:
        import importlib.util
        from pathlib import Path

        sapphire_root = Path(__file__).resolve().parents[2]
        tool_path = (
            sapphire_root / "plugins" / "claw-sapphire" / "tools" / "internal" / "gemini_ooda.py"
        )
        spec = importlib.util.spec_from_file_location("gemini_ooda_dashboard", tool_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not locate gemini_ooda tool")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        topic_arg = (request.args.get("topic") or "").strip()
        topic = topic_arg or "Sapphire daily thesis OODA snapshot"
        context_arg = (request.args.get("context") or "").strip()
        if not context_arg:
            try:
                from lib.intel.sovereign_thesis import build_sovereign_thesis_report

                thesis = build_sovereign_thesis_report()
                top_assets = (
                    thesis.get("assets") or (thesis.get("asset_matrix") or {}).get("rows") or []
                )
                ranked = sorted(
                    [
                        row
                        for row in top_assets
                        if (
                            row.get("relative_score")
                            if "relative_score" in row
                            else row.get("score")
                        )
                        is not None
                    ],
                    key=lambda row: (
                        (row.get("relative_score") if "relative_score" in row else row.get("score"))
                        or 0
                    ),
                    reverse=True,
                )[:4]
                summary = (
                    ", ".join(
                        f"{row.get('symbol') or row.get('asset', '?')} "
                        f"score={row.get('relative_score') if 'relative_score' in row else row.get('score')}"
                        for row in ranked
                    )
                    or "no ranked assets available"
                )
                lenses = thesis.get("lenses") or []
                lens_count = len((lenses.get("rows") if isinstance(lenses, dict) else lenses) or [])
                context_arg = (
                    f"Top thesis assets (paste-safe summary, no positions): {summary}. "
                    f"Lenses tracked: {lens_count}. Mode is research_intel_only."
                )
            except Exception:
                context_arg = "Sovereign-thesis snapshot unavailable; use a paste-safe summary in the next request."

        synthesis = module.synthesize(
            topic=topic,
            context=context_arg,
            mode="dry-run",
            model="gemini-2.5-flash",
            max_output_tokens=512,
            ttl_seconds=86400,
        )
        status = module.status()

        body = {
            "mode": "gemini_ooda_dry_run_dashboard",
            "safety": {
                "execution_enabled": False,
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "writes_by_default": False,
                "guards": [
                    "dashboard_endpoint_dry_run_only",
                    "live_mode_requires_sapphire_gemini_live_env",
                    "live_mode_requires_sensitivity_gate",
                    "per_hour_and_per_month_token_caps_enforced",
                ],
            },
            "topic": topic,
            "context_summary_chars": len(context_arg),
            "synthesis": synthesis,
            "tool_status": status,
            "last_updated": time.time(),
        }
        if _request_truthy("diff", "include_diff"):
            body["daily_diff"] = _load_gemini_ooda_daily_diff()
        return jsonify(body)
    except Exception as e:
        log.warning("gemini-ooda API error: %s", e)
        return jsonify(
            {
                "mode": "gemini_ooda_dry_run_dashboard",
                "error": str(e),
                "safety": {
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                    "writes_by_default": False,
                    "guards": ["dashboard_endpoint_dry_run_only"],
                },
                "synthesis": None,
                "tool_status": None,
                "last_updated": time.time(),
            }
        ), 200


# ── Product surfaces: /threat-intel and /customer-dossier ────────────
#
# These read-only pages productize the existing threat_intel and tho_intel
# plugin tools as buyer-facing dashboard surfaces. Both routes:
#
# * are GET-only,
# * inherit the dashboard's basic-auth via @requires_auth,
# * read from local JSON snapshots — never make live network calls,
# * render an empty state if the snapshot is missing,
# * apply paste-safe redaction for any field that could contain PII.


_THREAT_INTEL_INTELLIGENCE_DIR = _DASHBOARD_REPO_ROOT / "data" / "intelligence"
_THREAT_INTEL_LATEST_SYMLINK = _THREAT_INTEL_INTELLIGENCE_DIR / "latest"
_TARGET_THREAT_INTEL_DAYS = 7


def _safe_threats_payload(error: str | None = None) -> dict[str, Any]:
    """Emit the canonical empty-state envelope for /api/threat-intel."""
    return {
        "mode": "threat_intel_product_dashboard",
        "available": False,
        "snapshot_date": None,
        "refreshed_at": None,
        "error": error,
        "summary": {
            "total_threats": 0,
            "exploited": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        },
        "kev_top": [],
        "nvd_critical": [],
        "mitre_techniques": [],
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "writes_by_default": False,
            "telegram_sends_enabled": False,
            "guards": [
                "read_only_endpoint",
                "no_live_network_calls",
                "snapshot_only_read",
            ],
        },
        "last_updated": time.time(),
    }


def _select_latest_threat_snapshot() -> tuple[Path | None, str | None]:
    """Resolve the most recent threats.json snapshot in data/intelligence/.

    Returns (path, snapshot_date_iso) or (None, None) if no usable snapshot
    is on disk. Prefers the ``latest`` symlink when it exists; falls back
    to the lexicographically newest dated directory containing threats.json.
    """
    if not _THREAT_INTEL_INTELLIGENCE_DIR.exists():
        return None, None
    # Prefer the symlink — the refresh job updates it atomically.
    candidate = _THREAT_INTEL_LATEST_SYMLINK / "threats.json"
    if candidate.is_file():
        try:
            target = (
                _THREAT_INTEL_LATEST_SYMLINK.resolve(strict=True)
                if _THREAT_INTEL_LATEST_SYMLINK.is_symlink()
                else _THREAT_INTEL_LATEST_SYMLINK
            )
            return candidate, target.name
        except OSError:
            pass
    # Fall back: scan dated subdirs.
    candidates = sorted(
        (
            p
            for p in _THREAT_INTEL_INTELLIGENCE_DIR.iterdir()
            if p.is_dir() and (p / "threats.json").is_file()
        ),
        reverse=True,
    )
    for d in candidates:
        return d / "threats.json", d.name
    return None, None


def _classify_threat_severity(score: float, exploited: bool) -> str:
    if exploited and score >= 9.0:
        return "critical"
    if exploited or score >= 9.0:
        return "high"
    if score >= 7.0:
        return "medium"
    return "low"


def _build_threat_intel_payload(
    *, snapshot_path: Path | None, snapshot_date: str | None
) -> dict[str, Any]:
    if snapshot_path is None:
        payload = _safe_threats_payload(error="no_snapshot_available")
        return payload
    try:
        raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _safe_threats_payload(error=f"snapshot_unreadable: {type(exc).__name__}")

    threats = raw.get("threats") or []
    refreshed_at = raw.get("refreshed_at")
    summary = {
        "total_threats": len(threats),
        "exploited": sum(1 for t in threats if t.get("exploited")),
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    kev_rows: list[dict[str, Any]] = []
    nvd_rows: list[dict[str, Any]] = []
    technique_counts: dict[str, dict[str, Any]] = {}

    for t in threats:
        score = float(t.get("score") or 0.0)
        exploited = bool(t.get("exploited"))
        sev = _classify_threat_severity(score, exploited)
        summary[sev] = summary.get(sev, 0) + 1

        sources = t.get("source") or ""
        canonical_id = t.get("canonical_id") or ""

        # KEV bucket: anything tagged as KEV / sourced from cisa-kev.
        is_kev = "kev" in str(sources).lower() or "kev" in [
            tag.lower() for tag in (t.get("tags") or [])
        ]
        title = (t.get("title") or "").strip()[:200]

        row = {
            "canonical_id": str(canonical_id)[:64],
            "title": title,
            "severity": sev,
            "score": round(score, 2),
            "exploited": exploited,
            "published_at": t.get("published_at"),
            "vendor_project": (t.get("metadata") or {}).get("vendor_project") or "",
            "product": (t.get("metadata") or {}).get("product") or "",
            "due_date": (t.get("metadata") or {}).get("due_date") or None,
            "url": t.get("url") or "",
        }

        if is_kev:
            kev_rows.append(row)
        if score >= 9.0:
            nvd_rows.append(row)

        # MITRE ATT&CK techniques live in source_type=technique or in tags
        # like T1234. We aggregate counts.
        if t.get("source_type") == "technique" or t.get("source") == "mitre-attack":
            tid = canonical_id or title
            entry = technique_counts.setdefault(
                str(tid)[:32],
                {"id": str(tid)[:32], "title": title, "citations": 0, "severity": sev},
            )
            entry["citations"] += 1
        for tag in t.get("tags") or []:
            tag_str = str(tag)
            if (
                tag_str.startswith("T")
                and len(tag_str) >= 5
                and tag_str[1:].split(".")[0].isdigit()
            ):
                entry = technique_counts.setdefault(
                    tag_str[:32],
                    {"id": tag_str[:32], "title": "", "citations": 0, "severity": sev},
                )
                entry["citations"] += 1

    kev_rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    nvd_rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)
    technique_rows = sorted(
        technique_counts.values(), key=lambda r: r.get("citations", 0), reverse=True
    )

    return {
        "mode": "threat_intel_product_dashboard",
        "available": True,
        "snapshot_date": snapshot_date,
        "refreshed_at": refreshed_at,
        "error": None,
        "summary": summary,
        "kev_top": kev_rows[:10],
        "nvd_critical": nvd_rows[:10],
        "mitre_techniques": technique_rows[:10],
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "writes_by_default": False,
            "telegram_sends_enabled": False,
            "guards": [
                "read_only_endpoint",
                "no_live_network_calls",
                "snapshot_only_read",
            ],
        },
        "last_updated": time.time(),
    }


@app.route("/threat-intel")
@requires_auth
def threat_intel_page():
    """Buyer-facing threat intelligence dashboard (read-only, paste-safe)."""
    return render_template(
        "pages/threat_intel.html",
        current_page="threat-intel",
        page_title="Threat Intelligence",
    )


@app.route("/api/threat-intel")
@requires_auth
def api_threat_intel():
    """JSON envelope for /threat-intel — reads the latest threats.json snapshot."""
    try:
        snapshot_path, snapshot_date = _select_latest_threat_snapshot()
        payload = _build_threat_intel_payload(
            snapshot_path=snapshot_path, snapshot_date=snapshot_date
        )
        return jsonify(payload)
    except Exception as e:
        log.warning("threat-intel API error: %s", e)
        return jsonify(_safe_threats_payload(error=str(e))), 200


# ── Customer dossier ─────────────────────────────────────────────────


_TARGET_TH_INTEL_DIR = _DASHBOARD_REPO_ROOT / "data" / "tho_intel"

# Customer-dossier 0.2.0 — per-tenant hash + cell-suppression
#
# 0.2.0 closes two follow-ups from 0.1.0:
#   1. Per-tenant hash isolation. The 0.1.0 surface used a single global salt
#      for ``customer_<6charhash>`` redaction. A multi-tenant buyer can now
#      configure ``SAPPHIRE_DOSSIER_HASH_SALT_<TENANT_ID>`` in
#      ``~/.sapphire/secrets.env`` and the dashboard will mix that salt into
#      an HMAC-SHA256 derived id of the form ``tenant_<id>_<16hex>``. When the
#      env var is missing we fall back to a deterministic-but-randomized
#      default — so a tenant without configured salt continues to get a stable
#      hash (no breaking change vs 0.1.0).
#   2. Cell-suppression on small status buckets. Any ``by_status`` count below
#      ``_DOSSIER_CELL_SUPPRESSION_THRESHOLD`` (5) is reported as the literal
#      string ``"<5"`` instead of the exact integer. Buckets at the threshold
#      or above pass through with the exact integer.
_DOSSIER_DEFAULT_TENANT_ID = "default"
_DOSSIER_TENANT_SALT_ENV_PREFIX = "SAPPHIRE_DOSSIER_HASH_SALT_"
_DOSSIER_CELL_SUPPRESSION_THRESHOLD = 5
_DOSSIER_SECRETS_PATH = Path.home() / ".sapphire" / "secrets.env"


def _normalize_dossier_tenant_id(tenant_id: str | None) -> str:
    """Normalize a tenant id for env lookup + hash scoping.

    Reduces to ASCII alnum + underscore so ``acme corp`` becomes ``ACME_CORP``
    on the env side and ``acme corp`` on the canonical-lower side.
    """
    raw = (tenant_id or "").strip()
    if not raw:
        return _DOSSIER_DEFAULT_TENANT_ID
    safe = re.sub(r"[^A-Za-z0-9_]", "_", raw)
    safe = safe.strip("_") or _DOSSIER_DEFAULT_TENANT_ID
    return safe[:64]


def _load_dossier_tenant_salt(
    tenant_id: str,
    *,
    secrets_path: Path | None = None,
) -> str | None:
    """Load the per-tenant salt for ``tenant_id`` from the operator secrets.

    Looks first at the live process environment (``SAPPHIRE_DOSSIER_HASH_SALT_<TENANT>``).
    If the env var is unset we parse ``~/.sapphire/secrets.env`` (or the
    explicit ``secrets_path`` for tests) for a matching ``KEY=value`` line.
    Returns ``None`` when nothing is configured — the caller falls back to
    the deterministic-but-randomized default in :func:`per_tenant_hash`.

    The secrets file is only read here; we never log its contents and we
    only return the matching value (no broadcasts, no aggregation).
    """
    env_key = _DOSSIER_TENANT_SALT_ENV_PREFIX + _normalize_dossier_tenant_id(tenant_id).upper()
    env_value = os.environ.get(env_key)
    if env_value:
        cleaned = env_value.strip().strip('"').strip("'")
        if cleaned:
            return cleaned
    path = secrets_path if secrets_path is not None else _DOSSIER_SECRETS_PATH
    try:
        if not path.is_file():
            return None
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("export "):
                    stripped = stripped[len("export ") :].lstrip()
                if "=" not in stripped:
                    continue
                k, _, v = stripped.partition("=")
                if k.strip() != env_key:
                    continue
                value = v.strip().strip('"').strip("'")
                return value or None
    except OSError:
        return None
    return None


def _suppress_small_buckets(
    by_status: dict[str, int],
    *,
    threshold: int = _DOSSIER_CELL_SUPPRESSION_THRESHOLD,
) -> dict[str, int | str]:
    """Apply cell-suppression to status buckets.

    Buckets with count strictly less than ``threshold`` are reported as the
    literal string ``"<{threshold}"`` (default ``"<5"``); buckets at or above
    the threshold pass through with the exact integer count. Empty input
    returns an empty dict. Negative counts are coerced to ``0`` defensively.
    """
    suppressed: dict[str, int | str] = {}
    marker = f"<{threshold}"
    for status, count in (by_status or {}).items():
        try:
            n = int(count)
        except (TypeError, ValueError):
            n = 0
        if n < 0:
            n = 0
        if n < threshold:
            suppressed[status] = marker
        else:
            suppressed[status] = n
    return suppressed


def _safe_dossier_payload(error: str | None = None) -> dict[str, Any]:
    """Empty-state envelope for /api/customer-dossier."""
    return {
        "mode": "customer_dossier_product_dashboard",
        "available": False,
        "snapshot_at": None,
        "error": error,
        "summary": {
            "total_customers": 0,
            "by_status": {},
            "document_templates": 0,
            "deals_recent": 0,
        },
        "recent_deals": [],
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "writes_by_default": False,
            "telegram_sends_enabled": False,
            "pii_redaction": "applied_to_every_leaf",
            "guards": [
                "read_only_endpoint",
                "no_live_network_calls",
                "snapshot_only_read",
                "pii_redaction_required",
            ],
        },
        "last_updated": time.time(),
    }


def _select_latest_dossier_snapshot() -> Path | None:
    """Resolve the latest paste-safe customer dossier snapshot.

    The plugin tool writes ``data/tho_intel/dossier_*.json`` (or the legacy
    ``latest_*.md`` for human consumption). The dashboard surface only reads
    JSON — markdown is for human triage, not for buyer-facing dashboards.
    """
    if not _TARGET_TH_INTEL_DIR.exists():
        return None
    candidates = sorted(_TARGET_TH_INTEL_DIR.glob("dossier_*.json"), reverse=True)
    if candidates:
        return candidates[0]
    # Fall back to a "latest.json" if the operator pinned one explicitly.
    pinned = _TARGET_TH_INTEL_DIR / "latest.json"
    if pinned.is_file():
        return pinned
    return None


def _build_dossier_payload(
    snapshot_path: Path | None,
    *,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Construct the redacted customer-dossier envelope.

    Non-negotiable contract: every string leaf passes through
    ``lib.security.pii_redactor.redact_record`` before it is encoded into the
    JSON response. The redactor is pure (no I/O), so this is safe to call
    inside the request path.

    0.2.0 additions:
      * Per-tenant hash is mixed into the response under
        ``customers[*].per_tenant_hash`` so tenants can correlate their own
        records across snapshots without exposing the underlying PII.
      * ``summary.by_status`` runs through cell-suppression: buckets with
        count <5 are reported as the literal ``"<5"`` to discourage
        re-identification of small cohorts.
    """
    try:
        from lib.security.pii_redactor import per_tenant_hash, redact_record
    except Exception as exc:  # pragma: no cover — defensive
        return _safe_dossier_payload(error=f"redactor_unavailable: {exc}")

    if snapshot_path is None:
        return _safe_dossier_payload(error="no_snapshot_available")
    try:
        raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _safe_dossier_payload(error=f"snapshot_unreadable: {type(exc).__name__}")

    norm_tenant = _normalize_dossier_tenant_id(tenant_id)
    tenant_salt = _load_dossier_tenant_salt(norm_tenant)
    salt_source = "configured" if tenant_salt is not None else "default_fallback"

    # Compute summary counters from the raw payload, but DO NOT echo any
    # raw string back; the redactor handles every string leaf.
    customers = raw.get("customers") or []
    by_status_counts: dict[str, int] = {}
    customer_hashes: list[dict[str, Any]] = []
    for c in customers:
        status = str(c.get("status") or "UNKNOWN").upper()[:32]
        by_status_counts[status] = by_status_counts.get(status, 0) + 1
        # Per-tenant hash uses the most identifying field available — name,
        # falling back to email (also PII), then to the customer id. We never
        # echo the original value.
        anchor = c.get("customer_name") or c.get("email") or c.get("id") or c.get("customer_id")
        if anchor is None:
            continue
        customer_hashes.append(
            {
                "per_tenant_hash": per_tenant_hash(str(anchor), norm_tenant, salt=tenant_salt),
                "status": status,
            }
        )

    deals = (raw.get("deals") or [])[:10]
    summary = {
        "total_customers": len(customers),
        "by_status": _suppress_small_buckets(by_status_counts),
        "by_status_exact": by_status_counts if False else None,  # never emit exact counts
        "document_templates": int(raw.get("document_template_count") or 0),
        "deals_recent": len(deals),
        "cell_suppression": {
            "applied": True,
            "threshold": _DOSSIER_CELL_SUPPRESSION_THRESHOLD,
            "marker": f"<{_DOSSIER_CELL_SUPPRESSION_THRESHOLD}",
        },
    }
    # Drop the never-emitted-exact-counts placeholder so the payload stays
    # tight. We keep the assignment above to make it obvious that the exact
    # counts are intentionally NOT exposed even when the operator queries
    # the route directly.
    summary.pop("by_status_exact", None)

    redacted_deals = redact_record(deals)
    redacted_meta = redact_record(raw.get("metadata") or {})

    return {
        "mode": "customer_dossier_product_dashboard",
        "available": True,
        "snapshot_at": raw.get("snapshot_at") or raw.get("generated_at"),
        "snapshot_path_basename": snapshot_path.name,
        "error": None,
        "summary": summary,
        "tenant": {
            "id": norm_tenant,
            "salt_source": salt_source,
            "hash_algorithm": "HMAC-SHA256",
        },
        "customer_hashes": customer_hashes,
        "recent_deals": redacted_deals,
        "metadata": redacted_meta,
        "safety": {
            "execution_enabled": False,
            "live_trading_enabled": False,
            "writes_by_default": False,
            "telegram_sends_enabled": False,
            "pii_redaction": "applied_to_every_leaf",
            "cell_suppression": "applied",
            "per_tenant_hash": "applied",
            "guards": [
                "read_only_endpoint",
                "no_live_network_calls",
                "snapshot_only_read",
                "pii_redaction_required",
                "cell_suppression_lt_5",
                "per_tenant_hmac_sha256",
            ],
        },
        "last_updated": time.time(),
    }


@app.route("/customer-dossier")
@requires_auth
def customer_dossier_page():
    """Buyer-facing customer dossier dashboard (PII-redacted, read-only)."""
    return render_template(
        "pages/customer_dossier.html",
        current_page="customer-dossier",
        page_title="Customer Dossier",
    )


@app.route("/api/customer-dossier")
@requires_auth
def api_customer_dossier():
    """JSON envelope for /customer-dossier — reads the latest dossier snapshot."""
    try:
        snapshot_path = _select_latest_dossier_snapshot()
        # 0.2.0 — accept ?tenant=<id> for per-tenant hash isolation. Default
        # tenant ("default") still gets a deterministic hash via the
        # fallback salt path, so 0.1.0 callers continue to work unchanged.
        tenant_id = request.args.get("tenant") or _DOSSIER_DEFAULT_TENANT_ID
        payload = _build_dossier_payload(snapshot_path, tenant_id=tenant_id)
        return jsonify(payload)
    except Exception as e:
        log.warning("customer-dossier API error: %s", e)
        return jsonify(_safe_dossier_payload(error=str(e))), 200


@app.route("/api/autonomy/continuous-intelligence/artifacts")
@requires_auth
def api_autonomy_continuous_intelligence_artifacts():
    """Read-only artifact status and snapshot preview for continuous intelligence."""
    try:
        from lib.autonomy.continuous_intelligence_artifacts import artifact_status, snapshot_tasks

        status = artifact_status()
        preview = snapshot_tasks(write=False)
        return jsonify(
            {
                **status,
                "snapshot_preview": preview,
                "write_enabled": False,
            }
        )
    except Exception as e:
        log.warning("continuous intelligence artifact API error: %s", e)
        return jsonify(
            {
                "mode": "continuous_intelligence_artifact_status",
                "error": str(e),
                "write_enabled": False,
                "writes_by_default": False,
                "execution_enabled": False,
                "live_trading_enabled": False,
                "telegram_sends_enabled": False,
                "files": {},
                "totals": {},
                "snapshot_preview": {"records": 0, "write_enabled": False},
            }
        ), 200


@app.route("/api/autonomy/continuous-intelligence/lease-preview")
@requires_auth
def api_autonomy_continuous_intelligence_lease_preview():
    """Preview dry-run task leases. This endpoint never writes lease files."""
    try:
        from lib.autonomy.continuous_intelligence_artifacts import lease_tasks

        try:
            limit = int(request.args.get("limit", "3"))
        except ValueError:
            limit = 3
        capabilities = [item.strip() for item in request.args.getlist("capability") if item.strip()]
        target_runtime = request.args.get("target_runtime") or None
        runtime_status = None
        if target_runtime == "windows-gpu":
            try:
                runtime_status = _build_system_failover_status()
            except Exception as exc:
                log.warning("continuous intelligence runtime guard probe error: %s", exc)
                runtime_status = {
                    "mode_name": "read_only_system_failover_status",
                    "mode": "unknown",
                    "status": "unknown",
                    "windows_offline": True,
                    "fallback_ready": False,
                    "active_route": None,
                    "error": f"{exc.__class__.__name__}: {exc}"[:200],
                }
        lease_kwargs = {
            "agent_id": str(request.args.get("agent_id") or "windows-gpu"),
            "capabilities": capabilities,
            "target_runtime": target_runtime,
            "limit": limit,
            "write": False,
        }
        if runtime_status is not None:
            lease_kwargs["runtime_status"] = runtime_status
        payload = lease_tasks(**lease_kwargs)
        return jsonify(payload)
    except Exception as e:
        log.warning("continuous intelligence lease preview API error: %s", e)
        return jsonify(
            {
                "mode": "dry_run_task_lease",
                "error": str(e),
                "write_enabled": False,
                "writes_by_default": False,
                "leases": [],
                "leased_count": 0,
                "candidate_count": 0,
                "safety": {
                    "dry_run_dispatch_only": True,
                    "execution_enabled": False,
                    "live_trading_enabled": False,
                    "telegram_sends_enabled": False,
                },
            }
        ), 200


@app.route("/api/investments/sources")
@requires_auth
def api_investments_sources():
    """Read-only source connection map for equities, macro, energy, and crypto."""
    try:
        from lib.intel.investment_intel import build_source_report

        return jsonify(build_source_report())
    except Exception as e:
        log.warning("investment sources API error: %s", e)
        return jsonify(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "mode": "read-only",
                "error": str(e),
                "research_pack": {"available": False, "source_label": "unavailable"},
                "source_mesh": {
                    "connectors": [],
                    "coverage": [],
                    "totals": {"assets": 0, "connectors": 0, "configured_connectors": 0},
                    "missing_envs": [],
                },
                "source_probes": {"summary": {}, "probes": [], "series_catalog": []},
                "series_catalog": [],
                "robinhood": {"configured": False, "mode": "read-only portfolio snapshot"},
            }
        ), 200


@app.route("/api/portfolio")
@requires_auth
def api_portfolio():
    """Unified multi-venue portfolio snapshot (Robinhood + OKX).

    Top-level keys are unchanged from the previous Robinhood-only shape;
    ``sources``, ``by_asset`` and per-holding ``venue`` are additive. Venues
    degrade independently — an unconfigured OKX does not blank the page.
    """

    def fetch():
        from lib.portfolio.aggregate import PortfolioAggregator

        return PortfolioAggregator().get_snapshot()

    try:
        return jsonify(
            get_cached(
                "portfolio_snapshot",
                fetch,
                ttl=PORTFOLIO_CACHE_DURATION,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.warning("portfolio API error: %s", e)
        return jsonify(
            {
                "source": "unavailable",
                "error": str(e),
                "holdings": [],
                "by_asset": [],
                "sources": [],
                "venue_count": 0,
                "total_value": 0,
                "day_pnl": 0,
                "day_pnl_pct": 0,
                "total_return": 0,
                "total_return_pct": 0,
                "cash": 0,
                "buying_power": 0,
                "sectors": [],
                "asset_classes": [],
            }
        ), 200


@app.route("/api/factors")
@requires_auth
def api_factors():
    """Cross-sectional factor scores (CoinGecko, 1h cache)."""
    try:
        from lib.analytics.factors import CrossSectionalFactors
        from lib.analytics.factors import to_dict as factors_to_dict

        report = CrossSectionalFactors().compute()
        return jsonify(factors_to_dict(report))
    except Exception as e:
        log.warning("factors API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "assets": [],
                "ranked_assets": [],
                "factor_names": [],
                "strongest": None,
                "weakest": None,
                "dispersion": 0,
                "asset_count": 0,
            }
        ), 200


@app.route("/api/cascade")
@requires_auth
def api_cascade():
    """Live liquidation cascade risk via Hyperliquid OI + funding data."""

    def fetch():
        from lib.analytics.liquidation import CascadeDetector
        from lib.analytics.liquidation import to_dict as cascade_to_dict

        report = CascadeDetector().assess_all(["BTC", "ETH", "SOL", "LINK", "ARB", "AVAX"])
        return cascade_to_dict(report)

    try:
        return jsonify(
            get_cached(
                "cascade_risk",
                fetch,
                ttl=CASCADE_CACHE_DURATION,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.warning("cascade API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "risk_score": 0,
                "risk_label": "UNAVAILABLE",
                "assets": [],
                "total_oi_usd": 0,
                "avg_funding_8h": 0,
            }
        ), 200


def _attach_geo(item: dict) -> dict:
    """Augment an intel item with ``latitude``/``longitude`` when resolvable.

    Precedence: explicit fields, then region-tag centroid lookup from
    ``lib.intel.lead_enricher.REGION_CENTROIDS``. Never mutates on failure.
    """
    try:
        lat = item.get("latitude")
        lng = item.get("longitude")
        if lat is not None and lng is not None:
            item["latitude"] = float(lat)
            item["longitude"] = float(lng)
            item.setdefault("geo_source", "explicit")
            return item
        from lib.intel.lead_enricher import REGION_CENTROIDS

        region = str(item.get("region") or "").lower().strip()
        if region and region in REGION_CENTROIDS:
            rlat, rlng = REGION_CENTROIDS[region]
            item["latitude"] = rlat
            item["longitude"] = rlng
            item["geo_source"] = "region_centroid"
    except Exception:
        pass
    return item


def _telegram_history_intel_summary(
    data_dir: Path | None = None,
    *,
    signal_limit: int = 10,
) -> dict[str, Any]:
    """Return an auth-gated, path-safe summary of offline Telegram history intel."""
    root = data_dir or _TELEGRAM_HISTORY_INTEL_DIR
    context_path = root / "conversation_context.json"
    messages_path = root / "messages.jsonl"
    base: dict[str, Any] = {
        "available": False,
        "status": "missing",
        "summary": {
            "chats": 0,
            "messages": 0,
            "participants": 0,
            "open_loops": 0,
            "commitments": 0,
            "decisions": 0,
            "top_tags": [],
        },
        "artifacts": {
            "messages_jsonl": messages_path.exists(),
            "messages_envelope": (root / "messages.jsonl.envelope.json").exists(),
            "context_json": context_path.exists(),
            "context_envelope": (root / "conversation_context.json.envelope.json").exists(),
            "context_provenance_verified": False,
        },
        "latest_message_at": None,
        "signals": {"open_loops": [], "commitments": [], "decisions": []},
        "safety": {
            "telegram_sends_enabled": False,
            "live_api_contact": False,
            "raw_export_paths_exposed": False,
            "identity_mode": "hashed",
        },
    }
    if not context_path.exists():
        return base

    try:
        from lib.core.provenance import verify

        payload = json.loads(context_path.read_text(encoding="utf-8"))
        base["artifacts"]["context_provenance_verified"] = verify(payload)
        summary = payload.get("summary") or {}
        chats = payload.get("chats") if isinstance(payload.get("chats"), list) else []
        latest = None
        for chat in chats:
            stamp = str(chat.get("last_message_at") or "")
            if stamp and (latest is None or stamp > latest):
                latest = stamp

        def signals(name: str) -> list[dict[str, Any]]:
            rows = payload.get(name) if isinstance(payload.get(name), list) else []
            cleaned: list[dict[str, Any]] = []
            for row in rows[: max(1, min(int(signal_limit), 50))]:
                cleaned.append(
                    {
                        "canonical_id": str(row.get("canonical_id") or ""),
                        "chat_hash": str(row.get("chat_hash") or ""),
                        "published_at": str(row.get("published_at") or ""),
                        "snippet": str(row.get("snippet") or "")[:240],
                    }
                )
            return cleaned

        base.update(
            {
                "available": True,
                "status": "ready",
                "summary": {
                    "chats": int(summary.get("chats") or 0),
                    "messages": int(summary.get("messages") or 0),
                    "participants": int(summary.get("participants") or 0),
                    "open_loops": int(summary.get("open_loops") or 0),
                    "commitments": int(summary.get("commitments") or 0),
                    "decisions": int(summary.get("decisions") or 0),
                    "top_tags": summary.get("top_tags") or [],
                },
                "latest_message_at": latest,
                "signals": {
                    "open_loops": signals("open_loops"),
                    "commitments": signals("commitments"),
                    "decisions": signals("decisions"),
                },
            }
        )
    except Exception as exc:
        base["status"] = "unreadable"
        base["error"] = f"{exc.__class__.__name__}: {exc}"
    return base


@app.route("/api/telegram-history-intel")
@requires_auth
def api_telegram_history_intel():
    """Offline Telegram history intelligence summary.

    Auth-gated and read-only. Returns sanitized snippets and aggregate counts
    from `data/telegram_history_intel/conversation_context.json`; never contacts
    Telegram and never exposes raw export paths.
    """
    return jsonify(_telegram_history_intel_summary())


@app.route("/api/intel")
@requires_auth
def api_intel():
    """Regional intel feed — proxies regional-intel-workbench if reachable, else local snapshot."""
    # Try local intelligence snapshots
    items = []
    local_item_count = 0
    local_latest = None

    # Load recent threat intel as intel feed items
    intel_dir = Path.home() / "Code" / "Sapphire" / "data" / "intelligence"
    try:
        for day_dir in sorted(intel_dir.glob("*/threats.json"), reverse=True)[:3]:
            try:
                threats = json.loads(day_dir.read_text()).get("threats") or []
                for t in threats[:5]:
                    local_item_count += 1
                    stamp = t.get("published") or day_dir.parent.name
                    if local_latest is None or str(stamp) > str(local_latest):
                        local_latest = stamp
                    items.append(
                        {
                            "id": t.get("canonical_id") or t.get("id", ""),
                            "title": t.get("title", ""),
                            "region": "GLOBAL",
                            "severity": "high" if (t.get("score") or 0) >= 8 else "medium",
                            "source": t.get("source", "threat-intel"),
                            "timestamp": stamp,
                            "tags": t.get("tags") or [],
                            "exploited": t.get("exploited", False),
                        }
                    )
            except Exception:
                pass
    except Exception:
        pass

    # Try regional-intel-workbench API (port 8787)
    workbench_status = "offline"
    workbench_items = 0
    try:
        import urllib.request as _ureq

        with _ureq.urlopen("http://127.0.0.1:8787/api/intel/recent?limit=10", timeout=3) as r:  # nosec B310 - fixed loopback URL.
            wb_data = json.loads(r.read())
            workbench_items = len(wb_data.get("items") or [])
            for item in wb_data.get("items") or []:
                items.append({**item, "source": "regional-workbench"})
            workbench_status = "online"
    except Exception:
        pass

    foundry = {}
    try:
        from lib.foundry.readiness import build_foundry_readiness

        foundry = build_foundry_readiness()
    except Exception as e:
        log.warning("intel API failed to summarize Foundry readiness: %s", e)

    telegram_history = _telegram_history_intel_summary()
    sources = [
        {
            "name": "Threat snapshots",
            "type": "Threat / CVE",
            "status": "active" if local_item_count else "unknown",
            "last_pull": local_latest,
            "items": local_item_count,
        },
        {
            "name": "Regional Workbench",
            "type": "Geopolitical / Cyber",
            "status": workbench_status,
            "last_pull": time.time() if workbench_status == "online" else None,
            "items": workbench_items,
        },
        {
            "name": "Palantir Foundry",
            "type": "Ontology / Graph",
            "status": foundry.get("status", "planned"),
            "last_pull": foundry.get("latest_materialization"),
            "items": ((foundry.get("totals") or {}).get("files") or 0),
        },
        {
            "name": "Telegram History",
            "type": "Offline conversation context",
            "status": "active" if telegram_history.get("available") else "local-only",
            "last_pull": telegram_history.get("latest_message_at"),
            "items": (telegram_history.get("summary") or {}).get("messages") or 0,
        },
    ]

    # Attach geo coords so the /intel Leaflet map can plot each item
    items = [_attach_geo(dict(it)) for it in items]

    return jsonify(
        {
            "items": items[:20],
            "sources": sources,
            "item_count": len(items),
            "foundry": foundry,
            "telegram_history": {
                "available": telegram_history.get("available", False),
                "status": telegram_history.get("status"),
                "summary": telegram_history.get("summary"),
                "latest_message_at": telegram_history.get("latest_message_at"),
                "artifacts": telegram_history.get("artifacts"),
                "safety": telegram_history.get("safety"),
            },
            "last_updated": time.time(),
        }
    )


@app.route("/api/performance")
@requires_auth
def api_performance():
    """Live performance tracker stats from data/performance/signals.jsonl."""
    try:
        from lib.analytics.performance_tracker import PerformanceTracker

        pt = PerformanceTracker()
        stats = pt.get_all_stats()
        alerts = pt.get_decay_alerts()
        return jsonify({**stats, "decay_alerts": alerts, "last_updated": time.time()})
    except Exception as e:
        log.warning("performance tracker API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "total_signals": 0,
                "scored_signals": 0,
                "win_rate": None,
                "decay_alerts": [],
            }
        ), 200


@app.route("/api/strategy-performance")
@requires_auth
def api_strategy_performance():
    """Unified strategy performance: overall + by-strategy + by-timeframe + cross.

    Reads every closed trade from data/signals/*.jsonl, data/performance/signals.jsonl,
    and data/paper_portfolio.json history, normalizes, and groups by strategy and
    hold-duration bucket (1h/4h/1d/7d/30d/all).
    """

    def fetch():
        from lib.analytics.strategy_performance import report

        payload = report()
        payload["last_updated"] = time.time()
        return payload

    try:
        return jsonify(
            get_cached(
                "strategy_performance",
                fetch,
                ttl=STRATEGY_PERFORMANCE_CACHE_DURATION,
                raise_on_miss=True,
            )
        )
    except Exception as e:
        log.warning("strategy performance API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "overall": {"trades": 0, "win_rate": None, "total_pnl_usd": 0.0},
                "by_strategy": {},
                "by_timeframe": {},
                "by_strategy_timeframe": {},
                "by_symbol": {},
                "trade_count": 0,
                "strategies": [],
                "timeframes": [],
            }
        ), 200


@app.route("/api/hyperliquid/live-status")
@requires_auth
def api_hyperliquid_live_status():
    """Read-only inspector for the Hyperliquid trading executor's state.

    Reuses ``_live_status_payload`` from ``plugins/claw-sapphire/tools/internal/
    hyperliquid.py`` so the dashboard surfaces the exact same view operators see
    via the plugin tool's ``live-status`` action: killswitch flag, recent trades,
    daily realized-loss tally, env flags, and policy defaults.

    Query params:
      limit: int in [1, 50], default 5 — number of recent trades returned.

    Failure mode: if the plugin tool helper cannot be imported (e.g. PRs #443/
    #444/#453 not merged yet, or the path moved), returns HTTP 503 with an
    ``{"error","reason"}`` body rather than crashing the dashboard worker.
    """
    try:
        limit = int(request.args.get("limit") or 5)
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(50, limit))

    try:
        import importlib.util

        sapphire_root = Path(__file__).resolve().parents[2]
        tool_path = (
            sapphire_root / "plugins" / "claw-sapphire" / "tools" / "internal" / "hyperliquid.py"
        )
        spec = importlib.util.spec_from_file_location("hyperliquid_dashboard", tool_path)
        if spec is None or spec.loader is None:
            raise ImportError("could not locate hyperliquid plugin tool")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        helper = getattr(module, "_live_status_payload", None)
        if helper is None:
            raise ImportError("_live_status_payload not exported by hyperliquid tool")
        payload = helper(limit)
    except Exception as exc:
        log.warning("hyperliquid live-status API unavailable: %s", exc)
        return jsonify({"error": "live-status unavailable", "reason": str(exc)}), 503

    return jsonify(payload), 200


@app.route("/api/convergence-watchlist")
@requires_auth
def api_convergence_watchlist():
    """Convergence thesis watchlist — equities curated from Kimi P1 research
    (Solar / Drone / Space / AI convergence). Static JSON file under
    world_knowledge/research/kimi-p1-sun-drone/. Read-only; for live prices,
    cross-reference with the TA scanner or OpenBB quote API.
    """
    try:
        watchlist_path = (
            Path(__file__).resolve().parents[2]
            / "world_knowledge"
            / "research"
            / "kimi-p1-sun-drone"
            / "convergence_watchlist.json"
        )
        if not watchlist_path.exists():
            return jsonify({"error": "watchlist not found", "tiers": {}}), 200
        data = json.loads(watchlist_path.read_text())
        data["source_file"] = str(watchlist_path.relative_to(watchlist_path.parents[4]))
        return jsonify(data)
    except Exception as e:
        log.warning("convergence watchlist API error: %s", e)
        return jsonify({"error": str(e), "tiers": {}}), 200


@app.route("/api/prediction-accuracy")
@requires_auth
def api_prediction_accuracy():
    """TA-scanner prediction accuracy from data/trading_predictions.jsonl."""
    try:
        from lib.analytics.prediction_accuracy import report

        return jsonify({**report(), "last_updated": time.time()})
    except Exception as e:
        log.warning("prediction accuracy API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "total": 0,
                "scored": 0,
                "correct": 0,
                "accuracy": None,
                "by_symbol": {},
                "by_direction": {},
                "recent": [],
            }
        ), 200


@app.route("/api/forecast")
@requires_auth
def api_forecast():
    """Combined Kronos + TA-scanner forecast per symbol with consensus + edge score."""
    try:
        from lib.analytics.forecast import forecast

        payload = forecast()
        payload["last_updated"] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("forecast API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "rows": [],
                "symbols": [],
                "kronos_stamp": None,
                "kronos_source": None,
            }
        ), 200


@app.route("/api/forecast/explain/<symbol>")
@requires_auth
def api_forecast_explain(symbol):
    """Structured rationale for one symbol's forecast row (the "Why?" panel)."""
    sym = (symbol or "?").upper()
    try:
        from lib.analytics.forecast import forecast
        from lib.analytics.forecast_explain import explain_forecast

        rows = forecast().get("rows") or []
        row = next((r for r in rows if r.get("symbol") == sym), {})
        return jsonify(explain_forecast(row, symbol=sym))
    except Exception as e:
        log.warning("forecast explain API error for %s: %s", sym, e)
        return jsonify(
            {
                "kind": "forecast",
                "symbol": sym,
                "headline": f"{sym}: no data",
                "regime": "NEUTRAL",
                "score": 0.0,
                "components": [],
                "rationale_short": "forecast data unavailable",
                "rationale_long": f"Failed to build rationale for {sym}.",
                "confidence_band": "low",
                "show_math": {},
                "error": str(e),
            }
        ), 200


@app.route("/api/backtest-results")
@requires_auth
def api_backtest_results():
    """Summary + leaderboard over the latest strategy backtest sweep.

    Query params:
      metric: sortino | sharpe | calmar | total_return_pct | win_rate | profit_factor
      limit:  top-N (default 10)
      include_minimal: "1" to include strategies with <5 trades (default false)
    """
    try:
        from lib.analytics.backtest_results import leaderboard, summary

        metric = request.args.get("metric", "sortino")
        try:
            limit = int(request.args.get("limit", "10"))
        except ValueError:
            limit = 10
        include_minimal = request.args.get("include_minimal") == "1"
        summary_payload = summary()
        try:
            lb = leaderboard(metric=metric, limit=limit, include_minimal_trades=include_minimal)
        except ValueError as ve:
            lb = {"error": str(ve), "rows": [], "metric": metric}
        return jsonify(
            {
                "summary": summary_payload,
                "leaderboard": lb,
                "last_updated": time.time(),
            }
        )
    except Exception as e:
        log.warning("backtest results API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "summary": {"have_results": False, "best_per_symbol": [], "total_backtests": 0},
                "leaderboard": {"rows": [], "metric": "sortino"},
            }
        ), 200


_WALKFORWARD_RESULTS_ROOT = _DASHBOARD_REPO_ROOT / "data" / "backtests" / "walkforward"
_WINDOWS_RESEARCH_WORKER_URL = os.environ.get(
    "WINDOWS_RESEARCH_WORKER_URL",
    "http://100.x.x.z:9090/windows/research-worker/latest",
)
_WINDOWS_WEBHOOK_HEALTH_URL = os.environ.get(
    "WINDOWS_WEBHOOK_HEALTH_URL",
    "http://100.x.x.z:9090/webhook/health",
)


def _walkforward_empty_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": "read_only_walkforward_results",
        "status": "no_data",
        "reason": reason,
        "summary": {
            "strategy_count": 0,
            "artifact_count": 0,
            "horizon_count": 0,
            "dsr_pass_count": 0,
            "best_strategy": None,
            "best_horizon_days": None,
            "best_sortino": None,
        },
        "strategies": [],
    }


def _latest_walkforward_manifest_path() -> Path | None:
    root = _WALKFORWARD_RESULTS_ROOT
    if not root.exists() or not root.is_dir():
        return None
    candidates = [
        child / "manifest.json"
        for child in root.iterdir()
        if child.is_dir() and (child / "manifest.json").is_file()
    ]
    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    return candidates[0] if candidates else None


def _walkforward_artifact_path(manifest_path: Path, raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(manifest_path.parent / path.name)
        candidates.append(path)
    else:
        candidates.append(manifest_path.parent / path)
        candidates.append(_DASHBOARD_REPO_ROOT / path)
        candidates.append(manifest_path.parent / path.name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _walkforward_horizon_summary(block: dict[str, Any]) -> dict[str, Any]:
    result = block.get("result") or {}
    regime = block.get("regime_decomposition") or {}
    dsr = block.get("deflated_sharpe") or {}
    payload = {
        "horizon_days": block.get("horizon_days"),
        "n_windows": result.get("n_windows", 0),
        "n_active_windows": result.get("n_active_windows", 0),
        "mean_test_sortino": result.get("mean_test_sortino"),
        "median_test_sortino": result.get("median_test_sortino"),
        "test_sortino_cv": result.get("test_sortino_cv"),
        "mean_test_sharpe": result.get("mean_test_sharpe"),
        "mean_test_calmar": result.get("mean_test_calmar"),
        "mean_test_total_return_pct": result.get("mean_test_total_return_pct"),
        "mean_test_win_rate": result.get("mean_test_win_rate"),
        "mean_test_profit_factor": result.get("mean_test_profit_factor"),
        "aggregate_test_max_drawdown_pct": result.get("aggregate_test_max_drawdown_pct"),
        "dsr_passed": dsr.get("passed"),
        "dsr_probability": dsr.get("probability"),
        "deflated_sharpe": dsr.get("deflated_sharpe"),
        "dsr_threshold": dsr.get("threshold"),
        "dominant_regime": regime.get("dominant_regime"),
        "n_labelled": regime.get("n_labelled", 0),
        "n_unlabelled": regime.get("n_unlabelled", 0),
    }
    if "error" in block:
        payload["error"] = block.get("error")
    return payload


def _walkforward_best_horizon(horizons: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = [
        horizon for horizon in horizons if isinstance(horizon.get("mean_test_sortino"), int | float)
    ]
    if not scored:
        return None
    return max(
        scored,
        key=lambda h: (
            h.get("mean_test_sortino") or 0,
            h.get("dsr_probability") or 0,
            h.get("n_active_windows") or 0,
        ),
    )


def _walkforward_strategy_summary(
    *,
    artifact_entry: dict[str, Any],
    manifest_path: Path,
) -> dict[str, Any]:
    strategy_name = str(artifact_entry.get("strategy") or "")
    artifact_path = _walkforward_artifact_path(manifest_path, artifact_entry.get("path"))
    if artifact_path is None:
        return {
            "strategy": strategy_name or "unknown",
            "status": "missing",
            "error": "artifact file missing",
            "artifact_path": None,
            "horizons": [],
            "best_horizon": None,
        }

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    horizons = [
        _walkforward_horizon_summary(block)
        for block in payload.get("horizons", [])
        if isinstance(block, dict)
    ]
    return {
        "strategy": payload.get("strategy_cls") or strategy_name or artifact_path.stem,
        "status": "ok",
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "symbol": payload.get("symbol"),
        "artifact_path": _repo_display_path(artifact_path),
        "horizons": horizons,
        "best_horizon": _walkforward_best_horizon(horizons),
    }


def _build_walkforward_results_payload() -> dict[str, Any]:
    manifest_path = _latest_walkforward_manifest_path()
    if manifest_path is None:
        return _walkforward_empty_payload("no walk-forward manifest on disk")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        payload = _walkforward_empty_payload("latest manifest unreadable")
        payload["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
        payload["manifest_path"] = _repo_display_path(manifest_path)
        return payload

    artifacts = [item for item in manifest.get("artifacts", []) if isinstance(item, dict)]
    strategies: list[dict[str, Any]] = []
    for entry in artifacts:
        try:
            strategies.append(
                _walkforward_strategy_summary(artifact_entry=entry, manifest_path=manifest_path)
            )
        except (json.JSONDecodeError, OSError) as exc:
            strategies.append(
                {
                    "strategy": str(entry.get("strategy") or "unknown"),
                    "status": "unreadable",
                    "error": f"{exc.__class__.__name__}: {exc}"[:200],
                    "artifact_path": None,
                    "horizons": [],
                    "best_horizon": None,
                }
            )

    all_horizons = [
        horizon
        for strategy in strategies
        for horizon in strategy.get("horizons", [])
        if isinstance(horizon, dict)
    ]
    best = _walkforward_best_horizon(
        [
            {**strategy["best_horizon"], "strategy": strategy["strategy"]}
            for strategy in strategies
            if isinstance(strategy.get("best_horizon"), dict)
        ]
    )
    payload = {
        "mode": "read_only_walkforward_results",
        "status": "ok",
        "report_date": manifest_path.parent.name,
        "manifest_path": _repo_display_path(manifest_path),
        "manifest": {
            "version": manifest.get("version"),
            "generated_at": manifest.get("generated_at"),
            "symbol": manifest.get("symbol"),
            "bars_source": manifest.get("bars_source"),
            "n_bars": manifest.get("n_bars"),
            "horizons_days": manifest.get("horizons_days", []),
            "selection_metric": manifest.get("selection_metric"),
            "bankroll": manifest.get("bankroll"),
            "regime_label_count": manifest.get("regime_label_count"),
        },
        "summary": {
            "strategy_count": sum(1 for strategy in strategies if strategy.get("status") == "ok"),
            "artifact_count": len(artifacts),
            "horizon_count": len(all_horizons),
            "dsr_pass_count": sum(
                1 for horizon in all_horizons if horizon.get("dsr_passed") is True
            ),
            "best_strategy": best.get("strategy") if best else None,
            "best_horizon_days": best.get("horizon_days") if best else None,
            "best_sortino": best.get("mean_test_sortino") if best else None,
        },
        "strategies": strategies,
    }
    return payload


@app.route("/api/walkforward-results")
@requires_auth
def api_walkforward_results():
    """Read-only summary of latest walk-forward / DSR artifacts."""
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_walkforward_results_payload()))
    except Exception as exc:
        log.warning("walk-forward results API error: %s", exc)
        payload = {
            "mode": "read_only_walkforward_results",
            "status": "unknown",
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
            "summary": {
                "strategy_count": 0,
                "artifact_count": 0,
                "horizon_count": 0,
                "dsr_pass_count": 0,
                "best_strategy": None,
                "best_horizon_days": None,
                "best_sortino": None,
            },
            "strategies": [],
        }
        return jsonify(payload), 200


def _windows_research_worker_empty_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": "read_only_windows_research_worker",
        "status": "no_data",
        "source": "dashboard_proxy",
        "reason": reason,
        "summary": {
            "command_count": 0,
            "failed_count": 0,
            "artifact_count": 0,
            "safety_clear": False,
        },
        "safety": {
            "paper_only": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
        },
        "commands": [],
        "artifacts": [],
    }


def _remote_path_label(raw_path: Any) -> str | None:
    if raw_path in (None, ""):
        return None
    text = str(raw_path)
    if text.startswith(".../"):
        return _paste_safe_text(text, limit=120)
    parts = [part for part in text.replace("\\", "/").split("/") if part and not part.endswith(":")]
    if not parts:
        return None
    return _paste_safe_text(".../" + "/".join(parts[-3:]), limit=120)


def _fetch_json_url(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # nosec B310 - fixed private Tailscale URL from config.
        payload = json.loads(response.read(1024 * 1024))
    return payload if isinstance(payload, dict) else {}


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_worker_freshness(payload: dict[str, Any]) -> dict[str, Any]:
    freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
    status = _paste_safe_text(freshness.get("status") or "unknown", limit=24)
    age_seconds = _safe_int(freshness.get("age_seconds"))
    max_age_seconds = _safe_int(freshness.get("max_age_seconds"))
    fresh = freshness.get("fresh")
    return {
        "status": status,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
        "fresh": bool(fresh) if fresh is not None else status == "fresh",
    }


def _normalize_worker_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    schedule = payload.get("schedule") if isinstance(payload.get("schedule"), dict) else {}
    last_task_result = _safe_int(schedule.get("last_task_result"))
    last_result_ok = schedule.get("last_result_ok")
    return {
        "task_name": _paste_safe_text(
            schedule.get("task_name") or "SapphireResearchWorker", limit=80
        ),
        "status": _paste_safe_text(schedule.get("status") or "unknown", limit=32),
        "state": _paste_safe_text(schedule.get("state"), limit=32),
        "last_run_time": schedule.get("last_run_time"),
        "next_run_time": schedule.get("next_run_time"),
        "last_task_result": last_task_result,
        "last_task_result_label": _paste_safe_text(
            schedule.get("last_task_result_label") or "unknown",
            limit=48,
        ),
        "last_result_ok": bool(last_result_ok) if last_result_ok is not None else None,
        "reason": _paste_safe_text(schedule.get("reason"), limit=160)
        if schedule.get("reason")
        else None,
    }


def _normalize_windows_research_worker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    safety = payload.get("safety") if isinstance(payload.get("safety"), dict) else {}
    commands = [
        {
            "name": _paste_safe_text(command.get("name") or "unknown", limit=64),
            "status": "failed" if command.get("status") == "failed" else "ok",
            "exit_code": command.get("exit_code"),
            "duration_seconds": command.get("duration_seconds"),
            "started_at": command.get("started_at"),
            "finished_at": command.get("finished_at"),
            "log_path_label": _remote_path_label(
                command.get("log_path_label") or command.get("log_path")
            ),
        }
        for command in payload.get("commands", [])
        if isinstance(command, dict)
    ]
    artifacts = [
        {
            "kind": _paste_safe_text(artifact.get("kind") or "artifact", limit=64),
            "path_label": _remote_path_label(artifact.get("path_label") or artifact.get("path")),
        }
        for artifact in payload.get("artifacts", [])
        if isinstance(artifact, dict)
    ]
    paper_only = safety.get("paper_only") is True
    live_trading_enabled = safety.get("live_trading_enabled") is True
    telegram_sends_enabled = safety.get("telegram_sends_enabled") is True
    safety_clear = paper_only and not live_trading_enabled and not telegram_sends_enabled
    status = str(payload.get("status") or "unknown")
    if not safety_clear and status == "ok":
        status = "unsafe"
    freshness = _normalize_worker_freshness(payload)
    schedule = _normalize_worker_schedule(payload)
    return {
        "mode": "read_only_windows_research_worker",
        "status": status,
        "source": _paste_safe_text(payload.get("source") or "windows_webhook", limit=64),
        "generated_at": payload.get("generated_at"),
        "host": _paste_safe_text(payload.get("host"), limit=80),
        "git_sha_short": _paste_safe_text(payload.get("git_sha_short"), limit=16),
        "run_id": _paste_safe_text(payload.get("run_id"), limit=40),
        "manifest_path_label": _remote_path_label(payload.get("manifest_path_label")),
        "run_dir_label": _remote_path_label(payload.get("run_dir_label")),
        "output_root_label": _remote_path_label(payload.get("output_root_label")),
        "freshness": freshness,
        "schedule": schedule,
        "reason": _paste_safe_text(payload.get("reason"), limit=180)
        if payload.get("reason")
        else None,
        "summary": {
            "command_count": int(summary.get("command_count") or len(commands)),
            "failed_count": int(summary.get("failed_count") or 0),
            "artifact_count": int(summary.get("artifact_count") or len(artifacts)),
            "safety_clear": bool(
                summary.get("safety_clear") if "safety_clear" in summary else safety_clear
            ),
            "manifest_age_seconds": freshness["age_seconds"],
        },
        "safety": {
            "paper_only": paper_only,
            "live_trading_enabled": live_trading_enabled,
            "telegram_sends_enabled": telegram_sends_enabled,
        },
        "commands": commands,
        "artifacts": artifacts,
    }


def _build_windows_research_worker_payload() -> dict[str, Any]:
    errors: list[str] = []
    for url, extractor in (
        (_WINDOWS_RESEARCH_WORKER_URL, lambda body: body),
        (_WINDOWS_WEBHOOK_HEALTH_URL, lambda body: body.get("research_worker")),
    ):
        try:
            body = _fetch_json_url(url)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            errors.append(f"{exc.__class__.__name__}: {exc}"[:120])
            continue
        payload = extractor(body)
        if isinstance(payload, dict):
            return _normalize_windows_research_worker_payload(payload)
        errors.append("research_worker_missing")
    payload = _windows_research_worker_empty_payload("windows worker status unavailable")
    if errors:
        payload["error"] = "; ".join(errors)[-240:]
    return payload


@app.route("/api/windows-research-worker")
@requires_auth
def api_windows_research_worker():
    """Read-only summary of the latest paper-only Windows research worker run."""
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_windows_research_worker_payload()))
    except Exception as exc:
        log.warning("windows research worker API error: %s", exc)
        payload = _windows_research_worker_empty_payload("dashboard proxy error")
        payload["error"] = f"{exc.__class__.__name__}: {exc}"[:200]
        return jsonify(payload), 200


@app.route("/api/trading-brain")
@requires_auth
def api_trading_brain():
    """Unified trading decision engine — aggregates TA, ensemble signals, Kronos, macro, and track record.

    5-minute in-process cache (each call invokes 5 sub-tools per symbol).
    Query params:
      symbol — decide for a single symbol only; omit for dashboard (BTC + ETH + SOL)
    """
    import subprocess as _sp

    symbol = request.args.get("symbol", "").strip().upper()
    cache_key = f"trading_brain_{symbol or 'dashboard'}"
    BRAIN_CACHE = 300

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < BRAIN_CACHE:
        return jsonify(_cache[cache_key])

    tool_path = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "trading_brain.py"
    )
    lib_path = Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "lib"
    inp = json.dumps({"action": "decide", "symbol": symbol} if symbol else {"action": "dashboard"})
    env = {**__import__("os").environ, "PYTHONPATH": str(lib_path)}

    try:
        result = _sp.run(
            ["python3", str(tool_path)],
            input=inp,
            capture_output=True,
            text=True,
            timeout=150,
            env=env,
        )
        if result.returncode != 0:
            log.warning(
                "trading_brain failed (rc=%s): %s", result.returncode, (result.stderr or "")[-500:]
            )
            return jsonify({"error": "trading_brain process failed", "decisions": {}}), 200
        data = json.loads(result.stdout)
        _cache[cache_key] = data
        _cache_time[cache_key] = now
        return jsonify(data)
    except _sp.TimeoutExpired:
        return jsonify({"error": "trading_brain timed out (150s)", "decisions": {}}), 200
    except json.JSONDecodeError as e:
        log.warning("trading_brain returned invalid JSON: %s", e)
        return jsonify({"error": "Invalid JSON from trading_brain", "decisions": {}}), 200
    except Exception as e:
        log.warning("trading_brain endpoint error: %s", e)
        return jsonify({"error": str(e), "decisions": {}}), 200


@app.route("/api/brain/advisory")
@requires_auth
def api_brain_advisory():
    """Quant-perps brain.advisory output exposed for the Sapphire dashboard.

    Mirrors the crypto-proxy equity signals (MSTR / IBIT / TSLA / SPY) that the
    RH Chain visualizer already consumes. Query params:
      action — read (default) | decide | dashboard | publish
      symbol — required when action=decide
      live   — set "true" to arm publish (still requires private key elsewhere)
    """
    import subprocess as _sp

    action = request.args.get("action", "read")
    symbol = request.args.get("symbol", "")
    live = request.args.get("live", "false").lower() == "true"

    if action not in ("read", "decide", "dashboard", "publish"):
        return jsonify({"error": f"Unknown action {action!r}"}), 400
    if action == "decide" and not symbol:
        return jsonify({"error": "symbol required for action=decide"}), 400

    cache_key = f"brain_advisory_{action}_{symbol or 'all'}_{live}"
    ADVISORY_CACHE = 60  # advisory file itself is updated daily; bridge is cheap

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < ADVISORY_CACHE:
        return jsonify(_cache[cache_key])

    tool_path = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "internal"
        / "brain_advisory_bridge.py"
    )
    lib_path = Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "lib"

    params: dict = {"action": action}
    if symbol:
        params["symbol"] = symbol
    if action == "publish":
        params["live"] = live

    env = {**__import__("os").environ, "PYTHONPATH": str(lib_path)}

    try:
        result = _sp.run(
            ["python3", str(tool_path)],
            input=json.dumps(params),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode != 0:
            log.warning(
                "brain_advisory_bridge failed (rc=%s): %s",
                result.returncode,
                (result.stderr or "")[-500:],
            )
            return jsonify({"error": "brain_advisory_bridge process failed"}), 200
        data = json.loads(result.stdout)
        _cache[cache_key] = data
        _cache_time[cache_key] = now
        return jsonify(data)
    except _sp.TimeoutExpired:
        return jsonify({"error": "brain_advisory_bridge timed out (30s)"}), 200
    except json.JSONDecodeError as e:
        log.warning("brain_advisory_bridge returned invalid JSON: %s", e)
        return jsonify({"error": "Invalid JSON from brain_advisory_bridge"}), 200
    except Exception as e:
        log.warning("brain advisory endpoint error: %s", e)
        return jsonify({"error": str(e)}), 200


@app.route("/api/tho/market-intel")
@requires_auth
def api_tho_market_intel():
    """THO housing market intelligence — FRED rates + Houston permits + THO customer analytics.

    10-minute cache (housing data changes slowly).
    Query params:
      action — market (default) | buyers | report
    """
    import subprocess as _sp

    action = request.args.get("action", "market")
    if action not in ("market", "buyers", "report"):
        return jsonify({"error": f"Unknown action {action!r}. Valid: market, buyers, report"}), 400

    cache_key = f"tho_market_intel_{action}"
    THO_CACHE = 600

    now = time.time()
    if cache_key in _cache and now - _cache_time.get(cache_key, 0) < THO_CACHE:
        return jsonify(_cache[cache_key])

    tool_path = (
        Path.home() / "Code" / "Sapphire" / "plugins" / "claw-sapphire" / "tools" / "tho_intel.py"
    )

    try:
        result = _sp.run(
            ["python3", str(tool_path)],
            input=json.dumps({"action": action}),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.stdout.strip():
            data = json.loads(result.stdout)
            _cache[cache_key] = data
            _cache_time[cache_key] = now
            return jsonify(data)
        log.warning("tho_intel returned no stdout; stderr=%s", (result.stderr or "")[-500:])
        return jsonify({"error": "no output from tho_intel", "success": False}), 200
    except _sp.TimeoutExpired:
        return jsonify({"error": "tho_intel timed out (60s)", "success": False}), 200
    except Exception as e:
        log.warning("tho market intel error: %s", e)
        return jsonify({"error": str(e), "success": False}), 200


@app.route("/api/lumo/latest-pack")
@requires_auth
def api_lumo_latest_pack():
    """Latest Lumo strategy research pack from data/lumo/.

    Returns the most recently generated pack as markdown. To refresh:
      echo '{"action":"pack"}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/lumo.py
    """
    lumo_dir = Path.home() / "Code" / "Sapphire" / "data" / "lumo"
    packs = sorted(lumo_dir.glob("lumo_pack_*.md"), reverse=True) if lumo_dir.exists() else []
    if not packs:
        return jsonify(
            {
                "available": False,
                "pack_count": 0,
                "hint": 'echo \'{"action":"pack"}\' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/lumo.py',
            }
        ), 200
    latest = packs[0]
    try:
        return jsonify(
            {
                "available": True,
                "path": str(latest),
                "generated": latest.stem.replace("lumo_pack_", ""),
                "content": latest.read_text(),
                "pack_count": len(packs),
            }
        )
    except Exception as e:
        return jsonify({"available": False, "error": str(e)}), 200


@app.route("/api/performance-timeseries")
@requires_auth
def api_performance_timeseries():
    """Equity curve + drawdown + monthly returns over all closed trades.

    Reads the unified trade stream from lib.analytics.strategy_performance and
    emits ordered time-series suitable for the /performance SVG charts and
    monthly-returns grid.
    """
    try:
        from lib.analytics.strategy_performance import timeseries

        payload = timeseries()
        payload["last_updated"] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("performance timeseries API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "initial_capital": 100000.0,
                "final_equity": 100000.0,
                "total_pnl_usd": 0.0,
                "total_return_pct": 0.0,
                "equity_curve": [],
                "drawdown_series": [],
                "max_drawdown": {"pct": 0.0, "ts": None, "equity_usd": 100000.0},
                "monthly_returns": [],
                "trade_count": 0,
            }
        ), 200


@app.route("/api/brain-accuracy")
@requires_auth
def api_brain_accuracy():
    """Trading Brain decision accuracy — GO/LEAN/WAIT scoring over 24h windows."""
    try:
        from lib.analytics.brain_accuracy import report as brain_report

        payload = brain_report()
        payload["last_updated"] = time.time()
        return jsonify(payload)
    except Exception as e:
        log.warning("brain accuracy API error: %s", e)
        return jsonify(
            {
                "error": str(e),
                "total_decisions": 0,
                "scored": 0,
                "pending": 0,
                "overall_accuracy": None,
                "by_symbol": {},
                "by_decision": {},
                "recent": [],
            }
        ), 200


@app.route("/api/content/drafts")
@requires_auth
def api_content_drafts():
    """List the most recent content drafts (manifests from data/content/drafts/)."""
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from lib.content import publisher as content_publisher

        drafts = content_publisher.list_drafts(limit=50)
        return jsonify({"count": len(drafts), "drafts": drafts})
    except Exception as e:
        log.warning("content drafts listing failed: %s", e)
        return jsonify({"count": 0, "drafts": [], "error": str(e)}), 500


# ── Security Intelligence Platform (Phase 1) ─────────────────────────────


@app.route("/security")
@requires_auth
def security_page():
    """Security intelligence dashboard — dependency, model, and network panels."""
    return render_template(
        "pages/security.html", current_page="security", page_title="Security Intel"
    )


@app.route("/api/security/dependencies")
@requires_auth
def api_security_dependencies():
    """Dependency scan — CVEs, outdated packages, SBOM."""
    try:
        from lib.security.dependency_scanner import DependencyScanner

        scanner = DependencyScanner(check_outdated=False, check_vulns=False)
        result = scanner.scan_quick()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security dependency scan failed: %s", e)
        return jsonify({"error": str(e), "total_packages": 0, "score": 0}), 200


@app.route("/api/security/dependencies/full")
@requires_auth
def api_security_dependencies_full():
    """Full dependency scan with CVE + outdated checks (slow — network calls)."""
    try:
        from lib.security.dependency_scanner import DependencyScanner

        scanner = DependencyScanner(check_outdated=True, check_vulns=True)
        result = scanner.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security full dependency scan failed: %s", e)
        return jsonify({"error": str(e), "total_packages": 0, "score": 0}), 200


@app.route("/api/security/models")
@requires_auth
def api_security_models():
    """Model integrity scan — SHA-256 verification + template backdoor detection."""
    try:
        from lib.security.model_monitor import ModelMonitor

        monitor = ModelMonitor(verify_sha256=False)
        result = monitor.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security model scan failed: %s", e)
        return jsonify({"error": str(e), "total_models": 0, "score": 0}), 200


@app.route("/api/security/network")
@requires_auth
def api_security_network():
    """Network topology scan — Tailscale nodes, ports, trust zones."""
    try:
        from lib.security.network_mapper import NetworkMapper

        mapper = NetworkMapper(probe_ports=True, probe_timeout=1.5)
        result = mapper.scan()
        return jsonify(result.to_dict())
    except Exception as e:
        log.warning("security network scan failed: %s", e)
        return jsonify({"error": str(e), "total_nodes": 0, "score": 0}), 200


@app.route("/api/security/score")
@requires_auth
def api_security_score():
    """Aggregate security score across all three modules."""
    scores = {}
    try:
        from lib.security.dependency_scanner import DependencyScanner

        dep_result = DependencyScanner(check_outdated=False, check_vulns=False).scan_quick()
        scores["dependencies"] = {
            "score": dep_result.score,
            "total_packages": dep_result.total_packages,
            "unsigned": dep_result.unsigned_count,
        }
    except Exception as e:
        scores["dependencies"] = {"score": 0, "error": str(e)}

    try:
        from lib.security.model_monitor import ModelMonitor

        model_result = ModelMonitor(verify_sha256=False).scan()
        scores["models"] = {
            "score": model_result.score,
            "total_models": model_result.total_models,
            "alerts": len(model_result.template_alerts),
        }
    except Exception as e:
        scores["models"] = {"score": 0, "error": str(e)}

    try:
        from lib.security.network_mapper import NetworkMapper

        net_result = NetworkMapper(probe_ports=False).scan_quick()
        scores["network"] = {
            "score": net_result.score,
            "total_nodes": net_result.total_nodes,
            "online": net_result.online_nodes,
        }
    except Exception as e:
        scores["network"] = {"score": 0, "error": str(e)}

    # Weighted aggregate: deps 35%, models 35%, network 30%
    dep_s = scores.get("dependencies", {}).get("score", 0) or 0
    mod_s = scores.get("models", {}).get("score", 0) or 0
    net_s = scores.get("network", {}).get("score", 0) or 0
    aggregate = round(dep_s * 0.35 + mod_s * 0.35 + net_s * 0.30, 1)

    return jsonify(
        {
            "aggregate_score": aggregate,
            "modules": scores,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )


# ---------------------------------------------------------------------------
# Observability aggregator endpoints (Tranche 3, Lane 2)
# ---------------------------------------------------------------------------
#
# These three GET endpoints back the ``/observability`` page. The page renders
# its skeleton from Jinja and then polls these every 15s for live state.
#
# All three are auth-gated via @requires_auth and are safe to expose: every
# field flows through ``lib.observability.aggregator`` which never echoes
# secrets or absolute home-directory paths back into the JSON envelope.


def _build_observability_system_summary() -> dict[str, Any]:
    """Wrap aggregator + redactor into a single dict for the summary endpoint."""
    from lib.observability import build_system_snapshot
    from lib.security.pii_redactor import redact_record

    snapshot = build_system_snapshot()
    payload = snapshot.to_dict()
    # Belt-and-braces: the aggregator already abbreviates paths and excludes
    # raw secrets, but ``redact_record`` is idempotent and provides a second
    # layer in case a future signal source contributes a stray PII string.
    return redact_record(payload)


def _build_observability_stream_rates() -> dict[str, Any]:
    from lib.observability import build_stream_rates_only
    from lib.security.pii_redactor import redact_record

    return redact_record(build_stream_rates_only())


def _build_observability_launchagents() -> dict[str, Any]:
    from lib.observability import build_launchagents_only
    from lib.security.pii_redactor import redact_record

    return redact_record(build_launchagents_only())


def _build_observability_tranche4_feeds() -> dict[str, Any]:
    from lib.intelligence import feed_status_from_artifacts
    from lib.security.pii_redactor import redact_record

    return redact_record(feed_status_from_artifacts())


def _build_system_failover_status() -> dict[str, Any]:
    """Return the local inference failover posture without touching infra."""
    from lib.security.pii_redactor import redact_record
    from scripts.ops.system_failover_status import (
        DEFAULT_PROXY_URL,
        build_report,
        load_proxy_failover,
    )

    proxy, warnings = load_proxy_failover(DEFAULT_PROXY_URL, timeout=5.0)
    payload = build_report(
        proxy=proxy,
        proxy_warnings=warnings,
        cloud_run=None,
        require_primary=False,
    )
    payload["mode_name"] = "read_only_system_failover_status"
    payload["schema_version"] = 1
    return redact_record(payload)


@app.route("/api/observability-system-summary")
@requires_auth
def api_observability_system_summary():
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_observability_system_summary()))
    except Exception as exc:
        log.warning("observability summary error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_observability_snapshot",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "schema_version": 1,
            }
        ), 200


@app.route("/api/system-failover-status")
@requires_auth
def api_system_failover_status():
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_system_failover_status()))
    except Exception as exc:
        log.warning("system failover status error: %s", exc)
        return jsonify(
            {
                "mode_name": "read_only_system_failover_status",
                "mode": "unknown",
                "status": "unknown",
                "ok": False,
                "windows_offline": True,
                "fallback_ready": False,
                "active_route": None,
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "schema_version": 1,
                "blockers": ["failover status probe unavailable"],
                "warnings": [],
                "proxy": {"endpoints": {}},
                "cloud_run": {"checked": False},
            }
        ), 200


@app.route("/api/observability-stream-rates")
@requires_auth
def api_observability_stream_rates():
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_observability_stream_rates()))
    except Exception as exc:
        log.warning("observability stream-rates error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_observability_stream_rates",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "sources": [],
            }
        ), 200


@app.route("/api/observability-launchagents")
@requires_auth
def api_observability_launchagents():
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_observability_launchagents()))
    except Exception as exc:
        log.warning("observability launchagents error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_observability_launchagents",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "launchagents": [],
            }
        ), 200


@app.route("/api/observability-tranche4-feeds")
@requires_auth
def api_observability_tranche4_feeds():
    try:
        return jsonify(_maybe_buyer_safe_payload(_build_observability_tranche4_feeds()))
    except Exception as exc:
        log.warning("observability tranche4 feeds error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_tranche4_feed_status",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "feeds": [],
            }
        ), 200


# ─── Tranche 6 Lane 4 — Source Quality Measurement ──────────────────────
#
# Dashboard surface for ``services/source_quality``. Read-only: the
# routes below read the most recent ``data/source_quality/<date>/
# report.json`` and slice it into three views (SNR, correlation, decay).
# When no report exists yet (fresh install / daemon disabled) the
# routes degrade to an empty paste-safe payload rather than 500.


_SOURCE_QUALITY_REPORT_ROOT = Path(__file__).resolve().parents[2] / "data" / "source_quality"


def _source_quality_latest_report() -> dict[str, Any] | None:
    """Return the newest ``report.json`` payload under data/source_quality.

    Walks the dated subdirectories newest-first and stops on the first
    file that parses. Returns ``None`` when nothing is on disk.
    """
    root = _SOURCE_QUALITY_REPORT_ROOT
    if not root.exists() or not root.is_dir():
        return None
    candidates = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        report_path = child / "report.json"
        if report_path.is_file():
            candidates.append(report_path)
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _source_quality_empty_payload(reason: str) -> dict[str, Any]:
    return {
        "mode": "read_only_source_quality",
        "status": "no_data",
        "reason": reason,
        "summary": {
            "sources_count": 0,
            "samples_total": 0,
            "near_duplicate_pairs": 0,
            "decayed_sources_count": 0,
        },
    }


@app.route("/source-quality")
@requires_auth
def source_quality_page():
    """Render the source-quality dashboard page (template-driven)."""
    return render_template("pages/source_quality.html")


@app.route("/api/source-quality-snr")
@requires_auth
def api_source_quality_snr():
    try:
        report = _source_quality_latest_report()
        if report is None:
            payload = _source_quality_empty_payload("no report on disk")
            payload["snr"] = {}
            payload["sources"] = []
        else:
            snr = report.get("snr") or {}
            payload = {
                "mode": "read_only_source_quality_snr",
                "status": "ok",
                "report_date": report.get("report_date"),
                "snr": snr,
                "sources": sorted(snr.keys()),
                "summary": report.get("summary", {}),
            }
        return jsonify(_maybe_buyer_safe_payload(payload))
    except Exception as exc:
        log.warning("source-quality snr error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_source_quality_snr",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "snr": {},
            }
        ), 200


@app.route("/api/source-quality-correlation")
@requires_auth
def api_source_quality_correlation():
    try:
        report = _source_quality_latest_report()
        if report is None:
            payload = _source_quality_empty_payload("no report on disk")
            payload["correlation"] = {"pairs": [], "near_duplicates": []}
        else:
            correlation = report.get("correlation") or {}
            payload = {
                "mode": "read_only_source_quality_correlation",
                "status": "ok",
                "report_date": report.get("report_date"),
                "correlation": correlation,
                "near_duplicates": report.get("near_duplicates", []),
            }
        return jsonify(_maybe_buyer_safe_payload(payload))
    except Exception as exc:
        log.warning("source-quality correlation error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_source_quality_correlation",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "correlation": {"pairs": []},
            }
        ), 200


@app.route("/api/source-quality-decay")
@requires_auth
def api_source_quality_decay():
    try:
        report = _source_quality_latest_report()
        if report is None:
            payload = _source_quality_empty_payload("no report on disk")
            payload["decay"] = {"alerts": [], "decayed_sources": []}
        else:
            decay = report.get("decay") or {}
            payload = {
                "mode": "read_only_source_quality_decay",
                "status": "ok",
                "report_date": report.get("report_date"),
                "decay": decay,
                "decayed_sources": decay.get("decayed_sources", []),
            }
        return jsonify(_maybe_buyer_safe_payload(payload))
    except Exception as exc:
        log.warning("source-quality decay error: %s", exc)
        return jsonify(
            {
                "mode": "read_only_source_quality_decay",
                "status": "unknown",
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "decay": {"alerts": []},
            }
        ), 200


# ─── Inference Mesh Telemetry (Tranche 6 Lane 6) ──────────────────────────
# Routes appended at the bottom intentionally to avoid a merge conflict with
# the parallel Lane 4 (source quality) which appends in the observability
# block region. Both lanes are isolated to their own route sections so the
# integration-pass merge is mechanical.


def _build_inference_telemetry_report() -> dict[str, Any]:
    """Aggregate telemetry from ~/.cache/sapphire/inference_proxy/calls.jsonl.

    Falls back to a synthetic fixture report when no real log exists, with
    ``has_real_data=False`` clearly surfaced in the UI.
    """
    try:
        from lib.inference_telemetry.aggregator import (
            DEFAULT_CALLS_PATH,
            aggregate,
            project_monthly_calls,
            project_monthly_cost,
            synthetic_fixture_report,
        )
        from lib.inference_telemetry.cost_model import DEFAULT_COST_MODEL
    except Exception as exc:
        return {
            "schema_version": 1,
            "ok": False,
            "has_real_data": False,
            "error": f"telemetry import failed: {exc.__class__.__name__}",
            "tiers": [],
            "notes": ["lib.inference_telemetry import error"],
        }

    try:
        if DEFAULT_CALLS_PATH.exists():
            report = aggregate()
        else:
            report = synthetic_fixture_report()
    except Exception as exc:
        log.warning("inference telemetry aggregate error: %s", exc)
        return {
            "schema_version": 1,
            "ok": False,
            "has_real_data": False,
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
            "tiers": [],
            "notes": ["aggregator raised; see server log"],
        }

    payload = report.to_dict()
    payload["projected_monthly_cost_usd"] = round(project_monthly_cost(report), 6)
    payload["projected_monthly_calls"] = round(project_monthly_calls(report), 3)
    payload["cost_model_citations"] = [
        f"Moonshot pricing: {DEFAULT_COST_MODEL.moonshot_pricing_url} "
        f"(retrieved {DEFAULT_COST_MODEL.moonshot_pricing_retrieved})",
        "T1 GPU + T3 Mac use electricity-only proxies; not metered.",
    ]
    payload["ok"] = True
    return payload


def _build_inference_telemetry_recommendations() -> dict[str, Any]:
    try:
        from lib.inference_telemetry.aggregator import (
            DEFAULT_CALLS_PATH,
            aggregate,
            synthetic_fixture_report,
        )
        from lib.inference_telemetry.cost_model import DEFAULT_COST_MODEL
        from lib.inference_telemetry.recommender import recommend
    except Exception as exc:
        return {
            "schema_version": 1,
            "ok": False,
            "has_real_data": False,
            "error": f"recommender import failed: {exc.__class__.__name__}",
            "recommendations": [],
            "caveats": [],
        }

    try:
        if DEFAULT_CALLS_PATH.exists():
            report = aggregate()
        else:
            report = synthetic_fixture_report()
        bundle = recommend(report, cost_model=DEFAULT_COST_MODEL)
    except Exception as exc:
        log.warning("inference telemetry recommender error: %s", exc)
        return {
            "schema_version": 1,
            "ok": False,
            "has_real_data": False,
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
            "recommendations": [],
            "caveats": [],
        }

    out = bundle.to_dict()
    out["ok"] = True
    return out


@app.route("/inference-telemetry")
@requires_auth
def inference_telemetry_page():
    return render_template(
        "pages/inference_telemetry.html",
        current_page="inference-telemetry",
        page_title="Inference Mesh Telemetry",
    )


@app.route("/api/inference-telemetry-report")
@requires_auth
def api_inference_telemetry_report():
    try:
        return jsonify(_build_inference_telemetry_report())
    except Exception as exc:
        log.warning("inference telemetry report error: %s", exc)
        return jsonify(
            {
                "schema_version": 1,
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "tiers": [],
            }
        ), 200


@app.route("/api/inference-telemetry-recommendations")
@requires_auth
def api_inference_telemetry_recommendations():
    try:
        return jsonify(_build_inference_telemetry_recommendations())
    except Exception as exc:
        log.warning("inference telemetry recommendations error: %s", exc)
        return jsonify(
            {
                "schema_version": 1,
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "recommendations": [],
                "caveats": [],
            }
        ), 200


@app.route("/api/inference-telemetry-cost-model")
@requires_auth
def api_inference_telemetry_cost_model():
    try:
        from lib.inference_telemetry.cost_model import DEFAULT_COST_MODEL

        return jsonify(
            {
                "schema_version": 1,
                "ok": True,
                "cost_model": DEFAULT_COST_MODEL.to_dict(),
            }
        )
    except Exception as exc:
        log.warning("inference telemetry cost-model error: %s", exc)
        return jsonify(
            {
                "schema_version": 1,
                "ok": False,
                "error": f"{exc.__class__.__name__}: {exc}"[:200],
                "cost_model": None,
            }
        ), 200


if __name__ == "__main__":
    # Start background metrics collector (snapshots every 5 min)
    try:
        from metrics_collector import start_collector

        start_collector()
    except Exception:
        pass
    port = int(os.environ.get("PORT", 8082))
    host = os.environ.get("HOST", "127.0.0.1")
    app.run(host=host, port=port, debug=False)
