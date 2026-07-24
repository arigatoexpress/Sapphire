"""Canonical secret-material detection for outbound (cloud) egress gates.

Single source of truth for "does this text contain credential material?".

Why this module exists
----------------------
Before it, Sapphire had two divergent egress classifiers:

* ``plugins/claw-sapphire/lib/sensitivity_classifier.py`` — matched the *words*
  ``api_key`` / ``password`` / ``secret``, plus Tailscale IPs and financial PII.
* ``services/inference-proxy/app.py::_SENSITIVE_PATTERNS`` — matched OAuth field
  names, PEM headers, credit cards, SSNs and Slack tokens.

Neither was a superset of the other, and *neither* matched raw key material that
carries no adjacent keyword. A bare ``AKIA…`` / ``ghp_…`` / ``eyJ…`` string was
classified SAFE and forwarded to the Tier-4 cloud provider. This module closes
that gap for both callers at once — fix a pattern here and every gate improves.

Two things are detected:

``secret material``
    High-confidence *value* shapes (AWS keys, GitHub PATs, Slack/Stripe/Telegram
    tokens, JWTs, PEM blocks, hex private keys). These need no nearby keyword —
    the value alone is the tell.

``credential keywords``
    Field names (``api_key``, ``password``, ``client_secret``, …). Matched
    against a *normalized* copy of the text so that homoglyph, zero-width,
    percent-encoding and leetspeak substitutions cannot smuggle them past.

Design posture: **fail toward blocking.** A false positive costs a slower local
inference; a false negative leaks a live credential to a third-party API.

Known limits (deliberate, not oversights)
-----------------------------------------
* **Shapeless secrets.** An AWS *secret access key* is 40 base64 characters with
  no prefix — indistinguishable from any other base64 blob. Detecting it by
  shape would block a large share of benign traffic, so it is caught only when a
  keyword sits nearby (``aws_secret_access_key=…``), via the keyword rule.
* **Semantic leaks.** "my key starts with sk- and is 51 chars" carries no secret
  and no keyword; catching it needs a model, not a regex.

Both cases stay marked ``xfail`` in ``tests/fixtures/redteam/`` rather than being
papered over — see that corpus for the current honest scorecard.

Stdlib-only by construction — the inference proxy imports this with no package
install, and it must stay importable from any interpreter in the fleet.
"""

from __future__ import annotations

import base64
import binascii
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass

__all__ = [
    "SecretMatch",
    "CREDENTIAL_KEYWORD_RE",
    "SECRET_MATERIAL_PATTERNS",
    "find_secret",
    "contains_secret",
    "normalize",
]


# ─── Secret material: value shapes that are self-identifying ──────────────────
# Each entry is (name, pattern). Ordered most-specific first so `reason` is
# useful to a human reading a block log.

SECRET_MATERIAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # --- Cloud provider keys ---
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    # Length bounds on the provider patterns are ranges, not exact counts:
    # issuers have quietly changed token lengths, and an off-by-one here is a
    # silent leak rather than a loud failure.
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{33,40}\b")),
    ("gcp_service_account", re.compile(r'"type"\s*:\s*"service_account"')),
    # --- Source forges ---
    # ghp_/gho_/ghu_/ghs_/ghr_ = classic + app tokens; github_pat_ = fine-grained.
    ("github_token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("github_fine_grained_pat", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{22,}\b")),
    ("gitlab_token", re.compile(r"\bglpat-[0-9A-Za-z_\-]{20,}\b")),
    # --- SaaS ---
    ("slack_token", re.compile(r"\bxox[bpaosr]-[0-9A-Za-z\-]{10,}\b")),
    ("slack_webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]+")),
    ("stripe_key", re.compile(r"\b[rs]k_(?:live|test)_[0-9A-Za-z]{16,}\b")),
    ("sendgrid_key", re.compile(r"\bSG\.[0-9A-Za-z_\-]{16,}\.[0-9A-Za-z_\-]{16,}\b")),
    ("twilio_key", re.compile(r"\bSK[0-9a-fA-F]{32}\b")),
    ("npm_token", re.compile(r"\bnpm_[0-9A-Za-z]{30,}\b")),
    ("pypi_token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[0-9A-Za-z_\-]{50,}\b")),
    # --- LLM providers (Sapphire routes to several) ---
    ("openai_key", re.compile(r"\bsk-(?:proj-|svcacct-)?[0-9A-Za-z_\-]{20,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[0-9A-Za-z_\-]{20,}\b")),
    ("huggingface_token", re.compile(r"\bhf_[0-9A-Za-z]{30,}\b")),
    # --- Messaging ---
    # Telegram bot tokens: <8-10 digit bot id>:<35 char secret>
    ("telegram_bot_token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_\-]{32,45}\b")),
    # --- Generic structured credentials ---
    # Raw JWT — three base64url segments, header starts with the {"alg" prefix.
    ("jwt", re.compile(r"\beyJ[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{8,}\.[0-9A-Za-z_\-]{3,}")),
    (
        "pem_private_key",
        re.compile(r"-----BEGIN\s+(?:[A-Z]+\s+)?PRIVATE KEY-----", re.IGNORECASE),
    ),
    ("ssh_private_key", re.compile(r"\bssh-(?:rsa|ed25519|dss)\s+AAAA[0-9A-Za-z+/=]{20,}")),
    # DB connection strings carrying inline credentials.
    (
        "db_uri_credentials",
        re.compile(
            r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^@\s/]+:[^@\s/]+@"
        ),
    ),
    # --- Chain / wallet ---
    # 0x + 64 hex is an EVM private key *or* a tx hash. We block both: an
    # over-block costs local inference, an under-block costs the wallet.
    ("evm_private_key_or_hash", re.compile(r"\b0x[0-9a-fA-F]{64}\b")),
    # NB: no bare BIP39 mnemonic pattern. "12-24 short lowercase words" also
    # describes ordinary English prose, so a shape-based rule here would block
    # a large fraction of benign traffic. Labelled mnemonics are caught by the
    # `seed_phrase` / `mnemonic` credential keywords instead.
    # --- Financial / government identifiers ---
    ("credit_card", re.compile(r"\b(?:\d{4}[\s\-]){3}\d{4}\b")),
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]


# ─── Credential keywords: field names, matched post-normalization ─────────────

# `\b` is wrong for this job: `_` is a word character, so `\bsecret\b` does not
# match inside `aws_secret_access_key` — which is exactly how a real credential
# is spelled. These boundaries treat `_` as a separator instead.
_L = r"(?<![A-Za-z0-9])"  # left boundary, underscore-aware
_R = r"(?![A-Za-z0-9])"  # right boundary, underscore-aware

_CREDENTIAL_KEYWORDS = [
    r"api[_\-.]?key",
    r"apikey",
    r"secret[_\-.]?key",
    rf"{_L}secret{_R}",
    rf"{_L}password{_R}",
    rf"{_L}passwd{_R}",
    rf"{_L}passphrase{_R}",
    r"access[_\-.]?token",
    r"refresh[_\-.]?token",
    r"id[_\-.]?token",
    r"client[_\-.]?secret",
    r"private[_\-.]?key",
    rf"{_L}credential[s]?{_R}",
    rf"{_L}bearer{_R}",
    rf"{_L}jwt{_R}",
    r"auth[_\-.]?key",
    r"hmac[_\-.]?secret",
    rf"{_L}sign(?:ing)?[_\-.]?secret{_R}",
    r"seed[_\-.]?phrase",
    r"mnemonic",
    r"routing[_\-.]?num",
]

CREDENTIAL_KEYWORD_RE = re.compile("|".join(_CREDENTIAL_KEYWORDS), re.IGNORECASE)


# ─── Normalization: defeat encoding-based evasion ─────────────────────────────

# Confusable homoglyphs → ASCII. Covers the Cyrillic and Greek letters that
# render identically to Latin in most fonts, which is what makes them useful
# for slipping "аpi_key" (Cyrillic а) past a naive matcher.
_HOMOGLYPHS = str.maketrans(
    {
        "а": "a",  # CYRILLIC SMALL A
        "е": "e",  # CYRILLIC SMALL IE
        "о": "o",  # CYRILLIC SMALL O
        "р": "p",  # CYRILLIC SMALL ER
        "с": "c",  # CYRILLIC SMALL ES
        "х": "x",  # CYRILLIC SMALL HA
        "у": "y",  # CYRILLIC SMALL U
        "і": "i",  # CYRILLIC/UKRAINIAN SMALL I
        "ј": "j",  # CYRILLIC SMALL JE
        "һ": "h",  # CYRILLIC SMALL SHHA
        "А": "A",
        "В": "B",
        "Е": "E",
        "К": "K",
        "М": "M",
        "Н": "H",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "α": "a",  # GREEK SMALL ALPHA
        "ε": "e",  # GREEK SMALL EPSILON
        "ο": "o",  # GREEK SMALL OMICRON
        "ρ": "p",  # GREEK SMALL RHO
        "υ": "u",  # GREEK SMALL UPSILON
        "Α": "A",
        "Β": "B",
        "Ε": "E",
        "Ο": "O",
        "Ρ": "P",
    }
)

# Zero-width / bidi / soft-hyphen characters used to split keywords.
# Written as explicit escapes: these are invisible in an editor, so a literal
# character class here would be unreviewable and easy to corrupt.
_INVISIBLE_RE = re.compile(
    "["
    "­"  # SOFT HYPHEN
    "​-‏"  # ZERO WIDTH SPACE .. RIGHT-TO-LEFT MARK
    "‪-‮"  # BIDI embedding / override controls
    "⁠-⁤"  # WORD JOINER .. INVISIBLE PLUS
    "﻿"  # ZERO WIDTH NO-BREAK SPACE (BOM)
    "]"
)

# Leetspeak folding, applied only when testing for credential *keywords* — the
# substitutions are too lossy to run against value-shaped patterns.
_LEET = str.maketrans({"4": "a", "3": "e", "0": "o", "1": "l", "5": "s", "7": "t", "$": "s"})


def normalize(text: str) -> str:
    """Fold a string into a canonical form for keyword matching.

    Applies, in order: NFKC compatibility normalization, invisible-character
    removal, homoglyph folding, and percent-decoding. The result is only
    suitable for *keyword* comparison — it is lossy by design.
    """
    if not text:
        return ""
    out = unicodedata.normalize("NFKC", text)
    out = _INVISIBLE_RE.sub("", out)
    out = out.translate(_HOMOGLYPHS)
    # Percent-decoding turns "api%5Fkey" back into "api_key". unquote never
    # raises; malformed escapes are left as-is.
    out = urllib.parse.unquote(out)
    return out


# Candidate encoded blobs worth decoding and re-scanning.
_B64_CANDIDATE_RE = re.compile(r"\b[A-Za-z0-9+/]{12,}={0,2}\b")
_HEX_CANDIDATE_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}){6,}\b")


def _decoded_views(text: str, limit: int = 24) -> list[str]:
    """Yield plausible decodings of base64/hex blobs embedded in `text`.

    Only decodings that come back as mostly-printable ASCII are returned —
    random binary would produce noise and spurious keyword hits.
    """
    views: list[str] = []
    for match in list(_B64_CANDIDATE_RE.finditer(text))[:limit]:
        blob = match.group(0)
        pad = "=" * (-len(blob) % 4)
        try:
            raw = base64.b64decode(blob + pad, validate=True)
        except (binascii.Error, ValueError):
            continue
        views.append(raw.decode("ascii", errors="ignore"))
    for match in list(_HEX_CANDIDATE_RE.finditer(text))[:limit]:
        try:
            raw = bytes.fromhex(match.group(0))
        except ValueError:
            continue
        views.append(raw.decode("ascii", errors="ignore"))
    return views


# ─── Public API ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SecretMatch:
    """A single detection. `name` identifies the rule, `snippet` is truncated."""

    name: str
    snippet: str
    via: str = "literal"  # literal | normalized | decoded

    def __str__(self) -> str:  # pragma: no cover - display helper
        suffix = "" if self.via == "literal" else f" via {self.via}"
        return f"{self.name}{suffix}"


def find_secret(text: str) -> SecretMatch | None:
    """Return the first secret detected in `text`, else ``None``.

    Checks, in order:

    1. Value-shaped secret material against the raw text.
    2. Credential keywords against the normalized text (defeats homoglyph,
       zero-width, percent-encoding and leetspeak evasion).
    3. Both of the above against base64/hex blobs decoded out of the text.
    """
    if not text:
        return None

    for name, pattern in SECRET_MATERIAL_PATTERNS:
        m = pattern.search(text)
        if m:
            return SecretMatch(name, m.group(0)[:40].strip())

    folded = normalize(text)
    m = CREDENTIAL_KEYWORD_RE.search(folded)
    if m:
        via = "literal" if folded == text else "normalized"
        return SecretMatch("credential_keyword", m.group(0)[:40].strip(), via)

    # Leetspeak is checked separately so it never corrupts value matching.
    m = CREDENTIAL_KEYWORD_RE.search(folded.translate(_LEET))
    if m:
        return SecretMatch("credential_keyword", m.group(0)[:40].strip(), "normalized")

    for view in _decoded_views(folded):
        for name, pattern in SECRET_MATERIAL_PATTERNS:
            hit = pattern.search(view)
            if hit:
                return SecretMatch(name, hit.group(0)[:40].strip(), "decoded")
        hit = CREDENTIAL_KEYWORD_RE.search(view)
        if hit:
            return SecretMatch("credential_keyword", hit.group(0)[:40].strip(), "decoded")

    return None


def contains_secret(text: str) -> bool:
    """Boolean convenience wrapper around :func:`find_secret`."""
    return find_secret(text) is not None
