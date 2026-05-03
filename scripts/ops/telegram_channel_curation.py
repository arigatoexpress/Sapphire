#!/usr/bin/env python3
"""Dry-run Telegram channel curation and bot-pump review helper.

This script evaluates a local JSON packet only. It never imports Telegram
clients, never opens sockets intentionally, never sends messages, and always
emits an operator-paste-safe report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.security.adversarial_detectors import BotPumpedChannelDetector
from services.telegram_intel.models import VALID_CATEGORIES
from services.telegram_intel.quality_filter import quality_filter, sanitize_text

SCHEMA_VERSION = 1
DEFAULT_MIN_SAMPLES = 3
FALSE_POSITIVE_REQUIREMENTS = (
    "independent_sources",
    "no_profit_claim",
    "no_coordination_burst",
    "no_bot_execution_language",
    "sample_message_ids",
)

SECRETISH_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|private[_-]?key)\s*[=:]\s*['\"]?[^'\"\s]{6,}"
)
LONG_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|[A-Za-z0-9_/-]{48,})\b")
HANDLE_RE = re.compile(r"(?<![\w/])@[A-Za-z0-9_]{3,}\b")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _short_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:10]


def _safe_text(value: Any, *, limit: int = 320) -> str:
    text = str(value or "")
    text = SECRETISH_RE.sub("[redacted-secret]", text)
    text = LONG_TOKEN_RE.sub("[redacted-token]", text)
    text = sanitize_text(text)
    return text[:limit]


def _safe_identifier(value: Any, *, fallback: str = "candidate") -> str:
    raw = str(value or "").strip()
    if not raw:
        return f"{fallback}-missing"
    redacted = HANDLE_RE.sub("[redacted-handle]", raw)
    if redacted != raw or raw.startswith("@"):
        return f"{fallback}-{_short_hash(raw)}"
    safe = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw).strip("-_.:")
    return safe[:80] or f"{fallback}-{_short_hash(raw)}"


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _sample_rows(candidate: dict[str, Any], safe_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(_as_list(candidate.get("sample_messages"))):
        sample = _as_mapping(raw)
        text = sample.get("text", raw if isinstance(raw, str) else "")
        rows.append(
            {
                "message_id": _safe_identifier(sample.get("message_id") or f"sample-{index}"),
                "channel_id": safe_id,
                "author": _safe_identifier(sample.get("author_ref") or sample.get("author") or ""),
                "text": str(text or ""),
                "timestamp": sample.get("published_at") or sample.get("timestamp") or index,
            }
        )
    return rows


def _quality_summary(rows: list[dict[str, Any]], *, min_quality_score: float) -> dict[str, Any]:
    decisions = [
        quality_filter(
            row.get("text"),
            channel_id=row.get("channel_id"),
            min_score=min_quality_score,
        )
        for row in rows
    ]
    if not decisions:
        return {
            "sample_count": 0,
            "average_quality_score": 0.0,
            "kept_ratio": 0.0,
            "tags": [],
            "snippets": [],
        }
    tags = Counter(tag for decision in decisions for tag in decision.tags)
    return {
        "sample_count": len(decisions),
        "average_quality_score": round(
            sum(float(decision.score) for decision in decisions) / len(decisions), 4
        ),
        "kept_ratio": round(
            sum(1 for decision in decisions if decision.keep) / len(decisions),
            4,
        ),
        "tags": [tag for tag, _count in tags.most_common()],
        "snippets": [decision.sanitized_text[:220] for decision in decisions[:3]],
    }


def _decision_for(
    *,
    score: float,
    sample_count: int,
    kept_ratio: float,
    category_valid: bool,
    bot_findings: int,
) -> str:
    if bot_findings:
        return "hold_bot_pump_review"
    if not category_valid:
        return "hold_invalid_category"
    if sample_count < DEFAULT_MIN_SAMPLES:
        return "hold_insufficient_samples"
    if score >= 0.72 and kept_ratio >= 0.67:
        return "eligible_for_disabled_watchlist_entry"
    if score >= 0.50:
        return "manual_review"
    return "reject_or_research_more"


def evaluate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    raw_id = candidate.get("candidate_id") or candidate.get("id") or candidate.get("source_ref")
    safe_id = _safe_identifier(raw_id)
    category = str(candidate.get("category") or "security").strip().lower()
    category_valid = category in VALID_CATEGORIES
    min_quality_score = _clamp(_float(candidate.get("min_quality_score"), 0.45))
    rows = _sample_rows(candidate, safe_id)
    quality = _quality_summary(rows, min_quality_score=min_quality_score)
    bot_report = BotPumpedChannelDetector().analyze(rows).to_dict()
    bot_findings = len(bot_report["findings"])
    known_risks = [_safe_text(item, limit=160) for item in _as_list(candidate.get("known_risks"))]
    risk_penalty = min(0.30, 0.06 * len(known_risks))
    if bot_findings:
        risk_penalty += 0.45
    if not category_valid:
        risk_penalty += 0.25

    sample_component = min(0.18, quality["sample_count"] * 0.06)
    score = _clamp(
        quality["average_quality_score"] * 0.72
        + quality["kept_ratio"] * 0.20
        + sample_component
        - risk_penalty
    )
    decision = _decision_for(
        score=score,
        sample_count=quality["sample_count"],
        kept_ratio=quality["kept_ratio"],
        category_valid=category_valid,
        bot_findings=bot_findings,
    )
    weight = round(_clamp(0.65 + score * 0.65, 0.5, 1.3), 2)
    return {
        "candidate_id": safe_id,
        "source_ref": _safe_identifier(candidate.get("source_ref") or raw_id, fallback="source"),
        "category": category if category_valid else "invalid",
        "score": round(score, 4),
        "decision": decision,
        "known_risks": known_risks,
        "operator_notes": _safe_text(candidate.get("operator_notes") or candidate.get("notes")),
        "quality": quality,
        "bot_pump_review": {
            "state": "review_required" if bot_findings else "no_bot_pump_finding_in_samples",
            "report": bot_report,
            "false_positive_requirements": list(FALSE_POSITIVE_REQUIREMENTS),
        },
        "disabled_config_stub": {
            "id": safe_id,
            "source": "[fill-local-only-in-home-config]",
            "category": category if category_valid else "security",
            "weight": weight,
            "enabled": False,
            "backend": "mtproto",
            "notes": "Curated via dry-run only; keep real source details out of git.",
        },
    }


def review_false_positive(item: dict[str, Any]) -> dict[str, Any]:
    review = _as_mapping(item.get("operator_review"))
    decision = str(review.get("decision") or "needs_review").strip().lower()
    evidence = _as_mapping(review.get("evidence"))
    missing = [name for name in FALSE_POSITIVE_REQUIREMENTS if not evidence.get(name)]
    if decision in {"dismiss_false_positive", "false_positive"}:
        state = "eligible_for_false_positive_label" if not missing else "cannot_dismiss_yet"
    elif decision in {"quarantine", "uphold", "true_positive"}:
        state = "quarantine_or_uphold"
    else:
        state = "needs_operator_review"
    finding = _as_mapping(item.get("finding"))
    return {
        "review_id": _safe_identifier(item.get("review_id") or item.get("id"), fallback="review"),
        "candidate_id": _safe_identifier(item.get("candidate_id") or finding.get("subject")),
        "state": state,
        "operator_decision": decision,
        "missing_requirements": missing,
        "rule_id": _safe_text(finding.get("rule_id"), limit=120),
        "severity": _safe_text(finding.get("severity"), limit=40),
        "summary": _safe_text(finding.get("summary")),
        "required_evidence": list(FALSE_POSITIVE_REQUIREMENTS),
    }


def build_report(packet: dict[str, Any], *, generated_at: str | None = None) -> dict[str, Any]:
    candidates = [
        evaluate_candidate(_as_mapping(item)) for item in _as_list(packet.get("candidates"))
    ]
    reviews = [
        review_false_positive(_as_mapping(item))
        for item in _as_list(packet.get("bot_pump_reviews"))
    ]
    decision_counts = Counter(item["decision"] for item in candidates)
    held = sum(1 for item in candidates if item["decision"].startswith("hold_"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "run_id": _safe_identifier(
            packet.get("run_id") or "telegram-curation-dry-run", fallback="run"
        ),
        "mode": "dry_run",
        "safety": {
            "telegram_contacted": False,
            "telegram_sends_enabled": False,
            "live_collection_enabled": False,
            "trading_critical_path_touched": False,
            "raw_handles_redacted": True,
        },
        "summary": {
            "candidate_count": len(candidates),
            "bot_pump_reviews": len(reviews),
            "held_candidates": held,
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "candidates": candidates,
        "bot_pump_false_positive_reviews": reviews,
        "next_operator_steps": [
            "Keep all real channel handles and private notes in ~/.sapphire/telegram_channels.yaml only.",
            "Do not set enabled=true until the operator accepts a disabled watchlist entry and live gates are separately authorized.",
            "Do not dismiss bot-pump findings unless all false-positive evidence requirements are present.",
        ],
    }


def load_packet(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("input JSON root must be an object")
    return loaded


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", required=True, type=Path, help="Local candidate/review JSON packet"
    )
    parser.add_argument("--output", type=Path, help="Optional report output path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(load_packet(args.input))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2 if args.pretty else None, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
