"""Exhaustive unit tests for ``lib.security.pii_redactor``.

PII redaction is a non-negotiable contract for the customer-dossier dashboard.
These tests cover names, phones, emails, addresses, mixed text, null/empty
inputs, unicode names, idempotence, and record-level dispatch. Property-style
fuzzing is appended at the bottom to catch regressions in the regex set.
"""

from __future__ import annotations

import random
import re
import string
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.security.pii_redactor import (  # noqa: E402
    redact,
    redact_address,
    redact_email,
    redact_name,
    redact_phone,
    redact_record,
    redact_text,
)

# ── Names ────────────────────────────────────────────────────────────


def test_redact_name_basic_ascii() -> None:
    out = redact_name("John Doe")
    assert out.startswith("customer_")
    assert len(out) == len("customer_") + 6
    assert out != "customer_unknown"


def test_redact_name_is_deterministic_per_input() -> None:
    assert redact_name("Jane Smith") == redact_name("Jane Smith")


def test_redact_name_normalizes_whitespace_and_case() -> None:
    a = redact_name("John Doe")
    b = redact_name("  john   doe  ")
    assert a == b


def test_redact_name_distinguishes_different_names() -> None:
    a = redact_name("Alice Liddell")
    b = redact_name("Bob Roberts")
    assert a != b


def test_redact_name_empty_and_none() -> None:
    assert redact_name(None) == "customer_unknown"
    assert redact_name("") == "customer_unknown"
    assert redact_name("   ") == "customer_unknown"


def test_redact_name_unicode() -> None:
    # Diacritics, CJK, emoji-ish — must redact, not crash.
    a = redact_name("Café Müller")
    b = redact_name("张伟")
    assert a.startswith("customer_") and a != "customer_unknown"
    assert b.startswith("customer_") and b != "customer_unknown"
    assert a != b


def test_redact_name_idempotent() -> None:
    once = redact_name("Sam Test")
    twice = redact_name(once)
    assert once == twice


# ── Phones ───────────────────────────────────────────────────────────


def test_redact_phone_dashed() -> None:
    assert redact_phone("555-123-4567") == "***-***-4567"


def test_redact_phone_parens_and_spaces() -> None:
    assert redact_phone("(555) 123-4567") == "***-***-4567"


def test_redact_phone_dotted() -> None:
    assert redact_phone("555.123.4567") == "***-***-4567"


def test_redact_phone_with_country_code() -> None:
    assert redact_phone("+1 555 123 4567") == "***-***-4567"


def test_redact_phone_runs_together() -> None:
    assert redact_phone("5551234567") == "***-***-4567"


def test_redact_phone_empty_or_none() -> None:
    assert redact_phone(None) == "***-***-****"
    assert redact_phone("") == "***-***-****"
    assert redact_phone("   ") == "***-***-****"


def test_redact_phone_too_short() -> None:
    assert redact_phone("12") == "***-***-****"


def test_redact_phone_idempotent() -> None:
    once = redact_phone("555-123-4567")
    twice = redact_phone(once)
    assert once == twice == "***-***-4567"


# ── Emails ───────────────────────────────────────────────────────────


def test_redact_email_simple() -> None:
    assert redact_email("alice@example.com") == "al***@example.com"


def test_redact_email_short_local_part() -> None:
    # Single-character local part keeps that one char.
    assert redact_email("a@example.com") == "a***@example.com"


def test_redact_email_with_dots_and_plus() -> None:
    out = redact_email("alice.smith+sales@example.co.uk")
    assert out == "al***@example.co.uk"


def test_redact_email_empty_or_none() -> None:
    assert redact_email(None) == "<redacted>@<redacted>"
    assert redact_email("") == "<redacted>@<redacted>"


def test_redact_email_invalid() -> None:
    assert redact_email("not-an-email") == "<redacted>@<redacted>"


def test_redact_email_idempotent() -> None:
    once = redact_email("alice@example.com")
    twice = redact_email(once)
    assert once == twice


# ── Addresses ────────────────────────────────────────────────────────


def test_redact_address_full_us() -> None:
    out = redact_address("123 Main Street, Houston, TX 77001")
    assert out == "Houston, TX"


def test_redact_address_apartment() -> None:
    out = redact_address("456 Oak Ave Apt 5B, Austin, TX 78701")
    assert out == "Austin, TX"


def test_redact_address_po_box() -> None:
    out = redact_address("PO Box 12345, Dallas, TX 75201")
    assert out == "Dallas, TX"


def test_redact_address_no_state_match() -> None:
    out = redact_address("Some random string with no state")
    assert out == "<redacted address>"


def test_redact_address_empty_or_none() -> None:
    assert redact_address(None) == "<redacted address>"
    assert redact_address("") == "<redacted address>"


def test_redact_address_already_redacted() -> None:
    once = redact_address("123 Main St, Houston, TX 77001")
    twice = redact_address(once)
    assert once == twice == "Houston, TX"


def test_redact_address_non_us_state_falls_through() -> None:
    # "ZZ" is not a US state — must not echo back the upstream content.
    out = redact_address("123 Main Street, Atlantis, ZZ")
    assert out == "<redacted address>"


# ── Mixed free-text ──────────────────────────────────────────────────


def test_redact_text_email_and_phone_in_paragraph() -> None:
    src = "Contact Jane at jane.doe@example.com or 555-123-4567 today."
    out = redact_text(src)
    assert "jane.doe@example.com" not in out
    assert "555-123-4567" not in out
    assert "ja***@example.com" in out
    assert "***-***-4567" in out


def test_redact_text_full_street_address() -> None:
    src = "Lead at 1234 Some Street Drive, Houston, TX 77001 wants a quote."
    out = redact_text(src)
    # Full street number must be scrubbed; locality may survive.
    assert "1234 Some Street" not in out
    assert "Houston, TX" in out


def test_redact_text_po_box() -> None:
    src = "Mail to PO Box 9999, Dallas, TX 75201 please."
    out = redact_text(src)
    assert "9999" not in out
    assert "<redacted PO Box>" in out
    assert "Dallas, TX" in out


def test_redact_text_empty_and_none() -> None:
    assert redact_text(None) == ""
    assert redact_text("") == ""


def test_redact_text_idempotent_on_paragraph() -> None:
    src = (
        "John Doe at john.doe@example.com / 555-123-4567 — "
        "PO Box 42, Austin, TX 78701"
    )
    once = redact_text(src)
    twice = redact_text(once)
    assert once == twice


def test_redact_text_preserves_non_pii_content() -> None:
    src = "Sapphire OS shipped 36 plugin tools and 1,088 tests this week."
    assert redact_text(src) == src


# ── Record-level dispatch ────────────────────────────────────────────


def test_redact_record_basic_dict() -> None:
    rec = {
        "customer_name": "Jane Smith",
        "phone": "555-123-4567",
        "email": "jane@example.com",
        "address": "123 Main St, Houston, TX 77001",
        "status": "ENROLLED",
        "amount": 12500,
    }
    out = redact_record(rec)
    assert out["customer_name"].startswith("customer_")
    assert out["phone"] == "***-***-4567"
    assert out["email"] == "ja***@example.com"
    assert out["address"] == "Houston, TX"
    assert out["status"] == "ENROLLED"
    assert out["amount"] == 12500


def test_redact_record_drops_high_sensitivity_fields() -> None:
    rec = {
        "customer_name": "Bob",
        "ssn": "123-45-6789",
        "dob": "1980-01-01",
        "credit_card": "4111111111111111",
        "pin": "4832",
    }
    out = redact_record(rec)
    assert out["ssn"] == "<redacted>"
    assert out["dob"] == "<redacted>"
    assert out["credit_card"] == "<redacted>"
    assert out["pin"] == "<redacted>"


def test_redact_record_recurses_into_lists_and_dicts() -> None:
    rec = {
        "leads": [
            {"name": "Alice", "phone": "(555) 123-4567"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
        "summary": {
            "contact_email": "ops@example.com",
        },
    }
    out = redact_record(rec)
    assert all(lead["name"].startswith("customer_") for lead in out["leads"])
    assert out["leads"][0]["phone"] == "***-***-4567"
    assert out["leads"][1]["email"] == "bo***@example.com"


def test_redact_record_idempotent() -> None:
    rec = {
        "customer_name": "Jane Smith",
        "phone": "555-123-4567",
        "email": "jane.smith@example.com",
        "address": "456 Oak Ave, Austin, TX 78701",
    }
    once = redact_record(rec)
    twice = redact_record(once)
    assert once == twice


def test_redact_record_nested_string_field_runs_text_redaction() -> None:
    # A free-text "notes" field must still get scrubbed even though
    # "notes" is not in the field allowlist.
    rec = {
        "customer_name": "Carol",
        "notes": "Carol prefers SMS at 555-321-9876. email carol@example.com.",
    }
    out = redact_record(rec)
    assert "555-321-9876" not in out["notes"]
    assert "carol@example.com" not in out["notes"]


def test_redact_record_handles_recursion_bound() -> None:
    # Build a 50-deep chain — should not crash, hits truncation marker.
    deep: dict = {}
    cursor = deep
    for _ in range(50):
        cursor["next"] = {}
        cursor = cursor["next"]
    out = redact_record(deep)
    # Walk and confirm we hit a truncation marker somewhere down the chain.
    seen_truncated = False
    cursor = out
    for _ in range(60):
        if cursor == "<truncated>":
            seen_truncated = True
            break
        if not isinstance(cursor, dict) or "next" not in cursor:
            break
        cursor = cursor["next"]
    assert seen_truncated


# ── redact() convenience dispatcher ─────────────────────────────────


def test_redact_dispatches_by_type() -> None:
    assert redact(None) == ""
    assert redact("call 555-123-4567") == "call ***-***-4567"
    assert redact({"phone": "555-123-4567"})["phone"] == "***-***-4567"
    out_list = redact(["555-123-4567"])
    assert out_list == ["***-***-4567"]


def test_redact_passes_through_non_strings() -> None:
    assert redact(42) == 42
    assert redact(3.14) == 3.14
    assert redact(True) is True


# ── No-leak sweep on a representative dossier-shaped payload ─────────


def test_no_unredacted_pii_survives_record_redaction() -> None:
    """Build a payload that mixes every PII shape we expect to see, and
    assert that none of the original tokens survive in the redacted output's
    serialized JSON. This guards the dashboard contract: every leaf must
    be passed through a redactor before reaching the JSON encoder.
    """
    import json

    payload = {
        "customers": [
            {
                "customer_name": "Marie Curie",
                "phone": "555-867-5309",
                "email": "marie@example.org",
                "address": "1 Radium Way, Warsaw, NY 10001",
                "ssn": "999-99-9999",
                "notes": "Reach Marie at 555-867-5309 or marie@example.org.",
            },
            {
                "customer_name": "李雷",
                "phone": "(312) 555-0188",
                "email": "lilei@example.cn",
                "address": "PO Box 88, Chicago, IL 60601",
                "credit_card": "4111-1111-1111-1111",
            },
        ],
        "summary": {
            "support_email": "ops@example.com",
            "callback_phone": "1-800-555-0199",
        },
    }
    out = redact_record(payload)
    serialized = json.dumps(out)

    # Names — must not appear anywhere in the redacted blob.
    for forbidden in ("Marie Curie", "李雷"):
        assert forbidden not in serialized
    # Raw phone digit runs must not appear.
    for forbidden in ("8675309", "5550188", "5550199"):
        assert forbidden not in serialized
    # Email locals must not appear.
    for forbidden in ("marie@", "lilei@", "ops@"):
        assert forbidden not in serialized
    # Street numbers and PO Box numbers must not appear.
    for forbidden in ("1 Radium Way", "PO Box 88", "Box 88"):
        assert forbidden not in serialized
    # SSN and credit-card raw values must not appear.
    for forbidden in ("999-99-9999", "4111", "1111-1111"):
        assert forbidden not in serialized


# ── Property-style fuzz pass ─────────────────────────────────────────


@pytest.mark.parametrize("seed", [1, 7, 23, 101, 9001])
def test_random_strings_never_leak_phone_digits(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(50):
        digits = "".join(rng.choice(string.digits) for _ in range(10))
        formatted = f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        out = redact_text(f"call {formatted} please")
        # First 6 digits must be gone — only the last 4 may survive.
        assert digits[:6] not in out
        assert f"***-***-{digits[6:]}" in out


@pytest.mark.parametrize("seed", [2, 11, 47])
def test_random_emails_never_expose_full_local_part(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(30):
        local_len = rng.randint(3, 12)
        local = "".join(rng.choice(string.ascii_lowercase) for _ in range(local_len))
        domain = "example." + rng.choice(["com", "org", "co.uk"])
        email = f"{local}@{domain}"
        out = redact_email(email)
        # The local-part beyond the first 2 chars must be replaced.
        assert local not in out or local_len <= 2
        assert "***@" in out
        assert domain in out


def test_redact_text_idempotence_on_synthetic_paragraph() -> None:
    paragraph = (
        "Onboarded Sarah Connor (555-123-4567 / sarah.connor@skynet.example) at "
        "1234 Cyberdyne Drive, Sunnyvale, CA 94086. SSN 555-44-3333 on file. "
        "Backup contact PO Box 47, Reseda, CA 91335 — phone 818.555.7777."
    )
    once = redact_text(paragraph)
    twice = redact_text(once)
    assert once == twice
    # Sanity: no obvious raw PII fragments survived.
    for forbidden in (
        "sarah.connor@skynet.example",
        "555-123-4567",
        "1234 Cyberdyne",
        "Box 47",
        "818.555.7777",
    ):
        assert forbidden not in once


def test_emails_in_record_use_email_redaction_path() -> None:
    # The record-level redactor for "email" must NOT also re-walk text
    # redaction on the already-redacted output (idempotence check).
    rec = {"email": "alice@example.com"}
    out = redact_record(rec)
    assert out["email"] == "al***@example.com"
    # Run again — still same.
    out2 = redact_record(out)
    assert out2["email"] == "al***@example.com"


def test_already_redacted_email_in_text_pass_through() -> None:
    src = "ping ja***@example.com tomorrow"
    out = redact_text(src)
    assert "ja***@example.com" in out


def test_already_redacted_name_in_text_pass_through() -> None:
    """If a name is already redacted (``customer_<hash>``) the text walker
    must leave it untouched — no double-encoding."""
    src = "lead customer_abc123 wants a callback"
    # redact_text doesn't introduce names by itself — but redact_name on the
    # redacted token must be a no-op.
    assert redact_name("customer_abc123") == "customer_abc123"
    # The text walker simply doesn't do anything to it (no PII patterns
    # in the input string).
    assert redact_text(src) == src


def test_phone_number_pattern_redacts_digit_runs_conservatively() -> None:
    """Long digit runs that *could* contain a 10-digit phone get scrubbed.
    This is the safe direction — a buyer-facing dashboard would rather
    over-redact a numeric order ID than under-redact a real phone number.
    """
    src = "order id 1234567890123 was processed"
    out = redact_text(src)
    # The first 6 digits of any plausible phone subsequence must not survive.
    assert "1234567" not in out


def test_only_numbers_inside_word_boundaries_are_redacted() -> None:
    """Phone regex respects word boundaries: ``a555-123-4567b`` should not
    match because the surrounding alphanumerics break the boundary."""
    out = redact_text("token a555-123-4567b stays raw")
    # Because of word boundary anchors, this should NOT match. We assert
    # the redacted version still contains the *raw* form.
    assert "a555-123-4567b" in out


def test_redact_record_preserves_non_string_leaf_types() -> None:
    rec = {
        "customer_name": "Jane",
        "balance": 12345.67,
        "active": True,
        "tags": ["enrolled", "vip"],
        "count": 0,
    }
    out = redact_record(rec)
    assert out["balance"] == 12345.67
    assert out["active"] is True
    assert out["tags"] == ["enrolled", "vip"]
    assert out["count"] == 0
    assert out["customer_name"].startswith("customer_")


def test_redact_idempotence_full_round_trip() -> None:
    """Final defense-in-depth: running every redactor twice must be a no-op."""
    samples = [
        redact_name("John Doe"),
        redact_phone("555-123-4567"),
        redact_email("alice@example.com"),
        redact_address("1 Main St, Houston, TX 77001"),
        redact_text("call 555-123-4567 or email a@b.com"),
    ]
    for s in samples:
        # Each one must round-trip through the dispatcher unchanged.
        assert redact(s) == s, f"non-idempotent: {s!r}"


def test_redact_record_does_not_leave_phonelike_strings_in_text_fields() -> None:
    """Free-text 'description' values get phone numbers scrubbed even though
    the field name isn't in the allowlist."""
    rec = {"description": "Call back at 555-867-5309 today."}
    out = redact_record(rec)
    assert re.search(r"\b555-867-5309\b", out["description"]) is None
    assert "***-***-5309" in out["description"]
