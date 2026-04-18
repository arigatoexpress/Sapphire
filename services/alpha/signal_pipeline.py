"""
Sapphire Signal Pipeline — orchestration layer for trading signal processing.

Builds on signal_logger (ingestion) to add:
  - Risk kernel gate (HardRiskKernel — daily loss / drawdown / consecutive fail checks)
  - Position sizing recommendation (Kelly + volatility + drawdown multipliers)
  - Telegram routing with full scored context and direction icons
  - Confirmation firewall: confidence >= HIGH_CONF requires Telegram confirmation
    before the signal is elevated to execution-ready status
  - Per-day JSONL audit trail at data/signals/YYYY-MM-DD.jsonl

Usage (as a module, called from signal_logger.py):
    from signal_pipeline import pipeline
    result = pipeline.process(raw_signal_dict)

Usage (standalone CLI for testing):
    python3 signal_pipeline.py '{"symbol":"BTC","action":"buy","price":65000,"confidence":0.8}'
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid

log = logging.getLogger(__name__)
import contextlib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ─── Path Setup ────────────────────────────────────────────────────────────────
_ROOT       = Path.home() / "Code" / "Sapphire"
_CORE_SRC   = _ROOT / "lib" / "core" / "src"
_CORE_LIB   = _ROOT / "lib" / "core"
_TOOLS      = _ROOT / "plugins" / "claw-sapphire" / "tools"
_PLUGIN_LIB = _ROOT / "plugins" / "claw-sapphire" / "lib"

for _p in [str(_CORE_SRC), str(_CORE_LIB), str(_TOOLS), str(_PLUGIN_LIB)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ─── Optional Imports (graceful degradation) ──────────────────────────────────

try:
    from sapphire_core.risk_kernel import HardRiskKernel, RiskKernelEvent
    _KERNEL_AVAILABLE = True
except ImportError:
    _KERNEL_AVAILABLE = False

try:
    from sapphire_core.position_sizing import (
        MarketRegime,
        SizingInput,
        SizingMethod,
        compute_position_size,
    )
    _SIZING_AVAILABLE = True
except ImportError:
    _SIZING_AVAILABLE = False

try:
    from confirmation_firewall import ActionRisk, ConfirmationFirewall, classify_action
    _FIREWALL_AVAILABLE = True
except ImportError:
    _FIREWALL_AVAILABLE = False

try:
    from notify import send_telegram_message
    _NOTIFY_AVAILABLE = True
except ImportError:
    _NOTIFY_AVAILABLE = False

try:
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
    from services.pipeline.pubsub_publisher import publish_signal
    _PUBSUB_AVAILABLE = True
except Exception:
    _PUBSUB_AVAILABLE = False

# Signal enhancer (regime/funding/correlation-aware) — opt-in
try:
    _SAPPHIRE_ROOT = Path.home() / "Code" / "Sapphire"
    if str(_SAPPHIRE_ROOT) not in sys.path:
        sys.path.insert(0, str(_SAPPHIRE_ROOT))
    from lib.analytics.signal_enhancer import get_enhancer
    _ENHANCER_AVAILABLE = True
except ImportError:
    _ENHANCER_AVAILABLE = False

# Event bus — central nervous system. Degrades to JSONL fallback if Redis down.
try:
    from event_bus import get_bus as _get_event_bus
    _EVENT_BUS = _get_event_bus(source="signal_pipeline")
except Exception as e:  # pragma: no cover — import guard
    log.warning("event_bus unavailable: %s", e)
    _EVENT_BUS = None

# ─── Constants ────────────────────────────────────────────────────────────────

SIGNALS_DIR   = _ROOT / "data" / "signals"
SIGNALS_DIR.mkdir(parents=True, exist_ok=True)

# Paper trading — when enabled, signals are scored + logged but Telegram prefix
# is "[PAPER]" and P&L is tracked in a separate JSONL for review.
PAPER_TRADING = os.getenv("PAPER_TRADING", "0") == "1"
PAPER_TRADING_LOG = _ROOT / "data" / "paper_trading.jsonl"

# Confidence thresholds
HIGH_CONF    = float(os.getenv("SIGNAL_HIGH_CONF",    "0.75"))  # requires confirmation
MEDIUM_CONF  = float(os.getenv("SIGNAL_MEDIUM_CONF",  "0.50"))  # notify with details
# below MEDIUM_CONF → logged only

# Default paper portfolio balance for position sizing
PAPER_BALANCE = float(os.getenv("PAPER_BALANCE", "10000.0"))

# Default signal volatility assumption (3% = moderate crypto)
DEFAULT_VOLATILITY = float(os.getenv("SIGNAL_DEFAULT_VOL", "0.03"))

# Regime-aware enhancer toggle (off by default — enable when chain data is flowing)
ENHANCER_ENABLED = os.getenv("SIGNAL_ENHANCER", "1") == "1"


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class ScoredSignal:
    """A raw signal enriched with risk scoring and position sizing."""

    # Identity
    pipeline_id:  str
    timestamp:    str
    symbol:       str
    action:       str        # buy | sell | long | short | close
    direction:    str        # long | short | flat
    strategy:     str
    price:        float
    source:       str

    # Raw signal confidence (0–1, from Pine alert or webhook)
    confidence:   float

    # Risk kernel gate
    kernel_ok:    bool
    kernel_reason: str

    # Position sizing
    position_usd:  float
    position_pct:  float
    kelly_raw:     float
    kelly_capped:  float
    sizing_method: str
    sizing_reason: str

    # Composite score (0–100)
    score:         float

    # Routing decision
    routing:       str       # CONFIRMATION_REQUIRED | NOTIFY | LOG_ONLY | BLOCKED

    # Risk/reward from signal (if provided)
    take_profit:   float = 0.0
    stop_loss:     float = 0.0
    rr_ratio:      float = 0.0

    # Regime-aware enhancement (optional — populated if lib.analytics available)
    original_confidence:  float = 0.0
    regime:               str = "UNKNOWN"
    regime_score:         float = 0.0
    regime_confidence:    float = 0.0
    enhancer_flags:       list[str] = field(default_factory=list)
    enhancer_reasons:     list[str] = field(default_factory=list)

    # Full market context at the time the signal landed (for backtesting).
    funding_rate:          float | None = None
    funding_flag:          str | None = None
    correlation_btc_spy:   float | None = None
    fear_greed:            int | None = None
    kronos_direction:      str | None = None
    kronos_confidence:     float | None = None

    # Audit
    raw:           dict = field(default_factory=dict)
    notes:         list[str] = field(default_factory=list)


@dataclass
class ProcessedSignal:
    """Final result returned by pipeline.process()."""

    scored:         ScoredSignal
    telegram_sent:  bool
    confirmation_code: str   # non-empty if confirmation was requested
    audit_path:     str      # where the JSONL record was written
    elapsed_ms:     int


# ─── Signal Pipeline ──────────────────────────────────────────────────────────

class SignalPipeline:
    """
    Orchestrates signal scoring, routing, and audit logging.

    Thread-safe — uses one shared HardRiskKernel instance.
    Instantiate once and reuse across requests.
    """

    def __init__(self) -> None:
        # Risk kernel with conservative trading defaults
        if _KERNEL_AVAILABLE:
            self._kernel = HardRiskKernel(
                enabled=True,
                hold_seconds=1800,
                max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "4.0")),
                max_daily_loss_usd=float(os.getenv("MAX_DAILY_LOSS_USD", "0.0")),
                max_intraday_drawdown_pct=float(os.getenv("MAX_INTRADAY_DD_PCT", "3.5")),
                max_consecutive_loss_events=4,
                max_consecutive_hard_fails=5,
            )
        else:
            self._kernel = None

        # Confirmation firewall
        if _FIREWALL_AVAILABLE:
            self._firewall = ConfirmationFirewall()
        else:
            self._firewall = None

        # In-memory signal index for /signals active queries (lock-protected)
        self._active: dict[str, ScoredSignal] = {}
        self._active_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def process(self, raw: dict) -> ProcessedSignal:
        """
        Process a raw signal dict from signal_logger.

        Returns ProcessedSignal with scoring, routing decision, and audit path.
        Never raises — errors are captured in scored.notes.
        """
        t0 = time.time()
        scored = self._score(raw)
        telegram_sent = False
        confirmation_code = ""

        # Route based on decision
        if scored.routing == "BLOCKED":
            pass  # kernel blocked — log only

        elif scored.routing == "CONFIRMATION_REQUIRED" and self._firewall:
            try:
                # Trading signals always classify as FINANCIAL — skip
                # auto_approve (which only greenlights READ_ONLY/SELF_MODIFY)
                # and go straight to the Telegram confirmation request.
                code = self._request_telegram_confirmation(scored)
                confirmation_code = code
                telegram_sent = bool(code)
            except Exception as e:
                scored.notes.append(f"confirmation_firewall error: {e}")
                self._send_signal_telegram(scored, execution_status="NOTIFICATION-ONLY")
                telegram_sent = True

        elif scored.routing == "NOTIFY":
            self._send_signal_telegram(scored, execution_status="NOTIFICATION")
            telegram_sent = True

        # LOG_ONLY: write audit but no Telegram

        # Always write audit
        audit_path = self._write_audit(scored)

        # Track active signals (open positions) — keyed by symbol (not direction).
        # A new entry on a symbol that already has an open position implicitly
        # closes the prior one at the new signal's price. Kernel-blocked or
        # zero-size signals must NOT enter _active, else a later close
        # produces a fake $0 P&L event.
        is_close_action = scored.action.lower() in {"close", "flat", "exit"}
        is_live_entry = (
            not is_close_action
            and scored.routing != "BLOCKED"
            and scored.position_usd > 0
        )
        with self._active_lock:
            prior_open = self._active.pop(scored.symbol, None)
            if is_live_entry:
                self._active[scored.symbol] = scored

        if prior_open is not None:
            self._close_position(prior_open, close_price=scored.price)
        elif is_close_action:
            log.warning("close for %s but no open position in _active", scored.symbol)

        elapsed_ms = int((time.time() - t0) * 1000)

        # Event bus — publish signal.generated for any live entry that passed
        # the kernel gate. Close actions are handled in _close_position via
        # signal.closed.
        if _EVENT_BUS is not None and is_live_entry:
            try:
                _EVENT_BUS.publish("signal.generated", {
                    "pipeline_id": scored.pipeline_id,
                    "symbol": scored.symbol,
                    "action": scored.action,
                    "direction": scored.direction,
                    "strategy": scored.strategy,
                    "price": scored.price,
                    "confidence": scored.confidence,
                    "routing": scored.routing,
                    "position_usd": scored.position_usd,
                })
            except Exception as e:
                log.warning("event bus publish failed: %s", e)

        return ProcessedSignal(
            scored=scored,
            telegram_sent=telegram_sent,
            confirmation_code=confirmation_code,
            audit_path=str(audit_path),
            elapsed_ms=elapsed_ms,
        )

    def kernel_status(self) -> dict:
        """Return current risk kernel state."""
        if self._kernel:
            return self._kernel.status()
        return {"enabled": False, "reason": "sapphire_core not available"}

    def active_signals(self) -> list[dict]:
        """Return currently active (open) scored signals."""
        with self._active_lock:
            return [asdict(s) for s in self._active.values()]

    def _close_position(self, open_signal: ScoredSignal, close_price: float) -> None:
        """Calculate realised P&L for a closed position and update the JSONL audit record.

        Runs in a daemon thread so it does not block the main process() call.
        """
        entry = open_signal.price
        if entry > 0 and close_price > 0:
            direction_sign = 1.0 if open_signal.direction == "long" else -1.0
            pnl_pct = (close_price - entry) / entry * direction_sign
            pnl_usd = round(pnl_pct * open_signal.position_usd, 2)
        else:
            pnl_usd = 0.0

        if pnl_usd > 0:
            outcome = "win"
        elif pnl_usd < 0:
            outcome = "loss"
        else:
            outcome = "break_even"

        log.info(
            "-> closed %s | entry=%.4f exit=%.4f pnl=%.2f USD (%s)",
            open_signal.symbol, entry, close_price, pnl_usd, outcome,
        )

        if _EVENT_BUS is not None:
            try:
                _EVENT_BUS.publish("signal.closed", {
                    "pipeline_id": open_signal.pipeline_id,
                    "symbol": open_signal.symbol,
                    "direction": open_signal.direction,
                    "entry_price": entry,
                    "close_price": close_price,
                    "pnl_usd": pnl_usd,
                    "outcome": outcome,
                })
            except Exception as e:
                log.warning("event bus publish failed: %s", e)

        def _do_update() -> None:
            try:
                self.update_signal_outcome(
                    open_signal.pipeline_id, outcome, pnl_usd, close_price=close_price
                )
            except Exception as e:
                log.warning(
                    "Failed to write outcome for pipeline_id=%s: %s",
                    open_signal.pipeline_id, e,
                )

        threading.Thread(target=_do_update, daemon=True, name="signal-outcome-writer").start()

    def recent_signals(self, n: int = 20) -> list[dict]:
        """Read n most recent signals from today's audit JSONL."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        path = SIGNALS_DIR / f"{today}.jsonl"
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()[-n:]
        result = []
        for line in lines:
            with contextlib.suppress(json.JSONDecodeError):
                result.append(json.loads(line))
        return list(reversed(result))

    def _update_paper_outcome(
        self,
        pipeline_id: str,
        outcome: str,
        pnl_usd: float,
        close_price: float,
    ) -> bool:
        """Flip the matching pipeline_id row in paper_trading.jsonl to closed.

        Returns True if a row was updated. Silent no-op if the paper log is
        missing or the pipeline_id is not present.
        """
        if not PAPER_TRADING_LOG.exists():
            return False
        try:
            lines = PAPER_TRADING_LOG.read_text().splitlines()
        except OSError as e:
            log.warning("paper log read failed: %s", e)
            return False
        updated = False
        new_lines: list[str] = []
        closed_at = datetime.now(UTC).isoformat()
        for line in lines:
            stripped = line.strip()
            if not stripped:
                new_lines.append(line)
                continue
            try:
                r = json.loads(stripped)
                if r.get("pipeline_id") == pipeline_id and r.get("paper_status") == "open":
                    r["paper_status"] = "closed"
                    r["paper_outcome"] = outcome
                    r["paper_pnl_usd"] = round(pnl_usd, 2)
                    r["paper_close_price"] = close_price or None
                    r["paper_closed_at"] = closed_at
                    line = json.dumps(r)
                    updated = True
            except json.JSONDecodeError:
                pass
            new_lines.append(line)
        if not updated:
            return False
        import tempfile
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=PAPER_TRADING_LOG.parent, delete=False, suffix=".tmp"
            ) as tf:
                tf.write("\n".join(new_lines) + "\n")
                tmp_path = tf.name
            os.replace(tmp_path, PAPER_TRADING_LOG)
            tmp_path = None
            return True
        finally:
            if tmp_path and os.path.exists(tmp_path):
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)

    def update_signal_outcome(
        self,
        pipeline_id: str,
        outcome: str,       # "win" | "loss" | "break_even"
        pnl_usd: float,
        close_price: float = 0.0,
    ) -> bool:
        """
        Write outcome back to the JSONL audit record identified by pipeline_id.

        Searches the last 7 days of signal files (a position opened yesterday
        can be closed today). Rewrites the matching line in-place, adding
        ``outcome``, ``pnl_usd``, ``close_price``, and ``closed_at`` fields.

        Returns True if the record was found and updated, False otherwise.
        """
        from datetime import timedelta

        today = datetime.now(UTC).date()
        for delta in range(7):
            path = SIGNALS_DIR / f"{(today - timedelta(days=delta)).isoformat()}.jsonl"
            if not path.exists():
                continue
            lines = path.read_text().splitlines()
            updated = False
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    new_lines.append(line)
                    continue
                try:
                    record = json.loads(stripped)
                    if record.get("pipeline_id") == pipeline_id:
                        record["outcome"] = outcome
                        record["pnl_usd"] = round(pnl_usd, 2)
                        if close_price:
                            record["close_price"] = close_price
                        record["closed_at"] = datetime.now(UTC).isoformat()
                        line = json.dumps(record)
                        updated = True
                except json.JSONDecodeError:
                    pass
                new_lines.append(line)
            if updated:
                import tempfile
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w", dir=path.parent, delete=False, suffix=".tmp"
                    ) as tf:
                        tf.write("\n".join(new_lines) + "\n")
                        tmp_path = tf.name
                    os.replace(tmp_path, path)
                    tmp_path = None
                except Exception:
                    log.exception("update_signal_outcome: failed to rewrite %s", path)
                    raise
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        with contextlib.suppress(OSError):
                            os.unlink(tmp_path)
                # Mirror the outcome into paper_trading.jsonl so paper_stats()
                # reflects the close (not stuck at paper_status=open forever).
                if PAPER_TRADING:
                    self._update_paper_outcome(
                        pipeline_id, outcome, pnl_usd, close_price
                    )
                # Remove from in-memory active index (keyed by symbol)
                with self._active_lock:
                    to_remove = [
                        sym for sym, sig in self._active.items()
                        if sig.pipeline_id == pipeline_id
                    ]
                    for sym in to_remove:
                        self._active.pop(sym, None)
                # Publish outcome delta to Pub/Sub → BigQuery (new row with closed state;
                # v_signals_latest picks the most-recent per signal_id).
                if _PUBSUB_AVAILABLE:
                    try:
                        publish_signal({
                            "signal_id":     pipeline_id,
                            "symbol":        record.get("symbol", "UNKNOWN"),
                            "action":        "close",
                            "direction":     record.get("direction"),
                            "outcome":       outcome,
                            "pnl_usd":       round(pnl_usd, 2),
                            "closed_at":     record.get("closed_at"),
                            # Publish the actual close price (or null if missing).
                            # Falling back to the entry price silently corrupted
                            # BQ with close rows that matched the open row.
                            "price_at_signal": close_price,
                            "score":         record.get("score"),
                            "confidence":    record.get("confidence"),
                            "timestamp":     record.get("closed_at"),
                        })
                    except Exception as e:
                        log.warning("pubsub close publish skipped: %s", e)

                # Event bus — signal.closed so world-state PnL tracks live.
                try:
                    from lib.core.event_bus import get_bus
                    get_bus().publish(
                        "signal.closed",
                        {
                            "signal_id": pipeline_id,
                            "symbol":    record.get("symbol", "UNKNOWN"),
                            "direction": record.get("direction"),
                            "outcome":   outcome,
                            "pnl_usd":   round(pnl_usd, 2),
                            "entry_price": record.get("price"),
                            "close_price": close_price,
                            "closed_at": record.get("closed_at"),
                        },
                        source="signal_pipeline",
                    )
                except Exception as e:
                    log.debug("event bus signal.closed publish skipped: %s", e)
                return True
        return False

    def signal_stats(self) -> dict:
        """Basic win-rate stats from all historical scored signals."""
        total = wins = losses = 0
        total_pnl = 0.0
        files = sorted(SIGNALS_DIR.glob("*.jsonl"))
        for f in files[-30:]:  # last 30 days
            try:
                content = f.read_text()
            except OSError:
                continue
            for line in content.strip().splitlines():
                try:
                    s = json.loads(line)
                    outcome = s.get("outcome", "")
                    if outcome == "win":
                        wins += 1
                        total_pnl += float(s.get("pnl_usd", 0))
                    elif outcome == "loss":
                        losses += 1
                        total_pnl += float(s.get("pnl_usd", 0))
                    total += 1
                except Exception:
                    pass
        win_rate = wins / (wins + losses) if (wins + losses) > 0 else None
        return {
            "total_signals": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 3) if win_rate is not None else None,
            "total_pnl_usd": round(total_pnl, 2),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _score(self, raw: dict) -> ScoredSignal:
        """Build a ScoredSignal from a raw dict."""
        notes: list[str] = []

        symbol     = str(raw.get("symbol", "UNKNOWN")).upper()
        action_raw = str(raw.get("action", raw.get("side", "UNKNOWN"))).lower()
        strategy   = str(raw.get("strategy", "unknown"))
        price      = float(raw.get("price", 0) or 0)
        confidence = float(raw.get("confidence", 0.5) or 0.5)
        original_confidence = confidence
        tp         = float(raw.get("take_profit", raw.get("tp", 0)) or 0)
        sl         = float(raw.get("stop_loss",   raw.get("sl", 0)) or 0)

        # Normalize direction
        if action_raw in {"buy", "long", "entry_long"}:
            direction = "long"
        elif action_raw in {"sell", "short", "entry_short"}:
            direction = "short"
        else:
            direction = "flat"

        # ── Regime-aware enhancement ─────────────────────────────────────────
        regime = "UNKNOWN"
        regime_score = 0.0
        regime_confidence = 0.0
        enhancer_flags: list[str] = []
        enhancer_reasons: list[str] = []
        funding_rate: float | None = None
        funding_flag: str | None = None
        correlation_btc_spy: float | None = None
        fear_greed: int | None = None
        kronos_direction: str | None = None
        kronos_confidence: float | None = None
        if ENHANCER_ENABLED and _ENHANCER_AVAILABLE and direction != "flat":
            try:
                enhanced = get_enhancer().enhance(symbol, action_raw, confidence)
                confidence = enhanced.adjusted_confidence
                regime = enhanced.regime
                regime_score = enhanced.regime_score
                regime_confidence = enhanced.regime_confidence
                enhancer_flags = enhanced.flags
                enhancer_reasons = enhanced.reasons
                funding_rate = enhanced.funding_rate
                funding_flag = enhanced.funding_flag
                correlation_btc_spy = enhanced.btc_spy_correlation
                fear_greed = enhanced.fear_greed
                kronos_direction = enhanced.kronos_direction
                kronos_confidence = enhanced.kronos_confidence
                if enhanced.original_confidence != enhanced.adjusted_confidence:
                    notes.append(
                        f"confidence adjusted {enhanced.original_confidence:.2f}"
                        f"→{enhanced.adjusted_confidence:.2f} ({regime})"
                    )
            except Exception as e:
                notes.append(f"enhancer_error: {e}")

        # R:R ratio
        rr_ratio = 0.0
        if tp > 0 and sl > 0 and price > 0:
            reward = abs(tp - price)
            risk   = abs(price - sl)
            if risk > 0:
                rr_ratio = round(reward / risk, 2)

        # ── Risk Kernel Gate ──────────────────────────────────────────────────
        kernel_ok = True
        kernel_reason = ""
        if self._kernel:
            can_open, reason = self._kernel.can_open_entry()
            kernel_ok = can_open
            kernel_reason = reason
            if not kernel_ok:
                notes.append(f"kernel_blocked: {reason}")

        # ── Position Sizing ───────────────────────────────────────────────────
        position_usd = 0.0
        position_pct = 0.0
        kelly_raw    = 0.0
        kelly_capped = 0.0
        sizing_method = "unavailable"
        sizing_reason = ""

        if _SIZING_AVAILABLE and kernel_ok:
            try:
                inp = SizingInput(
                    balance=PAPER_BALANCE,
                    confidence=min(1.0, max(0.0, confidence)),
                    volatility=DEFAULT_VOLATILITY,
                    drawdown_pct=0.0,
                    win_rate=0.0,      # uses default 0.55
                    rr_ratio=rr_ratio if rr_ratio > 0 else 0.0,
                    regime=MarketRegime.UNKNOWN,
                    execution_stage="full_live",
                    current_exposure=0.0,
                )
                result = compute_position_size(inp, SizingMethod.KELLY)
                position_usd  = result.position_usd
                position_pct  = result.position_pct
                kelly_raw     = result.kelly_raw
                kelly_capped  = result.kelly_capped
                sizing_method = result.method
                sizing_reason = result.capped_reason
            except Exception as e:
                notes.append(f"sizing_error: {e}")
        elif not kernel_ok:
            sizing_reason = "kernel_blocked"

        # ── Composite Score ───────────────────────────────────────────────────
        # Weighted 40/25/20/15 — confidence dominates because it reflects the
        # strategy's own self-assessment; kernel is binary (gate, not gradient)
        # so it caps at 25; R:R and size are quality-of-setup modifiers.
        # Clamp confidence_pts to [0, 40] — bad-input confidence > 1.0 must not
        # overflow the composite; < 0 must not subtract from other factors.
        conf_pts  = min(40.0, max(0.0, confidence * 40))
        kern_pts  = 25 if kernel_ok else 0
        # Missing R:R should score LOWER than a valid 1:1 (7 pts), not higher.
        # Prior default of 10 rewarded ignorance — lower it below any real R:R.
        # The 7x multiplier means R:R=2.85 saturates at 20 (matches our target setup).
        rr_pts    = min(20, rr_ratio * 7) if rr_ratio > 0 else 5
        # Scales linearly to max position (10% of balance = full 15 pts); Kelly
        # below the cap produces a proportional haircut on the composite.
        pos_pts   = min(15, (position_pct / 0.10) * 15)
        score     = round(conf_pts + kern_pts + rr_pts + pos_pts, 1)

        # ── Routing Decision ──────────────────────────────────────────────────
        if not kernel_ok:
            routing = "BLOCKED"
        elif confidence >= HIGH_CONF:
            routing = "CONFIRMATION_REQUIRED"
        elif confidence >= MEDIUM_CONF:
            routing = "NOTIFY"
        else:
            routing = "LOG_ONLY"

        return ScoredSignal(
            pipeline_id  = str(uuid.uuid4())[:8],
            timestamp    = datetime.now(UTC).isoformat(),
            symbol       = symbol,
            action       = action_raw,
            direction    = direction,
            strategy     = strategy,
            price        = price,
            source       = str(raw.get("source", "webhook")),
            confidence   = round(confidence, 3),
            kernel_ok    = kernel_ok,
            kernel_reason= kernel_reason,
            position_usd = position_usd,
            position_pct = position_pct,
            kelly_raw    = kelly_raw,
            kelly_capped = kelly_capped,
            sizing_method= sizing_method,
            sizing_reason= sizing_reason,
            score        = score,
            routing      = routing,
            take_profit  = tp,
            stop_loss    = sl,
            rr_ratio     = rr_ratio,
            original_confidence = round(original_confidence, 3),
            regime       = regime,
            regime_score = regime_score,
            regime_confidence = regime_confidence,
            enhancer_flags = enhancer_flags,
            enhancer_reasons = enhancer_reasons,
            funding_rate = funding_rate,
            funding_flag = funding_flag,
            correlation_btc_spy = correlation_btc_spy,
            fear_greed = fear_greed,
            kronos_direction = kronos_direction,
            kronos_confidence = kronos_confidence,
            raw          = raw,
            notes        = notes,
        )

    def _send_signal_telegram(self, s: ScoredSignal, execution_status: str) -> None:
        """Send scored signal to Telegram. Silently ignores errors."""
        if not _NOTIFY_AVAILABLE:
            return
        try:
            icon = "🟢" if s.direction == "long" else "🔴" if s.direction == "short" else "⬜"
            routing_note = {
                "CONFIRMATION_REQUIRED": "⚠️ _Awaiting confirmation_",
                "AUTO-APPROVED":         "✅ _Auto-approved (within limits)_",
                "NOTIFICATION":          "📊 _Signal logged_",
                "NOTIFICATION-ONLY":     "📊 _Signal logged (firewall fallback)_",
            }.get(execution_status, f"_Status: {execution_status}_")

            paper_prefix = "*[PAPER]* " if PAPER_TRADING else ""
            lines = [
                f"{paper_prefix}*{icon} Signal Pipeline* — `{s.pipeline_id}`",
                "",
                f"*{s.action.upper()} {s.symbol}* | {s.strategy}",
                f"Price: `${s.price:,.4f}`",
                f"Confidence: `{s.confidence:.0%}`",
                f"Score: `{s.score:.0f}/100`",
                "",
                f"💰 Recommended size: `${s.position_usd:.0f}` ({s.position_pct:.1%})",
                f"Kelly: `{s.kelly_capped:.3f}` (raw: {s.kelly_raw:.3f})",
            ]
            if s.rr_ratio > 0:
                lines.append(f"R:R ratio: `{s.rr_ratio:.1f}:1`")
            if s.take_profit > 0:
                lines.append(f"TP: `${s.take_profit:,.4f}` | SL: `${s.stop_loss:,.4f}`")
            lines += ["", routing_note]
            if not s.kernel_ok:
                lines.append(f"🛑 Risk kernel: `{s.kernel_reason}`")

            priority = "p0" if execution_status in {"CONFIRMATION_REQUIRED", "AUTO-APPROVED"} else "p1"
            send_telegram_message("\n".join(lines), priority=priority)
        except Exception:
            pass

    def _request_telegram_confirmation(self, s: ScoredSignal) -> str:
        """Queue a pending confirmation + send Telegram request. Returns code.

        Non-blocking: writes the pending-confirmation file and fires the
        Telegram send in a daemon thread so ``process()`` stays responsive.
        The code can later be approved by the hermes-agent handler via
        ``ConfirmationFirewall.approve_pending(code)``.
        """
        if not self._firewall:
            return ""
        try:
            from confirmation_firewall import (
                ActionRisk,
                _send_confirmation_request,
                _write_pending,
            )
        except ImportError:
            return ""

        details = (
            f"Signal: {s.action.upper()} {s.symbol} @ ${s.price:,.4f}\n"
            f"Confidence: {s.confidence:.0%} | Score: {s.score:.0f}/100\n"
            f"Recommended size: ${s.position_usd:.0f} ({s.position_pct:.1%})\n"
            f"Strategy: {s.strategy}"
        )
        action_label = f"Trading signal: {s.action.upper()} {s.symbol}"
        code = str(uuid.uuid4()).split("-")[0].upper()

        try:
            _write_pending(code, action_label, ActionRisk.FINANCIAL, details)
        except Exception as e:
            log.warning("failed to write pending confirmation: %s", e)
            return ""

        def _send_bg() -> None:
            try:
                _send_confirmation_request(
                    code, action_label, ActionRisk.FINANCIAL, details, s.position_usd
                )
            except Exception as e:
                log.warning("confirmation telegram send failed: %s", e)

        threading.Thread(target=_send_bg, daemon=True).start()
        return code

    def _write_audit(self, s: ScoredSignal) -> Path:
        """Append scored signal to today's JSONL audit file.

        When PAPER_TRADING is enabled, also appends to paper_trading.jsonl
        with a ``paper_status: open`` marker so P&L can be tracked separately.
        """
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        path  = SIGNALS_DIR / f"{today}.jsonl"
        record = asdict(s)
        record.pop("raw", None)  # raw is noisy; already in signal_logger's log
        if PAPER_TRADING:
            record["paper_mode"] = True
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
            # Durability: ensure the record hits disk before we call the
            # record "audited". A crash between write-to-pagecache and fsync
            # would otherwise drop the most recent trade events.
            f.flush()
            with contextlib.suppress(OSError):
                os.fsync(f.fileno())

        # Real-time BigQuery publish (Pub/Sub → sapphire.trading_signals). Best-effort;
        # hourly gcp_sync also backfills from this JSONL if the publish is dropped.
        if _PUBSUB_AVAILABLE:
            try:
                publish_signal({
                    "signal_id":           s.pipeline_id,
                    "symbol":              s.symbol,
                    "action":              s.action,
                    "direction":           s.direction,
                    "score":               s.score,
                    "confidence":          s.confidence,
                    "original_confidence": s.original_confidence,
                    "regime":              s.regime,
                    "regime_score":        s.regime_score,
                    "source":              s.source,
                    "price_at_signal":     s.price,
                    "notes":               "; ".join(s.notes) if s.notes else None,
                    "flags":               list(s.enhancer_flags or []),
                    "outcome":             None,
                    "pnl_usd":             None,
                    "closed_at":           None,
                    "timestamp":           s.timestamp,
                })
            except Exception as e:
                log.warning("pubsub publish_signal skipped: %s", e)

        # Internal event bus publish — signal.generated with full context so any
        # subscriber (dashboard, strategy agents, watchdog) can react in-process.
        try:
            from lib.core.event_bus import get_bus
            get_bus().publish(
                "signal.generated",
                {
                    "signal_id":           s.pipeline_id,
                    "symbol":              s.symbol,
                    "action":              s.action,
                    "direction":           s.direction,
                    "price":               s.price,
                    "score":               s.score,
                    "confidence":          s.confidence,
                    "original_confidence": s.original_confidence,
                    "routing":             s.routing,
                    "regime":              s.regime,
                    "regime_score":        s.regime_score,
                    "funding_rate":        s.funding_rate,
                    "funding_flag":        s.funding_flag,
                    "correlation_btc_spy": s.correlation_btc_spy,
                    "fear_greed":          s.fear_greed,
                    "kronos_direction":    s.kronos_direction,
                    "kronos_confidence":   s.kronos_confidence,
                    "enhancer_flags":      list(s.enhancer_flags or []),
                    "position_usd":        s.position_usd,
                },
                source="signal_pipeline",
            )
        except Exception as e:
            log.debug("event bus signal.generated publish skipped: %s", e)

        # Paper trading secondary log
        if PAPER_TRADING and s.action.lower() in {"buy", "sell", "long", "short",
                                                   "entry_long", "entry_short"}:
            paper_record = {
                "pipeline_id": s.pipeline_id,
                "timestamp": s.timestamp,
                "symbol": s.symbol,
                "action": s.action,
                "direction": s.direction,
                "price": s.price,
                "position_usd": s.position_usd,
                "score": s.score,
                "strategy": s.strategy,
                "take_profit": s.take_profit,
                "stop_loss": s.stop_loss,
                "rr_ratio": s.rr_ratio,
                "paper_status": "open",
                "paper_outcome": None,
                "paper_pnl_usd": None,
                "paper_close_price": None,
            }
            PAPER_TRADING_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(PAPER_TRADING_LOG, "a") as f:
                f.write(json.dumps(paper_record) + "\n")
                f.flush()
                with contextlib.suppress(OSError):
                    os.fsync(f.fileno())

        return path

    def paper_stats(self) -> dict:
        """Return paper trading statistics from paper_trading.jsonl."""
        if not PAPER_TRADING_LOG.exists():
            return {"paper_trading": PAPER_TRADING, "total": 0, "open": 0,
                    "wins": 0, "losses": 0, "win_rate": None, "total_pnl_usd": 0.0}
        total = open_count = wins = losses = 0
        total_pnl = 0.0
        for line in PAPER_TRADING_LOG.read_text().strip().splitlines():
            try:
                r = json.loads(line)
                total += 1
                outcome = r.get("paper_outcome")
                if outcome is None:
                    open_count += 1
                elif outcome == "win":
                    wins += 1
                    total_pnl += float(r.get("paper_pnl_usd") or 0)
                elif outcome == "loss":
                    losses += 1
                    total_pnl += float(r.get("paper_pnl_usd") or 0)
            except Exception:
                pass
        closed = wins + losses
        return {
            "paper_trading": PAPER_TRADING,
            "total": total,
            "open": open_count,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / closed, 3) if closed > 0 else None,
            "total_pnl_usd": round(total_pnl, 2),
        }


# ─── Lazy singleton (avoid kernel/firewall init at import time) ─────────────

_pipeline: SignalPipeline | None = None


def get_pipeline() -> SignalPipeline:
    """Return the process-wide SignalPipeline, instantiating on first use."""
    global _pipeline
    if _pipeline is None:
        _pipeline = SignalPipeline()
    return _pipeline


def __getattr__(name: str):
    # Preserve `from signal_pipeline import pipeline` — instantiated lazily.
    if name == "pipeline":
        return get_pipeline()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ─── CLI Test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        try:
            raw = json.loads(sys.argv[1])
        except json.JSONDecodeError:
            print("Usage: python3 signal_pipeline.py '<json>'")
            print("Example: python3 signal_pipeline.py '{\"symbol\":\"BTC\",\"action\":\"buy\",\"price\":65000,\"confidence\":0.8}'")
            sys.exit(1)
    else:
        # Demo signal
        raw = {
            "symbol": "BTC",
            "action": "buy",
            "price": 65000.0,
            "confidence": 0.82,
            "strategy": "PairTrading_v3",
            "take_profit": 67000.0,
            "stop_loss": 64000.0,
        }

    result = get_pipeline().process(raw)
    s = result.scored
    print(f"\n{'='*60}")
    print(f"Signal Pipeline Result — ID: {s.pipeline_id}")
    print(f"{'='*60}")
    print(f"Symbol:      {s.symbol} | Action: {s.action.upper()} | Direction: {s.direction}")
    print(f"Price:       ${s.price:,.4f}")
    print(f"Confidence:  {s.confidence:.0%}")
    print(f"Score:       {s.score:.1f}/100")
    print(f"Routing:     {s.routing}")
    print(f"Kernel OK:   {s.kernel_ok} {('| ' + s.kernel_reason) if s.kernel_reason else ''}")
    print(f"Position:    ${s.position_usd:.2f} ({s.position_pct:.2%})")
    print(f"Kelly:       raw={s.kelly_raw:.4f} capped={s.kelly_capped:.4f}")
    if s.rr_ratio > 0:
        print(f"R:R ratio:   {s.rr_ratio:.2f}:1")
    print(f"Audit:       {result.audit_path}")
    print(f"Elapsed:     {result.elapsed_ms}ms")
    if s.notes:
        print(f"Notes:       {'; '.join(s.notes)}")
    if result.confirmation_code:
        print(f"Conf code:   {result.confirmation_code}")
    print(f"Telegram:    {'sent' if result.telegram_sent else 'not sent (notify unavailable)'}")
    print()

    # Print kernel status
    ks = get_pipeline().kernel_status()
    print(f"Kernel Status: day={ks.get('day','?')} | blocked={ks.get('blocked')} | "
          f"consec_losses={ks.get('consecutive_loss_events','?')}")
