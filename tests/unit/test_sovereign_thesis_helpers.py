"""Edge-case coverage for sovereign_thesis internal helpers.

Complements ``test_sovereign_thesis.py`` (which exercises the integration
report and the default Ari universe) by pinning down behaviour of the
small parsing/scoring/labelling helpers that the larger report builds on.
"""

from __future__ import annotations

import json

import pytest

from lib.intel import sovereign_thesis as st

# ── _as_float ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (1, 1.0),
        (1.5, 1.5),
        ("0.5", 0.5),
        ("-3", -3.0),
    ],
)
def test_as_float_parses_known_inputs(value, expected) -> None:
    assert st._as_float(value) == expected


@pytest.mark.parametrize("value", [None, "", "abc", [1, 2], {"a": 1}])
def test_as_float_returns_default_for_unparseable(value) -> None:
    assert st._as_float(value, default=0.42) == 0.42


# ── _as_mapping / _as_list / _as_str_tuple ────────────────────────────


@pytest.mark.parametrize("value", [None, [], "", 0, "string", [1, 2]])
def test_as_mapping_returns_empty_for_non_dict(value) -> None:
    assert st._as_mapping(value) == {}


def test_as_mapping_returns_dict_unchanged() -> None:
    payload = {"a": 1}
    assert st._as_mapping(payload) is payload


@pytest.mark.parametrize("value", [None, {}, "", 0, "string", {"a": 1}])
def test_as_list_returns_empty_for_non_list(value) -> None:
    assert st._as_list(value) == []


def test_as_list_returns_list_unchanged() -> None:
    payload = [1, 2, 3]
    assert st._as_list(payload) is payload


def test_as_str_tuple_filters_empty_and_whitespace() -> None:
    raw = ["one", "", "  ", None, "two", 0, 3]

    result = st._as_str_tuple(raw)

    # Empty strings, whitespace-only, and None drop; numerics are coerced.
    assert result == ("one", "two", "3")


def test_as_str_tuple_returns_empty_for_non_list() -> None:
    assert st._as_str_tuple("not a list") == ()


# ── _json_compatible_yaml ─────────────────────────────────────────────


def test_json_compatible_yaml_empty_returns_empty_dict() -> None:
    assert st._json_compatible_yaml("") == {}
    assert st._json_compatible_yaml("   \n\n  ") == {}


def test_json_compatible_yaml_strips_comments() -> None:
    text = "# comment\n" + json.dumps({"a": 1}) + "\n# trailing"

    assert st._json_compatible_yaml(text) == {"a": 1}


def test_json_compatible_yaml_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        st._json_compatible_yaml(json.dumps([1, 2, 3]))


def test_json_compatible_yaml_propagates_json_errors() -> None:
    with pytest.raises(json.JSONDecodeError):
        st._json_compatible_yaml("{not valid json")


# ── load_thesis_config ────────────────────────────────────────────────


def test_load_thesis_config_missing_file_raises(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        st.load_thesis_config(tmp_path / "no-such-file.yaml")


def test_load_thesis_config_non_mapping_raises(tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    # Both the YAML path and the JSON-compatible fallback reject lists
    # at the top level.
    with pytest.raises(ValueError, match="must be a mapping"):
        st.load_thesis_config(path)


# ── _lens_from_mapping ────────────────────────────────────────────────


def test_lens_from_mapping_requires_id() -> None:
    with pytest.raises(ValueError, match="lens requires id"):
        st._lens_from_mapping({"label": "no id"})


def test_lens_from_mapping_clamps_negative_weight_to_zero() -> None:
    lens = st._lens_from_mapping({"id": "x", "weight": -3.5})

    assert lens.weight == 0.0


def test_lens_from_mapping_defaults() -> None:
    lens = st._lens_from_mapping({"id": "minimal"})

    assert lens.label == "minimal"  # falls back to id
    assert lens.weight == 1.0
    assert lens.austrian_principle == ""
    assert lens.positive_tags == ()
    assert lens.negative_tags == ()
    assert lens.source_requirements == ()


def test_lens_from_mapping_invalid_weight_uses_default() -> None:
    lens = st._lens_from_mapping({"id": "x", "weight": "not a number"})

    assert lens.weight == 1.0


# ── _asset_from_mapping ───────────────────────────────────────────────


def test_asset_from_mapping_requires_symbol() -> None:
    with pytest.raises(ValueError, match="asset requires symbol"):
        st._asset_from_mapping({"name": "no symbol"})


def test_asset_from_mapping_uppercases_symbol() -> None:
    asset = st._asset_from_mapping({"symbol": "  btc  "})

    assert asset.symbol == "BTC"


@pytest.mark.parametrize(
    "raw,expected",
    [
        (-0.5, 0.0),
        (0.0, 0.0),
        (0.5, 0.5),
        (1.0, 1.0),
        (1.5, 1.0),
        ("garbage", 0.5),  # default applied first, then clamped
    ],
)
def test_asset_from_mapping_clamps_conviction(raw, expected) -> None:
    asset = st._asset_from_mapping({"symbol": "X", "conviction": raw})

    assert asset.conviction == expected


def test_asset_from_mapping_drops_blank_venue_symbols() -> None:
    asset = st._asset_from_mapping(
        {
            "symbol": "X",
            "venue_symbols": {"tradingview": "OK", "blank": "", "spaces": "   "},
        }
    )

    assert asset.venue_symbols == {"tradingview": "OK"}


def test_asset_from_mapping_coerces_lens_scores_to_floats() -> None:
    asset = st._asset_from_mapping(
        {
            "symbol": "X",
            "lens_scores": {"a": "0.7", "b": 1, "c": "garbage"},
        }
    )

    assert asset.lens_scores == {"a": 0.7, "b": 1.0, "c": 0.0}


# ── _inferred_lens_value ──────────────────────────────────────────────


def _lens(*, id_="L", positive=(), negative=(), source_requirements=()):
    return st.ThesisLens(
        id=id_,
        label=id_,
        weight=1.0,
        austrian_principle="",
        positive_tags=tuple(positive),
        negative_tags=tuple(negative),
        source_requirements=tuple(source_requirements),
    )


def _asset(*, lens_scores=None, tags=()):
    return st.ThesisAsset(
        symbol="X",
        name="X",
        asset_class="watch",
        conviction=1.0,
        thesis_tags=tuple(tags),
        lens_scores=dict(lens_scores or {}),
        venue_symbols={},
        evidence_sources=(),
        invalidation_triggers=(),
    )


def test_inferred_lens_value_explicit_score_wins() -> None:
    lens = _lens(id_="L", positive=("good",), negative=("bad",))
    asset = _asset(lens_scores={"L": 0.42}, tags=("good", "bad"))

    assert st._inferred_lens_value(asset, lens) == 0.42


def test_inferred_lens_value_explicit_score_clamped() -> None:
    lens = _lens(id_="L")
    assert st._inferred_lens_value(_asset(lens_scores={"L": 5.0}), lens) == 1.0
    assert st._inferred_lens_value(_asset(lens_scores={"L": -5.0}), lens) == -1.0


def test_inferred_lens_value_lens_id_in_tags_counts_positive() -> None:
    lens = _lens(id_="alpha")
    asset = _asset(tags=("alpha",))

    assert st._inferred_lens_value(asset, lens) == 0.5


def test_inferred_lens_value_positive_tag_only() -> None:
    lens = _lens(positive=("good",))
    assert st._inferred_lens_value(_asset(tags=("good",)), lens) == 0.5


def test_inferred_lens_value_negative_tag_only() -> None:
    lens = _lens(negative=("bad",))
    assert st._inferred_lens_value(_asset(tags=("bad",)), lens) == -0.5


def test_inferred_lens_value_both_tags_partial_credit() -> None:
    lens = _lens(positive=("good",), negative=("bad",))
    assert st._inferred_lens_value(_asset(tags=("good", "bad")), lens) == 0.25


def test_inferred_lens_value_no_match_neutral() -> None:
    lens = _lens(positive=("good",), negative=("bad",))
    assert st._inferred_lens_value(_asset(tags=("unrelated",)), lens) == 0.0


# ── _cell_state ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value,expected",
    [
        (1.0, "core"),
        (0.75, "core"),
        (0.74, "supporting"),
        (0.01, "supporting"),
        (0.0, "neutral"),
        (-0.01, "risk"),
        (-1.0, "risk"),
    ],
)
def test_cell_state_thresholds(value, expected) -> None:
    assert st._cell_state(value) == expected


# ── _fit_label ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "score,expected",
    [
        (100.0, "core"),
        (72.0, "core"),
        (71.99, "aligned"),
        (45.0, "aligned"),
        (44.99, "watch"),
        (30.0, "watch"),
        (29.99, "speculative"),
        (0.0, "speculative"),
        (-5.0, "speculative"),
    ],
)
def test_fit_label_thresholds(score, expected) -> None:
    assert st._fit_label(score) == expected


# ── _asset_lens_cells ─────────────────────────────────────────────────


def test_asset_lens_cells_includes_requirements_only_when_positive() -> None:
    lens_pos = _lens(id_="P", positive=("good",), source_requirements=("src:1",))
    lens_neg = _lens(id_="N", negative=("bad",), source_requirements=("src:2",))
    asset = _asset(tags=("good", "bad"))

    cells = {cell["id"]: cell for cell in st._asset_lens_cells(asset, [lens_pos, lens_neg])}

    assert cells["P"]["state"] == "supporting"
    assert cells["P"]["source_requirements"] == ["src:1"]
    assert cells["N"]["state"] == "risk"
    # Negative cells must not register source requirements — they are
    # counter-evidence, not coverage gaps.
    assert cells["N"]["source_requirements"] == []


def test_asset_lens_cells_weighted_score_uses_weight_and_conviction() -> None:
    lens = st.ThesisLens(
        id="L",
        label="L",
        weight=2.0,
        austrian_principle="",
        positive_tags=("good",),
        negative_tags=(),
        source_requirements=(),
    )
    asset = st.ThesisAsset(
        symbol="X",
        name="X",
        asset_class="watch",
        conviction=0.5,
        thesis_tags=("good",),
        lens_scores={},
        venue_symbols={},
        evidence_sources=(),
        invalidation_triggers=(),
    )

    cell = st._asset_lens_cells(asset, [lens])[0]

    # value 0.5 (positive-tag only) * weight 2.0 * conviction 0.5 = 0.5
    assert cell["value"] == 0.5
    assert cell["weighted_score"] == 0.5


# ── _required_source_lenses ───────────────────────────────────────────


def test_required_source_lenses_filters_inactive_states() -> None:
    cells = [
        {"id": "A", "state": "core", "source_requirements": ["src:1"]},
        {"id": "B", "state": "supporting", "source_requirements": ["src:1", "src:2"]},
        {"id": "C", "state": "risk", "source_requirements": ["src:3"]},
        {"id": "D", "state": "neutral", "source_requirements": ["src:4"]},
    ]

    required = st._required_source_lenses(cells)

    assert required == {"src:1": ["A", "B"], "src:2": ["B"]}


def test_required_source_lenses_handles_missing_requirements_key() -> None:
    cells = [{"id": "A", "state": "core"}]

    assert st._required_source_lenses(cells) == {}


# ── _source_gap ───────────────────────────────────────────────────────


def test_source_gap_returns_sorted_difference() -> None:
    asset = _asset()
    object.__setattr__(asset, "evidence_sources", ("src:b",))

    cells = [
        {"id": "X", "state": "core", "source_requirements": ["src:c", "src:a", "src:b"]},
    ]

    assert st._source_gap(asset, cells) == ["src:a", "src:c"]


# ── parse_lenses / parse_assets edge cases ───────────────────────────


def test_parse_lenses_empty_config() -> None:
    assert st.parse_lenses({}) == []


def test_parse_assets_empty_config() -> None:
    assert st.parse_assets({}) == []


def test_parse_lenses_skips_non_mapping_rows() -> None:
    """Non-mapping rows are coerced to {} and then raise on missing id."""
    config = {"lenses": ["not a dict", 42, None]}

    with pytest.raises(ValueError, match="lens requires id"):
        st.parse_lenses(config)


def test_parse_assets_skips_non_mapping_rows() -> None:
    config = {"assets": ["not a dict"]}

    with pytest.raises(ValueError, match="asset requires symbol"):
        st.parse_assets(config)
