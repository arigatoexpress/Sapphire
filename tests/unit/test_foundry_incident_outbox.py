"""Golden evals for Foundry's local, content-addressed incident outbox."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lib.foundry.incidents import (
    FoundryIncidentError,
    FoundryIncidentOutbox,
    classify_failure,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "foundry_july20_403_sequence.json"
)


def _envelopes(root: Path) -> list[Path]:
    return sorted(path for path in root.glob("*.json") if path.name != "state.json")


def _assert_content_addressed(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    assert path.stem == hashlib.sha256(raw).hexdigest()
    assert raw.endswith(b"\n")
    return json.loads(raw)


def test_july20_seventeen_cycle_sequence_is_one_open_incident(tmp_path):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    outbox = FoundryIncidentOutbox(
        root=tmp_path / "outbox",
        config_generation="foundry-config-r1",
    )

    created = [
        outbox.observe_failure([fixture["error"]], observed_at=timestamp)
        for timestamp in fixture["timestamps"]
    ]

    assert sum(path is not None for path in created) == 1
    envelopes = _envelopes(outbox.root)
    assert len(envelopes) == 1
    opened = _assert_content_addressed(envelopes[0])
    assert opened == {
        "config_generation": "foundry-config-r1",
        "error_class": "foundry_auth_403",
        "event": "opened",
        "incident_id": opened["incident_id"],
        "observed_at": fixture["timestamps"][0],
        "schema_version": "sapphire.foundry_incident.v1",
        "subsystem": "foundry_sync",
    }
    assert opened["incident_id"] == hashlib.sha256(
        (
            '{"config_generation":"foundry-config-r1",'
            '"error_class":"foundry_auth_403",'
            '"schema_version":"sapphire.foundry_incident_identity.v1",'
            '"subsystem":"foundry_sync"}'
        ).encode()
    ).hexdigest()
    state = json.loads((outbox.root / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "open"
    assert state["occurrences"] == 17
    assert state["first_observed_at"] == fixture["timestamps"][0]
    assert state["last_observed_at"] == fixture["timestamps"][-1]


def test_recovery_is_one_separate_content_addressed_envelope(tmp_path):
    outbox = FoundryIncidentOutbox(
        root=tmp_path / "outbox",
        config_generation="foundry-config-r1",
    )
    outbox.observe_failure(
        ["Foundry API GET /api/v2/ontologies returned 403"],
        observed_at="2026-07-20T05:22:26.158678+00:00",
    )
    outbox.observe_failure(
        ["Foundry API GET /api/v2/ontologies returned 403"],
        observed_at="2026-07-20T05:37:27.644940+00:00",
    )

    recovered = outbox.observe_recovery(
        observed_at="2026-07-20T05:52:30.000000+00:00"
    )

    assert recovered is not None
    assert outbox.observe_recovery(
        observed_at="2026-07-20T06:07:30.000000+00:00"
    ) is None
    rows = [_assert_content_addressed(path) for path in _envelopes(outbox.root)]
    assert {row["event"] for row in rows} == {"opened", "recovered"}
    recovery = next(row for row in rows if row["event"] == "recovered")
    assert recovery["occurrences"] == 2
    assert recovery["incident_id"] == next(
        row["incident_id"] for row in rows if row["event"] == "opened"
    )
    state = json.loads((outbox.root / "state.json").read_text(encoding="utf-8"))
    assert state["status"] == "healthy"


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        ("request returned 401 unauthorized", "foundry_auth_401"),
        ("request returned 403 forbidden", "foundry_auth_403"),
        ("request returned 404 missing", "foundry_target_404"),
        ("TLS handshake operation timed out", "foundry_timeout"),
        ("nodename nor servname provided", "foundry_dns"),
        ("request returned 500 internal", "foundry_server_5xx"),
        ("transform failed", "foundry_other"),
    ),
)
def test_failure_classification_is_sanitized_and_bounded(error, expected):
    assert classify_failure([error]) == expected


def test_changed_configuration_generation_creates_a_distinct_incident(tmp_path):
    first = FoundryIncidentOutbox(
        root=tmp_path / "outbox",
        config_generation="config-r1",
    )
    second = FoundryIncidentOutbox(
        root=tmp_path / "outbox",
        config_generation="config-r2",
    )
    first_path = first.observe_failure(
        ["403 forbidden"], observed_at="2026-07-20T05:22:26+00:00"
    )
    second_path = second.observe_failure(
        ["403 forbidden"], observed_at="2026-07-20T05:37:27+00:00"
    )
    assert first_path is not None
    assert second_path is not None
    assert first_path != second_path
    assert len(_envelopes(first.root)) == 2


def test_outbox_refuses_nonprivate_directory_and_symlink_state(tmp_path):
    root = tmp_path / "outbox"
    root.mkdir(mode=0o755)
    with pytest.raises(FoundryIncidentError):
        FoundryIncidentOutbox(root=root, config_generation="config-r1")

    root.chmod(0o700)
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    (root / "state.json").symlink_to(target)
    outbox = FoundryIncidentOutbox(root=root, config_generation="config-r1")
    with pytest.raises(FoundryIncidentError):
        outbox.observe_failure(
            ["403 forbidden"], observed_at="2026-07-20T05:22:26+00:00"
        )


def test_foundry_runtime_contains_no_direct_message_transport():
    foundry_root = Path(__file__).resolve().parents[2] / "lib" / "foundry"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(foundry_root.glob("*.py"))
    )
    for forbidden in (
        "api.telegram.org",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "sapphire_telegram.safe_send",
        "_send_telegram_alert",
    ):
        assert forbidden not in source
