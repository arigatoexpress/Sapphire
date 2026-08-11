"""Windows private DC acceptance evaluation (pure)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

# Ordered P0 ladder from WINDOWS-DATACENTER-MASTERPLAN
P0_CHECKS = (
    ("post_boot_report", "WIN-POST-BOOT report exists with crash hypothesis"),
    ("tailscale_up", "Tailscale connected"),
    ("ssh_stable", "SSH BatchMode probe ok"),
    ("ollama_aliases", "Required inference-proxy aliases callable"),
    ("no_sleep", "Sleep/lock disabled for overnight"),
    ("free_reign_parity", "free-reign / dens / killswitch parity with Mac"),
    ("schtasks_inventory", "Scheduled tasks inventoried (not necessarily armed)"),
)

P1_CHECKS = (
    ("research_worker_smoke", "Research worker manual smoke produced paper_only manifest"),
    ("tv_agent_readonly", "TV agent read-only listening"),
    ("genome_seeded", "Genome lessons seeded (AXTI + dens)"),
)

# Point-in-time evidence must expire before it can authorize a worker arm. The
# slower-changing host configuration checks retain a longer window, while live
# connectivity and policy parity must be re-probed immediately before use.
P0_EVIDENCE_MAX_AGE_SECONDS = {
    "post_boot_report": 24 * 60 * 60,
    "tailscale_up": 5 * 60,
    "ssh_stable": 5 * 60,
    "ollama_aliases": 15 * 60,
    "no_sleep": 24 * 60 * 60,
    "free_reign_parity": 5 * 60,
    "schtasks_inventory": 60 * 60,
}

REQUIRED_WINDOWS_PROXY_ALIASES = frozenset(
    {
        "fast",
        "balanced",
        "code",
        "reason",
        "qwen-reason",
        "deep",
        "qwen3.6",
        "large",
    }
)


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _p0_evidence_reason(
    key: str,
    *,
    raw_ok: bool,
    evidence: Mapping[str, Any] | None,
    receipt_boot_id: str | None,
    current_boot_id: str | None,
    now: datetime,
) -> str | None:
    if not raw_ok:
        return "state_false"
    if not receipt_boot_id or not current_boot_id:
        return "boot_identity_unverified"
    if receipt_boot_id != current_boot_id:
        return "boot_mismatch"
    if not isinstance(evidence, Mapping):
        return "missing_evidence"
    if evidence.get("status") != "pass":
        return "evidence_not_pass"

    observed_at = _parse_timestamp(evidence.get("observed_at"))
    if observed_at is None:
        return "invalid_evidence_timestamp"
    age_seconds = (now - observed_at).total_seconds()
    if age_seconds < -60:
        return "future_evidence"
    if age_seconds > P0_EVIDENCE_MAX_AGE_SECONDS[key]:
        return "stale_evidence"

    if key == "ollama_aliases":
        passed_aliases = evidence.get("passed_aliases")
        passed = (
            {item for item in passed_aliases if isinstance(item, str)}
            if isinstance(passed_aliases, list)
            else set()
        )
        has_live_proxy_probe = evidence.get("probe") == "inference_proxy_alias_calls"
        has_every_required_alias = REQUIRED_WINDOWS_PROXY_ALIASES.issubset(passed)
        if not has_live_proxy_probe or not has_every_required_alias:
            return "proxy_alias_unverified"
    return None


def evaluate_windows_acceptance(
    state: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any] | None = None,
    receipt_boot_id: str | None = None,
    current_boot_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate state plus fresh, boot-bound evidence.

    Missing state, evidence, or a live current-boot identity counts as fail.
    This keeps persisted snapshots useful for diagnostics without turning them
    into evergreen worker-arm authority.
    """
    evaluated_at = now or datetime.now(UTC)
    if evaluated_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    evaluated_at = evaluated_at.astimezone(UTC)

    p0_results = []
    for key, label in P0_CHECKS:
        raw_ok = bool(state.get(key))
        item_evidence = evidence.get(key) if isinstance(evidence, Mapping) else None
        reason = _p0_evidence_reason(
            key,
            raw_ok=raw_ok,
            evidence=item_evidence if isinstance(item_evidence, Mapping) else None,
            receipt_boot_id=receipt_boot_id,
            current_boot_id=current_boot_id,
            now=evaluated_at,
        )
        p0_results.append(
            {
                "id": key,
                "label": label,
                "ok": reason is None,
                "raw_ok": raw_ok,
                "reason": reason,
            }
        )
    p1_results = []
    for key, label in P1_CHECKS:
        ok = bool(state.get(key))
        p1_results.append({"id": key, "label": label, "ok": ok})

    p0_ok = all(x["ok"] for x in p0_results)
    p1_ok = all(x["ok"] for x in p1_results)
    arm_allowed = p0_ok  # never ARM L2 workers before P0 green

    return {
        "p0_ok": p0_ok,
        "p1_ok": p1_ok,
        "arm_l2_allowed": arm_allowed,
        "p0": p0_results,
        "p1": p1_results,
        "failed_p0": [x["id"] for x in p0_results if not x["ok"]],
        "failed_p1": [x["id"] for x in p1_results if not x["ok"]],
    }


def evaluate_windows_acceptance_receipt(
    receipt: Mapping[str, Any],
    *,
    current_boot_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a persisted acceptance receipt without granting stale authority."""
    state = receipt.get("state")
    evidence = receipt.get("evidence")
    source = receipt.get("source")
    return evaluate_windows_acceptance(
        state if isinstance(state, Mapping) else {},
        evidence=evidence if isinstance(evidence, Mapping) else None,
        receipt_boot_id=(
            str(source.get("boot_id"))
            if isinstance(source, Mapping) and source.get("boot_id")
            else None
        ),
        current_boot_id=current_boot_id,
        now=now,
    )
