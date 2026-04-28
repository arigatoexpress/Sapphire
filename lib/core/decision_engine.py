"""Adaptive decision engine — evaluate signals against world state.

Reads regime/funding/sentiment from `data/intelligence/latest/chain.json` and
applies a rule set that can adjust signal confidence, block entries, or fire
alerts when the macro picture shifts. Each evaluation is logged to
`data/decisions/YYYY-MM-DD.jsonl` for later feature-importance analysis.

Rules shipped:
  - regime_penalty: reduce confidence for entries fighting the prevailing regime
  - funding_crowding: flag extreme funding rates (> |0.10%| / 8h) as crowded
  - fear_contrarian: fade extreme fear (F&G < 20) on longs, add bonus
  - regime_shift: compare live regime to the last-seen regime; alert on change

Usage:
    from lib.core.decision_engine import DecisionEngine
    eng = DecisionEngine()
    decision = eng.evaluate({"symbol": "BTC", "direction": "long", "confidence": 0.70})
    # → Decision(verdict="ALLOW", adjusted_confidence=0.78, reasons=[...])

    # Check for regime shifts as a standalone pass:
    alerts = eng.scan_alerts()
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

try:
    from lib.core.autonomy_audit import AutonomyAuditLog
except ModuleNotFoundError:  # pragma: no cover - direct script execution fallback
    from autonomy_audit import AutonomyAuditLog

log = logging.getLogger(__name__)

DEFAULT_CHAIN_PATH = Path("data/intelligence/latest/chain.json")
DEFAULT_DECISIONS_DIR = Path("data/decisions")
DEFAULT_STATE_PATH = Path("data/decisions/_last_regime.json")


@dataclass
class Decision:
    """Outcome of evaluating a signal against world state."""

    signal_id: str
    symbol: str
    direction: str
    original_confidence: float
    adjusted_confidence: float
    verdict: str  # ALLOW | REDUCE | BLOCK | ALERT_ONLY
    reasons: list[str] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)
    world_snapshot: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


@dataclass
class Alert:
    """Macro alert — regime shift, funding spike, etc."""

    kind: str  # regime_shift | funding_extreme | fear_extreme
    severity: str  # info | warn | critical
    message: str
    data: dict = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


# ─── Rule protocol ────────────────────────────────────────────────────────────


class Rule(Protocol):
    name: str

    def evaluate(self, signal: dict, world: dict) -> tuple[float, str] | None:  # noqa: D401
        """Return (confidence_delta, reason) or None to skip."""


# ─── Built-in rules ───────────────────────────────────────────────────────────


class RegimePenaltyRule:
    name = "regime_penalty"

    def evaluate(self, signal: dict, world: dict) -> tuple[float, str] | None:
        regime = str(world.get("regime", "UNKNOWN")).upper()
        direction = str(signal.get("direction", "")).lower()
        if regime == "UNKNOWN" or direction not in {"long", "short"}:
            return None
        # Opposed: long in TREND_DOWN / RISK_OFF, short in TREND_UP / RISK_ON
        opposed = (direction == "long" and regime in {"TREND_DOWN", "RISK_OFF"}) or (
            direction == "short" and regime in {"TREND_UP", "RISK_ON"}
        )
        aligned = (direction == "long" and regime in {"TREND_UP", "RISK_ON"}) or (
            direction == "short" and regime in {"TREND_DOWN", "RISK_OFF"}
        )
        if opposed:
            return -0.15, f"regime_penalty: {direction} fights {regime}"
        if aligned:
            return +0.05, f"regime_aligned: {direction} with {regime}"
        return None


class FundingCrowdingRule:
    name = "funding_crowding"
    # 8h funding expressed as APR. > 30% APR = extreme crowding one way.
    EXTREME_APR = 0.30

    def evaluate(self, signal: dict, world: dict) -> tuple[float, str] | None:
        funding_apr = world.get("funding_apr")
        if funding_apr is None:
            return None
        funding_apr = float(funding_apr)
        direction = str(signal.get("direction", "")).lower()
        if abs(funding_apr) < self.EXTREME_APR:
            return None
        # Positive APR → longs are paying → long-crowded → penalize longs.
        if funding_apr > self.EXTREME_APR and direction == "long":
            return -0.10, f"funding_crowded: longs paying {funding_apr*100:.1f}% APR"
        if funding_apr < -self.EXTREME_APR and direction == "short":
            return -0.10, f"funding_crowded: shorts paying {abs(funding_apr)*100:.1f}% APR"
        # Contrarian bonus (small) — fade the crowd
        if funding_apr > self.EXTREME_APR and direction == "short":
            return +0.05, f"funding_contrarian: fade crowded longs ({funding_apr*100:.1f}% APR)"
        if funding_apr < -self.EXTREME_APR and direction == "long":
            return (
                +0.05,
                f"funding_contrarian: fade crowded shorts ({abs(funding_apr)*100:.1f}% APR)",
            )
        return None


class FearContrarianRule:
    name = "fear_contrarian"
    EXTREME_FEAR = 20
    EXTREME_GREED = 80

    def evaluate(self, signal: dict, world: dict) -> tuple[float, str] | None:
        fg = world.get("fear_greed")
        if fg is None:
            return None
        fg = int(fg)
        direction = str(signal.get("direction", "")).lower()
        if fg <= self.EXTREME_FEAR and direction == "long":
            return +0.08, f"contrarian_bonus: longs into extreme fear ({fg})"
        if fg >= self.EXTREME_GREED and direction == "short":
            return +0.08, f"contrarian_bonus: shorts into extreme greed ({fg})"
        # Fading a contrarian setup — mild penalty
        if fg <= self.EXTREME_FEAR and direction == "short":
            return -0.05, f"contrarian_fade: shorts into extreme fear ({fg})"
        if fg >= self.EXTREME_GREED and direction == "long":
            return -0.05, f"contrarian_fade: longs into extreme greed ({fg})"
        return None


# ─── State loader ─────────────────────────────────────────────────────────────


class StateLoader:
    """Reads world snapshot from chain.json; falls back to env-provided root."""

    def __init__(self, chain_path: Path | None = None):
        self.chain_path = chain_path or self._resolve_chain_path()

    @staticmethod
    def _resolve_chain_path() -> Path:
        explicit = os.environ.get("SAPPHIRE_CHAIN_PATH")
        if explicit:
            return Path(explicit)
        # Try worktree-relative first, then Sapphire root fallback.
        cand_cwd = DEFAULT_CHAIN_PATH
        if cand_cwd.exists():
            return cand_cwd
        home = os.environ.get("SAPPHIRE_HOME") or str(Path.home() / "Code" / "Sapphire")
        return Path(home) / "data" / "intelligence" / "latest" / "chain.json"

    def load(self) -> dict[str, Any]:
        """Return a normalized world-state dict, empty if nothing available."""
        if not self.chain_path.exists():
            return {}
        try:
            raw = json.loads(self.chain_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("chain.json unreadable: %s", e)
            return {}
        return _normalize_world(raw)


def _normalize_world(raw: dict) -> dict[str, Any]:
    """Flatten the multiple shapes chain.json has taken over time."""
    out: dict[str, Any] = {}
    # Regime (current chain.json stores it under multiple keys historically)
    regime_block = raw.get("regime") or raw.get("market_regime") or {}
    if isinstance(regime_block, dict):
        out["regime"] = str(
            regime_block.get("state") or regime_block.get("label") or "UNKNOWN"
        ).upper()
        rs = regime_block.get("score")
        if rs is not None:
            out["regime_score"] = float(rs)
        rc = regime_block.get("confidence")
        if rc is not None:
            out["regime_confidence"] = float(rc)
    elif isinstance(regime_block, str):
        out["regime"] = regime_block.upper()

    # Funding (any-of)
    for key in ("funding_apr", "funding_rate_apr"):
        if key in raw:
            out["funding_apr"] = float(raw[key])
            break
    funding_block = raw.get("funding")
    if isinstance(funding_block, dict):
        apr = funding_block.get("apr") or funding_block.get("weighted_apr")
        if apr is not None:
            out["funding_apr"] = float(apr)

    # Sentiment / F&G
    sentiment = raw.get("sentiment") or {}
    if isinstance(sentiment, dict):
        fg = sentiment.get("fear_greed") or sentiment.get("fear_greed_value")
        if fg is not None:
            out["fear_greed"] = int(fg)
    if "fear_greed" in raw:
        out["fear_greed"] = int(raw["fear_greed"])

    # Open interest delta (24h)
    oi = raw.get("open_interest") or {}
    if isinstance(oi, dict):
        d = oi.get("change_24h_pct") or oi.get("delta_24h_pct")
        if d is not None:
            out["oi_change_24h_pct"] = float(d)

    return out


# ─── Decision engine ──────────────────────────────────────────────────────────


class DecisionEngine:
    """Evaluate signals against macro state and log every decision."""

    BLOCK_BELOW = 0.20
    REDUCE_BELOW = 0.45
    DEFAULT_RULES: tuple[Rule, ...] = (
        RegimePenaltyRule(),
        FundingCrowdingRule(),
        FearContrarianRule(),
    )

    def __init__(
        self,
        rules: list[Rule] | None = None,
        state_loader: StateLoader | None = None,
        decisions_dir: Path | None = None,
        state_path: Path | None = None,
        audit_log: AutonomyAuditLog | None = None,
        audit_path: str | Path | bool | None = None,
    ):
        self.rules: list[Rule] = list(rules) if rules is not None else list(self.DEFAULT_RULES)
        self.state_loader = state_loader or StateLoader()
        self.decisions_dir = decisions_dir or DEFAULT_DECISIONS_DIR
        self.state_path = state_path or DEFAULT_STATE_PATH
        self.audit_log = audit_log if audit_log is not None else AutonomyAuditLog(audit_path)
        self._lock = threading.Lock()

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, signal: dict, world: dict | None = None) -> Decision:
        """Apply every rule, compute final verdict, log the decision."""
        world = world if world is not None else self.state_loader.load()
        original = float(signal.get("confidence", 0.5))
        adjusted = original
        reasons: list[str] = []
        fired: list[str] = []
        for rule in self.rules:
            try:
                res = rule.evaluate(signal, world)
            except Exception as e:
                reasons.append(f"rule_error:{rule.name}:{e}")
                continue
            if res is None:
                continue
            delta, reason = res
            adjusted += delta
            reasons.append(reason)
            fired.append(rule.name)

        adjusted = max(0.0, min(1.0, adjusted))

        if adjusted < self.BLOCK_BELOW:
            verdict = "BLOCK"
        elif adjusted < self.REDUCE_BELOW:
            verdict = "REDUCE"
        else:
            verdict = "ALLOW"

        decision = Decision(
            signal_id=str(signal.get("signal_id") or signal.get("id") or ""),
            symbol=str(signal.get("symbol", "")).upper(),
            direction=str(signal.get("direction", "")).lower(),
            original_confidence=original,
            adjusted_confidence=round(adjusted, 4),
            verdict=verdict,
            reasons=reasons,
            rules_fired=fired,
            world_snapshot=world,
        )
        self._log(decision)
        self._audit_decision(decision, world)
        return decision

    # ── Alerts / regime shift ─────────────────────────────────────────────────

    def scan_alerts(self, world: dict | None = None) -> list[Alert]:
        """One-shot macro alert scan; call from a cron."""
        world = world if world is not None else self.state_loader.load()
        alerts: list[Alert] = []

        # Regime shift detection — compare against last-seen persisted value.
        regime = str(world.get("regime", "UNKNOWN")).upper()
        prev = self._read_last_regime()
        if regime != "UNKNOWN" and prev and prev != regime:
            alerts.append(
                Alert(
                    kind="regime_shift",
                    severity="warn",
                    message=f"Regime: {prev} → {regime}",
                    data={"from": prev, "to": regime},
                )
            )
        if regime != "UNKNOWN":
            self._write_last_regime(regime)

        # Funding extreme
        fap = world.get("funding_apr")
        if fap is not None and abs(float(fap)) >= FundingCrowdingRule.EXTREME_APR:
            alerts.append(
                Alert(
                    kind="funding_extreme",
                    severity="warn" if abs(float(fap)) < 0.60 else "critical",
                    message=f"Funding APR {float(fap)*100:+.1f}%",
                    data={"apr": float(fap)},
                )
            )

        # F&G extremes
        fg = world.get("fear_greed")
        if fg is not None:
            if int(fg) <= FearContrarianRule.EXTREME_FEAR:
                alerts.append(
                    Alert(
                        kind="fear_extreme",
                        severity="info",
                        message=f"Extreme fear: F&G {fg}",
                        data={"fear_greed": int(fg)},
                    )
                )
            elif int(fg) >= FearContrarianRule.EXTREME_GREED:
                alerts.append(
                    Alert(
                        kind="fear_extreme",
                        severity="info",
                        message=f"Extreme greed: F&G {fg}",
                        data={"fear_greed": int(fg)},
                    )
                )

        self._audit_alerts(alerts, world)
        return alerts

    # ── Event-bus compatible dispatch ─────────────────────────────────────────

    def on_event(self, event_type: str, payload: dict) -> list[Any]:
        """Single entry point for event-bus wiring.

        Supported event types:
          - signal.emitted | signal.scored  → returns [Decision]
          - regime.refreshed | chain.refreshed → returns [Alert, ...]
          - anything else → []
        """
        if event_type in {"signal.emitted", "signal.scored"}:
            return [self.evaluate(payload)]
        if event_type in {"regime.refreshed", "chain.refreshed", "regime.shifted"}:
            world = payload.get("world") or self.state_loader.load()
            return self.scan_alerts(world)
        return []

    # ── Background polling (optional) ─────────────────────────────────────────

    def poll_forever(
        self, interval_sec: float = 300.0, emit: Callable[[Alert], None] | None = None
    ) -> None:
        """Simple polling loop — alternative to event bus for lightweight deployments."""
        while True:
            try:
                for a in self.scan_alerts():
                    if emit:
                        emit(a)
                    else:
                        log.info("[alert] %s %s: %s", a.severity, a.kind, a.message)
            except Exception as e:
                log.exception("poll loop error: %s", e)
            time.sleep(interval_sec)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _log(self, decision: Decision) -> None:
        with self._lock:
            self.decisions_dir.mkdir(parents=True, exist_ok=True)
            path = self.decisions_dir / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
            try:
                with path.open("a") as f:
                    f.write(json.dumps(asdict(decision), default=str) + "\n")
            except OSError as e:
                log.warning("decision log write failed: %s", e)

    def _audit_decision(self, decision: Decision, world: dict[str, Any]) -> None:
        try:
            self.audit_log.append(
                "autonomy.decision_evaluated",
                actor="decision_engine",
                action="evaluate_signal",
                outcome=decision.verdict.lower(),
                risk="financial_decision",
                object_ref=decision.signal_id or f"{decision.symbol}:{decision.direction}",
                metadata={
                    "signal_id": decision.signal_id,
                    "symbol": decision.symbol,
                    "direction": decision.direction,
                    "original_confidence": decision.original_confidence,
                    "adjusted_confidence": decision.adjusted_confidence,
                    "rules_fired": decision.rules_fired,
                    "reason_count": len(decision.reasons),
                    "world_keys": sorted(world.keys()),
                },
            )
        except Exception as e:
            log.warning("autonomy decision audit write failed: %s", e)

    def _audit_alerts(self, alerts: list[Alert], world: dict[str, Any]) -> None:
        for alert in alerts:
            try:
                self.audit_log.append(
                    "autonomy.alert_detected",
                    actor="decision_engine",
                    action="scan_alerts",
                    outcome=alert.severity,
                    risk="market_alert",
                    object_ref=alert.kind,
                    metadata={
                        "kind": alert.kind,
                        "severity": alert.severity,
                        "data_keys": sorted(alert.data.keys()),
                        "world_keys": sorted(world.keys()),
                    },
                )
            except Exception as e:
                log.warning("autonomy alert audit write failed: %s", e)

    def _read_last_regime(self) -> str:
        try:
            if not self.state_path.exists():
                return ""
            return json.loads(self.state_path.read_text()).get("regime", "")
        except (OSError, json.JSONDecodeError):
            return ""

    def _write_last_regime(self, regime: str) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(
                    {
                        "regime": regime,
                        "ts": datetime.now(UTC).isoformat(),
                    }
                )
            )
        except OSError as e:
            log.warning("last-regime write failed: %s", e)


# ─── CLI entrypoint ───────────────────────────────────────────────────────────


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Sapphire decision engine")
    p.add_argument("--signal", help="Signal JSON to evaluate (reads stdin if '-')")
    p.add_argument("--alerts", action="store_true", help="Run one alert scan and exit")
    p.add_argument("--poll", type=float, help="Poll every N seconds (forever)")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    eng = DecisionEngine()

    if args.poll:
        eng.poll_forever(interval_sec=args.poll)
        return 0

    if args.alerts:
        alerts = eng.scan_alerts()
        print(json.dumps([asdict(a) for a in alerts], indent=2))
        return 0

    if args.signal:
        import sys

        raw = sys.stdin.read() if args.signal == "-" else args.signal
        decision = eng.evaluate(json.loads(raw))
        print(json.dumps(asdict(decision), indent=2, default=str))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
