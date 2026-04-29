"""Property-based tests for ``lib.correlator.scoring``.

The correlator emits a single ``edge_score`` in ``[-1, +1]`` from N
heterogeneous source signals. The downstream consumers (sizing, kill-switch
gating) treat the score as a probability-like number, so any output outside
the documented range is a hard contract violation. The properties below
assert:

* **Bound**: ``-1 <= edge_score <= +1`` for every input shape.
* **Monotone agreement**: adding a corroborating bull source never decreases
  the bull edge_score.
* **Monotone freshness decay**: ``freshness_factor`` is non-increasing in age.
* **Determinism**: same dict + same weights yield byte-identical output.
* **Symmetry**: flipping every direction flips the sign of the edge_score.
* **Contradiction dampening**: a single bull + single bear contributes a
  smaller-magnitude edge_score than the same bull alone.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tests.property  # noqa: E402, F401
from lib.correlator.scoring import (  # noqa: E402
    DEFAULT_SOURCE_WEIGHTS,
    ScoringWeights,
    compose_score,
    freshness_factor,
    normalize_direction,
)

# ---------------------------------------------------------------------------
# Strategy helpers — synthesize inputs that compose_score actually consumes.
# ---------------------------------------------------------------------------

_KNOWN_SOURCES = list(DEFAULT_SOURCE_WEIGHTS.keys())

_directions = st.sampled_from(["bull", "bear", "neutral"])
_confidence = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_age_seconds = st.floats(
    min_value=0.0, max_value=86_400 * 7, allow_nan=False, allow_infinity=False
)


@st.composite
def signal_dicts(draw: st.DrawFn) -> dict[str, dict]:
    """Synthesize a {source: {direction, confidence, age_seconds}} mapping.

    Forced to use known sources only — unknown source names always score 0
    and dilute the test surface.
    """
    sources = draw(
        st.lists(
            st.sampled_from(_KNOWN_SOURCES),
            min_size=1,
            max_size=len(_KNOWN_SOURCES),
            unique=True,
        )
    )
    out: dict[str, dict] = {}
    for source in sources:
        out[source] = {
            "direction": draw(_directions),
            "confidence": draw(_confidence),
            "age_seconds": draw(_age_seconds),
        }
    return out


# ---------------------------------------------------------------------------
# 1. Bound — edge_score always within [-1, +1]
# ---------------------------------------------------------------------------


@given(signal_dicts())
def test_edge_score_within_unit_interval(payload: dict[str, dict]) -> None:
    score = compose_score(payload)
    assert -1.0 <= score.edge_score <= 1.0, (
        f"edge_score {score.edge_score} outside [-1, +1] for {payload!r}"
    )


@given(signal_dicts())
def test_raw_score_within_unit_interval(payload: dict[str, dict]) -> None:
    """Raw score (before agreement/contradict adjustments) is also in [-1, +1]."""
    score = compose_score(payload)
    assert -1.0 <= score.raw_score <= 1.0


# ---------------------------------------------------------------------------
# 2. Determinism — same input → same output, byte for byte
# ---------------------------------------------------------------------------


@given(signal_dicts())
def test_compose_score_deterministic(payload: dict[str, dict]) -> None:
    a = compose_score(payload)
    b = compose_score(payload)
    assert a == b


# ---------------------------------------------------------------------------
# 3. Symmetry — flipping every direction flips the score's sign
# ---------------------------------------------------------------------------


@given(signal_dicts())
def test_direction_flip_symmetry(payload: dict[str, dict]) -> None:
    flip_map = {"bull": "bear", "bear": "bull", "neutral": "neutral"}
    flipped = {
        src: {**sig, "direction": flip_map[sig["direction"]]}
        for src, sig in payload.items()
    }
    a = compose_score(payload)
    b = compose_score(flipped)
    # The magnitudes must be equal, and signs opposite (modulo zero).
    assert math.isclose(abs(a.edge_score), abs(b.edge_score), abs_tol=1e-9)
    if a.edge_score != 0.0:
        assert (a.edge_score > 0) != (b.edge_score > 0)


# ---------------------------------------------------------------------------
# 4. Monotonicity — agreement bonus is non-decreasing in num corroborating
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.sampled_from(_KNOWN_SOURCES),
        min_size=2,
        max_size=len(_KNOWN_SOURCES),
        unique=True,
    ),
    _confidence,
)
def test_agreement_bonus_monotone(sources: list[str], confidence: float) -> None:
    """For all-bull payloads, adding a corroborating source must not decrease the score."""
    if confidence == 0:
        # All-zero confidence means the score collapses to zero regardless.
        return
    base_signal = {"direction": "bull", "confidence": confidence, "age_seconds": 0.0}
    one_source = {sources[0]: base_signal}
    two_sources = {sources[0]: base_signal, sources[1]: base_signal}

    score_one = compose_score(one_source)
    score_two = compose_score(two_sources)
    assert score_two.edge_score >= score_one.edge_score - 1e-9, (
        f"two-source score {score_two.edge_score} regressed below one-source "
        f"{score_one.edge_score}"
    )


@given(
    st.lists(
        st.sampled_from(_KNOWN_SOURCES),
        min_size=3,
        max_size=len(_KNOWN_SOURCES),
        unique=True,
    ),
)
def test_agreement_multiplier_monotone_in_count(sources: list[str]) -> None:
    """``agreement_multiplier`` must be non-decreasing as we add corroborating sources."""
    base_signal = {"direction": "bull", "confidence": 0.8, "age_seconds": 0.0}
    payloads = [
        {src: base_signal for src in sources[: i + 1]}
        for i in range(len(sources))
    ]
    multipliers = [compose_score(p).agreement_multiplier for p in payloads]
    for prev, curr in zip(multipliers, multipliers[1:]):
        assert curr >= prev - 1e-9


# ---------------------------------------------------------------------------
# 5. Freshness decay — older signals never weigh more than fresher ones
# ---------------------------------------------------------------------------


@given(
    st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=86_400, allow_nan=False, allow_infinity=False),
)
def test_freshness_factor_monotone_decreasing(
    a_age: float, b_age: float, half_life: float
) -> None:
    if a_age <= b_age:
        younger, older = a_age, b_age
    else:
        younger, older = b_age, a_age
    fa = freshness_factor(younger, half_life)
    fb = freshness_factor(older, half_life)
    assert fa >= fb - 1e-12, f"younger {younger}s decayed below older {older}s"


@given(
    st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False),
    st.floats(min_value=1.0, max_value=86_400, allow_nan=False, allow_infinity=False),
)
def test_freshness_factor_bounded_below_zero(
    age: float, half_life: float
) -> None:
    """Freshness factor is bounded in [0, 1] — never negative, never > 1."""
    f = freshness_factor(age, half_life)
    assert 0.0 <= f <= 1.0


# ---------------------------------------------------------------------------
# 6. Confidence monotonicity — increasing confidence on a bull source
#    must not decrease the bull edge_score (single-source case is the
#    cleanest pin; multi-source has interactions with contradict factor).
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(_KNOWN_SOURCES),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_confidence_monotone_for_single_bull_source(
    source: str, c1: float, c2: float
) -> None:
    if c1 > c2:
        c1, c2 = c2, c1  # ensure c1 <= c2
    a = compose_score(
        {source: {"direction": "bull", "confidence": c1, "age_seconds": 0.0}}
    )
    b = compose_score(
        {source: {"direction": "bull", "confidence": c2, "age_seconds": 0.0}}
    )
    assert b.edge_score >= a.edge_score - 1e-9


# ---------------------------------------------------------------------------
# 7. Contradiction penalty — single bull + single bear has lower magnitude
#    than the same bull alone (when contradict_penalty < 1).
# ---------------------------------------------------------------------------


@given(
    st.sampled_from(_KNOWN_SOURCES),
    st.sampled_from(_KNOWN_SOURCES),
)
def test_contradiction_dampens_score(bull_src: str, bear_src: str) -> None:
    if bull_src == bear_src:
        return
    bull_only = {
        bull_src: {"direction": "bull", "confidence": 0.9, "age_seconds": 0.0}
    }
    contradicted = {
        bull_src: {"direction": "bull", "confidence": 0.9, "age_seconds": 0.0},
        bear_src: {"direction": "bear", "confidence": 0.9, "age_seconds": 0.0},
    }
    a = compose_score(bull_only)
    b = compose_score(contradicted)
    # Contradicted score must have smaller absolute magnitude (or equal,
    # if the bear weight collapses raw to zero).
    assert abs(b.edge_score) <= abs(a.edge_score) + 1e-9


# ---------------------------------------------------------------------------
# 8. Empty / unknown-source inputs — score collapses to 0
# ---------------------------------------------------------------------------


@given(st.dictionaries(st.text(min_size=1, max_size=12), st.dictionaries(st.text(), st.integers())))
def test_unknown_sources_score_zero(payload: dict[str, dict]) -> None:
    """Sources not in the weight table contribute zero."""
    # Override: only keep sources NOT in the known list.
    filtered = {k: v for k, v in payload.items() if k not in _KNOWN_SOURCES}
    score = compose_score(filtered)
    assert score.edge_score == 0.0
    assert score.raw_score == 0.0


# ---------------------------------------------------------------------------
# 9. Direction normalization — every alias maps to {-1, 0, +1}
# ---------------------------------------------------------------------------


@given(
    st.one_of(
        st.sampled_from(["bull", "bullish", "long", "buy", "up", "+", "1"]),
        st.sampled_from(["bear", "bearish", "short", "sell", "down", "-", "-1"]),
        st.sampled_from(["neutral", "flat", "hold", "0", ""]),
        st.text(min_size=0, max_size=8),
        st.integers(min_value=-100, max_value=100),
        st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        st.none(),
        st.booleans(),
    )
)
def test_normalize_direction_returns_canonical(value) -> None:  # type: ignore[no-untyped-def]
    out = normalize_direction(value)
    assert out in (-1, 0, 1)


# ---------------------------------------------------------------------------
# 10. Custom weights — score still bounded when weights are uniformly scaled
# ---------------------------------------------------------------------------


@given(
    signal_dicts(),
    st.floats(min_value=0.01, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_score_bound_under_weight_scaling(payload: dict[str, dict], scale: float) -> None:
    weights = ScoringWeights(
        source_weights={k: v * scale for k, v in DEFAULT_SOURCE_WEIGHTS.items()}
    )
    score = compose_score(payload, weights)
    assert -1.0 <= score.edge_score <= 1.0


# ---------------------------------------------------------------------------
# 11. Score bounds preserved under all valid weight knobs
# ---------------------------------------------------------------------------


@given(
    signal_dicts(),
    st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
@hyp_settings(max_examples=80)
def test_score_bound_under_arbitrary_knobs(
    payload: dict[str, dict],
    max_agree: float,
    contradict: float,
) -> None:
    weights = ScoringWeights(
        max_agreement_multiplier=max_agree,
        contradict_penalty=contradict,
    )
    score = compose_score(payload, weights)
    assert -1.0 <= score.edge_score <= 1.0
    # ComposedScore rounds the multiplier / factor fields to 6 decimal
    # places (see ``round(..., 6)`` in compose_score). Allow up to 1e-5
    # slop on the bounds for both sides of the rounding.
    assert contradict - 1e-5 <= score.contradict_factor <= 1.0 + 1e-5
    # agreement_multiplier in [1.0, max_agree]
    assert 1.0 - 1e-5 <= score.agreement_multiplier <= max_agree + 1e-5
