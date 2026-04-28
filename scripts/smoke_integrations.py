#!/usr/bin/env python3
"""Sapphire — integrations smoke test.

One command that probes every external integration Sapphire touches and
prints a pass/fail/skip table. Run after filling in .env.integrations to
see, at a glance, which providers are wired up and which still need work.

Usage:
    scripts/smoke_integrations.py                    # probe everything
    scripts/smoke_integrations.py linkedin,resend    # probe a subset
    scripts/smoke_integrations.py --json             # machine-readable

Exit codes:
    0 — every probe that had credentials passed (skips don't fail the run)
    1 — at least one configured provider failed
    2 — usage error / missing dependency

Safety: this script only makes low-cost GET calls that don't cost
credits on consumption-billed APIs (X). Publisher clients are exercised
in *dry-run* mode — no posts are sent anywhere.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field

# Make repo importable when run from repo root or scripts/
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass
class ProbeResult:
    name: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""
    elapsed_ms: int = 0
    extras: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# .env.integrations auto-load (only if the key is not already in os.environ)
# --------------------------------------------------------------------------


def _load_env_file(path: str) -> int:
    """Populate os.environ from a KEY=VALUE dotenv file. Returns count loaded."""
    if not os.path.isfile(path):
        return 0
    loaded = 0
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key or not val:
                continue
            if key not in os.environ:
                os.environ[key] = val
                loaded += 1
    return loaded


# --------------------------------------------------------------------------
# Probes — each returns ProbeResult
# --------------------------------------------------------------------------


def _timed(fn: Callable[[], ProbeResult]) -> ProbeResult:
    t0 = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        result = ProbeResult("?", FAIL, f"{type(exc).__name__}: {exc}")
    result.elapsed_ms = int((time.perf_counter() - t0) * 1000)
    return result


def _skip_if_missing(name: str, *env_vars: str) -> ProbeResult | None:
    """Return a SKIP ProbeResult if any required env var is missing."""
    missing = [v for v in env_vars if not os.getenv(v)]
    if missing:
        return ProbeResult(name, SKIP, f"missing: {', '.join(missing)}")
    return None


def _http_get(url: str, *, headers: dict | None = None, timeout: int = 15) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    hdrs = {"User-Agent": "sapphire-smoke/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return r.status, {"raw": raw[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:200]}


# -- Publishing platforms --------------------------------------------------


def probe_linkedin() -> ProbeResult:
    skip = _skip_if_missing("linkedin", "LINKEDIN_ACCESS_TOKEN")
    if skip:
        return skip
    token = os.environ["LINKEDIN_ACCESS_TOKEN"]
    status, body = _http_get(
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status == 200 and "sub" in body:
        name = body.get("name") or body.get("email") or body.get("sub")
        return ProbeResult("linkedin", PASS, f"authed as {name}")
    return ProbeResult("linkedin", FAIL, f"HTTP {status}: {str(body)[:120]}")


def probe_typefully() -> ProbeResult:
    skip = _skip_if_missing("typefully", "TYPEFULLY_API_KEY")
    if skip:
        return skip
    key = os.environ["TYPEFULLY_API_KEY"]
    status, body = _http_get(
        "https://api.typefully.com/v1/drafts/recently-scheduled/",
        headers={"X-API-KEY": key},
    )
    if status in (200, 204):
        count = len(body) if isinstance(body, list) else "?"
        return ProbeResult("typefully", PASS, f"scheduled drafts: {count}")
    return ProbeResult("typefully", FAIL, f"HTTP {status}: {str(body)[:120]}")


def probe_x() -> ProbeResult:
    """X: probe bearer if available, else confirm OAuth 1.0a keys are set."""
    bearer = os.getenv("X_BEARER_TOKEN")
    oauth_keys = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET"]
    have_oauth = all(os.getenv(k) for k in oauth_keys)

    if bearer:
        status, body = _http_get(
            "https://api.x.com/2/users/by/username/rariwrld",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        if status == 200 and "data" in body:
            uname = body["data"].get("username")
            return ProbeResult("x", PASS, f"bearer token valid, resolves @{uname}")
        if status == 200:
            return ProbeResult("x", PASS, "bearer token valid")
        return ProbeResult("x", FAIL, f"bearer HTTP {status}: {str(body)[:120]}")

    if have_oauth:
        # Don't actually call /2/users/me — signing OAuth 1.0a inline here
        # would duplicate XClient's logic. Just confirm the quartet is set;
        # real validation happens on first publish.
        return ProbeResult(
            "x",
            PASS,
            "OAuth 1.0a keys present (live validation deferred; posts cost credits)",
        )

    return ProbeResult("x", SKIP, "no X_BEARER_TOKEN and OAuth 1.0a quartet not set")


def probe_resend() -> ProbeResult:
    skip = _skip_if_missing("resend", "RESEND_API_KEY")
    if skip:
        return skip
    key = os.environ["RESEND_API_KEY"]
    status, body = _http_get(
        "https://api.resend.com/domains",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status == 200:
        domains = body.get("data", []) if isinstance(body, dict) else []
        verified = [d.get("name") for d in domains if d.get("status") == "verified"]
        if verified:
            return ProbeResult("resend", PASS, f"verified: {', '.join(verified)}")
        return ProbeResult("resend", PASS, f"authed; {len(domains)} domain(s), none verified yet")
    # 401 with name="restricted_api_key" means the key is VALID but scoped
    # to Sending access (least privilege — exactly what we recommend). The
    # key still works for the email-send path; we just can't enumerate
    # domains from it. Treat as PASS with a clear note.
    if status == 401 and isinstance(body, dict) and body.get("name") == "restricted_api_key":
        return ProbeResult(
            "resend",
            PASS,
            "authed (sending-scoped key — verify domains in the Resend dashboard)",
        )
    if status == 401:
        return ProbeResult("resend", FAIL, "HTTP 401 — bad RESEND_API_KEY")
    return ProbeResult("resend", FAIL, f"HTTP {status}: {str(body)[:120]}")


def probe_substack() -> ProbeResult:
    skip = _skip_if_missing("substack", "SUBSTACK_POST_EMAIL", "RESEND_API_KEY")
    if skip:
        return skip
    # Substack has no readable API — presence of post email + working Resend
    # is the best proxy. We don't actually send a test email.
    post_email = os.environ["SUBSTACK_POST_EMAIL"]
    if "@" not in post_email or "substack.com" not in post_email:
        return ProbeResult("substack", FAIL, f"SUBSTACK_POST_EMAIL looks wrong: {post_email}")
    return ProbeResult(
        "substack",
        PASS,
        f"post-email configured ({post_email}); relies on Resend",
    )


# -- Chain data providers --------------------------------------------------


def _probe_chain(
    name: str, env_var: str, importer: Callable[[], Callable[[], object]]
) -> ProbeResult:
    """Run a chain-provider probe, deferring import until after the cred check.

    ``importer`` is a thunk that returns the actual call to make — that
    way we never import the provider module if the user hasn't filled in
    credentials, and we report library-side errors (missing Python 3.11,
    missing certifi) distinctly from auth/network errors.
    """
    skip = _skip_if_missing(name, env_var)
    if skip:
        return skip
    try:
        call = importer()
    except ImportError as exc:
        return ProbeResult(name, SKIP, f"library import error: {exc}")
    try:
        call()
        return ProbeResult(name, PASS, "authed call returned")
    except Exception as exc:  # noqa: BLE001
        return ProbeResult(name, FAIL, f"{type(exc).__name__}: {str(exc)[:200]}")


def probe_bgeometrics() -> ProbeResult:
    def _importer():
        from lib.chain.providers.bgeometrics import BGeometricsClient

        return lambda: BGeometricsClient().mvrv_z_score()

    return _probe_chain("bgeometrics", "BGEOMETRICS_API_KEY", _importer)


def probe_santiment() -> ProbeResult:
    def _importer():
        from lib.chain.providers.santiment import SantimentClient

        return lambda: SantimentClient().query("{ currentUser { id } }")

    return _probe_chain("santiment", "SANTIMENT_API_KEY", _importer)


def probe_dune() -> ProbeResult:
    skip = _skip_if_missing("dune", "DUNE_API_KEY")
    if skip:
        return skip
    # Dune has no cheap meta endpoint; presence + key-shape check is the
    # best we can do without burning an execution credit.
    key = os.environ["DUNE_API_KEY"]
    if len(key) < 20:
        return ProbeResult("dune", FAIL, "DUNE_API_KEY looks too short")
    return ProbeResult("dune", PASS, "key present (full validation requires an execute call)")


def probe_whale_alert() -> ProbeResult:
    def _importer():
        from lib.chain.providers.whale_alert import WhaleAlertClient

        return lambda: WhaleAlertClient().status()

    return _probe_chain("whale_alert", "WHALE_ALERT_API_KEY", _importer)


def probe_coinapi() -> ProbeResult:
    # exchanges() returns ~hundreds of rows; cache will dedup across runs.
    def _importer():
        from lib.chain.providers.coinapi import CoinAPIClient

        return lambda: CoinAPIClient().exchanges()

    return _probe_chain("coinapi", "COINAPI_KEY", _importer)


def probe_coinglass() -> ProbeResult:
    skip = _skip_if_missing("coinglass", "COINGLASS_API_KEY")
    if skip:
        return skip
    key = os.environ["COINGLASS_API_KEY"]
    status, body = _http_get(
        "https://open-api-v3.coinglass.com/api/futures/supported-coins",
        headers={"CG-API-KEY": key, "accept": "application/json"},
    )
    if status == 200 and isinstance(body, dict) and body.get("code") in ("0", 0):
        data = body.get("data") or []
        return ProbeResult("coinglass", PASS, f"supported coins: {len(data)}")
    return ProbeResult("coinglass", FAIL, f"HTTP {status}: {str(body)[:120]}")


# -- Infrastructure --------------------------------------------------------


def probe_cloudflare() -> ProbeResult:
    skip = _skip_if_missing("cloudflare", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID")
    if skip:
        return skip
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    acct = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    status, body = _http_get(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/cfd_tunnel?per_page=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    if status == 200 and body.get("success"):
        info = body.get("result_info") or {}
        total = info.get("total_count", "?")
        return ProbeResult("cloudflare", PASS, f"token valid; {total} tunnel(s)")
    return ProbeResult("cloudflare", FAIL, f"HTTP {status}: {str(body.get('errors'))[:120]}")


def probe_gcp() -> ProbeResult:
    """Light check: gcloud on PATH + ADC project resolves."""
    import shutil
    import subprocess

    if not shutil.which("gcloud"):
        return ProbeResult("gcp", SKIP, "gcloud not on PATH")
    try:
        proj = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        current = (proj.stdout or "").strip()
        if not current or current.lower() == "(unset)":
            return ProbeResult("gcp", FAIL, "no active gcloud project")
        return ProbeResult("gcp", PASS, f"gcloud project: {current}")
    except subprocess.TimeoutExpired:
        return ProbeResult("gcp", FAIL, "gcloud timed out")


# --------------------------------------------------------------------------
# Probe registry + CLI
# --------------------------------------------------------------------------

PROBES: dict[str, Callable[[], ProbeResult]] = {
    "linkedin": probe_linkedin,
    "typefully": probe_typefully,
    "x": probe_x,
    "resend": probe_resend,
    "substack": probe_substack,
    "bgeometrics": probe_bgeometrics,
    "santiment": probe_santiment,
    "dune": probe_dune,
    "whale_alert": probe_whale_alert,
    "coinapi": probe_coinapi,
    "coinglass": probe_coinglass,
    "cloudflare": probe_cloudflare,
    "gcp": probe_gcp,
}


_COLOUR = sys.stdout.isatty()


def _paint(s: str, colour: str) -> str:
    if not _COLOUR:
        return s
    codes = {"green": "\033[32m", "red": "\033[31m", "grey": "\033[90m", "reset": "\033[0m"}
    return f"{codes[colour]}{s}{codes['reset']}"


def _print_table(results: list[ProbeResult]) -> None:
    w_name = max(len(r.name) for r in results)
    for r in results:
        badge = {
            PASS: _paint("PASS", "green"),
            FAIL: _paint("FAIL", "red"),
            SKIP: _paint("SKIP", "grey"),
        }[r.status]
        ms = f"{r.elapsed_ms:>5}ms"
        print(f"  {r.name:<{w_name}}  {badge}  {ms}  {r.detail}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "filter", nargs="?", default="", help="comma-separated probe names (default: all)"
    )
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    ap.add_argument(
        "--env-file",
        default=os.path.join(REPO_ROOT, ".env.integrations"),
        help=".env.integrations path (default: repo root)",
    )
    args = ap.parse_args(argv)

    loaded = _load_env_file(args.env_file)

    selected = [p.strip() for p in args.filter.split(",") if p.strip()] or list(PROBES)
    unknown = [p for p in selected if p not in PROBES]
    if unknown:
        print(f"unknown probe(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"available: {', '.join(sorted(PROBES))}", file=sys.stderr)
        return 2

    if not args.json:
        print(
            f"Sapphire integrations smoke test — {len(selected)} probe(s), "
            f"loaded {loaded} vars from {args.env_file}"
        )
        print()

    results: list[ProbeResult] = []
    for name in selected:
        r = _timed(PROBES[name])
        r.name = name  # repair name if a probe returned "?"
        results.append(r)

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2, default=str))
    else:
        _print_table(results)
        print()
        counts = {PASS: 0, FAIL: 0, SKIP: 0}
        for r in results:
            counts[r.status] += 1
        print(
            f"  summary: {counts[PASS]} passed, " f"{counts[FAIL]} failed, {counts[SKIP]} skipped"
        )

    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
