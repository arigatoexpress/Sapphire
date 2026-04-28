"""Red-team corpus driver.

Loads adversarial probes from tests/fixtures/redteam/*.json and asserts the
sensitivity classifier + model-monitor scanner behave as declared. Probes
marked `"xfail": true` are expected to fail with the current code — fixing
them is the point of the red-team engagement. When a probe starts passing,
flip its JSON entry to `"xfail": false` to lock the fix in as a regression.

Run:
    pytest tests/unit/test_redteam_corpus.py -v

Add a probe: edit the JSON and restart pytest. See
tests/fixtures/redteam/README.md for the expected schema.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "redteam"

# Add plugin lib to path so we can import the classifier directly.
sys.path.insert(0, str(ROOT / "plugins" / "claw-sapphire" / "lib"))
sys.path.insert(0, str(ROOT))

from sensitivity_classifier import classify  # noqa: E402

from lib.security.model_monitor import BACKDOOR_PATTERNS  # noqa: E402

# ---------------------------------------------------------------------------
# Sensitivity classifier probes
# ---------------------------------------------------------------------------


def _load_probes(filename: str) -> list[dict]:
    path = FIXTURES / filename
    if not path.exists():
        return []
    return json.loads(path.read_text())


@pytest.mark.parametrize(
    "probe",
    _load_probes("sensitivity_classifier_probes.json"),
    ids=lambda p: p["id"],
)
def test_classifier(probe: dict) -> None:
    """Each probe: classifier's verdict must match `expected`."""
    if probe.get("xfail"):
        pytest.xfail(f"Known-unfixed bypass ({probe.get('category', 'uncategorized')})")

    result = classify(probe["input"])
    want_sensitive = probe["expected"] == "sensitive"
    assert result.sensitive == want_sensitive, (
        f"{probe['id']}: expected {probe['expected']!r}, got "
        f"{'sensitive' if result.sensitive else 'safe'} "
        f"(reason={result.reason!r})"
    )


# ---------------------------------------------------------------------------
# Model-monitor template probes
# ---------------------------------------------------------------------------


def _match_any_backdoor_pattern(template: str) -> list[str]:
    """Return the names of every BACKDOOR_PATTERNS entry that fires on `template`."""
    hits = []
    for p in BACKDOOR_PATTERNS:
        if re.search(p["pattern"], template):
            hits.append(p["name"])
    return hits


@pytest.mark.parametrize(
    "probe",
    _load_probes("model_monitor_probes.json"),
    ids=lambda p: p["id"],
)
def test_model_monitor(probe: dict) -> None:
    """Each probe: scanner must fire (or not) the expected pattern."""
    if probe.get("xfail"):
        pytest.xfail(f"Known-unfixed scanner gap ({probe.get('category', 'uncategorized')})")

    hits = _match_any_backdoor_pattern(probe["template"])
    expected = probe["expected_pattern"]

    if expected is None:
        # Negative probe: nothing should fire.
        assert hits == [], f"{probe['id']}: benign template unexpectedly triggered {hits!r}"
    else:
        assert expected in hits, (
            f"{probe['id']}: expected pattern {expected!r} to fire, " f"got hits={hits!r}"
        )
