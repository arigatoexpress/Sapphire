"""EN→ES translator for the content engine.

Strategy: dictionary-driven, deterministic, offline. No LLM calls.
The formatters already emit text assembled from structured facts, so
translating that text with a term-substitution pass + a small library of
Spanish templates is enough for the platform outputs Sapphire ships.

Why not an LLM: the existing pipeline is offline, reproducible, and cheap.
Adding a translation-time network call would break `pytest` isolation and
introduce a failure mode the current pipeline doesn't have.

Public surface
--------------
translate_text(text, target, *, platform=None) -> str
    One-shot translate. Preserves numbers, tickers, dates, URLs, hashtags,
    CVE IDs, and dotted file paths. Applies the glossary case-insensitively.
    Multi-word terms are substituted before single-word terms so "bull
    market" never gets word-splatted.

Translator(target).translate(text) -> str
Translator(target).translate_x_thread(tweets) -> list[str]
Translator(target).translate_with_report(text) -> (str, ArtifactReport)
    Stateful wrapper — reuses the compiled substitution list so translating
    many strings inside one report is cheap.

detect_artifacts(text, *, language="es") -> ArtifactReport
    Sniff common machine-translation smells: doubled whitespace, leaked
    placeholder tokens, doubled punctuation, and language-mismatched
    boilerplate (English disclaimers surviving into a Spanish body).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from .glossary import GLOSSARY

LANG_EN = "en"
LANG_ES = "es"
_SUPPORTED = frozenset({LANG_EN, LANG_ES})

# ── Preservation patterns ────────────────────────────────────────────────────
# Anything matching one of these gets stashed under a placeholder BEFORE the
# glossary substitution runs, then restored verbatim at the end. This keeps
# `$103,500.00`, `data/foo.jsonl`, `BTC`, and `https://...` from being
# corrupted by well-meaning term matches.
#
# Order matters here — the first pattern to match a substring wins, so more
# specific patterns come first.
#
# Note on tickers (BTC/ETH/DXY/…): we intentionally do NOT preserve them via
# a `\b[A-Z]{2,10}\b` pattern. That would false-match all-caps English words
# like "BEAR MARKET" and prevent the glossary from seeing them. Tickers are
# safe from the glossary anyway — glossary keys are lowercase, and no single
# lowercased ticker ("btc", "eth", "dxy") is a glossary entry. The few 3-4
# letter symbols that DO appear in the glossary as canonical acronyms (RSI,
# MACD) round-trip to themselves.
_PRESERVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"https?://[^\s)\"']+"),  # URLs
    re.compile(r"`[^`]+`"),  # inline code
    re.compile(r"CVE-\d{4}-\d{4,7}"),  # CVE IDs
    # Dotted/slashed paths and identifiers — matches lowercase-starting
    # `data/trading_predictions.jsonl`, uppercase-starting `X-Y.NYB`, and
    # dotted module paths like `lib.content.formatters`.
    re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z0-9_.-]+)+"),
    re.compile(r"#\w+"),  # hashtags
    re.compile(r"@\w+"),  # mentions
    re.compile(r"\$[-+]?\d[\d,]*(?:\.\d+)?"),  # $103,500.00
    re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?%"),  # 83.3%
    re.compile(r"[-+]?\d[\d,]*\.\d+"),  # 1.234
    re.compile(r"[-+]?\d[\d,]+"),  # 1,234
    re.compile(r"\d+/\d+"),  # 30/40, 1/3 (tweet counters)
)

_PLACEHOLDER = "__SAPPHIRE_PH_{}__"
_PLACEHOLDER_RE = re.compile(r"__SAPPHIRE_PH_\d+__")


# ── Language detection helpers ───────────────────────────────────────────────


def is_supported_language(lang: str | None) -> bool:
    if not lang:
        return False
    return lang.lower() in _SUPPORTED


# ── Core substitution ────────────────────────────────────────────────────────


def _mask(text: str) -> tuple[str, list[str]]:
    """Replace preserved substrings with placeholders. Returns (masked, tokens)."""
    tokens: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        idx = len(tokens)
        tokens.append(token)
        return _PLACEHOLDER.format(idx)

    masked = text
    for pat in _PRESERVE_PATTERNS:
        masked = pat.sub(_sub, masked)
    return masked, tokens


def _unmask(text: str, tokens: list[str]) -> str:
    def _restore(match: re.Match[str]) -> str:
        digits = re.search(r"\d+", match.group(0))
        if digits is None:
            return match.group(0)
        idx = int(digits.group(0))
        if 0 <= idx < len(tokens):
            return tokens[idx]
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_restore, text)


def _en_plural(en: str) -> str:
    """Cheap English pluralizer covering the shapes present in our glossary.

    Not linguistically complete — e.g. "loss" → "losses" needs the -es rule
    while "portfolio" → "portfolios" is just +s. Terms with irregular plurals
    that we want to translate as a unit can be listed in the glossary as
    two entries (singular + plural), which sidesteps this function entirely.
    """
    if not en:
        return en
    tail = en[-1]
    if en.endswith(("s", "sh", "ch", "x", "z")):
        return en + "es"
    if len(en) >= 2 and tail == "y" and en[-2] not in "aeiou":
        return en[:-1] + "ies"
    return en + "s"


def _sorted_glossary_terms() -> list[tuple[str, str]]:
    """Return (en_pattern, es_replacement) pairs, longest-first.

    Multi-word terms win over single-word ones (so "bull market" is tried
    before "market"). Each single-word term is expanded into singular +
    plural — the plural ES uses ``term.plural_es`` when set, otherwise a
    naive ``es + "s"``. Multi-word terms are not auto-pluralized (their
    plural forms rarely differ from the singular in these compounds, and
    when they do a second glossary entry is the cleaner fix).
    """
    pairs: list[tuple[str, str]] = []
    for term in GLOSSARY.values():
        pairs.append((term.en, term.es))
        if " " not in term.en:
            plural_en = _en_plural(term.en)
            if plural_en != term.en:
                plural_es = term.plural_es or (term.es + "s")
                pairs.append((plural_en, plural_es))
    # Dedup while preserving order (keep the first — singular before plural).
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for en, es in pairs:
        key = en.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((en, es))
    uniq.sort(key=lambda p: -len(p[0]))
    return uniq


_SORTED_PAIRS: list[tuple[str, str]] = _sorted_glossary_terms()


def _apply_glossary(text: str, pairs: Iterable[tuple[str, str]] = _SORTED_PAIRS) -> str:
    """Case-insensitive term-by-term replacement.

    Matches are on word boundaries so we don't rewrite fragments of longer
    words. Substitution is case-insensitive but rendering is always the
    glossary's canonical ES form — we don't try to preserve English casing
    across the swap.
    """
    out = text
    for en, es in pairs:
        pattern = re.compile(rf"\b{re.escape(en)}\b", re.IGNORECASE)
        out = pattern.sub(es, out)
    return out


def translate_text(text: str, target: str, *, platform: str | None = None) -> str:
    """Translate `text` into `target` language.

    - target="en" is identity (we don't back-translate).
    - target="es" runs mask → glossary → unmask.

    `platform` is accepted for forward-compat with per-platform tweaks
    (currently the substitution set is the same across platforms; if
    platform-specific term overrides are needed later, wire them in here).
    """
    if not is_supported_language(target):
        raise ValueError(f"unsupported language: {target!r}")
    target = target.lower()
    if target == LANG_EN:
        return text

    masked, tokens = _mask(text)
    swapped = _apply_glossary(masked)
    return _unmask(swapped, tokens)


# ── Artifact detection ───────────────────────────────────────────────────────


@dataclass
class ArtifactReport:
    ok: bool = True
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "artifacts": list(self.artifacts)}


# Boilerplate strings that should NOT survive into a Spanish output.
_EN_BOILERPLATE: tuple[str, ...] = (
    "not investment advice",
    "informational only",
    "informational and educational purposes only",
    "data sources",
    "not financial advice",
    "for informational",
)


def detect_artifacts(text: str, *, language: str = "es") -> ArtifactReport:
    """Sniff common machine-translation / mask-swap smells.

    Rules:
      1. Placeholder tokens must never survive to the output.
      2. Doubled interior whitespace usually means a swap left a gap.
      3. Doubled punctuation (`..`, `!!`, `??`) is almost always an artifact.
      4. English boilerplate strings in an ES output are untranslated.
    """
    artifacts: list[str] = []

    if _PLACEHOLDER_RE.search(text):
        artifacts.append("placeholder_leak")

    # Doubled spaces INSIDE a line (leading/trailing don't count).
    if re.search(r"\S  +\S", text):
        artifacts.append("double_space")

    if re.search(r"([.!?])\1+", text):
        artifacts.append("double_punctuation")

    if language.lower() == LANG_ES:
        low = text.lower()
        for phrase in _EN_BOILERPLATE:
            if phrase in low:
                artifacts.append(f"untranslated:{phrase}")
                break

    return ArtifactReport(ok=not artifacts, artifacts=artifacts)


# ── Stateful translator ──────────────────────────────────────────────────────


class Translator:
    """Small stateful wrapper. Reuse across many strings in one report cycle."""

    def __init__(self, target: str) -> None:
        if not is_supported_language(target):
            raise ValueError(f"unsupported language: {target!r}")
        self.target = target.lower()
        self._pairs = _SORTED_PAIRS

    def translate(self, text: str, *, platform: str | None = None) -> str:
        return translate_text(text, self.target, platform=platform)

    def translate_with_report(
        self, text: str, *, platform: str | None = None
    ) -> tuple[str, ArtifactReport]:
        out = self.translate(text, platform=platform)
        return out, detect_artifacts(out, language=self.target)

    def translate_x_thread(self, tweets: list[str]) -> list[str]:
        """Translate a pre-numbered tweet thread.

        Tweets already carry `(i/n)` suffixes from `_split_tweets`. Each tweet
        is translated in isolation; if a translation would push a tweet past
        the platform limit, we trim from the end (before the counter) rather
        than resplit — the number of tweets stays stable so the counters keep
        pointing at the right thing.
        """
        from .formatters import X_TWEET_LIMIT  # local import: avoid cycle

        out: list[str] = []
        counter_re = re.compile(r"\s*\((\d+)/(\d+)\)\s*$")
        for tweet in tweets:
            m = counter_re.search(tweet)
            if m:
                counter = m.group(0)
                body = tweet[: m.start()]
            else:
                counter = ""
                body = tweet
            translated_body = self.translate(body, platform="x")
            candidate = translated_body + counter
            if len(candidate) > X_TWEET_LIMIT:
                # Trim body from the right, preserve counter.
                budget = X_TWEET_LIMIT - len(counter) - 1  # -1 for the ellipsis
                if budget > 0:
                    translated_body = translated_body[:budget].rstrip() + "…"
                    candidate = translated_body + counter
                else:
                    candidate = counter.strip()
            out.append(candidate)
        return out
