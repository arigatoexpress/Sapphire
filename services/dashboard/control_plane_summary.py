"""Normalized Control Plane summary cards for the dashboard React spine."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SURFACE_INVENTORY = ROOT / "services" / "dashboard" / "config" / "surface_inventory.json"
X402_PRODUCTS = ROOT / "config" / "x402_products.json"
X402_SOURCES = ROOT / "config" / "x402_source_registry.json"
AGENTWIKI_ARTIFACTS = ROOT / "config" / "agentwiki_artifacts.json"

CARD_STATUSES = {"ok", "warn", "fail", "unknown"}
CARD_MODES = {"live", "read_only", "paper", "modeled", "stale", "blocked"}


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _file_source(path: Path, *, now: datetime, kind: str = "file") -> dict[str, Any]:
    rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    if not path.exists():
        return {
            "kind": kind,
            "path_or_url": rel,
            "generated_at": None,
            "age_seconds": None,
        }
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC).replace(microsecond=0)
    return {
        "kind": kind,
        "path_or_url": rel,
        "generated_at": _iso(mtime),
        "age_seconds": max(0, int((now - mtime).total_seconds())),
    }


def _card(
    *,
    module: str,
    status: str,
    mode: str,
    title: str,
    value: str,
    summary: str,
    source: Mapping[str, Any],
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if status not in CARD_STATUSES:
        raise ValueError(f"invalid card status: {status}")
    if mode not in CARD_MODES:
        raise ValueError(f"invalid card mode: {mode}")
    return {
        "module": module,
        "status": status,
        "mode": mode,
        "title": title,
        "value": value,
        "summary": summary,
        "source": dict(source),
        "actions": actions or [],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _probe_json(
    url: str,
    *,
    timeout_seconds: float = 0.6,
    opener: Callable[..., Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw.strip() else {}
            return "ok", payload if isinstance(payload, dict) else {"payload": payload}
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return "fail", {"error": f"{type(exc).__name__}: {exc}"}


def _fast_worktree_count(root: Path = ROOT) -> tuple[int | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=root,
            text=True,
            capture_output=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "git worktree list failed")[:160]
    count = sum(1 for line in result.stdout.splitlines() if line.startswith("worktree "))
    return count, None


def _dashboard_surface_card(now: datetime) -> dict[str, Any]:
    inventory = _read_json(SURFACE_INVENTORY)
    summary = inventory.get("summary", {})
    lifecycles = summary.get("lifecycles", {})
    hard_stops = int(lifecycles.get("hard-stop") or 0)
    route_count = int(summary.get("route_count") or 0)
    page_count = int(summary.get("page_template_count") or 0)
    merge_count = int(lifecycles.get("merge") or 0)
    status = "ok" if route_count and page_count else "fail"
    return _card(
        module="Home / Worldline",
        status=status,
        mode="read_only",
        title="Dashboard Surface",
        value=f"{route_count} routes · {page_count} templates",
        summary=(
            f"{merge_count} legacy surfaces are marked for module merge; "
            f"{hard_stops} x402 routes remain hard-stop/simulated."
        ),
        source=_file_source(SURFACE_INVENTORY, now=now),
        actions=[
            {
                "label": "Regenerate inventory",
                "mode": "dry_run",
                "requires_confirm": False,
            }
        ],
    )


def _control_plane_health_card(now: datetime, *, probe_services: bool) -> dict[str, Any]:
    url = "http://127.0.0.1:8082/health"
    if not probe_services:
        return _card(
            module="Operations",
            status="unknown",
            mode="stale",
            title="Control Plane Runtime",
            value="not probed",
            summary="Service probing is disabled for this summary build.",
            source={
                "kind": "service",
                "path_or_url": url,
                "generated_at": _iso(now),
                "age_seconds": 0,
            },
        )
    status, payload = _probe_json(url)
    ok = status == "ok" and str((payload or {}).get("status", "")).lower() in {"ok", "healthy"}
    runtime_mode = (payload or {}).get("runtime_mode") or "unknown"
    store = (payload or {}).get("store") or "unknown"
    return _card(
        module="Operations",
        status="ok" if ok else "fail",
        mode="live" if ok else "blocked",
        title="Control Plane Runtime",
        value=f"{runtime_mode} · {store}" if ok else "unreachable",
        summary=(
            "Local control-plane health is responding with the current runtime/store posture."
            if ok
            else f"Local control-plane health probe failed: {(payload or {}).get('error', 'unknown')}"
        ),
        source={"kind": "probe", "path_or_url": url, "generated_at": _iso(now), "age_seconds": 0},
    )


def _fast_org_status_card(now: datetime) -> dict[str, Any]:
    try:
        from scripts.ops.org_status import load_manifest

        manifest = load_manifest()
        repos = manifest.get("repos") or []
        upstream = manifest.get("upstream_repos") or []
        worktree_count, worktree_error = _fast_worktree_count()
        status = "ok" if worktree_error is None else "unknown"
        value = (
            f"{len(repos)} repos · {worktree_count} worktrees"
            if worktree_count is not None
            else f"{len(repos)} repos · worktrees unknown"
        )
        detail = (
            f"{len(upstream)} upstream integrations are tracked. "
            "Dirty-state sweep is deferred to the Operations module."
            if worktree_error is None
            else f"Worktree count probe failed: {worktree_error}"
        )
        return _card(
            module="Operations",
            status=status,
            mode="read_only" if worktree_error is None else "stale",
            title="Org Repo Posture",
            value=value,
            summary=detail,
            source={
                "kind": "script",
                "path_or_url": "infra/org-repos.yaml + git worktree list --porcelain",
                "generated_at": _iso(now),
                "age_seconds": 0,
            },
            actions=[
                {
                    "label": "Run detailed no-external status",
                    "mode": "read_only",
                    "requires_confirm": False,
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return _card(
            module="Operations",
            status="unknown",
            mode="stale",
            title="Org Repo Posture",
            value="not available",
            summary=f"Fast org posture could not be built: {type(exc).__name__}: {exc}",
            source={
                "kind": "script",
                "path_or_url": "infra/org-repos.yaml",
                "generated_at": _iso(now),
                "age_seconds": 0,
            },
        )


def _detailed_org_status_card(now: datetime) -> dict[str, Any]:
    try:
        from scripts.ops.org_status import collect_status, load_manifest

        report = collect_status(load_manifest(), external=False)
        summary = report.get("summary", {})
        dirty_repos = summary.get("dirty_repos") or []
        dirty_worktrees = summary.get("dirty_worktrees") or []
        repo_count = int(summary.get("repo_count") or 0)
        worktree_count = int(summary.get("worktree_count") or 0)
        status = "warn" if dirty_repos or dirty_worktrees else "ok"
        detail = (
            f"{len(dirty_repos)} dirty repos and {len(dirty_worktrees)} dirty worktrees."
            if status == "warn"
            else "Canonical tracked repos are clean in the no-external snapshot."
        )
        return _card(
            module="Operations",
            status=status,
            mode="read_only",
            title="Org Repo Posture",
            value=f"{repo_count} repos · {worktree_count} worktrees",
            summary=detail,
            source={
                "kind": "script",
                "path_or_url": "scripts/ops/org_status.py --no-external",
                "generated_at": report.get("generated_at") or _iso(now),
                "age_seconds": 0,
            },
            actions=[
                {
                    "label": "Refresh no-external status",
                    "mode": "read_only",
                    "requires_confirm": False,
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return _card(
            module="Operations",
            status="unknown",
            mode="stale",
            title="Org Repo Posture",
            value="not available",
            summary=f"No-external org status could not be built: {type(exc).__name__}: {exc}",
            source={
                "kind": "script",
                "path_or_url": "scripts/ops/org_status.py",
                "generated_at": _iso(now),
                "age_seconds": 0,
            },
        )


def _x402_product_card(now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    from lib.payments.x402_product_index import build_product_index
    from lib.payments.x402_products import load_validated_catalogs

    catalog, registry = load_validated_catalogs()
    index = build_product_index(catalog, registry, generated_at=_iso(now))
    summary = index["summary"]
    product_count = int(summary["product_count"])
    live_count = int(summary["live_settlement_allowed_count"])
    source_review_count = int(summary["source_review_required_count"])
    readiness_status = "warn" if source_review_count else "ok"
    return (
        _card(
            module="Products / Diligence",
            status=readiness_status,
            mode="read_only",
            title="x402 Product Spine",
            value=f"{product_count} products · {live_count} live settlement",
            summary=(
                f"{source_review_count} products still require source/terms review; "
                "all catalogued products remain simulated or testnet-only."
            ),
            source=_file_source(X402_PRODUCTS, now=now),
            actions=[
                {
                    "label": "Review product catalog",
                    "mode": "read_only",
                    "requires_confirm": False,
                }
            ],
        ),
        index,
    )


def _agentwiki_card(now: datetime) -> dict[str, Any]:
    from lib.payments.agentwiki import load_validated_agentwiki_artifacts
    from lib.payments.x402_products import load_validated_catalogs

    catalog, registry = load_validated_catalogs()
    artifacts = load_validated_agentwiki_artifacts(catalog, registry)
    source_ids = {source_id for artifact in artifacts for source_id in artifact.source_ids}
    return _card(
        module="Intelligence",
        status="warn",
        mode="read_only",
        title="AgentWiki Builder Briefs",
        value=f"{len(artifacts)} briefs · {len(source_ids)} sources",
        summary=(
            "Static rights-labeled artifacts are ready for discovery and simulated x402 delivery; "
            "live crawling and resale of raw source material stay blocked."
        ),
        source=_file_source(AGENTWIKI_ARTIFACTS, now=now),
        actions=[
            {
                "label": "Search AgentWiki",
                "mode": "read_only",
                "requires_confirm": False,
            }
        ],
    )


def _x402_safety_card(now: datetime, product_index: Mapping[str, Any]) -> dict[str, Any]:
    safety = product_index.get("safety", {})
    summary = product_index.get("summary", {})
    safe = (
        safety.get("live_settlement_default") is False
        and safety.get("real_trading_enabled") is False
        and safety.get("telegram_sends_enabled") is False
        and safety.get("production_mutation_enabled") is False
        and int(summary.get("live_settlement_allowed_count") or 0) == 0
    )
    return _card(
        module="Security",
        status="ok" if safe else "fail",
        mode="blocked",
        title="Commercial Safety Contract",
        value="live settlement off" if safe else "review required",
        summary=(
            "Paid APIs can be discovered and simulated, but live settlement, real trading, "
            "Telegram sends, and production mutations are explicitly disabled."
        ),
        source=_file_source(X402_SOURCES, now=now),
        actions=[
            {
                "label": "Plan operator-gated settlement test",
                "mode": "dry_run",
                "requires_confirm": True,
            }
        ],
    )


def _dashboard_runtime_card(now: datetime) -> dict[str, Any]:
    return _card(
        module="Home / Worldline",
        status="ok",
        mode="live",
        title="Dashboard Runtime",
        value="serving",
        summary="The authenticated Flask dashboard is serving this Control Plane summary.",
        source={
            "kind": "service",
            "path_or_url": "/api/v2/control-plane/summary",
            "generated_at": _iso(now),
            "age_seconds": 0,
        },
    )


def _module_rollup(cards: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    modules = [
        "Home / Worldline",
        "Operations",
        "Intelligence",
        "Markets",
        "Security",
        "Products / Diligence",
        "Automation",
        "Settings / Contracts",
    ]
    severity = {"fail": 3, "warn": 2, "unknown": 1, "ok": 0}
    rollup: list[dict[str, Any]] = []
    for module in modules:
        module_cards = [card for card in cards if card.get("module") == module]
        if not module_cards:
            rollup.append(
                {
                    "name": module,
                    "status": "unknown",
                    "summary": "No v2 summary card is wired for this module yet.",
                    "card_count": 0,
                }
            )
            continue
        worst = max(module_cards, key=lambda card: severity.get(str(card.get("status")), 1))
        rollup.append(
            {
                "name": module,
                "status": worst.get("status", "unknown"),
                "summary": f"{len(module_cards)} card(s) wired.",
                "card_count": len(module_cards),
            }
        )
    return rollup


def _overall_status(cards: list[Mapping[str, Any]]) -> str:
    statuses = {str(card.get("status")) for card in cards}
    if "fail" in statuses:
        return "fail"
    if statuses & {"warn", "unknown"}:
        return "warn"
    return "ok"


def build_control_plane_summary(
    *,
    probe_services: bool = True,
    detailed_org_status: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build normalized, real-data cards for `/api/v2/control-plane/summary`."""

    now = now or _now()
    x402_card, product_index = _x402_product_card(now)
    org_card = _detailed_org_status_card(now) if detailed_org_status else _fast_org_status_card(now)
    cards = [
        _dashboard_runtime_card(now),
        x402_card,
        _agentwiki_card(now),
        _x402_safety_card(now, product_index),
        _dashboard_surface_card(now),
        _control_plane_health_card(now, probe_services=probe_services),
        org_card,
    ]
    status = _overall_status(cards)
    return {
        "schema_version": 1,
        "status": status,
        "generated_at": _iso(now),
        "mode": "read_only",
        "summary": {
            "card_count": len(cards),
            "warn_count": sum(1 for card in cards if card["status"] == "warn"),
            "fail_count": sum(1 for card in cards if card["status"] == "fail"),
            "blocked_mode_count": sum(1 for card in cards if card["mode"] == "blocked"),
        },
        "safety": {
            "live_settlement_allowed": False,
            "real_trading_enabled": False,
            "telegram_sends_enabled": False,
            "production_mutation_enabled": False,
        },
        "modules": _module_rollup(cards),
        "cards": cards,
    }


__all__ = ["build_control_plane_summary"]
