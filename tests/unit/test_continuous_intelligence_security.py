"""Security-guard coverage for ``continuous_intelligence_artifacts``.

The module exposes a record-of-result endpoint that accepts agent-supplied
result and artifact payloads. ``_assert_no_sensitive_keys`` is the
in-process guard that prevents secrets from being persisted to the
JSONL audit log. This file pins down its behaviour, the surrounding
``record_task_result`` flow, and the small validation helpers that the
lease/snapshot path relies on.
"""

from __future__ import annotations

import json

import pytest

from lib.autonomy import continuous_intelligence_artifacts as artifacts

# ── _assert_no_sensitive_keys ─────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"id": "task-1", "name": "ok", "value": 42, "metadata": {"safe": True}},
        ["one", "two", {"id": 3}],
        "scalar string",
        42,
        None,
    ],
)
def test_assert_no_sensitive_keys_accepts_safe_payloads(payload) -> None:
    artifacts._assert_no_sensitive_keys(payload)


@pytest.mark.parametrize(
    "key",
    [
        "secret",
        "SECRET",
        "Secret",
        "client_secret",
        "token",
        "access_token",
        "auth_token",
        "password",
        "user_password",
        "private_key",
        "private-key",
        "privateKey",  # camelCase still matches `private_key|private-key|privatekey`-loose? Actually no — regex is on substring. Verified below.
        "api_key",
        "api-key",
        "apikey",
        "seed",
        "seed_phrase",
        "mnemonic",
        "credential",
        "credentials",
    ],
)
def test_assert_no_sensitive_keys_rejects_top_level(key) -> None:
    with pytest.raises(ValueError, match="sensitive result key rejected"):
        artifacts._assert_no_sensitive_keys({key: "x"})


def test_assert_no_sensitive_keys_rejects_nested_in_dict() -> None:
    payload = {"outer": {"inner": {"secret": "x"}}}

    with pytest.raises(ValueError, match=r"result\.outer\.inner\.secret"):
        artifacts._assert_no_sensitive_keys(payload)


def test_assert_no_sensitive_keys_rejects_nested_in_list() -> None:
    payload = {"items": [{"id": 1}, {"id": 2, "api_key": "leak"}]}

    with pytest.raises(ValueError, match=r"result\.items\[1\]\.api_key"):
        artifacts._assert_no_sensitive_keys(payload)


def test_assert_no_sensitive_keys_uses_custom_root_path() -> None:
    with pytest.raises(ValueError, match=r"artifacts\[0\]\.token"):
        artifacts._assert_no_sensitive_keys([{"token": "x"}], path="artifacts")


def test_assert_no_sensitive_keys_substring_match() -> None:
    """Regex is a substring search — 'secret_url' is still rejected."""
    with pytest.raises(ValueError):
        artifacts._assert_no_sensitive_keys({"secret_url": "https://"})


def test_assert_no_sensitive_keys_tokenizer_is_actually_rejected() -> None:
    """The substring guard is strict by design — anything containing 'token'
    (including ``tokenizer``, ``tokenizer_config``) gets caught.

    Pins the current behaviour so future relaxation is a deliberate choice
    rather than a silent drift.
    """
    with pytest.raises(ValueError, match="token"):
        artifacts._assert_no_sensitive_keys({"tokenizer": "ok"})
    with pytest.raises(ValueError, match="token"):
        artifacts._assert_no_sensitive_keys({"tokenizer_config": "ok"})


def test_assert_no_sensitive_keys_clean_keys_pass() -> None:
    artifacts._assert_no_sensitive_keys(
        {
            "section": "ok",
            "id": "x",
            "value": 1,
            "metadata": {"label": "y"},
            "items": [1, 2, 3],
        }
    )


# ── record_task_result ────────────────────────────────────────────────


def test_record_task_result_rejects_invalid_status() -> None:
    with pytest.raises(ValueError, match="status must be one of"):
        artifacts.record_task_result(
            task_id="t-1",
            agent_id="agent-1",
            status="bogus",
        )


def test_record_task_result_rejects_secret_in_result(tmp_path) -> None:
    with pytest.raises(ValueError, match="sensitive result key"):
        artifacts.record_task_result(
            task_id="t-1",
            agent_id="agent-1",
            status="completed",
            result={"output": "ok", "api_key": "AKIA..."},
            artifact_dir=tmp_path,
            write=False,
        )


def test_record_task_result_rejects_secret_in_artifacts(tmp_path) -> None:
    with pytest.raises(ValueError, match=r"artifacts\[0\]\.password"):
        artifacts.record_task_result(
            task_id="t-1",
            agent_id="agent-1",
            status="completed",
            artifacts=[{"path": "/tmp/x", "password": "leak"}],
            artifact_dir=tmp_path,
            write=False,
        )


def test_record_task_result_dry_run_does_not_write(tmp_path) -> None:
    response = artifacts.record_task_result(
        task_id="t-1",
        agent_id="agent-1",
        status="completed",
        result={"output": "ok"},
        artifact_dir=tmp_path,
        write=False,
    )

    assert response["mode"] == "task_result_record"
    assert response["write_enabled"] is False
    assert response["writes_by_default"] is False
    assert response["record"]["status"] == "completed"
    assert response["record"]["safety"]["operator_review_required"] is True
    assert not (tmp_path / artifacts.RESULT_FILE).exists()


def test_record_task_result_write_appends_jsonl(tmp_path) -> None:
    response = artifacts.record_task_result(
        task_id="t-1",
        agent_id="agent-1",
        status="completed",
        result={"output": "ok"},
        artifact_dir=tmp_path,
        write=True,
    )

    assert response["write_enabled"] is True
    target = tmp_path / artifacts.RESULT_FILE
    assert target.exists()
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["task_id"] == "t-1"
    assert rows[0]["status"] == "completed"

    # A second call appends rather than overwrites.
    artifacts.record_task_result(
        task_id="t-2",
        agent_id="agent-1",
        status="failed",
        artifact_dir=tmp_path,
        write=True,
    )
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert [r["task_id"] for r in rows] == ["t-1", "t-2"]
    assert rows[1]["safety"]["operator_review_required"] is False


@pytest.mark.parametrize(
    "status,review_required",
    [
        ("completed", True),
        ("needs_review", True),
        ("failed", False),
        ("blocked", False),
        ("rejected", False),
    ],
)
def test_record_task_result_operator_review_flag(tmp_path, status, review_required) -> None:
    response = artifacts.record_task_result(
        task_id="t",
        agent_id="a",
        status=status,
        artifact_dir=tmp_path,
        write=False,
    )

    assert response["record"]["safety"]["operator_review_required"] is review_required


def test_record_task_result_normalizes_task_and_agent_id(tmp_path) -> None:
    response = artifacts.record_task_result(
        task_id="task with spaces!@#",
        agent_id="agent/path/with/slashes",
        status="completed",
        artifact_dir=tmp_path,
        write=False,
    )

    # Sanitization should land within the safe-token charset and not be empty.
    assert response["record"]["task_id"]
    assert response["record"]["agent_id"]
    assert " " not in response["record"]["task_id"]
    assert "/" not in response["record"]["agent_id"]


def test_record_task_result_default_task_and_agent_for_blanks(tmp_path) -> None:
    response = artifacts.record_task_result(
        task_id="",
        agent_id="",
        status="completed",
        artifact_dir=tmp_path,
        write=False,
    )

    assert response["record"]["task_id"] == "task"
    assert response["record"]["agent_id"] == "agent"


# ── _validate_task ────────────────────────────────────────────────────


def test_validate_task_requires_id() -> None:
    with pytest.raises(ValueError, match="task is missing id"):
        artifacts._validate_task({"safe_mode": "read_only"})


def test_validate_task_rejects_unsafe_mode() -> None:
    with pytest.raises(ValueError, match="unsafe task mode"):
        artifacts._validate_task({"id": "t-1", "safe_mode": "live"})


@pytest.mark.parametrize("mode", sorted(artifacts.SAFE_MODES))
def test_validate_task_accepts_safe_modes(mode) -> None:
    artifacts._validate_task({"id": "t-1", "safe_mode": mode})


def test_validate_task_missing_safe_mode_rejected() -> None:
    """Empty-string safe_mode must fail closed."""
    with pytest.raises(ValueError, match="unsafe task mode"):
        artifacts._validate_task({"id": "t-1"})


# ── _safe_token ──────────────────────────────────────────────────────


def test_safe_token_strips_unsafe_chars() -> None:
    assert artifacts._safe_token("hello world!@#") == "hello-world"


def test_safe_token_caps_at_96_chars() -> None:
    long = "a" * 200
    assert len(artifacts._safe_token(long)) == 96


def test_safe_token_falls_back_to_default() -> None:
    assert artifacts._safe_token("") == "item"
    assert artifacts._safe_token("   ") == "item"
    assert artifacts._safe_token("!!!") == "item"
    assert artifacts._safe_token("", default="custom") == "custom"


# ── _jsonl_rows ──────────────────────────────────────────────────────


def test_jsonl_rows_returns_empty_when_file_missing(tmp_path) -> None:
    assert artifacts._jsonl_rows(tmp_path / "nope.jsonl") == []


def test_jsonl_rows_skips_blank_and_malformed_lines(tmp_path) -> None:
    target = tmp_path / "log.jsonl"
    target.write_text(
        json.dumps({"id": "ok-1"})
        + "\n\n   \n"
        + "not-json\n"
        + json.dumps({"id": "ok-2"})
        + "\n"
        + json.dumps([1, 2, 3])  # list, not dict — must be skipped
        + "\n"
    )

    rows = artifacts._jsonl_rows(target)

    assert [row["id"] for row in rows] == ["ok-1", "ok-2"]


# ── lease_tasks edge cases ───────────────────────────────────────────


def _stub_plan(*tasks: dict) -> dict:
    return {
        "generated_at": "2026-04-27T19:00:00Z",
        "totals": {"tasks": len(tasks)},
        "tasks": list(tasks),
    }


def _safe_task(**overrides) -> dict:
    base = {
        "id": "t-1",
        "lane": "thesis",
        "priority": "P1",
        "target_runtime": "windows-gpu",
        "safe_mode": "read_only",
    }
    base.update(overrides)
    return base


def test_lease_tasks_empty_plan_returns_no_leases(tmp_path) -> None:
    response = artifacts.lease_tasks(
        _stub_plan(),
        agent_id="a",
        artifact_dir=tmp_path,
        write=False,
    )

    assert response["candidate_count"] == 0
    assert response["leased_count"] == 0
    assert response["leases"] == []


def test_lease_tasks_excludes_blocked_tasks(tmp_path) -> None:
    response = artifacts.lease_tasks(
        _stub_plan(
            _safe_task(id="t-1"),
            _safe_task(id="t-2", blocked_by=["dep-x"]),
        ),
        agent_id="a",
        artifact_dir=tmp_path,
        write=False,
    )

    leased_ids = [lease["task_id"] for lease in response["leases"]]
    assert leased_ids == ["t-1"]


def test_lease_tasks_filters_by_target_runtime(tmp_path) -> None:
    response = artifacts.lease_tasks(
        _stub_plan(
            _safe_task(id="t-1", target_runtime="windows-gpu"),
            _safe_task(id="t-2", target_runtime="mac-cpu"),
        ),
        agent_id="a",
        target_runtime="mac-cpu",
        artifact_dir=tmp_path,
        write=False,
    )

    assert [lease["task_id"] for lease in response["leases"]] == ["t-2"]


def test_lease_tasks_filters_by_capability(tmp_path) -> None:
    """Capability filter intersects with task lane/runtime/safe_mode/inputs/symbols."""
    response = artifacts.lease_tasks(
        _stub_plan(
            _safe_task(id="t-1", lane="thesis"),
            _safe_task(id="t-2", lane="research"),
        ),
        agent_id="a",
        capabilities=["thesis"],
        artifact_dir=tmp_path,
        write=False,
    )

    assert [lease["task_id"] for lease in response["leases"]] == ["t-1"]


def test_lease_tasks_clamps_limit(tmp_path) -> None:
    plan = _stub_plan(*[_safe_task(id=f"t-{i}", lane=f"lane-{i:02d}") for i in range(50)])

    too_high = artifacts.lease_tasks(
        plan, agent_id="a", limit=999, artifact_dir=tmp_path, write=False
    )
    too_low = artifacts.lease_tasks(plan, agent_id="a", limit=0, artifact_dir=tmp_path, write=False)

    assert too_high["leased_count"] == 20  # max
    assert too_low["leased_count"] == 1  # min


def test_lease_tasks_orders_by_priority_then_lane_then_id(tmp_path) -> None:
    plan = _stub_plan(
        _safe_task(id="t-c", priority="P3", lane="zeta"),
        _safe_task(id="t-a", priority="P1", lane="alpha"),
        _safe_task(id="t-b", priority="P2", lane="beta"),
        _safe_task(id="t-aa", priority="P1", lane="alpha"),
    )

    response = artifacts.lease_tasks(
        plan, agent_id="a", limit=10, artifact_dir=tmp_path, write=False
    )

    leased_ids = [lease["task_id"] for lease in response["leases"]]
    assert leased_ids == ["t-a", "t-aa", "t-b", "t-c"]


def test_lease_tasks_dry_run_does_not_write(tmp_path) -> None:
    artifacts.lease_tasks(
        _stub_plan(_safe_task()),
        agent_id="a",
        artifact_dir=tmp_path,
        write=False,
    )

    assert not (tmp_path / artifacts.LEASE_FILE).exists()


def test_lease_tasks_write_creates_jsonl(tmp_path) -> None:
    response = artifacts.lease_tasks(
        _stub_plan(_safe_task()),
        agent_id="windows-gpu",
        artifact_dir=tmp_path,
        write=True,
    )

    target = tmp_path / artifacts.LEASE_FILE
    assert target.exists()
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert rows[0]["agent_id"] == "windows-gpu"
    assert rows[0]["safety"]["execution_enabled"] is False
    assert rows[0]["safety"]["live_trading_enabled"] is False
    assert rows[0]["safety"]["telegram_sends_enabled"] is False
    assert response["leased_count"] == 1


def test_lease_tasks_lease_seconds_clamped(tmp_path) -> None:
    """Leases bounded to 60s..24h. lease_seconds=0 falls through to the
    default (1800) via ``int(lease_seconds or 1800)`` — explicitly small
    positive values get clamped UP to 60."""
    fell_through = artifacts.lease_tasks(
        _stub_plan(_safe_task()),
        agent_id="a",
        lease_seconds=0,
        artifact_dir=tmp_path,
        write=False,
    )
    too_short = artifacts.lease_tasks(
        _stub_plan(_safe_task()),
        agent_id="a",
        lease_seconds=10,  # explicit positive but below the 60s floor
        artifact_dir=tmp_path,
        write=False,
    )
    too_long = artifacts.lease_tasks(
        _stub_plan(_safe_task()),
        agent_id="a",
        lease_seconds=100_000,
        artifact_dir=tmp_path,
        write=False,
    )

    assert fell_through["lease_seconds"] == 1800  # default
    assert too_short["lease_seconds"] == 60  # floor
    assert too_long["lease_seconds"] == 24 * 3600  # ceiling


# ── artifact_status ──────────────────────────────────────────────────


def test_artifact_status_empty_directory(tmp_path) -> None:
    status = artifacts.artifact_status(artifact_dir=tmp_path)

    assert status["mode"] == "continuous_intelligence_artifact_status"
    for key in ("task_snapshots", "task_leases", "task_results"):
        assert status["files"][key]["exists"] is False
        assert status["files"][key]["rows"] == 0


def test_artifact_status_reports_existing_rows(tmp_path) -> None:
    snapshot_path = tmp_path / artifacts.TASK_SNAPSHOT_FILE
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps({"task_id": "t-1"}) + "\n" + json.dumps({"task_id": "t-2"}) + "\n"
    )

    status = artifacts.artifact_status(artifact_dir=tmp_path)

    assert status["files"]["task_snapshots"]["exists"] is True
    assert status["files"]["task_snapshots"]["rows"] == 2
