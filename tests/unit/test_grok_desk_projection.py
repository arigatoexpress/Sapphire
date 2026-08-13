from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.grok.desk_projection import build_desk_projection, markets_pulse, publisher_checklist
from lib.grok.windows import P0_CHECKS, REQUIRED_WINDOWS_PROXY_ALIASES


def _green_windows_acceptance() -> tuple[
    dict[str, object], dict[str, bool], dict[str, object], str
]:
    now = datetime.now(UTC)
    boot_started = now - timedelta(minutes=10)
    boot_id = f"DESKTOP-HFCK6U9@{boot_started.isoformat().replace('+00:00', 'Z')}"
    observed_at = (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    state = {key: True for key, _label in P0_CHECKS}
    evidence: dict[str, object] = {
        key: {"status": "pass", "observed_at": observed_at, "boot_id": boot_id}
        for key, _label in P0_CHECKS
    }
    evidence["ollama_aliases"] = {
        "status": "pass",
        "observed_at": observed_at,
        "boot_id": boot_id,
        "probe": "inference_proxy_alias_calls",
        "passed_aliases": sorted(REQUIRED_WINDOWS_PROXY_ALIASES),
    }
    receipt: dict[str, object] = {
        "state": state,
        "evidence": evidence,
        "source": {"boot_id": boot_id},
    }
    return receipt, state, evidence, boot_id


def test_desk_has_fresh_updated_at_and_no_wallet_keys():
    d = build_desk_projection(thesis="late cycle preservation", regime_label="mean_reverting")
    assert d["version"] == 1
    assert d["updated_at"]
    assert d["posture"] == "capital_preservation"
    assert d["epistemics"]["fresh"] is True
    # no wallet/balance keys in risk or top-level capital fields
    assert "wallet" not in d
    assert "balance" not in d
    assert "balance" not in d.get("risk", {})
    assert "realized_pnl_usd" not in d.get("epistemics", {}).get("learning", {})


def test_desk_projection_accepts_trusted_live_boot_for_receipt():
    receipt, _state, _evidence, boot_id = _green_windows_acceptance()

    without_live_boot = build_desk_projection(win_state=receipt)
    with_live_boot = build_desk_projection(
        win_state=receipt,
        win_current_boot_id=boot_id,
    )

    assert without_live_boot["autonomy"]["windows_arm_l2_allowed"] is False
    assert with_live_boot["autonomy"]["windows_arm_l2_allowed"] is True


def test_desk_projection_forwards_legacy_live_acceptance_evidence():
    _receipt, state, evidence, boot_id = _green_windows_acceptance()

    desk = build_desk_projection(
        win_state=state,
        win_evidence=evidence,
        win_receipt_boot_id=boot_id,
        win_current_boot_id=boot_id,
    )

    assert desk["autonomy"]["windows_arm_l2_allowed"] is True


def test_markets_pulse_unknown_safe():
    m = markets_pulse(events_per_min=100.0, feed_age_s=30.0, decision_gate="manual")
    assert m["status"] == "current"
    assert m["decision_gate"] == "manual"


def test_checklist_nonempty():
    assert len(publisher_checklist()) >= 5
