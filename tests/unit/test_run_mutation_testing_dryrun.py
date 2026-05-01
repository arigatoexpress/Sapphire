"""Dry-run tests for the operator-supervised mutation testing wrapper.

We exercise the public ``scripts.ops.run_mutation_testing`` surface in dry-run
mode (default — no ``SAPPHIRE_MUTATION_TEST_LIVE`` flag), validating:

* Each curated module emits a build command.
* The Markdown summary is paste-safe (no PII, no $HOME, no secrets).
* The JSON sidecar conforms to the documented schema.
* The CLI argv plumbing routes flags correctly.
* A targeted ``--module`` flag narrows the run.
* Live runs without the gate flag stay in dry-run mode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops import run_mutation_testing  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ensure_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the live flag off; tests must never accidentally invoke mutmut."""
    monkeypatch.delenv(run_mutation_testing.LIVE_FLAG_ENV, raising=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dry_run_emits_command_for_every_target() -> None:
    """Every entry in MUTATION_TARGETS yields a non-empty command tuple."""
    results = run_mutation_testing.run_targets(live=False)
    assert len(results) == len(run_mutation_testing.MUTATION_TARGETS)
    for r in results:
        assert r.mode == "dry_run"
        assert r.command, "dry-run must still emit the planned command"
        assert "mutmut" in " ".join(r.command)
        assert "run" in r.command
        assert "--paths-to-mutate" in r.command


def test_dry_run_command_includes_every_test_path() -> None:
    """For each module, the command runner string must include each test path."""
    results = run_mutation_testing.run_targets(live=False)
    by_module = {r.module: r for r in results}
    for source, tests in run_mutation_testing.MUTATION_TARGETS:
        result = by_module[source]
        joined = " ".join(result.command)
        for test_path in tests:
            assert test_path in joined, f"command for {source!r} missing test path {test_path!r}"


def test_render_markdown_is_paste_safe(tmp_path: Path) -> None:
    """Markdown output must not include $HOME or test data paths."""
    results = run_mutation_testing.run_targets(live=False)
    md = run_mutation_testing.render_markdown(results, mode="dry_run")
    home = str(Path.home())
    assert home not in md, "$HOME path leaked into mutation report"
    assert "Sapphire mutation testing report" in md
    assert "operator-gated" in md.lower()


def test_write_report_emits_schema_v1_json(tmp_path: Path) -> None:
    """The JSON sidecar conforms to the documented schema_version=1 envelope."""
    results = run_mutation_testing.run_targets(live=False)
    path = run_mutation_testing.write_report(results, root=tmp_path, mode="dry_run")
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["mode"] == "dry_run"
    assert "generated_at" in payload
    assert isinstance(payload["modules"], list)
    assert len(payload["modules"]) == len(run_mutation_testing.MUTATION_TARGETS)
    for entry in payload["modules"]:
        assert {"module", "killed", "survived", "kill_rate"}.issubset(entry.keys())


def test_filter_targets_narrows_to_one_module() -> None:
    """``--module lib/...`` restricts the run to that single module."""
    targets = run_mutation_testing._filter_targets(["lib/correlator/scoring.py"])
    assert len(targets) == 1
    assert targets[0][0] == "lib/correlator/scoring.py"


def test_filter_targets_unknown_module_raises() -> None:
    """Asking for a module outside MUTATION_TARGETS must hard-fail."""
    with pytest.raises(SystemExit):
        run_mutation_testing._filter_targets(["lib/does/not/exist.py"])


def test_main_dry_run_prints_markdown_and_writes_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Calling ``main`` in dry-run mode prints Markdown + writes the JSON sidecar."""
    rc = run_mutation_testing.main(["--report-root", str(tmp_path)])
    assert rc == 0
    captured = capsys.readouterr().out
    assert "Sapphire mutation testing report" in captured
    # Sidecar exists and is valid JSON.
    files = list(tmp_path.glob("mutation_report_*.json"))
    assert len(files) == 1, f"expected 1 report file, got {files}"
    json.loads(files[0].read_text())


def test_main_print_only_skips_sidecar(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``--print-only`` keeps Markdown but does not write a JSON sidecar."""
    rc = run_mutation_testing.main(["--report-root", str(tmp_path), "--print-only"])
    assert rc == 0
    files = list(tmp_path.glob("mutation_report_*.json"))
    assert files == []


def test_live_flag_unset_stays_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even if ``run_targets(live=False)`` we never shell out to mutmut."""

    # Sentinel: replace _live_run with a function that raises if called.
    def _should_not_run(target):  # noqa: ANN001, ANN202
        raise AssertionError("Live mutation runner invoked without flag!")

    monkeypatch.setattr(run_mutation_testing, "_live_run", _should_not_run)
    results = run_mutation_testing.run_targets(live=False)
    # ``_live_run`` was never called, so we got dry-run results.
    assert all(r.mode == "dry_run" for r in results)


def test_parse_mutmut_results_handles_empty_output() -> None:
    """The parser must degrade gracefully on empty output (no summary line)."""
    out = run_mutation_testing._parse_mutmut_results("")
    assert out["killed"] == 0
    assert out["total"] == 0


def test_force_live_flag_takes_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--force-live`` flips the gate without setting the env var."""
    seen: list[bool] = []

    def _capture_live(target):  # noqa: ANN001, ANN202
        seen.append(True)
        return run_mutation_testing.ModuleResult(module=target[0], mode="live", command=("noop",))

    monkeypatch.setattr(run_mutation_testing, "_live_run", _capture_live)
    rc = run_mutation_testing.main(
        ["--print-only", "--force-live", "--module", "lib/correlator/scoring.py"]
    )
    # Live-run path returned no survivors → exit 0.
    assert rc == 0
    assert seen == [True]
