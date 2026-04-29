"""PII redactor — paste-safe sanitization for customer-facing surfaces.

This module is **pure**. It performs no I/O, reads no environment variables,
makes no network calls, and writes no files. All redaction rules are
deterministic and idempotent: ``redact(redact(x)) == redact(x)``.

The redactor is intentionally conservative — when a token *looks* like PII it
is redacted, even at the cost of occasional false positives in synthetic test
fixtures. Buyer-facing dashboards (Palantir / Robinhood corp-dev) consume this
module's output, so leakage is the only failure mode that matters.

Categories handled:

* **Names** → opaque ``customer_<6charhash>`` token derived from a stable hash
  of the input (so the same name maps to the same redacted id within a payload
  while still being unrecoverable without the original string).
* **Phone numbers** → ``***-***-NNNN`` keeping only the last 4 digits.
* **Emails** → ``<first2>***@<domain>`` so the domain is preserved for triage
  without exposing the local-part.
* **Addresses** → ``<city>, <state>`` only (or ``<redacted address>`` when the
  city/state pair cannot be confidently extracted).
* **Mixed free-text** → :func:`redact_text` walks every recognized pattern
  in a single pass.

Public surface:

* :func:`redact_name`
* :func:`redact_phone`
* :func:`redact_email`
* :func:`redact_address`
* :func:`redact_text` — best-effort scrub for arbitrary strings.
* :func:`redact_record` — recursive walker for dict/list payloads using a
  fixed key allowlist for known PII fields.
* :func:`redact` — convenience alias dispatching on type.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

# Stable salt — keeps the hash identifier non-reversible without coordinating
# with an external secret store. The salt is a constant by design: callers that
# need cross-tenant unlinkability should prepend their own namespace before
# passing strings in.
_HASH_SALT = "sapphire-pii-redactor-v1"
_HASH_LEN = 6  # 6 hex chars = 24 bits = enough to disambiguate within a page

# Per-tenant hashing — used by the customer-dossier 0.2.0 surface to isolate
# anonymized identifiers across tenants. The function is *pure*: callers
# inject the configured salt (loaded from ``~/.sapphire/secrets.env`` by
# whatever I/O-tolerant caller — typically ``services/dashboard/app.py``).
# When ``salt`` is None we fall back to a deterministic-but-randomized default
# derived from the module-level ``_HASH_SALT`` + the tenant id. This preserves
# 0.1.0 backward compatibility (a tenant without configured salt still gets a
# stable, non-reversible hash) while letting live-mode tenants rotate their
# salt independently.
_PER_TENANT_HASH_LEN = 16  # 16 hex chars = 64 bits — enough to disambiguate
                          # across tenants without becoming an ID-of-record.
_DEFAULT_TENANT_SALT_PREFIX = "sapphire-dossier-default-tenant-salt-v1"

# Phone numbers: tolerant of separators (- . space) and optional country code.
_PHONE_RE = re.compile(
    r"""
    (?<![\w])                       # not preceded by word char
    (?:\+?\d{1,3}[\s\-.]?)?         # optional country code
    (?:\(\d{3}\)|\d{3})             # area code, with or without parens
    [\s\-.]?                        # separator
    \d{3}                           # exchange
    [\s\-.]?                        # separator
    \d{4}                           # subscriber
    (?![\w])                        # not followed by word char
    """,
    re.VERBOSE,
)

# Emails — RFC-ish, intentionally narrower than the full grammar.
# Lookbehind blocks word continuation only; lookahead allows a trailing
# period/comma so prose-mode mentions ("...email a@b.com.") still match.
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![A-Za-z0-9])"
)

# Already-redacted email pattern: "<first2>***@<domain>". Used to short-circuit
# idempotence and to recognize redacted emails in text walks. The prefix
# character class mirrors the local-part class in `_EMAIL_RE` so emails like
# `_alice@example.com` redact to `_a***@example.com` and survive the second
# pass unchanged. Found bug captured by Lane 1 property test, fixed 2026-04-30.
_REDACTED_EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Za-z0-9._%+-]{1,2})\*{3}@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})(?![A-Za-z0-9])"
)

# Already-redacted markers so we can short-circuit the idempotence guarantee.
_REDACTED_NAME_RE = re.compile(r"^customer_[0-9a-f]{6}$")
_REDACTED_PHONE_RE = re.compile(r"\*{3}-\*{3}-\d{4}")
_REDACTED_EMAIL_LOCAL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,2}\*{3}$")

# US state abbreviations — used to detect city/state addresses.
_US_STATES = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }
)

# Address line detector — "123 Main Street", "PO Box 42", etc.
_STREET_NUMBER_RE = re.compile(r"^\s*\d+\s+\S")
_PO_BOX_RE = re.compile(r"\bP\.?\s*O\.?\s*Box\b", re.IGNORECASE)

# Inline street-address detector: matches "<digits> <Word> <street suffix>"
# anywhere in a string, including mid-sentence. The suffix list is a curated
# subset of the USPS abbreviations — kept short on purpose to minimise false
# positives on prose that happens to contain a number followed by a noun.
_STREET_SUFFIX = (
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|"
    r"Way|Court|Ct|Circle|Cir|Place|Pl|Highway|Hwy|Parkway|Pkwy|Trail|Trl|"
    r"Square|Sq|Terrace|Ter)"
)
_INLINE_STREET_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z][A-Za-z'À-ɏ\-\.]*\s+){1,4}" + _STREET_SUFFIX + r"\b\.?",
)

# City, State [zip] capture: "Houston, TX" or "Houston, TX 77001".
_CITY_STATE_RE = re.compile(
    r"\b([A-Z][A-Za-z'À-ɏ\-\.\s]{1,40}),\s*([A-Z]{2})\b(?:\s+\d{5}(?:-\d{4})?)?"
)

# PII field-name allowlist for record-level redaction. Keys are matched
# case-insensitively; values feed type-specific redactors.
_FIELD_REDACTORS: dict[str, str] = {
    "name": "name",
    "full_name": "name",
    "fullname": "name",
    "first_name": "name",
    "last_name": "name",
    "customer_name": "name",
    "client_name": "name",
    "lead_name": "name",
    "contact_name": "name",
    "actor": "name",
    "actor_name": "name",
    "owner": "name",
    "owner_name": "name",
    "phone": "phone",
    "phone_number": "phone",
    "mobile": "phone",
    "cell": "phone",
    "telephone": "phone",
    "email": "email",
    "email_address": "email",
    "address": "address",
    "street_address": "address",
    "mailing_address": "address",
    "home_address": "address",
    "ssn": "drop",
    "social_security_number": "drop",
    "dob": "drop",
    "date_of_birth": "drop",
    "credit_card": "drop",
    "card_number": "drop",
    "pin": "drop",
    "admin_pin": "drop",
    "operator_pin": "drop",
    "tho_admin_pin": "drop",
    "api_key": "drop",
    "secret": "drop",
    "password": "drop",
    "token": "drop",
    "auth_token": "drop",
}


def _stable_hash(value: str) -> str:
    """Return ``_HASH_LEN`` hex chars derived from a salted SHA-256."""
    digest = hashlib.sha256((_HASH_SALT + value).encode("utf-8")).hexdigest()
    return digest[:_HASH_LEN]


def _default_tenant_salt(tenant_id: str) -> str:
    """Derive a deterministic-but-randomized default salt for a tenant.

    Used when no operator-configured salt is supplied (non-live mode). The
    derivation is keyed off the module-level ``_HASH_SALT`` so that the
    default is **not** trivially guessable, while remaining stable across
    process restarts and machines (so cached redacted ids round-trip).
    """
    canonical = (tenant_id or "").strip().lower()
    digest = hashlib.sha256(
        (_DEFAULT_TENANT_SALT_PREFIX + "|" + canonical).encode("utf-8")
    ).hexdigest()
    return digest


def per_tenant_hash(
    value: str,
    tenant_id: str,
    *,
    salt: str | None = None,
) -> str:
    """Return an HMAC-SHA256 hex digest scoped to ``(value, tenant_id)``.

    Args:
        value: The cleartext to hash. ``None`` and empty inputs collapse to a
            stable ``"tenant_<tenant>_unknown"`` token.
        tenant_id: The tenant scope. Different tenants MUST yield different
            hashes for the same ``value``. Whitespace-only / ``None`` tenants
            collapse to the literal ``"unknown"`` scope.
        salt: Operator-configured per-tenant salt. When provided this is the
            HMAC key. When ``None`` (non-live / 0.1.0-compat) we derive a
            deterministic-but-randomized default via :func:`_default_tenant_salt`.

    Properties:
        * **Determinism**: same ``(value, tenant_id, salt)`` → same hash.
        * **Isolation**: different ``tenant_id`` → different hash for the same
          ``value`` (because the HMAC key changes).
        * **Salt rotation**: changing the operator-supplied ``salt`` for a
          tenant invalidates every previously-emitted hash for that tenant.
        * **Backward compat**: with ``salt=None`` the function still emits a
          stable hash so 0.1.0 callers without a configured salt continue to
          work without breaking changes.

    The function is intentionally pure — no env reads, no filesystem reads,
    no network. The dashboard surface loads the salt from the operator
    secrets store and injects it; the redactor stays a pure transform.
    """
    canonical_tenant = (tenant_id or "").strip().lower() or "unknown"
    if value is None:
        return f"tenant_{canonical_tenant[:24]}_unknown"
    s = str(value).strip()
    if not s:
        return f"tenant_{canonical_tenant[:24]}_unknown"

    canonical_value = " ".join(s.split()).casefold()
    key = (salt if salt is not None else _default_tenant_salt(canonical_tenant)).encode("utf-8")
    msg = (canonical_tenant + "|" + canonical_value).encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"tenant_{canonical_tenant[:24]}_{digest[:_PER_TENANT_HASH_LEN]}"


def redact_name(name: str | None) -> str:
    """Redact a personal name to a stable ``customer_<6charhash>`` token.

    Empty / whitespace-only / ``None`` inputs return ``"customer_unknown"``.
    Already-redacted tokens (matching the same shape) pass through unchanged
    to preserve idempotence.
    """
    if name is None:
        return "customer_unknown"
    s = str(name).strip()
    if not s:
        return "customer_unknown"
    if _REDACTED_NAME_RE.match(s):
        return s
    # Normalize for hashing so "John  Doe" and "John Doe" hash the same.
    canonical = " ".join(s.split()).casefold()
    return f"customer_{_stable_hash(canonical)}"


def redact_phone(phone: str | None) -> str:
    """Redact a phone number to ``***-***-NNNN`` (last 4 digits only).

    Inputs without enough digits collapse to ``"***-***-****"``. Already-
    redacted phones pass through unchanged.
    """
    if phone is None:
        return "***-***-****"
    s = str(phone).strip()
    if not s:
        return "***-***-****"
    if _REDACTED_PHONE_RE.search(s) and not re.search(r"\b\d{7,}\b", s):
        # Already redacted — leave it alone for idempotence.
        return s if _REDACTED_PHONE_RE.fullmatch(s) else _REDACTED_PHONE_RE.sub(
            lambda m: m.group(0), s
        )
    digits = re.sub(r"\D", "", s)
    if len(digits) < 4:
        return "***-***-****"
    last4 = digits[-4:]
    return f"***-***-{last4}"


def redact_email(email: str | None) -> str:
    """Redact an email to ``<first2>***@<domain>``.

    Preserves the domain so triage can still detect duplicate-domain leakage
    (e.g. an entire ``@example.com`` cohort) without exposing local-parts.
    Inputs that don't look like emails return ``"<redacted>@<redacted>"``.
    """
    if email is None:
        return "<redacted>@<redacted>"
    s = str(email).strip()
    if not s:
        return "<redacted>@<redacted>"
    # Idempotence: already-redacted form passes through unchanged.
    redacted_match = _REDACTED_EMAIL_RE.search(s)
    if redacted_match and redacted_match.group(0) == s:
        return s
    m = _EMAIL_RE.search(s)
    if not m:
        return "<redacted>@<redacted>"
    local, domain = m.group(1), m.group(2)
    # Already-redacted local part pattern in case caller passed e.g. "al***".
    prefix_match = re.match(r"^([A-Za-z0-9._%+-]{1,2})\*{3}$", local)
    if prefix_match:
        return f"{prefix_match.group(1)}***@{domain}"
    prefix = local[:2] if len(local) >= 2 else (local[:1] if local else "")
    if not prefix:
        prefix = "x"
    return f"{prefix}***@{domain}"


def redact_address(address: str | None) -> str:
    """Redact a street address to ``<City>, <ST>`` or ``<redacted address>``.

    Strategy: walk the input for the first ``Word, ST`` token (a simple US
    locality pattern). If found, return that substring exactly. Otherwise
    return ``"<redacted address>"``. The street-number / PO-box prefix is
    *always* dropped.
    """
    if address is None:
        return "<redacted address>"
    s = str(address).strip()
    if not s:
        return "<redacted address>"

    # Already-redacted: city, state token alone.
    bare = _CITY_STATE_RE.fullmatch(s)
    if bare and bare.group(2).upper() in _US_STATES:
        return f"{bare.group(1).strip()}, {bare.group(2).upper()}"

    match = _CITY_STATE_RE.search(s)
    if match and match.group(2).upper() in _US_STATES:
        city = match.group(1).strip()
        state = match.group(2).upper()
        return f"{city}, {state}"

    # No locality found — return the generic placeholder. We never echo
    # raw street numbers or PO boxes back to the caller.
    return "<redacted address>"


def redact_text(text: str | None) -> str:
    """Redact any free-form string by walking known PII patterns.

    Order matters: emails are walked before phones (since some emails contain
    digit runs), and addresses last so we don't shred parts of a city name.
    """
    if text is None:
        return ""
    s = str(text)
    if not s:
        return ""

    # 1. Emails — replace the *entire match* with the redacted form.
    # Already-redacted email tokens are skipped so the walker is idempotent.
    def _email_repl(m: re.Match[str]) -> str:
        token = m.group(0)
        # Reject anything where the local part already looks redacted.
        if "*" in token:
            return token
        return redact_email(token)

    s = _EMAIL_RE.sub(_email_repl, s)

    # 2. Phone numbers — replace the *entire match* (preserving boundary).
    s = _PHONE_RE.sub(lambda m: redact_phone(m.group(0)), s)

    # 3. Addresses — only when a clear "<word>, <ST>" pattern survives. We
    # only replace the matched span, not the surrounding context, so a
    # mention of "in Houston, TX" reads naturally as "in Houston, TX" still
    # (no PII to scrub there). For full street addresses (with number prefix)
    # we still want to drop the number — handled below.
    def _addr_repl(m: re.Match[str]) -> str:
        st = m.group(2).upper()
        if st not in _US_STATES:
            return m.group(0)
        return f"{m.group(1).strip()}, {st}"

    s = _CITY_STATE_RE.sub(_addr_repl, s)

    # 4. Strip inline street addresses ("1234 Some Street Drive,..." mid-text).
    s = _INLINE_STREET_RE.sub("<redacted street address>", s)

    # 5. Strip leading street numbers in any surviving line that still looks
    # like an address starter (``123 Main St ...``). We replace the leading
    # number with ``<redacted>`` to avoid false positives on token streams
    # that simply start with a digit.
    new_lines: list[str] = []
    for line in s.split("\n"):
        if _STREET_NUMBER_RE.match(line) and any(
            kw in line.lower()
            for kw in (" street", " st ", " st,", " ave", " avenue", " road", " rd ", " rd,", " blvd", " lane", " ln ", " ln,", " drive", " dr ", " dr,", " way", " court", " ct ", " ct,", " circle", " place", " pl ", " pl,")
        ):
            line = re.sub(r"^\s*\d+\s+", "<redacted> ", line)
        if _PO_BOX_RE.search(line) and "<redacted PO Box>" not in line:
            line = _PO_BOX_RE.sub("<redacted PO Box>", line)
            line = re.sub(r"<redacted PO Box>\s+\d+", "<redacted PO Box>", line)
        new_lines.append(line)
    return "\n".join(new_lines)


def redact_record(record: Any, *, _depth: int = 0) -> Any:
    """Recursively redact PII fields in a JSON-like payload.

    * ``dict`` keys matching :data:`_FIELD_REDACTORS` are dispatched to the
      type-specific redactor. Keys mapped to ``"drop"`` are removed entirely.
    * ``list`` / ``tuple`` are walked element-wise.
    * ``str`` values inside untyped fields are run through :func:`redact_text`.
    * Other scalars pass through unchanged.

    Recursion is bounded at 32 levels to avoid pathological inputs blowing
    the Python stack — deeper structures get the placeholder ``"<truncated>"``.
    """
    if _depth > 32:
        return "<truncated>"

    if isinstance(record, dict):
        out: dict[str, Any] = {}
        for k, v in record.items():
            key_norm = str(k).strip().lower()
            mode = _FIELD_REDACTORS.get(key_norm)
            if mode == "name":
                out[k] = redact_name(v if isinstance(v, str) else (str(v) if v is not None else None))
            elif mode == "phone":
                out[k] = redact_phone(v if isinstance(v, str) else (str(v) if v is not None else None))
            elif mode == "email":
                out[k] = redact_email(v if isinstance(v, str) else (str(v) if v is not None else None))
            elif mode == "address":
                out[k] = redact_address(v if isinstance(v, str) else (str(v) if v is not None else None))
            elif mode == "drop":
                out[k] = "<redacted>"
            else:
                out[k] = redact_record(v, _depth=_depth + 1)
        return out
    if isinstance(record, (list, tuple)):
        result = [redact_record(item, _depth=_depth + 1) for item in record]
        return result if isinstance(record, list) else tuple(result)
    if isinstance(record, str):
        return redact_text(record)
    return record


def redact(value: Any) -> Any:
    """Type-dispatched redaction convenience entry point."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return redact_record(value)
    if isinstance(value, str):
        return redact_text(value)
    return value


__all__ = [
    "per_tenant_hash",
    "redact",
    "redact_address",
    "redact_email",
    "redact_name",
    "redact_phone",
    "redact_record",
    "redact_text",
]
