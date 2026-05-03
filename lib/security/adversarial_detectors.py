"""Pure adversarial intelligence detectors for Sapphire.

The detectors in this module are intentionally deterministic and side-effect
free. They accept already-collected records, return structured findings, and do
not mutate upstream signal, Telegram, oracle, or threat-intel inputs.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from statistics import median
from typing import Any

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AdversarialFinding:
    """One adversarial signal emitted by a detector."""

    detector: str
    rule_id: str
    severity: str
    confidence: float
    score: float
    subject: str
    summary: str
    evidence: tuple[str, ...] = ()
    recommended_action: str = "manual_review"
    quarantine_eligible: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["confidence"] = round(float(self.confidence), 4)
        data["score"] = round(float(self.score), 4)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True)
class DetectorReport:
    """Structured result for one detector pass."""

    detector: str
    checked: int
    findings: tuple[AdversarialFinding, ...] = ()
    generated_at: str = field(default_factory=utc_now_iso)

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def severity(self) -> str:
        if not self.findings:
            return "info"
        return max(self.findings, key=lambda item: SEVERITY_ORDER.get(item.severity, 0)).severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "checked": self.checked,
            "clean": self.clean,
            "severity": self.severity,
            "generated_at": self.generated_at,
            "findings": [finding.to_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class CombinedAdversarialReport:
    """Combined report across multiple detector passes."""

    reports: tuple[DetectorReport, ...]
    generated_at: str = field(default_factory=utc_now_iso)

    @property
    def findings(self) -> tuple[AdversarialFinding, ...]:
        return tuple(finding for report in self.reports for finding in report.findings)

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def severity(self) -> str:
        if not self.findings:
            return "info"
        return max(self.findings, key=lambda item: SEVERITY_ORDER.get(item.severity, 0)).severity

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "clean": self.clean,
            "severity": self.severity,
            "findings_count": len(self.findings),
            "reports": [report.to_dict() for report in self.reports],
        }


def combine_reports(reports: Iterable[DetectorReport]) -> CombinedAdversarialReport:
    return CombinedAdversarialReport(tuple(reports))


def _coerce_rows(records: Iterable[Mapping[str, Any] | str]) -> list[Mapping[str, Any] | str]:
    return list(records or [])


def _value(row: Mapping[str, Any], names: Sequence[str], default: Any = "") -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower_id(value: Any) -> str:
    text = _text(value).lower()
    return re.sub(r"\s+", " ", text)


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int | float):
        number = float(value)
        return number if math.isfinite(number) else default
    text = _text(value).replace(",", "")
    if not text:
        return default
    try:
        number = float(text)
    except ValueError:
        return default
    return number if math.isfinite(number) else default


def _timestamp_seconds(value: Any) -> float:
    if isinstance(value, int | float):
        return float(value)
    text = _text(value)
    if not text:
        return 0.0
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _pct_delta(left: float, right: float) -> float:
    base = max(abs(left), abs(right), 1e-12)
    return abs(left - right) / base


def _snippet(text: str, match: re.Match[str] | None = None, *, limit: int = 160) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not match:
        return compact[:limit]
    start = max(0, match.start() - 40)
    end = min(len(compact), match.end() + 80)
    return compact[start:end][:limit]


class WashTradeDetector:
    """Detect obvious self-trading and reciprocal round-trip wash patterns."""

    detector_name = "wash_trade"

    BUYER_FIELDS = ("buyer", "buyer_account", "buy_account", "taker", "taker_account")
    SELLER_FIELDS = ("seller", "seller_account", "sell_account", "maker", "maker_account")
    SYMBOL_FIELDS = ("symbol", "asset", "market", "pair")
    QUANTITY_FIELDS = ("quantity", "qty", "amount", "size", "base_amount")
    PRICE_FIELDS = ("price", "trade_price", "fill_price")
    TIME_FIELDS = ("timestamp", "ts", "time", "created_at")
    ID_FIELDS = ("id", "trade_id", "order_id", "tx_hash", "hash")

    def __init__(
        self,
        *,
        reciprocal_window_seconds: int = 90,
        min_round_trips: int = 3,
        max_price_delta_pct: float = 0.0025,
        max_quantity_delta_pct: float = 0.05,
    ) -> None:
        self.reciprocal_window_seconds = reciprocal_window_seconds
        self.min_round_trips = min_round_trips
        self.max_price_delta_pct = max_price_delta_pct
        self.max_quantity_delta_pct = max_quantity_delta_pct

    def analyze(self, trades: Iterable[Mapping[str, Any]]) -> DetectorReport:
        rows = [row for row in trades if isinstance(row, Mapping)]
        events = [self._normalize_trade(row, index) for index, row in enumerate(rows)]
        findings: list[AdversarialFinding] = []

        for event in events:
            buyer = event["buyer"]
            seller = event["seller"]
            if buyer and seller and buyer == seller:
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="self_trade_same_account",
                        severity="high",
                        confidence=0.96,
                        score=0.92,
                        subject=f"{event['symbol']}:{buyer}",
                        summary="Trade has the same normalized buyer and seller account.",
                        evidence=(
                            f"trade_id={event['id']}",
                            f"symbol={event['symbol']}",
                            f"quantity={event['quantity']}",
                            f"price={event['price']}",
                        ),
                        recommended_action="exclude_from_signal_features_and_review_account_links",
                        quarantine_eligible=True,
                    )
                )

        pair_matches: dict[tuple[str, str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = (
            defaultdict(list)
        )
        ordered = sorted(
            [event for event in events if event["buyer"] and event["seller"]],
            key=lambda item: item["timestamp"],
        )
        for left_index, left in enumerate(ordered):
            if left["buyer"] == left["seller"]:
                continue
            for right in ordered[left_index + 1 :]:
                delta = right["timestamp"] - left["timestamp"]
                if delta > self.reciprocal_window_seconds:
                    break
                if delta < 0 or left["symbol"] != right["symbol"]:
                    continue
                if left["buyer"] != right["seller"] or left["seller"] != right["buyer"]:
                    continue
                if not self._near_match(left, right):
                    continue
                pair = tuple(sorted((left["buyer"], left["seller"]))) + (left["symbol"],)
                pair_matches[pair].append((left, right))

        for (account_a, account_b, symbol), matches in pair_matches.items():
            if len(matches) < self.min_round_trips:
                continue
            evidence = tuple(
                f"{left['id']}<->{right['id']} dt={int(right['timestamp'] - left['timestamp'])}s"
                for left, right in matches[:5]
            )
            findings.append(
                AdversarialFinding(
                    detector=self.detector_name,
                    rule_id="reciprocal_round_trip_cluster",
                    severity="high",
                    confidence=min(0.99, 0.78 + len(matches) * 0.04),
                    score=min(1.0, 0.70 + len(matches) * 0.05),
                    subject=f"{symbol}:{account_a}<->{account_b}",
                    summary="Accounts repeatedly trade the same symbol in opposite directions with near-identical size and price.",
                    evidence=evidence,
                    recommended_action="downweight_volume_and_require_independent_venue_confirmation",
                    quarantine_eligible=True,
                    metadata={
                        "round_trips": len(matches),
                        "window_seconds": self.reciprocal_window_seconds,
                    },
                )
            )

        return DetectorReport(self.detector_name, checked=len(rows), findings=tuple(findings))

    def _normalize_trade(self, row: Mapping[str, Any], index: int) -> dict[str, Any]:
        quantity = _float(_value(row, self.QUANTITY_FIELDS))
        price = _float(_value(row, self.PRICE_FIELDS))
        return {
            "id": _text(_value(row, self.ID_FIELDS, f"row-{index}")) or f"row-{index}",
            "buyer": _lower_id(_value(row, self.BUYER_FIELDS)),
            "seller": _lower_id(_value(row, self.SELLER_FIELDS)),
            "symbol": _lower_id(_value(row, self.SYMBOL_FIELDS, "unknown")) or "unknown",
            "quantity": quantity,
            "price": price,
            "timestamp": _timestamp_seconds(_value(row, self.TIME_FIELDS)),
        }

    def _near_match(self, left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        left_qty = float(left["quantity"])
        right_qty = float(right["quantity"])
        left_price = float(left["price"])
        right_price = float(right["price"])
        if left_qty <= 0 or right_qty <= 0 or left_price <= 0 or right_price <= 0:
            return False
        return (
            _pct_delta(left_qty, right_qty) <= self.max_quantity_delta_pct
            and _pct_delta(left_price, right_price) <= self.max_price_delta_pct
        )


class BotPumpedChannelDetector:
    """Detect Telegram-style pump coordination and bot-amplified hype."""

    detector_name = "bot_pumped_channel"

    TEXT_FIELDS = ("text", "message", "content", "body", "summary")
    CHANNEL_FIELDS = ("channel_id", "channel", "source", "room")
    AUTHOR_FIELDS = ("author", "author_id", "sender", "user")
    TIME_FIELDS = ("timestamp", "published_at", "ts", "time", "created_at")

    PUMP_RE = re.compile(
        r"\b(pump|moon|ape|send\s+it|buy\s+now|target\s+coin|coin\s+reveal|"
        r"next\s+call|entry\s+now|raid|shill|trend\s+this|hold\s+the\s+line)\b",
        re.I,
    )
    PROFIT_RE = re.compile(
        r"\b(guaranteed|risk[-\s]?free|profit|100x|50x|10x|[3-9]\d{2,}%|"
        r"1,?000%|no\s+risk)\b",
        re.I,
    )
    BOT_RE = re.compile(
        r"\b(bot|sniper|auto[-\s]?buy|copy[-\s]?trade|api\s+faster|"
        r"execute\s+in\s+seconds|auto[-\s]?sell)\b",
        re.I,
    )
    COORDINATION_RE = re.compile(
        r"\b(everyone|all\s+members|coordinated|same\s+time|share\s+everywhere|"
        r"raid\s+twitter|do\s+not\s+sell|hold\s+until)\b",
        re.I,
    )
    CASHTAG_RE = re.compile(r"(?<!\w)(?:[$#][A-Z][A-Z0-9]{1,9}|[A-Z]{2,10}/USDT)\b")

    def __init__(self, *, burst_window_seconds: int = 600, min_burst_messages: int = 4) -> None:
        self.burst_window_seconds = burst_window_seconds
        self.min_burst_messages = min_burst_messages

    def analyze(self, messages: Iterable[Mapping[str, Any]]) -> DetectorReport:
        rows = [row for row in messages if isinstance(row, Mapping)]
        normalized = [self._normalize_message(row, index) for index, row in enumerate(rows)]
        findings: list[AdversarialFinding] = []

        suspicious: list[dict[str, Any]] = []
        for message in normalized:
            score, reasons = self._score_message(message["text"])
            message["score"] = score
            message["reasons"] = reasons
            if score >= 3:
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="pump_language_with_bot_or_profit_claim",
                        severity="medium",
                        confidence=min(0.95, 0.55 + score * 0.08),
                        score=min(1.0, score / 6.0),
                        subject=message["channel"],
                        summary="Message combines pump coordination language with bot execution or unrealistic profit claims.",
                        evidence=tuple(reasons[:5]) + (_snippet(message["text"]),),
                        recommended_action="treat_channel_signal_as_untrusted_until_cross_source_confirmation",
                        quarantine_eligible=True,
                    )
                )
            if score >= 2:
                suspicious.append(message)

        by_channel: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for message in suspicious:
            by_channel[message["channel"]].append(message)
        for channel, channel_messages in by_channel.items():
            channel_messages.sort(key=lambda item: item["timestamp"])
            burst = self._find_burst(channel_messages)
            if not burst:
                continue
            authors = {item["author"] for item in burst if item["author"]}
            evidence = tuple(
                f"{item['id']} score={item['score']} reasons={','.join(item['reasons'][:3])}"
                for item in burst[:5]
            )
            findings.append(
                AdversarialFinding(
                    detector=self.detector_name,
                    rule_id="coordinated_pump_burst",
                    severity="high",
                    confidence=min(0.98, 0.70 + len(burst) * 0.04),
                    score=min(1.0, 0.65 + len(burst) * 0.05),
                    subject=channel,
                    summary="Channel has a burst of pump-like messages inside the configured coordination window.",
                    evidence=evidence,
                    recommended_action="quarantine_channel_outputs_pending_operator_review",
                    quarantine_eligible=True,
                    metadata={
                        "burst_messages": len(burst),
                        "unique_authors": len(authors),
                        "window_seconds": self.burst_window_seconds,
                    },
                )
            )

        return DetectorReport(self.detector_name, checked=len(rows), findings=tuple(findings))

    def _normalize_message(self, row: Mapping[str, Any], index: int) -> dict[str, Any]:
        return {
            "id": _text(_value(row, ("id", "message_id"), f"row-{index}")) or f"row-{index}",
            "text": _text(_value(row, self.TEXT_FIELDS)),
            "channel": _lower_id(_value(row, self.CHANNEL_FIELDS, "unknown")) or "unknown",
            "author": _lower_id(_value(row, self.AUTHOR_FIELDS)),
            "timestamp": _timestamp_seconds(_value(row, self.TIME_FIELDS)),
        }

    def _score_message(self, text: str) -> tuple[int, list[str]]:
        reasons: list[str] = []
        if self.PUMP_RE.search(text):
            reasons.append("pump-language")
        if self.PROFIT_RE.search(text):
            reasons.append("unrealistic-profit-claim")
        if self.BOT_RE.search(text):
            reasons.append("bot-or-sniper-execution")
        if self.COORDINATION_RE.search(text):
            reasons.append("coordination-call")
        if len(self.CASHTAG_RE.findall(text)) >= 2:
            reasons.append("multiple-cashtags")
        if _repeated_symbol_ratio(text) > 0.18 and len(text) > 60:
            reasons.append("spammy-repetition")
        return len(reasons), reasons

    def _find_burst(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(messages) < self.min_burst_messages:
            return []
        for start, left in enumerate(messages):
            burst = [
                item
                for item in messages[start:]
                if item["timestamp"] - left["timestamp"] <= self.burst_window_seconds
            ]
            if len(burst) >= self.min_burst_messages:
                return burst
        return []


def _repeated_symbol_ratio(text: str) -> float:
    if not text:
        return 0.0
    repeated = sum(1 for char in text if char in "!$#*")
    return repeated / max(1, len(text))


class OracleAnomalyDetector:
    """Detect source divergence and abrupt reference-price oracle anomalies."""

    detector_name = "oracle_anomaly"

    ASSET_FIELDS = ("asset", "symbol", "market", "pair")
    SOURCE_FIELDS = ("source", "venue", "oracle", "provider")
    PRICE_FIELDS = ("price", "oracle_price", "value", "mark_price")
    REFERENCE_FIELDS = ("reference_price", "median_price", "twap_price", "index_price")
    TIME_FIELDS = ("timestamp", "ts", "time", "observed_at")

    def __init__(
        self,
        *,
        source_divergence_pct: float = 0.20,
        reference_divergence_pct: float = 0.25,
        bucket_seconds: int = 60,
    ) -> None:
        self.source_divergence_pct = source_divergence_pct
        self.reference_divergence_pct = reference_divergence_pct
        self.bucket_seconds = bucket_seconds

    def analyze(self, observations: Iterable[Mapping[str, Any]]) -> DetectorReport:
        rows = [row for row in observations if isinstance(row, Mapping)]
        normalized = [self._normalize_observation(row, index) for index, row in enumerate(rows)]
        findings: list[AdversarialFinding] = []

        for item in normalized:
            reference = item["reference_price"]
            price = item["price"]
            if price <= 0 or reference <= 0:
                continue
            delta = abs(price - reference) / reference
            if delta >= self.reference_divergence_pct:
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="reference_price_divergence",
                        severity="high",
                        confidence=min(0.98, 0.70 + delta),
                        score=min(1.0, delta),
                        subject=f"{item['asset']}:{item['source']}",
                        summary="Oracle price diverges materially from supplied reference, TWAP, or index price.",
                        evidence=(
                            f"id={item['id']}",
                            f"price={price}",
                            f"reference={reference}",
                            f"delta_pct={delta:.2%}",
                        ),
                        recommended_action="require_independent_oracle_confirmation_before_any_signal_use",
                        quarantine_eligible=True,
                    )
                )

        buckets: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for item in normalized:
            if item["price"] <= 0:
                continue
            bucket = int(item["timestamp"] // self.bucket_seconds) if item["timestamp"] else 0
            buckets[(item["asset"], bucket)].append(item)

        for (asset, bucket), items in buckets.items():
            sources = {item["source"] for item in items if item["source"]}
            if len(items) < 3 or len(sources) < 3:
                continue
            med = median(item["price"] for item in items)
            if med <= 0:
                continue
            for item in items:
                delta = abs(item["price"] - med) / med
                if delta < self.source_divergence_pct:
                    continue
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="cross_source_oracle_outlier",
                        severity="high",
                        confidence=min(0.98, 0.72 + delta),
                        score=min(1.0, delta),
                        subject=f"{asset}:{item['source']}",
                        summary="One oracle/source is an outlier against same-minute cross-source median.",
                        evidence=(
                            f"id={item['id']}",
                            f"bucket={bucket}",
                            f"source_price={item['price']}",
                            f"cross_source_median={med}",
                            f"delta_pct={delta:.2%}",
                        ),
                        recommended_action="exclude_outlier_source_from_composite_until_reconciled",
                        quarantine_eligible=True,
                    )
                )

        return DetectorReport(self.detector_name, checked=len(rows), findings=tuple(findings))

    def _normalize_observation(self, row: Mapping[str, Any], index: int) -> dict[str, Any]:
        return {
            "id": _text(_value(row, ("id", "observation_id"), f"row-{index}")) or f"row-{index}",
            "asset": _lower_id(_value(row, self.ASSET_FIELDS, "unknown")) or "unknown",
            "source": _lower_id(_value(row, self.SOURCE_FIELDS, "unknown")) or "unknown",
            "price": _float(_value(row, self.PRICE_FIELDS)),
            "reference_price": _float(_value(row, self.REFERENCE_FIELDS)),
            "timestamp": _timestamp_seconds(_value(row, self.TIME_FIELDS)),
        }


class PromptInjectionDetector:
    """Detect direct and indirect prompt-injection payloads in untrusted text."""

    detector_name = "prompt_injection"

    TEXT_FIELDS = ("text", "message", "content", "body", "prompt", "summary")
    ID_FIELDS = ("id", "message_id", "document_id", "source_id")

    PATTERNS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
        (
            "instruction_override",
            "high",
            "Prompt tries to override system, developer, or prior instructions.",
            re.compile(
                r"\b(ignore|disregard|override|forget)\s+(all\s+)?"
                r"(previous|prior|above|system|developer)\s+(instructions|rules|messages)\b",
                re.I,
            ),
        ),
        (
            "jailbreak_persona",
            "high",
            "Prompt attempts to assign an unrestricted or jailbreak persona.",
            re.compile(
                r"\byou\s+are\s+now\s+(dan|jailbroken|unrestricted|developer\s+mode)\b", re.I
            ),
        ),
        (
            "secret_exfiltration_request",
            "critical",
            "Prompt asks the model to reveal or transmit protected secrets or prompts.",
            re.compile(
                r"\b(reveal|print|dump|show|send|exfiltrate|upload)\b.{0,80}"
                r"\b(system\s+prompt|developer\s+message|api[_\s-]?key|secret|token|password|private\s+key)\b",
                re.I,
            ),
        ),
        (
            "tool_hijack",
            "high",
            "Prompt tries to coerce shell, network, or code execution through a tool.",
            re.compile(
                r"\b(run|execute|call|invoke)\b.{0,80}"
                r"\b(shell|bash|curl|wget|subprocess|os\.system|rm\s+-rf|python\s+-c)\b",
                re.I,
            ),
        ),
        (
            "indirect_external_content_hijack",
            "high",
            "External content contains instructions addressed to an AI agent.",
            re.compile(
                r"\b(assistant|agent|llm|model)\b.{0,80}"
                r"\b(must|should|will)\b.{0,80}\b(ignore|override|send|exfiltrate|tool)\b",
                re.I,
            ),
        ),
        (
            "hidden_html_instruction",
            "medium",
            "Hidden HTML or markdown appears to carry agent-facing instructions.",
            re.compile(
                r"(?is)<(?:span|div|p)[^>]*(?:display\s*:\s*none|visibility\s*:\s*hidden)[^>]*>.*?"
                r"\b(ignore|override|send|exfiltrate|tool)\b.*?</(?:span|div|p)>",
            ),
        ),
    )

    ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")
    BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{80,}={0,2}\b")

    def analyze(self, items: Iterable[Mapping[str, Any] | str]) -> DetectorReport:
        rows = _coerce_rows(items)
        findings: list[AdversarialFinding] = []

        for index, item in enumerate(rows):
            item_id, text = self._extract_item(item, index)
            if not text:
                continue
            for rule_id, severity, summary, pattern in self.PATTERNS:
                match = pattern.search(text)
                if not match:
                    continue
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id=rule_id,
                        severity=severity,
                        confidence=0.94 if severity == "critical" else 0.88,
                        score=0.95 if severity == "critical" else 0.82,
                        subject=item_id,
                        summary=summary,
                        evidence=(_snippet(text, match),),
                        recommended_action="treat_content_as_untrusted_and_strip_before_model_context",
                        quarantine_eligible=True,
                    )
                )

            zero_width_count = len(self.ZERO_WIDTH_RE.findall(text))
            if zero_width_count >= 3 and re.search(
                r"(?i)\b(ignore|override|secret|tool|send)\b", text
            ):
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="zero_width_instruction_smuggling",
                        severity="medium",
                        confidence=0.80,
                        score=min(1.0, 0.55 + zero_width_count / 20),
                        subject=item_id,
                        summary="Text uses repeated zero-width characters around instruction-like terms.",
                        evidence=(f"zero_width_count={zero_width_count}", _snippet(text)),
                        recommended_action="normalize_unicode_and_review_untrusted_content",
                        quarantine_eligible=True,
                    )
                )

            for match in self.BASE64_RE.finditer(text):
                if not _decoded_base64_has_instruction(match.group(0)):
                    continue
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="encoded_instruction_blob",
                        severity="medium",
                        confidence=0.76,
                        score=0.66,
                        subject=item_id,
                        summary="Long base64-like blob decodes to instruction-like text.",
                        evidence=(_snippet(text, match),),
                        recommended_action="decode_and_sandbox_before_any_model_ingest",
                        quarantine_eligible=True,
                    )
                )

        return DetectorReport(self.detector_name, checked=len(rows), findings=tuple(findings))

    def _extract_item(self, item: Mapping[str, Any] | str, index: int) -> tuple[str, str]:
        if isinstance(item, str):
            return f"text-{index}", item
        if not isinstance(item, Mapping):
            return f"row-{index}", ""
        item_id = _text(_value(item, self.ID_FIELDS, f"row-{index}")) or f"row-{index}"
        return item_id, _text(_value(item, self.TEXT_FIELDS))


def _decoded_base64_has_instruction(value: str) -> bool:
    try:
        decoded = base64.b64decode(value + ("=" * (-len(value) % 4)), validate=False)
    except (binascii.Error, ValueError):
        return False
    try:
        text = decoded.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return False
    return bool(
        re.search(r"(?i)\b(ignore|override|system prompt|secret|developer message)\b", text)
    )


class FalseFlagThreatIntelDetector:
    """Detect attribution claims that need false-flag or confidence review."""

    detector_name = "false_flag_threat_intel"

    TEXT_FIELDS = ("title", "summary", "body", "description", "analysis", "claim")
    CLAIMED_FIELDS = ("claimed_actor", "public_claim_actor", "actor_claim", "claim_actor")
    ASSESSED_FIELDS = ("assessed_actor", "likely_actor", "ttp_match_actor", "cluster_actor")
    CONFIDENCE_FIELDS = ("confidence", "attribution_confidence")

    FALSE_FLAG_RE = re.compile(
        r"\b(false\s+flag|hacktivist\s+persona|front\s+group|spoofed\s+attribution|"
        r"claimed\s+by.+but|disguised\s+as\s+ransomware|feigned\s+extortion|"
        r"misdirect\s+attribution)\b",
        re.I,
    )
    HARD_ATTRIBUTION_RE = re.compile(
        r"\b(definitively|definitely|confirmed|we\s+attribute|attributed\s+to|"
        r"responsible\s+for|was\s+conducted\s+by)\b",
        re.I,
    )
    LOW_CONFIDENCE_RE = re.compile(
        r"\b(low\s+confidence|unconfirmed|single\s+source|uncorroborated|"
        r"possible|suspected|alleged)\b",
        re.I,
    )

    def analyze(self, reports: Iterable[Mapping[str, Any]]) -> DetectorReport:
        rows = [row for row in reports if isinstance(row, Mapping)]
        findings: list[AdversarialFinding] = []

        for index, row in enumerate(rows):
            item_id = (
                _text(_value(row, ("id", "report_id", "slug"), f"row-{index}")) or f"row-{index}"
            )
            text = self._report_text(row)
            claimed = _lower_id(_value(row, self.CLAIMED_FIELDS))
            assessed = _lower_id(_value(row, self.ASSESSED_FIELDS))
            confidence = self._confidence(row, text)

            if claimed and assessed and claimed != assessed:
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="claimed_actor_conflicts_with_ttp_assessment",
                        severity="high",
                        confidence=0.87,
                        score=0.84,
                        subject=item_id,
                        summary="Public claim actor differs from assessed actor or TTP cluster.",
                        evidence=(f"claimed={claimed}", f"assessed={assessed}"),
                        recommended_action="separate_claimed_responsibility_from_sapphire_attribution",
                        quarantine_eligible=True,
                    )
                )

            false_flag_match = self.FALSE_FLAG_RE.search(text)
            if false_flag_match:
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="false_flag_or_persona_marker",
                        severity="medium",
                        confidence=0.82,
                        score=0.74,
                        subject=item_id,
                        summary="Report text includes false-flag, persona, or feigned-extortion attribution markers.",
                        evidence=(_snippet(text, false_flag_match),),
                        recommended_action="retain_as_claimed_actor_only_until_correlated",
                        quarantine_eligible=False,
                    )
                )

            if confidence < 0.50 and self.HARD_ATTRIBUTION_RE.search(text):
                match = self.HARD_ATTRIBUTION_RE.search(text)
                findings.append(
                    AdversarialFinding(
                        detector=self.detector_name,
                        rule_id="hard_attribution_on_low_confidence_report",
                        severity="medium",
                        confidence=0.78,
                        score=0.68,
                        subject=item_id,
                        summary="Low-confidence or weakly corroborated reporting uses hard attribution language.",
                        evidence=(f"confidence={confidence:.2f}", _snippet(text, match)),
                        recommended_action="downgrade_to_cluster_or_claim_language_before_distribution",
                        quarantine_eligible=False,
                    )
                )

        return DetectorReport(self.detector_name, checked=len(rows), findings=tuple(findings))

    def _report_text(self, row: Mapping[str, Any]) -> str:
        parts = [_text(_value(row, (field,))) for field in self.TEXT_FIELDS]
        parts.extend(
            [
                _text(_value(row, self.CLAIMED_FIELDS)),
                _text(_value(row, self.ASSESSED_FIELDS)),
                _text(_value(row, self.CONFIDENCE_FIELDS)),
            ]
        )
        return " ".join(part for part in parts if part)

    def _confidence(self, row: Mapping[str, Any], text: str) -> float:
        raw = _value(row, self.CONFIDENCE_FIELDS, "")
        numeric = _float(raw, default=-1.0)
        if 0.0 <= numeric <= 1.0:
            return numeric
        label = _text(raw).lower()
        if label in {"high", "strong"}:
            return 0.85
        if label in {"medium", "moderate"}:
            return 0.60
        if label in {"low", "weak"}:
            return 0.30
        if self.LOW_CONFIDENCE_RE.search(text):
            return 0.35
        return 0.70


__all__ = [
    "AdversarialFinding",
    "BotPumpedChannelDetector",
    "CombinedAdversarialReport",
    "DetectorReport",
    "FalseFlagThreatIntelDetector",
    "OracleAnomalyDetector",
    "PromptInjectionDetector",
    "WashTradeDetector",
    "combine_reports",
]
