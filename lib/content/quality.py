"""Research-grade content quality gate.

The original version of this module only filtered for a few banned
phrases, minimum numeric density, and runaway sentences. That kept
obvious slop out, but it was still easy for unsupported or weakly
argued content to pass.

This revision keeps the original heuristics and adds lightweight
institutional research checks that do not require external model calls:

1. Evidence density: enough numbers and/or concrete source references.
2. Evidence coverage: enough sentences are actually anchored in evidence.
3. Citation quality: longer pieces need specific sources, not just vibes.
4. Unsupported conclusions: flag conclusion language without nearby proof.
5. Argument coherence: reward linked, evidence-backed sentence flow.
6. Originality: penalize cliche-heavy or repetitive phrasing.
7. Small-sample performance claims: block public accuracy boasts before the
   prediction sample is large enough to support them.

The goal is still not literary beauty; it is truthful, specific,
traceable, and decision-useful writing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .performance_policy import has_public_accuracy_track_record, prediction_sample_size

BANNED_PHRASES: tuple[str, ...] = (
    "in today's rapidly evolving",
    "it's worth noting",
    "let's dive in",
    "buckle up",
    "game-changer",
    "paradigm shift",
    "deep dive",
    "unpack",
    "robust",
    "seamless",
    "cutting-edge",
    "revolutionary",
)

MAX_BANNED = 2
MIN_NUMBERS = 3
MIN_WORDS = 30
MAX_AVG_SENTENCE_WORDS = 35  # >35 is typically runaway
MIN_EVIDENCE_DENSITY = 4.0
MIN_EVIDENCE_COVERAGE = 0.5
MIN_ARGUMENT_COHERENCE = 0.4
MIN_ORIGINALITY_SCORE = 0.45
MIN_CITATION_QUALITY = 0.2
LONG_FORM_WORDS = 80
SHORT_FORM_MIN_WORDS = 18


_NUM_RE = re.compile(r"(?<!\w)(\$?\-?\d[\d,]*(?:\.\d+)?%?)")
_SENT_SPLIT_RE = re.compile(r"(?:[.!?]+\s+|\n+)")
_PATH_CITATION_RE = re.compile(r"(?:(?:data|docs|benchmarks|lib|services|infra)/[A-Za-z0-9_./-]+)")
_URL_CITATION_RE = re.compile(r"https?://[^\s)]+")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_PERFORMANCE_CLAIM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b\d+(?:\.\d+)?%\s+accuracy\b", re.IGNORECASE),
    re.compile(r"\baccuracy\b[^.\n]{0,40}\b\d+(?:\.\d+)?%", re.IGNORECASE),
    re.compile(r"\b\d+\s*/\s*\d+\s+correct\b", re.IGNORECASE),
    re.compile(r"\b[A-Z]{2,10}\s+\d+\s*/\s*\d+\b"),
    re.compile(r"\b[A-Z]{2,10}:\s*\d+\s*/\s*\d+\s*(?:\(\d+(?:\.\d+)?%\))?"),
)

_EVIDENCE_MARKERS: tuple[str, ...] = (
    "according to",
    "data source",
    "data sources",
    "source:",
    "sources:",
    "dataset",
)
_TRANSITION_PREFIXES: tuple[str, ...] = (
    "however",
    "but",
    "because",
    "therefore",
    "meanwhile",
    "instead",
    "still",
    "this",
    "these",
    "that",
    "those",
)
_UNSUPPORTED_CUES: tuple[str, ...] = (
    "this means",
    "which means",
    "therefore",
    "clearly",
    "obviously",
    "proves",
    "guarantees",
    "everyone",
    "nobody",
    "always",
    "never",
)
_OVERREACH_CUES: tuple[str, ...] = (
    "guarantee",
    "guarantees",
    "always",
    "never",
    "everyone",
    "nobody",
    "cannot fail",
    "can't lose",
)
_STOPWORDS: set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "there",
    "this",
    "to",
    "was",
    "were",
    "with",
}


@dataclass
class QualityReport:
    passed: bool
    banned_hits: list[str] = field(default_factory=list)
    number_count: int = 0
    citation_count: int = 0
    word_count: int = 0
    avg_sentence_words: float = 0.0
    evidence_density: float = 0.0
    evidence_coverage: float = 0.0
    citation_quality: float = 0.0
    coherence_score: float = 0.0
    originality_score: float = 0.0
    unsupported_claims: list[str] = field(default_factory=list)
    overreach_hits: list[str] = field(default_factory=list)
    performance_claim_violations: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "banned_hits": self.banned_hits,
            "number_count": self.number_count,
            "citation_count": self.citation_count,
            "word_count": self.word_count,
            "avg_sentence_words": self.avg_sentence_words,
            "evidence_density": self.evidence_density,
            "evidence_coverage": self.evidence_coverage,
            "citation_quality": self.citation_quality,
            "coherence_score": self.coherence_score,
            "originality_score": self.originality_score,
            "unsupported_claims": self.unsupported_claims,
            "overreach_hits": self.overreach_hits,
            "performance_claim_violations": self.performance_claim_violations,
            "reasons": self.reasons,
        }


def count_banned(text: str, phrases: tuple[str, ...] = BANNED_PHRASES) -> list[str]:
    lower = text.lower()
    return [p for p in phrases if p in lower]


def count_numbers(text: str) -> int:
    return len(_NUM_RE.findall(text))


def extract_citations(text: str) -> list[str]:
    refs = _PATH_CITATION_RE.findall(text)
    refs.extend(_URL_CITATION_RE.findall(text))
    # Keep ordering stable while de-duping.
    return list(dict.fromkeys(refs))


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT_RE.split(text) if s.strip()]


def readability(text: str) -> tuple[int, float]:
    words = text.split()
    sents = _sentences(text)
    avg = (len(words) / len(sents)) if sents else float(len(words))
    return len(words), round(avg, 2)


def _content_tokens(text: str) -> set[str]:
    return {
        token
        for token in (t.lower() for t in _TOKEN_RE.findall(text))
        if token not in _STOPWORDS and len(token) > 2
    }


def _has_evidence(sentence: str) -> bool:
    lower = sentence.lower()
    return (
        count_numbers(sentence) > 0
        or bool(extract_citations(sentence))
        or any(marker in lower for marker in _EVIDENCE_MARKERS)
    )


def evidence_metrics(text: str) -> tuple[int, int, float, float]:
    sents = _sentences(text)
    citations = extract_citations(text)
    evidence_sentences = sum(1 for s in sents if _has_evidence(s))
    evidence_units = count_numbers(text) + len(citations)
    word_count = max(1, len(text.split()))
    density = round(evidence_units / word_count * 100, 2)
    coverage = round(evidence_sentences / len(sents), 3) if sents else 0.0
    return len(citations), evidence_units, density, coverage


def find_unsupported_claims(text: str) -> list[str]:
    claims: list[str] = []
    sents = _sentences(text)
    for idx, sent in enumerate(sents):
        lower = sent.lower()
        if not any(cue in lower for cue in _UNSUPPORTED_CUES):
            continue
        same_sentence_evidence = _has_evidence(sent)
        prior_sentence_evidence = idx > 0 and _has_evidence(sents[idx - 1])
        if not same_sentence_evidence and not prior_sentence_evidence:
            claims.append(sent)
    return claims


def find_overreach(text: str) -> list[str]:
    hits: list[str] = []
    for sent in _sentences(text):
        lower = sent.lower()
        if any(cue in lower for cue in _OVERREACH_CUES) and not _has_evidence(sent):
            hits.append(sent)
    return hits


def coherence(text: str) -> float:
    sents = _sentences(text)
    if not sents:
        return 0.0
    if len(sents) == 1:
        return 1.0 if _has_evidence(sents[0]) else 0.5

    supported = 0
    linked_pairs = 0
    prev_tokens: set[str] = set()

    for idx, sent in enumerate(sents):
        lower = sent.lower()
        tokens = _content_tokens(sent)
        if _has_evidence(sent) or lower.startswith(_TRANSITION_PREFIXES):
            supported += 1
        if idx > 0:
            if tokens & prev_tokens or lower.startswith(_TRANSITION_PREFIXES):
                linked_pairs += 1
        prev_tokens = tokens

    support_score = supported / len(sents)
    linkage_score = linked_pairs / (len(sents) - 1)
    return round((support_score + linkage_score) / 2, 3)


def originality(text: str) -> float:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    if len(tokens) < 6:
        return 1.0

    trigrams = [tuple(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    repeated_trigrams = len(trigrams) - len(set(trigrams))
    trigram_repeat_ratio = repeated_trigrams / len(trigrams) if trigrams else 0.0

    sents = _sentences(text)
    normalized_sents = [
        re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", s.lower())).strip() for s in sents
    ]
    repeated_sentences = len(normalized_sents) - len(set(normalized_sents))
    sentence_repeat_ratio = repeated_sentences / len(normalized_sents) if normalized_sents else 0.0
    cliche_ratio = len(count_banned(text)) / max(1, len(sents))

    penalty = min(1.0, trigram_repeat_ratio + sentence_repeat_ratio + cliche_ratio)
    return round(max(0.0, 1.0 - penalty), 3)


def citation_quality(text: str) -> float:
    refs = extract_citations(text)
    sents = _sentences(text)
    if not sents:
        return 0.0
    generic_mentions = len(
        re.findall(r"\b(?:source|sources|data source|data sources|according to)\b", text.lower())
    )
    specific_refs = sum(
        1 for ref in refs if "/" in ref or ref.startswith("http://") or ref.startswith("https://")
    )
    raw_score = specific_refs + min(generic_mentions, 2) * 0.25
    return round(min(1.0, raw_score / max(1.0, len(sents) / 3)), 3)


def find_small_sample_performance_claims(
    text: str, facts: dict[str, object] | None = None
) -> list[str]:
    if facts is None or has_public_accuracy_track_record(facts):
        return []
    if prediction_sample_size(facts) <= 0:
        return []
    return [
        sent
        for sent in _sentences(text)
        if any(pattern.search(sent) for pattern in _PERFORMANCE_CLAIM_PATTERNS)
    ]


def check(
    text: str,
    min_coherence: float = MIN_ARGUMENT_COHERENCE,
    facts: dict[str, object] | None = None,
) -> QualityReport:
    """Run all checks and return a structured report."""
    hits = count_banned(text)
    nums = count_numbers(text)
    words, avg_sent = readability(text)
    citation_count, _evidence_units, density, coverage = evidence_metrics(text)
    unsupported = find_unsupported_claims(text)
    overreach = find_overreach(text)
    coherence_score = coherence(text)
    originality_score = originality(text)
    citation_score = citation_quality(text)
    performance_claim_violations = find_small_sample_performance_claims(text, facts)

    reasons: list[str] = []
    if len(hits) > MAX_BANNED:
        reasons.append(f"too_many_banned_phrases ({len(hits)}>{MAX_BANNED}): {hits}")
    if nums < MIN_NUMBERS:
        reasons.append(f"data_density_low ({nums}<{MIN_NUMBERS} numbers)")
    short_form_exception = words >= SHORT_FORM_MIN_WORDS and density >= (MIN_EVIDENCE_DENSITY * 2)
    if words < MIN_WORDS and not short_form_exception:
        reasons.append(f"too_short ({words}<{MIN_WORDS} words)")
    if avg_sent > MAX_AVG_SENTENCE_WORDS:
        reasons.append(f"sentences_too_long ({avg_sent}>{MAX_AVG_SENTENCE_WORDS})")
    if density < MIN_EVIDENCE_DENSITY:
        reasons.append(
            f"evidence_density_low ({density}<{MIN_EVIDENCE_DENSITY} evidence units / 100 words)"
        )
    if coverage < MIN_EVIDENCE_COVERAGE:
        reasons.append(
            f"evidence_coverage_low ({coverage}<{MIN_EVIDENCE_COVERAGE} evidence-backed sentences)"
        )
    if words >= LONG_FORM_WORDS and citation_score < MIN_CITATION_QUALITY:
        reasons.append(f"citation_quality_low ({citation_score}<{MIN_CITATION_QUALITY})")
    if coherence_score < min_coherence:
        reasons.append(f"argument_coherence_low ({coherence_score}<{min_coherence})")
    if originality_score < MIN_ORIGINALITY_SCORE:
        reasons.append(f"originality_low ({originality_score}<{MIN_ORIGINALITY_SCORE})")
    if unsupported:
        reasons.append(f"unsupported_conclusions ({len(unsupported)})")
    if overreach:
        reasons.append(f"logical_overreach ({len(overreach)})")
    if performance_claim_violations:
        reasons.append(f"performance_claim_sample_too_small ({len(performance_claim_violations)})")

    return QualityReport(
        passed=not reasons,
        banned_hits=hits,
        number_count=nums,
        citation_count=citation_count,
        word_count=words,
        avg_sentence_words=avg_sent,
        evidence_density=density,
        evidence_coverage=coverage,
        citation_quality=citation_score,
        coherence_score=coherence_score,
        originality_score=originality_score,
        unsupported_claims=unsupported,
        overreach_hits=overreach,
        performance_claim_violations=performance_claim_violations,
        reasons=reasons,
    )
