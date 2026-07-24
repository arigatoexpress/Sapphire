"""Tests for lib.security.secret_patterns — the shared cloud-egress rule set.

The regression this file locks in: before it, raw credential *material* with no
adjacent keyword (``AKIA…``, ``ghp_…``, a bare JWT) was classified SAFE by both
egress gates and forwarded to the Tier-4 cloud provider.

False negatives here leak live credentials to a third party, so the positive
cases are the point. The negative cases matter too — an over-eager gate pushes
every request onto ~90s CPU inference, which is how a gate gets disabled.
"""

from __future__ import annotations

import pytest

from lib.security.secret_patterns import contains_secret, find_secret, normalize

# ─── Value-shaped secrets: no keyword anywhere in the string ──────────────────
#
# Every probe is assembled at runtime from a prefix and a filler body. Writing
# these as string literals puts real-shaped credentials in the repo, which trips
# GitHub push protection and every scanner we run in CI — the fixtures for a
# secret detector are exactly the thing a secret detector is built to find.
# `_p()` keeps the assembled value byte-identical to the literal while leaving
# no matchable token in the source.

_ALNUM = "abcdefghijklmnopqrstuvwxyz0123456789"


def _p(prefix: str, length: int, alphabet: str = _ALNUM) -> str:
    """Build `prefix` + `length` filler chars cycled from `alphabet`."""
    body = (alphabet * (length // len(alphabet) + 1))[:length]
    return f"{prefix}{body}"


BARE_SECRETS = [
    ("aws_access_key_id", _p("AKIA", 16, "IOSFODNN7EXAMPLE")),
    ("aws_sts_key", _p("ASIA", 16, "Y34FZKBOKMUTVV7A")),
    ("github_token", _p("gh" + "p_", 38)),
    ("github_fine_grained", _p("github" + "_pat_", 60)),
    ("gitlab_token", _p("gl" + "pat-", 24)),
    ("slack_bot", "xox" + "b-" + _p("", 12, "0123456789") + "-" + _p("", 24)),
    ("slack_webhook", "https://hooks.slack.com/services/" + _p("T", 8) + "/" + _p("B", 24)),
    ("stripe_live", _p("s" + "k_" + "live_", 24)),
    ("stripe_restricted", _p("r" + "k_" + "test_", 24)),
    ("openai", _p("s" + "k-proj-", 40)),
    ("anthropic", _p("s" + "k-ant-api03-", 36)),
    ("huggingface", _p("h" + "f_", 34)),
    ("google_api", _p("AIza", 35)),
    ("telegram_bot", _p("", 10, "0123456789") + ":" + _p("", 35)),
    ("npm", _p("np" + "m_", 38)),
    # JWT: base64url of {"alg":"HS256"} . {"sub":"1"} . signature
    ("jwt", "eyJhbGciOiJIUzI1NiJ9." + _p("eyJzdWIiOiIx", 12) + "." + _p("", 16)),
    ("pem", "-----BEGIN RSA PRIVATE KEY-----"),
    ("pem_openssh", "-----BEGIN OPENSSH PRIVATE KEY-----"),
    ("evm_private_key", _p("0x", 64, "0123456789abcdef")),
    ("postgres_uri", "postgres://admin:hunter2@db.internal:5432/sapphire"),
    ("mongodb_srv", "mongodb+srv://user:pass@cluster0.mongodb.net"),
    ("credit_card", "4111 1111 1111 1111"),
    ("us_ssn", "123-45-6789"),
]


@pytest.mark.parametrize("label,payload", BARE_SECRETS, ids=[c[0] for c in BARE_SECRETS])
def test_bare_secret_material_is_detected(label: str, payload: str) -> None:
    """Raw key material must be caught with no surrounding keyword."""
    hit = find_secret(payload)
    assert hit is not None, f"{label}: {payload!r} would be forwarded to the cloud tier"


# ─── Evasion: the value is a keyword, obfuscated ──────────────────────────────

EVASIONS = [
    ("homoglyph_cyrillic", "my аpi_key is abc"),  # Cyrillic а
    ("zero_width", "api​_key = abc"),
    ("soft_hyphen", "pass­word: hunter2"),
    ("percent_encoded", "please use api%5Fkey=abc"),
    ("leetspeak", "my p4ssw0rd is hunter2"),
    ("hex_encoded", "env 6170695f6b6579 equals abc"),
]


@pytest.mark.parametrize("label,payload", EVASIONS, ids=[c[0] for c in EVASIONS])
def test_obfuscated_keywords_are_normalized_and_caught(label: str, payload: str) -> None:
    hit = find_secret(payload)
    assert hit is not None, f"{label}: {payload!r} evaded the keyword rule"


# ─── Negatives: benign traffic must reach the fast cloud tier ─────────────────

BENIGN = [
    "What is the best way to learn Python?",
    "What is BTC doing today?",
    "Can you review this Python function?",
    "explain the RSI indicator",
    "summarize the hexagonal architecture pattern",
    "How is the market today? BTC is up 2%",
    "Write a function to parse JSON and return a dataclass",
    "The deploy finished at 14:32 and all checks were green",
    "Compare Sortino and Calmar ratios for a trend strategy",
]


@pytest.mark.parametrize("payload", BENIGN)
def test_benign_text_is_not_blocked(payload: str) -> None:
    """Over-blocking forces slow local inference — guard against creep."""
    hit = find_secret(payload)
    assert hit is None, f"benign text over-blocked as {hit}"


# ─── Normalization helper ─────────────────────────────────────────────────────


def test_normalize_strips_invisible_characters() -> None:
    assert normalize("api​_key") == "api_key"


def test_normalize_folds_cyrillic_homoglyphs() -> None:
    assert normalize("аpi_key") == "api_key"


def test_normalize_percent_decodes() -> None:
    assert normalize("api%5Fkey") == "api_key"


def test_normalize_is_safe_on_empty_input() -> None:
    assert normalize("") == ""


# ─── Reporting surface ────────────────────────────────────────────────────────


def test_match_reports_rule_name_for_block_logs() -> None:
    hit = find_secret(dict(BARE_SECRETS)["aws_access_key_id"])
    assert hit is not None
    assert hit.name == "aws_access_key_id"
    assert hit.via == "literal"


def test_match_reports_normalized_provenance() -> None:
    hit = find_secret("api​_key = abc")
    assert hit is not None
    assert hit.via == "normalized"


def test_contains_secret_matches_find_secret() -> None:
    assert contains_secret(dict(BARE_SECRETS)["github_token"]) is True
    assert contains_secret("explain the RSI indicator") is False


def test_empty_input_is_not_sensitive() -> None:
    assert find_secret("") is None
    assert contains_secret("") is False


# ─── Documented limits — these SHOULD fail, and we assert that they do ────────
# If one of these starts passing, the corresponding xfail in
# tests/fixtures/redteam/sensitivity_classifier_probes.json can be flipped.


def test_known_limit_shapeless_aws_secret_key() -> None:
    """40 chars of base64 has no distinguishing shape; keyword-only detection."""
    assert find_secret("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY") is None
    # ...but it is caught the moment it is labelled.
    assert find_secret("aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCY") is not None


def test_known_limit_semantic_description_without_material() -> None:
    """Describing a secret in prose leaks nothing a regex can anchor on."""
    assert find_secret("my OpenAI auth value starts with sk- and is 51 chars") is None
