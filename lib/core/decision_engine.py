"""Decision Engine — adaptive rules over the event bus.

Subscribes to canonical events (`regime.*`, `signal.*`, `sentiment.*`,
`correlation.*`, `threat.*`, `service.*`), maintains a local view of the
world, and emits `decision.made` events whenever a rule fires.

Design:
- **Rules are pure functions of WorldState + triggering Event.** They
  return a `Decision` with an action string, confidence, and rationale.
  No I/O inside rules — the engine handles publishing.
- **Adaptive weighting.** Each rule has an `enabled` flag and a `weight`
  that the engine re-tunes based on recent outcomes (`signal.closed`
  events) — rules that have produced profitable decisions get weighted
  up, rules associated with losses get weighted down (bounded in
  [MIN_WEIGHT, MAX_WEIGHT]).
- **Cooldowns.** Each rule has a per-symbol cooldown to prevent
  firing-storms during volatile regimes.
- **Backfill-safe.** Rules see both the triggering event *and* a
  snapshot of `WorldState` so they can reason about context.

Usage:
    from decision_engine import DecisionEngine

    eng = DecisionEngine()
    eng.start()          # spawns subscriber thread; returns immediately
    ...
    eng.stop()

    # Inspect the current rule weights (dashboard / debug):
    weights = eng.rule_weights()
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from event_bus import Event, EventBus, WorldState, get_bus

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# Weight bounds for adaptive tuning
MIN_WEIGHT = 0.1
MAX_WEIGHT = 3.0
DEFAULT_WEIGHT = 1.0
WEIGHT_STEP = 0.05  # per winning/losing outcome

# Per-rule, per-symbol cooldown so a rule can't fire on every bar
DEFAULT_COOLDOWN_SEC = 300

# Confidence floor — decisions below this are logged but not published
MIN_PUBLISH_CONFIDENCE = 0.30


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Decision:
    """Output of a rule evaluation."""

    rule: str
    action: str              # e.g. "derisk", "tighten_stops", "attention", "hedge"
    symbol: str | None       # subject symbol, None for portfolio-level
    confidence: float        # 0.0–1.0 (after weighting)
    base_confidence: float   # confidence before rule weight applied
    rationale: str
    triggered_by: str        # event type that fired the rule
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    context: dict = field(default_factory=dict)


# A rule is a function that takes (event, world_state) and returns
# Decision|None. Returning None means "this rule didn't match."
Rule = Callable[[Event, WorldState], "Decision | None"]


@dataclass
class _RuleRecord:
    name: str
    fn: Rule
    patterns: list[str]
    enabled: bool = True
    weight: float = DEFAULT_WEIGHT
    fires: int = 0
    wins: int = 0
    losses: int = 0
    cooldown_sec: int = DEFAULT_COOLDOWN_SEC
    # Per-symbol last-fired timestamp for cooldown enforcement
    _last_fire: dict[str, datetime] = field(default_factory=dict)

    def on_cooldown(self, symbol: str | None, now: datetime) -> bool:
        key = symbol or "_portfolio_"
        last = self._last_fire.get(key)
        if last is None:
            return False
        return (now - last) < timedelta(seconds=self.cooldown_sec)

    def record_fire(self, symbol: str | None, now: datetime) -> None:
        key = symbol or "_portfolio_"
        self._last_fire[key] = now
        self.fires += 1


# ---------------------------------------------------------------------------
# DecisionEngine
# ---------------------------------------------------------------------------


class DecisionEngine:
    """Event-bus subscriber that runs adaptive rules and emits decisions."""

    def __init__(
        self,
        bus: EventBus | None = None,
        rules: list[_RuleRecord] | None = None,
    ) -> None:
        self._bus = bus or get_bus(source="decision_engine")
        self._rules: list[_RuleRecord] = rules if rules is not None else _default_rules()
        self._rules_lock = threading.Lock()
        self._sub = None
        # Map symbol → [(rule, decision_ts)] so signal.closed can credit the
        # most recent rule that acted on this symbol.
        self._attribution: dict[str, list[tuple[str, datetime]]] = {}
        self._attribution_lock = threading.Lock()

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def start(self, start_id: str = "$") -> None:
        """Subscribe to the canonical event set and begin evaluating rules.

        start_id="$" (default) reads only new events; pass "0" to replay
        from the beginning — useful for tests.
        """
        patterns = [
            "regime.*",
            "signal.*",
            "sentiment.*",
            "correlation.*",
            "threat.*",
            "funding.*",
            "service.*",
        ]
        self._sub = self._bus.subscribe(patterns, self._on_event, start_id=start_id)
        log.info("decision_engine: subscribed to %s", patterns)

    def stop(self) -> None:
        if self._sub is not None:
            self._sub.stop()
            self._sub = None

    # ── Rule registration ───────────────────────────────────────────────────

    def register_rule(
        self,
        name: str,
        fn: Rule,
        patterns: list[str],
        weight: float = DEFAULT_WEIGHT,
        cooldown_sec: int = DEFAULT_COOLDOWN_SEC,
    ) -> None:
        with self._rules_lock:
            self._rules.append(_RuleRecord(
                name=name, fn=fn, patterns=patterns,
                weight=weight, cooldown_sec=cooldown_sec,
            ))

    def rule_weights(self) -> dict[str, float]:
        with self._rules_lock:
            return {r.name: round(r.weight, 3) for r in self._rules}

    def rule_stats(self) -> list[dict]:
        with self._rules_lock:
            return [
                {
                    "name": r.name, "enabled": r.enabled,
                    "weight": round(r.weight, 3),
                    "fires": r.fires, "wins": r.wins, "losses": r.losses,
                }
                for r in self._rules
            ]

    # ── Core evaluation ─────────────────────────────────────────────────────

    def _on_event(self, ev: Event) -> None:
        """Fired by the EventBus for every matching event."""
        try:
            if ev.type == "signal.closed":
                self._attribute_outcome(ev)
                # Still run rules — closing a signal can trigger follow-ups.

            ws = self._bus.get_world_state()
            self._evaluate(ev, ws)
        except Exception as e:
            log.exception("decision_engine: event handling failed (%s)", e)

    def evaluate_once(self, ev: Event, ws: WorldState | None = None) -> list[Decision]:
        """Synchronous evaluation — useful for tests. Returns all decisions.

        Does NOT publish or advance cooldowns.
        """
        ws = ws or self._bus.get_world_state()
        decisions: list[Decision] = []
        with self._rules_lock:
            rules = list(self._rules)
        for r in rules:
            if not r.enabled or not _matches_any(ev.type, r.patterns):
                continue
            try:
                d = r.fn(ev, ws)
            except Exception as e:
                log.warning("rule %s raised: %s", r.name, e)
                continue
            if d is None:
                continue
            d.confidence = max(0.0, min(1.0, d.base_confidence * r.weight))
            decisions.append(d)
        return decisions

    # ------------------------------------------------------------------

    def _evaluate(self, ev: Event, ws: WorldState) -> None:
        now = datetime.now(UTC)
        published: list[str] = []
        with self._rules_lock:
            rules = list(self._rules)

        for r in rules:
            if not r.enabled or not _matches_any(ev.type, r.patterns):
                continue
            try:
                d = r.fn(ev, ws)
            except Exception as e:
                log.warning("rule %s raised: %s", r.name, e)
                continue
            if d is None:
                continue

            # Apply rule weight — after this, cooldown + publish gates.
            d.confidence = max(0.0, min(1.0, d.base_confidence * r.weight))
            if d.confidence < MIN_PUBLISH_CONFIDENCE:
                continue
            if r.on_cooldown(d.symbol, now):
                continue

            r.record_fire(d.symbol, now)
            self._record_attribution(d.symbol, r.name, now)
            published.append(r.name)

            self._bus.publish("decision.made", {
                "rule": d.rule,
                "action": d.action,
                "symbol": d.symbol,
                "confidence": round(d.confidence, 3),
                "base_confidence": round(d.base_confidence, 3),
                "rationale": d.rationale,
                "triggered_by": d.triggered_by,
                "context": d.context,
            }, source="decision_engine")

        if published:
            log.info("decision_engine: %s → published %s", ev.type, published)

    # ── Adaptive weighting ──────────────────────────────────────────────────

    def _record_attribution(self, symbol: str | None, rule: str, now: datetime) -> None:
        if symbol is None:
            return
        with self._attribution_lock:
            lst = self._attribution.setdefault(symbol, [])
            lst.append((rule, now))
            # Keep only the last 10 attributions per symbol — bounded memory.
            if len(lst) > 10:
                del lst[: len(lst) - 10]

    def _attribute_outcome(self, ev: Event) -> None:
        """Credit the most recent rule(s) that acted on the closed signal's symbol.

        The signal.closed payload carries `symbol` and `pnl_usd` (win vs loss).
        We walk recent attribution entries for that symbol and nudge the
        corresponding rule weights up on wins, down on losses, within
        [MIN_WEIGHT, MAX_WEIGHT].
        """
        symbol = ev.data.get("symbol")
        if not symbol:
            return
        try:
            pnl = float(ev.data.get("pnl_usd") or 0.0)
        except (TypeError, ValueError):
            return
        if pnl == 0:
            return

        with self._attribution_lock:
            recents = list(self._attribution.get(symbol, []))

        if not recents:
            return

        # Credit the most-recent rule (most proximate cause).
        rule_name, _ = recents[-1]
        with self._rules_lock:
            for r in self._rules:
                if r.name != rule_name:
                    continue
                if pnl > 0:
                    r.wins += 1
                    r.weight = min(MAX_WEIGHT, r.weight + WEIGHT_STEP)
                else:
                    r.losses += 1
                    r.weight = max(MIN_WEIGHT, r.weight - WEIGHT_STEP)
                log.info(
                    "decision_engine: rule %s → %s (pnl=%.2f, weight=%.2f)",
                    rule_name, "win" if pnl > 0 else "loss", pnl, r.weight,
                )
                break


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matches_any(event_type: str, patterns: list[str]) -> bool:
    import fnmatch
    return any(fnmatch.fnmatchcase(event_type, p) for p in patterns)


# ---------------------------------------------------------------------------
# Default rules
# ---------------------------------------------------------------------------


def _rule_regime_shift_derisk(ev: Event, ws: WorldState) -> Decision | None:
    """On regime shift to RISK_OFF, emit portfolio-level derisk recommendation."""
    if ev.type not in ("regime.shifted", "regime.snapshot"):
        return None
    new_regime = ev.data.get("regime") or ev.data.get("new_regime")
    if new_regime != "RISK_OFF":
        return None
    conf = float(ev.data.get("confidence") or ev.data.get("regime_confidence") or 0.6)
    return Decision(
        rule="regime_shift_derisk",
        action="derisk",
        symbol=None,
        confidence=conf,
        base_confidence=conf,
        rationale=f"Regime → RISK_OFF (confidence {conf:.2f}); reduce exposure",
        triggered_by=ev.type,
        context={"prior_regime": ev.data.get("prior_regime"), "regime": new_regime},
    )


def _rule_threat_tighten_stops(ev: Event, ws: WorldState) -> Decision | None:
    """On high/critical threat detection, tighten stops across all positions."""
    if ev.type != "threat.detected":
        return None
    level = str(ev.data.get("level", "")).lower()
    if level not in ("high", "critical"):
        return None
    conf = 0.85 if level == "critical" else 0.65
    return Decision(
        rule="threat_tighten_stops",
        action="tighten_stops",
        symbol=None,
        confidence=conf,
        base_confidence=conf,
        rationale=f"Threat level {level} → pre-emptively tighten stops",
        triggered_by=ev.type,
        context={"threat_level": level, "cve": ev.data.get("cve")},
    )


def _rule_decorrelation_attention(ev: Event, ws: WorldState) -> Decision | None:
    """When a tracked pair decouples, flag symbols in that pair for attention."""
    if ev.type != "correlation.broken":
        return None
    pair = ev.data.get("pair") or []
    if not isinstance(pair, list) or len(pair) < 2:
        return None
    severity = str(ev.data.get("severity", "moderate")).lower()
    conf = {"severe": 0.85, "moderate": 0.60, "mild": 0.40}.get(severity, 0.50)
    symbol = pair[0] if isinstance(pair[0], str) else None
    return Decision(
        rule="decorrelation_attention",
        action="attention",
        symbol=symbol,
        confidence=conf,
        base_confidence=conf,
        rationale=f"{pair[0]}↔{pair[1]} decoupled ({severity})",
        triggered_by=ev.type,
        context={"pair": pair, "severity": severity},
    )


def _rule_extreme_funding_fade(ev: Event, ws: WorldState) -> Decision | None:
    """On extreme funding rates, fade the crowded side."""
    if ev.type != "funding.extreme":
        return None
    symbol = ev.data.get("symbol")
    bias = str(ev.data.get("bias", "")).lower()
    rate = float(ev.data.get("rate") or 0.0)
    if bias not in ("long", "short") or not symbol:
        return None
    conf = min(0.9, 0.5 + abs(rate) * 500)  # 0.05% funding → 0.75 confidence
    action = "fade_long" if bias == "long" else "fade_short"
    return Decision(
        rule="extreme_funding_fade",
        action=action,
        symbol=symbol,
        confidence=conf,
        base_confidence=conf,
        rationale=f"Funding bias={bias} @ {rate:+.4%} on {symbol} → crowded, fade",
        triggered_by=ev.type,
        context={"bias": bias, "rate": rate},
    )


def _rule_fear_greed_contrarian(ev: Event, ws: WorldState) -> Decision | None:
    """Classic contrarian play: extreme fear → accumulate, extreme greed → trim."""
    if ev.type != "sentiment.update":
        return None
    fg = ev.data.get("fear_greed")
    if not isinstance(fg, (int, float)):
        return None
    fg = int(fg)
    if fg <= 20:
        action, rationale, conf = "accumulate", f"Extreme fear (F&G={fg}) → contrarian accumulate", 0.65
    elif fg >= 80:
        action, rationale, conf = "trim", f"Extreme greed (F&G={fg}) → contrarian trim", 0.65
    else:
        return None
    return Decision(
        rule="fear_greed_contrarian",
        action=action,
        symbol=None,
        confidence=conf,
        base_confidence=conf,
        rationale=rationale,
        triggered_by=ev.type,
        context={"fear_greed": fg},
    )


def _rule_service_health_pause(ev: Event, ws: WorldState) -> Decision | None:
    """On infrastructure health turning critical, recommend pausing new entries."""
    if ev.type != "service.health":
        return None
    status = str(ev.data.get("status", "")).lower()
    if status != "critical":
        return None
    return Decision(
        rule="service_health_pause",
        action="pause_entries",
        symbol=None,
        confidence=0.90,
        base_confidence=0.90,
        rationale=f"Infrastructure health = critical ({ev.data.get('service', 'unknown')})",
        triggered_by=ev.type,
        context={"service": ev.data.get("service"), "status": status},
    )


def _default_rules() -> list[_RuleRecord]:
    return [
        _RuleRecord(
            name="regime_shift_derisk",
            fn=_rule_regime_shift_derisk,
            patterns=["regime.shifted", "regime.snapshot"],
        ),
        _RuleRecord(
            name="threat_tighten_stops",
            fn=_rule_threat_tighten_stops,
            patterns=["threat.detected"],
        ),
        _RuleRecord(
            name="decorrelation_attention",
            fn=_rule_decorrelation_attention,
            patterns=["correlation.broken"],
        ),
        _RuleRecord(
            name="extreme_funding_fade",
            fn=_rule_extreme_funding_fade,
            patterns=["funding.extreme"],
        ),
        _RuleRecord(
            name="fear_greed_contrarian",
            fn=_rule_fear_greed_contrarian,
            patterns=["sentiment.update"],
        ),
        _RuleRecord(
            name="service_health_pause",
            fn=_rule_service_health_pause,
            patterns=["service.health"],
        ),
    ]


__all__ = [
    "Decision",
    "DecisionEngine",
    "Rule",
    "MIN_PUBLISH_CONFIDENCE",
]


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import signal as _signal
    import time

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    eng = DecisionEngine()
    eng.start()
    print(f"decision_engine: live on bus. rules={list(eng.rule_weights().keys())}")

    def _shutdown(_sig, _frm):
        eng.stop()
        raise SystemExit(0)

    _signal.signal(_signal.SIGINT, _shutdown)
    _signal.signal(_signal.SIGTERM, _shutdown)
    while True:
        time.sleep(3600)
