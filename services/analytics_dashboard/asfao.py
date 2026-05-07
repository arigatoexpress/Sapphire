"""Sapphire ASFAO — Artificial Superintelligent Fully Autonomous Organization.

Promotes the Brain (passive observation) into a decision/action layer.

Three endpoints (deterministic, no LLM hop in v0):

    POST /api/asfao/decide
        Run the rules catalog over the latest brain synthesis +
        correlations. Returns proposed decisions and writes each one
        to the ``decisions`` BQ table with status='proposed'.

    POST /api/asfao/execute/<decision_id>
        Approve + execute a previously-proposed decision. Gated by
        the WebAuthn passkey ``@requires_admin`` decorator. Trading
        critical-path actions (kind=trading_*) NEVER auto-execute —
        they remain ``proposed`` and surface to a human review panel.

    GET  /api/asfao/decisions
        Recent decisions (filtered by status / role) for the dashboard.

Wire into the parent Flask app with :func:`register_asfao`. Mirrors
``brain.register_brain``'s injection pattern so we share the bigquery
client + project/dataset config without import cycles.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from flask import jsonify, request

log = logging.getLogger("sapphire.asfao")

# Roles in the ontology. Each rule belongs to exactly one role.
ROLES = ("CTO", "CFO", "Ops", "Threat", "Wildfire", "THO", "Strategy")

# Action kinds. Anything matching TRADING_CRITICAL_KINDS NEVER auto-executes.
TRADING_CRITICAL_KINDS = frozenset(
    {
        "trading_pause",
        "trading_resume",
        "trading_order",
        "payments_send",
        "hyperliquid_order",
        "hyperliquid_pause",
    }
)

# Vendors / products we care about for "CVE in our stack" matching.
# Sourced from a hand-curated read of requirements.txt — matched
# case-insensitively against threat_intel.affected_products.
SAPPHIRE_STACK_KEYWORDS = (
    "flask",
    "gunicorn",
    "google-cloud-bigquery",
    "google-cloud-firestore",
    "webauthn",
    "itsdangerous",
    "python",
    "ubuntu",
    "debian",
    "openssl",
    "openssh",
    "redis",
    "ollama",
    "tailscale",
    "node",
    "npm",
    "react",
    "fastapi",
    "uvicorn",
    "starlette",
    "pydantic",
)

# Per-rule defaults — each catalog entry can override.
DEFAULT_CONFIDENCE = 0.75


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _http_post_json(
    url: str,
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 5.0,
    method: str = "POST",
) -> tuple[int, dict | str | None]:
    """POST/GET helper — returns (status, body-as-dict-or-str)."""
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", "sapphire-asfao/1.0")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8")
        except Exception:  # noqa: BLE001
            raw = str(exc)
        return exc.code, raw
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc)


def _read_secret(name: str, project: str = "tho-ai-agent") -> str | None:
    """Best-effort secret-manager read. Returns None on failure or 'placeholder'."""
    # Prefer env override (LaunchAgent / dev path) before hitting metadata.
    env = os.environ.get(name.upper().replace("-", "_"))
    if env and env.strip() and env.strip() != "placeholder":
        return env.strip()
    try:
        from google.cloud import secretmanager  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    try:
        client = secretmanager.SecretManagerServiceClient()
        path = f"projects/{project}/secrets/{name}/versions/latest"
        resp = client.access_secret_version(request={"name": path})
        val = resp.payload.data.decode("utf-8").strip()
        if not val or val == "placeholder":
            return None
        return val
    except Exception as exc:  # noqa: BLE001
        log.info("secret %s unavailable: %s", name, exc)
        return None


# ---------------------------------------------------------------------------
# Side-effect adapters (the only things that touch the world).
# Every adapter returns a result dict that gets stored into decisions.result.
# ---------------------------------------------------------------------------


def _gh_find_open_issue(repo: str, title_substr: str, token: str) -> dict | None:
    """Search the repo for an open issue containing the title substring."""
    q = urllib.parse.quote(f'repo:{repo} is:issue is:open in:title "{title_substr}"')
    url = f"https://api.github.com/search/issues?q={q}"
    status, body = _http_post_json(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        method="GET",
    )
    if status != 200 or not isinstance(body, dict):
        return None
    items = body.get("items") or []
    return items[0] if items else None


def _gh_file_issue(repo: str, title: str, body: str, labels: list[str]) -> dict:
    """File a GitHub issue. Idempotent on title-substring match."""
    token = _read_secret("github-token")
    if not token:
        return {
            "ok": False,
            "error": "github_token_missing",
            "repo": repo,
            "title": title,
        }
    # Idempotency: only file if no open issue with same title prefix exists.
    existing = _gh_find_open_issue(repo, title, token)
    if existing:
        return {
            "ok": True,
            "skipped": "duplicate_open_issue",
            "issue_url": existing.get("html_url"),
            "issue_number": existing.get("number"),
        }
    url = f"https://api.github.com/repos/{repo}/issues"
    status, resp = _http_post_json(
        url,
        payload={"title": title, "body": body, "labels": labels},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
    )
    if status not in (200, 201) or not isinstance(resp, dict):
        return {"ok": False, "error": "github_api_failure", "status": status, "body": resp}
    return {
        "ok": True,
        "issue_url": resp.get("html_url"),
        "issue_number": resp.get("number"),
    }


def _telegram_notify(text: str, chat_id: str | None = None) -> dict:
    """Send a Telegram message via the ASFAO bot."""
    token = _read_secret("telegram-asfao-token")
    if not token:
        return {"ok": False, "error": "telegram_token_missing"}
    chat = chat_id or os.environ.get("TELEGRAM_ASFAO_CHAT_ID")
    if not chat:
        return {"ok": False, "error": "telegram_chat_id_missing"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    status, resp = _http_post_json(
        url,
        payload={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
        timeout=8.0,
    )
    if status != 200 or not isinstance(resp, dict):
        return {"ok": False, "status": status, "body": resp}
    return {"ok": True, "message_id": (resp.get("result") or {}).get("message_id")}


def _scheduler_refresh(job_name: str, project: str = "tho-ai-agent") -> dict:
    """Force-run a Cloud Scheduler job. No-op if SDK unavailable."""
    try:
        from google.cloud import scheduler_v1  # type: ignore
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "scheduler_sdk_unavailable"}
    try:
        client = scheduler_v1.CloudSchedulerClient()
        path = client.job_path(project, "us-central1", job_name)
        client.run_job(name=path)
        return {"ok": True, "job": job_name}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _execute_action(action: dict) -> dict:
    """Dispatch an action dict to the correct adapter.

    Action contract: ``{"kind": "<adapter_id>", **payload}``.

    Trading critical kinds are refused here as a defense-in-depth — the
    primary gate is in the ``execute`` endpoint which never reaches
    this function for those kinds.
    """
    kind = action.get("kind")
    if kind in TRADING_CRITICAL_KINDS:
        return {"ok": False, "error": "trading_critical_blocked", "kind": kind}
    if kind == "github_issue":
        return _gh_file_issue(
            repo=action.get("repo", "arigatoexpress/Sapphire"),
            title=action.get("title", "ASFAO autonomous decision"),
            body=action.get("body", ""),
            labels=action.get("labels", []),
        )
    if kind == "telegram_alert":
        return _telegram_notify(action.get("text", ""), chat_id=action.get("chat_id"))
    if kind == "scheduler_refresh":
        return _scheduler_refresh(action.get("job"))
    if kind == "noop":
        return {"ok": True, "noop": True, **{k: v for k, v in action.items() if k != "kind"}}
    return {"ok": False, "error": "unknown_kind", "kind": kind}


# ---------------------------------------------------------------------------
# Rules catalog — pure functions over (synthesis, correlations, ctx).
#
# Each rule:
#   * returns ``(should_propose: bool, decision: dict)``
#   * decision ``action.kind`` MUST NOT be a trading critical-path kind
#     unless the rule's intent is "alert humans only" (no auto-exec).
#
# New rules: append to RULES_CATALOG.
# ---------------------------------------------------------------------------


def rule_stale_collector_issue(
    synthesis: dict, _correlations: list[dict], _ctx: dict
) -> tuple[bool, dict]:
    """If a service silo has been silent for >6h, file a GitHub issue."""
    actions = synthesis.get("priority_actions") or []
    degraded = synthesis.get("degraded_silos") or []
    targets: list[tuple[str, float]] = []
    for action in actions:
        # Match shape: "regime: collector stale 8.4h — restart com.sapphire.regime-collector"
        if "stale" not in action.lower():
            continue
        try:
            silo, rest = action.split(":", 1)
        except ValueError:
            continue
        silo = silo.strip().lower()
        # Extract the X.Yh number
        import re

        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*h", rest)
        if not m:
            continue
        hours = float(m.group(1))
        if hours <= 6:
            continue
        targets.append((silo, hours))
    if not targets:
        return False, {}
    # Pick the worst-affected silo.
    silo, hours = max(targets, key=lambda t: t[1])
    title = f"[ASFAO] {silo} silent for {hours:.1f}h"
    body = (
        f"## Auto-filed by Sapphire ASFAO\n\n"
        f"The `{silo}` silo has been silent for **{hours:.1f}h** "
        f"(threshold: 6h).\n\n"
        f"### Brain narrative\n> {synthesis.get('narrative', '(no narrative)')}\n\n"
        f"### Degraded silos\n{', '.join(degraded) if degraded else '(none)'}\n\n"
        f"### Priority actions\n"
        + "\n".join(f"- {a}" for a in actions[:10])
        + f"\n\n*Filed at {_now_iso()} · health score: {synthesis.get('health_score')}*"
    )
    return True, {
        "role": "Ops",
        "trigger": {
            "rule": "stale_collector_issue",
            "silo": silo,
            "hours_silent": hours,
            "evidence": actions[:5],
        },
        "action": {
            "kind": "github_issue",
            "repo": "arigatoexpress/Sapphire",
            "title": title,
            "body": body,
            "labels": ["auto-filed", "ops"],
        },
        "confidence": 0.85,
    }


def rule_critical_cve_alert(
    _synthesis: dict, _correlations: list[dict], ctx: dict
) -> tuple[bool, dict]:
    """If a CRITICAL CVE in last 24h affects our stack, alert + file issue."""
    cves = ctx.get("critical_cves_24h") or []
    if not cves:
        return False, {}
    # Filter to ones whose affected_products intersect our stack keywords.
    matched: list[dict] = []
    kw_lower = [k.lower() for k in SAPPHIRE_STACK_KEYWORDS]
    for cve in cves:
        products = cve.get("affected_products") or []
        if not products:
            continue
        prod_blob = " ".join(p.lower() for p in products)
        if any(kw in prod_blob for kw in kw_lower):
            matched.append(cve)
    if not matched:
        return False, {}
    primary = matched[0]
    cve_id = primary.get("cve_id", "(unknown)")
    products = primary.get("affected_products") or []
    msg = (
        f"*ASFAO Threat Alert*\n\n"
        f"`{cve_id}` (CVSS {primary.get('cvss_score', 'n/a')}) is CRITICAL "
        f"and affects {', '.join(products[:3])}.\n\n"
        f"Total stack-relevant CRITICAL CVEs in last 24h: {len(matched)}."
    )
    return True, {
        "role": "Threat",
        "trigger": {
            "rule": "critical_cve_alert",
            "matched_count": len(matched),
            "primary_cve": cve_id,
            "affected_products": products[:5],
        },
        "action": {
            "kind": "telegram_alert",
            "text": msg,
        },
        "confidence": 0.9,
    }


def rule_trading_silo_silent(
    synthesis: dict, _correlations: list[dict], ctx: dict
) -> tuple[bool, dict]:
    """Trading silo silent + a live executor enabled → human-only critical alert.

    NEVER auto-disables trading. The action kind is ``telegram_alert``
    so we surface to humans; humans decide whether to flip the killswitch.
    """
    degraded = set(synthesis.get("degraded_silos") or [])
    if "trading" not in degraded:
        return False, {}
    live_enabled = ctx.get("hyperliquid_live_enabled") or ctx.get("any_live_executor_enabled")
    if not live_enabled:
        return False, {}
    msg = (
        "*ASFAO CRITICAL — trading silo silent w/ live executor enabled*\n\n"
        "The brain reports the trading silo as degraded *and* a live "
        "executor is currently enabled. ASFAO will NOT auto-pause "
        "(human-only control). Recommend: drop the killswitch file "
        "`~/.sapphire/hyperliquid_trading_pause` if this is unexpected.\n\n"
        f"Health: {synthesis.get('health_score')}"
    )
    return True, {
        "role": "CTO",
        "trigger": {
            "rule": "trading_silo_silent",
            "degraded": list(degraded),
            "live_executor": ctx.get("live_executor_label", "unknown"),
        },
        "action": {
            "kind": "telegram_alert",
            "text": msg,
        },
        "confidence": 0.95,
    }


def rule_lead_nurture(_synthesis: dict, _correlations: list[dict], ctx: dict) -> tuple[bool, dict]:
    """If THO has stale LEAD-status leads >7d old, propose a nurture digest.

    The action is a noop here — surfaces a recommendation to ops. The
    real execution path is operator-driven by hitting the existing
    THO lead-nurture endpoint manually after review.
    """
    stale_leads = ctx.get("stale_leads_count")
    if stale_leads is None or stale_leads <= 0:
        return False, {}
    return True, {
        "role": "THO",
        "trigger": {
            "rule": "lead_nurture",
            "stale_leads_count": stale_leads,
            "threshold_days": 7,
        },
        "action": {
            "kind": "noop",
            "recommendation": (
                f"{stale_leads} LEAD-status leads older than 7 days. "
                "Run THO lead-nurture endpoint in dry_run mode and review."
            ),
            "endpoint": "/api/leads/nurture?dry_run=1",
        },
        "confidence": 0.7,
    }


def rule_regional_intel_surge(
    _synthesis: dict, _correlations: list[dict], ctx: dict
) -> tuple[bool, dict]:
    """If a region's intel-item count is >2 std dev, propose a brief generation."""
    surge = ctx.get("regional_surge")  # {region_id, today, mean, stddev, z}
    if not surge:
        return False, {}
    if (surge.get("z") or 0) <= 2.0:
        return False, {}
    region = surge.get("region_id", "unknown")
    msg = (
        f"*ASFAO Regional Surge*\n\n"
        f"Region `{region}` intel-item count {surge.get('today')} is "
        f"{surge.get('z'):.1f}σ above its 30-day mean ({surge.get('mean'):.1f} ± {surge.get('stddev'):.1f}).\n\n"
        "Recommend: generate a regional brief."
    )
    return True, {
        "role": "Strategy",
        "trigger": {
            "rule": "regional_intel_surge",
            "region_id": region,
            "z_score": surge.get("z"),
            "today_count": surge.get("today"),
        },
        "action": {
            "kind": "telegram_alert",
            "text": msg,
        },
        "confidence": 0.8,
    }


RULES_CATALOG = [
    rule_stale_collector_issue,
    rule_critical_cve_alert,
    rule_trading_silo_silent,
    rule_lead_nurture,
    rule_regional_intel_surge,
]


def evaluate_rules(synthesis: dict, correlations: list[dict], ctx: dict) -> list[dict]:
    """Run every rule once and return the list of proposed decisions."""
    proposals: list[dict] = []
    for rule in RULES_CATALOG:
        try:
            should, decision = rule(synthesis, correlations, ctx)
            if should and decision:
                proposals.append(decision)
        except Exception as exc:  # noqa: BLE001
            log.warning("rule %s raised: %s", rule.__name__, exc)
    return proposals


# ---------------------------------------------------------------------------
# Flask integration.
# ---------------------------------------------------------------------------


def register_asfao(app, *, project: str, dataset: str, bq_client, query_param_factory) -> None:
    """Attach ASFAO endpoints to ``app``.

    Mirrors :func:`brain.register_brain` so the parent app injects the
    bigquery client and config. Lazy-imports ``requires_admin`` so a
    missing webauthn dep doesn't crash registration — admin gating
    will simply 503 in that case.
    """
    bigquery = query_param_factory  # alias

    try:
        from auth import requires_admin  # type: ignore
    except Exception as exc:  # noqa: BLE001
        log.warning("asfao admin gate disabled (%s) — execute endpoint will 503", exc)

        def requires_admin(view):  # type: ignore[no-redef]
            from functools import wraps

            @wraps(view)
            def _blocked(*a, **kw):
                return jsonify({"error": "admin_auth_not_configured"}), 503

            return _blocked

    def _rows(sql: str, params: list | None = None) -> list[dict]:
        job = bq_client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params or []),
        )
        return [dict(r) for r in job.result()]

    def _gather_context() -> dict:
        """Pull supplementary signals the rules catalog needs."""
        ctx: dict[str, Any] = {}
        # Critical CVEs in last 24h with affected_products populated.
        try:
            rows = _rows(f"""
                SELECT cve_id, severity, cvss_score, affected_products
                FROM `{project}.{dataset}.threat_intel`
                WHERE severity = 'CRITICAL'
                  AND ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                LIMIT 50
            """)
            ctx["critical_cves_24h"] = rows
        except Exception:
            ctx["critical_cves_24h"] = []
        # Stale lead count — defensive: skip if leads table doesn't exist.
        try:
            rows = _rows(f"""
                SELECT COUNT(*) AS n
                FROM `{project}.{dataset}.leads`
                WHERE LOWER(status) = 'lead'
                  AND COALESCE(updated_at, created_at) <
                      TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
            """)
            ctx["stale_leads_count"] = int(rows[0].get("n") or 0) if rows else 0
        except Exception:
            ctx["stale_leads_count"] = None
        # Regional intel surge — z-score per region today vs 30d.
        try:
            rows = _rows(f"""
                WITH per_day AS (
                    SELECT region_id,
                           DATE(ingested_at) AS d,
                           COUNT(*) AS n
                    FROM `{project}.{dataset}.regional_intel_items`
                    WHERE ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
                    GROUP BY region_id, d
                ),
                stats AS (
                    SELECT region_id, AVG(n) AS mean_n, STDDEV(n) AS sd_n
                    FROM per_day
                    WHERE d < CURRENT_DATE()
                    GROUP BY region_id
                ),
                today AS (
                    SELECT region_id, COUNT(*) AS today_n
                    FROM `{project}.{dataset}.regional_intel_items`
                    WHERE DATE(ingested_at) = CURRENT_DATE()
                    GROUP BY region_id
                )
                SELECT t.region_id, t.today_n, s.mean_n, s.sd_n,
                       SAFE_DIVIDE(t.today_n - s.mean_n, NULLIF(s.sd_n, 0)) AS z
                FROM today t
                JOIN stats s USING (region_id)
                WHERE SAFE_DIVIDE(t.today_n - s.mean_n, NULLIF(s.sd_n, 0)) > 2.0
                ORDER BY z DESC
                LIMIT 1
            """)
            if rows:
                r = rows[0]
                ctx["regional_surge"] = {
                    "region_id": r.get("region_id"),
                    "today": int(r.get("today_n") or 0),
                    "mean": float(r.get("mean_n") or 0),
                    "stddev": float(r.get("sd_n") or 0),
                    "z": float(r.get("z") or 0),
                }
        except Exception:
            ctx["regional_surge"] = None
        # Live executor — hyperliquid is the only one in tree today.
        ctx["hyperliquid_live_enabled"] = os.environ.get("HYPERLIQUID_TRADING_ENABLED", "0") == "1"
        ctx["any_live_executor_enabled"] = ctx["hyperliquid_live_enabled"]
        ctx["live_executor_label"] = "hyperliquid" if ctx["hyperliquid_live_enabled"] else "none"
        return ctx

    def _persist_proposal(decision: dict, source_synthesis_id: str | None) -> str:
        """Insert a proposed decision into the BQ table, return decision_id."""
        decision_id = secrets.token_hex(10)
        now = _now_iso()
        trigger = dict(decision.get("trigger") or {})
        if source_synthesis_id and "source_synthesis_id" not in trigger:
            trigger["source_synthesis_id"] = source_synthesis_id
        sql = f"""
            INSERT INTO `{project}.{dataset}.decisions`
            (decision_id, role, trigger, action, confidence, status,
             proposed_at, executed_at, result)
            VALUES (@id, @role, PARSE_JSON(@trigger), PARSE_JSON(@action),
                    @conf, @status, @proposed, NULL, NULL)
        """
        params = [
            bigquery.ScalarQueryParameter("id", "STRING", decision_id),
            bigquery.ScalarQueryParameter("role", "STRING", decision.get("role", "Ops")),
            bigquery.ScalarQueryParameter("trigger", "STRING", json.dumps(trigger)),
            bigquery.ScalarQueryParameter(
                "action", "STRING", json.dumps(decision.get("action") or {})
            ),
            bigquery.ScalarQueryParameter(
                "conf", "FLOAT64", float(decision.get("confidence") or DEFAULT_CONFIDENCE)
            ),
            bigquery.ScalarQueryParameter("status", "STRING", "proposed"),
            bigquery.ScalarQueryParameter("proposed", "TIMESTAMP", now),
        ]
        bq_client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
        return decision_id

    def _load_decision(decision_id: str) -> dict | None:
        try:
            rows = _rows(
                f"""
                SELECT decision_id, role, trigger, action, confidence,
                       status, proposed_at, executed_at, result
                FROM `{project}.{dataset}.decisions`
                WHERE decision_id = @id
                LIMIT 1
                """,
                params=[bigquery.ScalarQueryParameter("id", "STRING", decision_id)],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("load_decision failed: %s", exc)
            return None
        if not rows:
            return None
        d = rows[0]
        # JSON columns come back as already-parsed dict in BQ Python client.
        return {
            "decision_id": d.get("decision_id"),
            "role": d.get("role"),
            "trigger": d.get("trigger"),
            "action": d.get("action"),
            "confidence": d.get("confidence"),
            "status": d.get("status"),
            "proposed_at": d.get("proposed_at"),
            "executed_at": d.get("executed_at"),
            "result": d.get("result"),
        }

    def _update_decision(decision_id: str, *, status: str, result: dict | None) -> None:
        sql = f"""
            UPDATE `{project}.{dataset}.decisions`
            SET status = @status,
                executed_at = @executed,
                result = PARSE_JSON(@result)
            WHERE decision_id = @id
        """
        params = [
            bigquery.ScalarQueryParameter("id", "STRING", decision_id),
            bigquery.ScalarQueryParameter("status", "STRING", status),
            bigquery.ScalarQueryParameter("executed", "TIMESTAMP", _now_iso()),
            bigquery.ScalarQueryParameter("result", "STRING", json.dumps(result or {})),
        ]
        bq_client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()

    def _serialize_row(d: dict) -> dict:
        out = dict(d)
        for k in ("proposed_at", "executed_at"):
            v = out.get(k)
            if isinstance(v, datetime):
                out[k] = v.isoformat()
        return out

    def _self_fetch_synthesis() -> tuple[dict, list[dict], str | None]:
        """Loop back to /api/brain/* on the same instance via the test client.

        Cheap (in-process) and avoids needing an external HTTP hop or a
        baked-in DASHBOARD_BASE_URL. Returns (synthesis, correlations,
        synthesis_id-if-persisted).
        """
        client = app.test_client()
        synthesis: dict = {}
        correlations: list[dict] = []
        sid: str | None = None
        try:
            r = client.get("/api/brain/synthesis?persist=1")
            if r.status_code == 200:
                synthesis = r.get_json() or {}
                sid = synthesis.get("synthesis_id")
        except Exception as exc:  # noqa: BLE001
            log.warning("self-fetch synthesis failed: %s", exc)
        try:
            r = client.get("/api/brain/correlate")
            if r.status_code == 200:
                correlations = (r.get_json() or {}).get("matches") or []
        except Exception as exc:  # noqa: BLE001
            log.warning("self-fetch correlate failed: %s", exc)
        return synthesis, correlations, sid

    @app.post("/api/asfao/decide")
    def _asfao_decide_endpoint():
        body = request.get_json(silent=True) or {}
        synthesis = body.get("synthesis")
        correlations = body.get("correlations")
        source_synthesis_id = body.get("synthesis_id")
        # Scheduler fires this with an empty body — pull synthesis inline.
        if not synthesis:
            synthesis, fetched_corr, fetched_sid = _self_fetch_synthesis()
            if correlations is None:
                correlations = fetched_corr
            if not source_synthesis_id:
                source_synthesis_id = fetched_sid
        if correlations is None:
            correlations = []
        if not source_synthesis_id:
            source_synthesis_id = (synthesis or {}).get("synthesis_id")
        ctx = _gather_context()
        proposals = evaluate_rules(synthesis or {}, correlations, ctx)
        persisted: list[dict] = []
        for p in proposals:
            try:
                decision_id = _persist_proposal(p, source_synthesis_id)
                persisted.append({"decision_id": decision_id, **p})
            except Exception as exc:  # noqa: BLE001
                log.warning("persist proposal failed: %s", exc)
                persisted.append({"decision_id": None, "persist_error": str(exc), **p})
        return jsonify(
            {
                "ts": _now_iso(),
                "proposed_count": len(persisted),
                "decisions": persisted,
                "context_keys": sorted(ctx.keys()),
            }
        )

    @app.post("/api/asfao/execute/<decision_id>")
    @requires_admin
    def _asfao_execute_endpoint(decision_id: str):
        body = request.get_json(silent=True) or {}
        approve = bool(body.get("approve", True))
        rec = _load_decision(decision_id)
        if not rec:
            return jsonify({"error": "not_found"}), 404
        status = (rec.get("status") or "").lower()
        if status not in ("proposed", "approved"):
            return jsonify(
                {
                    "error": "invalid_status",
                    "status": status,
                    "message": "Only proposed/approved decisions can transition.",
                }
            ), 409
        if not approve:
            try:
                _update_decision(decision_id, status="rejected", result={"rejected_by": "admin"})
            except Exception as exc:  # noqa: BLE001
                return jsonify({"error": "update_failed", "detail": str(exc)}), 500
            return jsonify({"decision_id": decision_id, "status": "rejected"})
        action = rec.get("action") or {}
        kind = action.get("kind")
        if kind in TRADING_CRITICAL_KINDS:
            return jsonify(
                {
                    "error": "trading_critical_blocked",
                    "kind": kind,
                    "message": "Trading critical-path actions never auto-execute.",
                }
            ), 403
        # Mark approved → execute → update status to executed/failed.
        try:
            _update_decision(decision_id, status="approved", result={"approved_by": "admin"})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": "approve_failed", "detail": str(exc)}), 500
        side = _execute_action(action)
        new_status = "executed" if side.get("ok") else "rejected"
        try:
            _update_decision(decision_id, status=new_status, result=side)
        except Exception as exc:  # noqa: BLE001
            log.warning("post-execute persist failed: %s", exc)
        return jsonify(
            {
                "decision_id": decision_id,
                "status": new_status,
                "result": side,
            }
        )

    @app.get("/api/asfao/decisions")
    def _asfao_list_endpoint():
        status = request.args.get("status")
        role = request.args.get("role")
        limit = max(1, min(100, int(request.args.get("limit", "20"))))
        clauses = []
        params: list = []
        if status:
            clauses.append("status = @status")
            params.append(bigquery.ScalarQueryParameter("status", "STRING", status))
        if role:
            clauses.append("role = @role")
            params.append(bigquery.ScalarQueryParameter("role", "STRING", role))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT decision_id, role, trigger, action, confidence,
                   status, proposed_at, executed_at, result
            FROM `{project}.{dataset}.decisions`
            {where}
            ORDER BY proposed_at DESC
            LIMIT @limit
        """
        params.append(bigquery.ScalarQueryParameter("limit", "INT64", limit))
        try:
            rows = _rows(sql, params=params)
        except Exception as exc:  # noqa: BLE001
            log.info("decisions list miss: %s", exc)
            return jsonify({"rows": []})
        return jsonify({"rows": [_serialize_row(r) for r in rows]})
