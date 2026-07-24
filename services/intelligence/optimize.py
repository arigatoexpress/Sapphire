"""Self-optimization loop — weekly adjustment of signal-enhancer weights.

Runs every Sunday at 23:00 (LaunchAgent). For the last 30 days of closed
signal outcomes in `data/signals/YYYY-MM-DD.jsonl`:

  1. Compute feature importance — for each factor (regime alignment,
     funding-crowded flag, kronos agreement, RSI band, confidence bucket),
     measure the conditional win rate on outcomes. The delta from the
     overall baseline is a first-order "importance" score.
  2. Gradient-style adjustment — REGIME_PENALTY moves toward the observed
     win rate of regime-contradiction trades. Damped with a 0.25 learning
     rate so a single noisy week doesn't overshoot.
  3. Persist new weights to `data/enhancer_weights.json`, log a
     before/after diff into `data/system_events.jsonl` and publish an
     `optimization.completed` event on the bus.

Intentionally conservative: weights are clamped to safe bounds and will
only update if we observed at least MIN_SAMPLES decisive trades.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SAPPHIRE_ROOT = Path(__file__).resolve().parents[2]
if str(SAPPHIRE_ROOT) not in sys.path:
    sys.path.insert(0, str(SAPPHIRE_ROOT))

from lib.core.routine_pause import abort_if_paused  # noqa: E402

SIGNALS_DIR = SAPPHIRE_ROOT / "data" / "signals"
WEIGHTS_FILE = SAPPHIRE_ROOT / "data" / "enhancer_weights.json"
EVENTS_LOG = SAPPHIRE_ROOT / "data" / "system_events.jsonl"

LOOKBACK_DAYS = 30
MIN_SAMPLES = 10  # minimum decisive trades to act on
LEARNING_RATE = 0.25  # damping factor when adjusting weights
REGIME_PENALTY_BOUNDS = (0.50, 0.95)
REGIME_BOOST_BOUNDS = (1.00, 1.20)

# Default weights the enhancer ships with — optimizer only writes diffs.
DEFAULT_WEIGHTS = {
    "regime_penalty": 0.80,
    "regime_boost": 1.05,
}


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass
class OptimizationReport:
    generated_at: str
    lookback_days: int
    total_trades: int
    decisive_trades: int
    baseline_win_rate: float | None
    feature_importance: dict
    old_weights: dict
    new_weights: dict
    weight_changes: dict
    notes: list[str] = field(default_factory=list)
    applied: bool = False


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _load_closed_signals(days: int) -> list[dict]:
    """Load scored signals with outcomes from the last ``days`` days."""
    if not SIGNALS_DIR.exists():
        return []

    cutoff = datetime.now(UTC) - timedelta(days=days)
    out: list[dict] = []
    for f in sorted(SIGNALS_DIR.glob("*.jsonl")):
        # Skip files older than cutoff by date in filename (YYYY-MM-DD.jsonl)
        try:
            date_str = f.stem
            day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            if day < cutoff - timedelta(days=1):
                continue
        except ValueError:
            pass

        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("outcome") not in {"win", "loss", "break_even"}:
                    continue
                out.append(r)
        except OSError:
            continue

    return out


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------


def _compute_feature_importance(signals: list[dict]) -> tuple[dict, float | None]:
    """For each categorical factor, compute win rate by bucket.

    Returns (feature_importance, baseline_win_rate).

    importance[feature][bucket] = {
        "trades": int, "wins": int, "losses": int, "win_rate": float | None,
        "delta_vs_baseline": float | None,
    }
    """
    wins = sum(1 for s in signals if s.get("outcome") == "win")
    losses = sum(1 for s in signals if s.get("outcome") == "loss")
    decisive = wins + losses
    baseline = (wins / decisive) if decisive > 0 else None

    def _bucketize(conf: float) -> str:
        if conf is None:
            return "unknown"
        if conf >= 0.80:
            return ">=0.80"
        if conf >= 0.65:
            return "0.65-0.80"
        if conf >= 0.50:
            return "0.50-0.65"
        return "<0.50"

    features: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0})
    )

    for s in signals:
        outcome = s.get("outcome")
        regime = str(s.get("regime") or "UNKNOWN").upper()
        funding_flag = str(s.get("funding_flag") or "none")
        kronos_dir = str(s.get("kronos_direction") or "none")
        conf_bucket = _bucketize(float(s.get("confidence") or 0.0))
        flags = s.get("enhancer_flags") or []
        has_regime_contra = "regime_contradiction" in flags
        has_crowded = "crowded_entry" in flags
        has_kronos_contra = "kronos_contradiction" in flags

        updates = [
            ("regime", regime),
            ("funding_flag", funding_flag),
            ("kronos_direction", kronos_dir),
            ("confidence_bucket", conf_bucket),
            ("regime_contradiction", "yes" if has_regime_contra else "no"),
            ("crowded_entry", "yes" if has_crowded else "no"),
            ("kronos_contradiction", "yes" if has_kronos_contra else "no"),
        ]
        for feature, bucket in updates:
            b = features[feature][bucket]
            b["trades"] += 1
            if outcome == "win":
                b["wins"] += 1
            elif outcome == "loss":
                b["losses"] += 1

    # Build summary with win_rate + delta from baseline
    importance: dict[str, dict] = {}
    for feature, buckets in features.items():
        importance[feature] = {}
        for bucket, b in buckets.items():
            dec = b["wins"] + b["losses"]
            wr = (b["wins"] / dec) if dec > 0 else None
            delta = None
            if wr is not None and baseline is not None:
                delta = round(wr - baseline, 4)
            importance[feature][bucket] = {
                "trades": b["trades"],
                "wins": b["wins"],
                "losses": b["losses"],
                "win_rate": round(wr, 4) if wr is not None else None,
                "delta_vs_baseline": delta,
            }
    return importance, baseline


# ---------------------------------------------------------------------------
# Weight adjustment
# ---------------------------------------------------------------------------


def _load_current_weights() -> dict:
    if WEIGHTS_FILE.exists():
        try:
            return {**DEFAULT_WEIGHTS, **json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))}
        except (OSError, json.JSONDecodeError):
            pass
    return dict(DEFAULT_WEIGHTS)


def _save_weights(weights: dict) -> None:
    WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEIGHTS_FILE.write_text(json.dumps(weights, indent=2))


def _adjust_weights(
    current: dict, importance: dict, baseline: float | None
) -> tuple[dict, list[str]]:
    """Move weights toward the observed outcome of flagged signals.

    Logic:
      - If regime-contradiction trades underperform the baseline, lower the
        penalty multiplier (push confidence down more aggressively).
      - If they outperform, raise the penalty toward 1.0 (the enhancer was
        being too harsh — trust the signal more).
      - Mirror logic for the boost using regime-alignment outperformance.
    """
    new = dict(current)
    notes: list[str] = []

    # --- REGIME_PENALTY -------------------------------------------------
    contra_bucket = (importance.get("regime_contradiction") or {}).get("yes") or {}
    contra_wr = contra_bucket.get("win_rate")
    contra_n = contra_bucket.get("trades", 0)

    if baseline is not None and contra_wr is not None and contra_n >= 3:
        # Target penalty = observed win rate of contradicted trades relative
        # to baseline. Worse performance → smaller multiplier (stronger penalty).
        performance_ratio = max(0.1, contra_wr / baseline) if baseline > 0 else 1.0
        target = min(1.0, performance_ratio) * 0.95
        old = current["regime_penalty"]
        new_val = old + (target - old) * LEARNING_RATE
        new_val = max(REGIME_PENALTY_BOUNDS[0], min(REGIME_PENALTY_BOUNDS[1], new_val))
        new["regime_penalty"] = round(new_val, 4)
        notes.append(
            f"regime_penalty: {old:.3f} → {new_val:.3f} "
            f"(contra win_rate={contra_wr:.2%} over {contra_n} trades, "
            f"baseline={baseline:.2%})"
        )
    else:
        notes.append(
            f"regime_penalty unchanged — insufficient contradiction samples (n={contra_n})"
        )

    # --- REGIME_BOOST ---------------------------------------------------
    # Approximate "aligned" bucket = non-contra trades in a strong regime
    regime_perf = importance.get("regime") or {}
    on = regime_perf.get("RISK_ON") or {}
    off = regime_perf.get("RISK_OFF") or {}
    aligned_wins = on.get("wins", 0) + off.get("wins", 0)
    aligned_losses = on.get("losses", 0) + off.get("losses", 0)
    aligned_decisive = aligned_wins + aligned_losses
    aligned_wr = (aligned_wins / aligned_decisive) if aligned_decisive > 0 else None

    if baseline is not None and aligned_wr is not None and aligned_decisive >= 5:
        uplift = aligned_wr - baseline  # +0.05 means 5pp better than baseline
        target = 1.0 + max(0.0, uplift) * 2.0  # 5pp uplift → +10% boost (capped by bounds)
        old = current["regime_boost"]
        new_val = old + (target - old) * LEARNING_RATE
        new_val = max(REGIME_BOOST_BOUNDS[0], min(REGIME_BOOST_BOUNDS[1], new_val))
        new["regime_boost"] = round(new_val, 4)
        notes.append(
            f"regime_boost: {old:.3f} → {new_val:.3f} "
            f"(aligned win_rate={aligned_wr:.2%} over {aligned_decisive} trades, "
            f"uplift={uplift:+.2%})"
        )
    else:
        notes.append(
            f"regime_boost unchanged — insufficient aligned samples (n={aligned_decisive})"
        )

    return new, notes


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------


def _publish_event(report: OptimizationReport) -> None:
    """Publish to event bus + append to system_events.jsonl audit log."""
    payload = {
        "lookback_days": report.lookback_days,
        "total_trades": report.total_trades,
        "decisive_trades": report.decisive_trades,
        "baseline_win_rate": report.baseline_win_rate,
        "old_weights": report.old_weights,
        "new_weights": report.new_weights,
        "weight_changes": report.weight_changes,
        "applied": report.applied,
        "notes": report.notes,
    }

    # Event bus (Redis or JSONL fallback)
    try:
        from lib.core.event_bus import get_bus

        get_bus().publish("optimization.completed", payload, source="optimize")
    except Exception as e:
        log.warning("event bus publish failed: %s", e)

    # Legacy system_events.jsonl audit (tagged for dashboard event stream)
    try:
        EVENTS_LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "timestamp": report.generated_at,
            "type": "optimization.completed",
            "service": "intelligence.optimize",
            "priority": "p2",
            "tags": ["agent:optimizer", "service:intelligence"],
            "message": (
                f"self-optimization applied={report.applied} "
                f"trades={report.decisive_trades} "
                f"changes={report.weight_changes}"
            ),
            "data": payload,
        }
        with EVENTS_LOG.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except Exception as e:
        log.warning("system_events.jsonl append failed: %s", e)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run(dry_run: bool = False) -> OptimizationReport:
    """Execute the weekly optimization pass."""
    signals = _load_closed_signals(LOOKBACK_DAYS)
    wins = sum(1 for s in signals if s.get("outcome") == "win")
    losses = sum(1 for s in signals if s.get("outcome") == "loss")
    decisive = wins + losses
    importance, baseline = _compute_feature_importance(signals)
    current = _load_current_weights()

    notes: list[str] = []
    new_weights = dict(current)
    applied = False

    if decisive < MIN_SAMPLES:
        notes.append(f"skipped — only {decisive} decisive trades (need >= {MIN_SAMPLES})")
    else:
        new_weights, adjust_notes = _adjust_weights(current, importance, baseline)
        notes.extend(adjust_notes)
        if new_weights != current and not dry_run:
            _save_weights(new_weights)
            applied = True
        elif dry_run:
            notes.append("dry-run — weights not persisted")

    changes = {
        k: {"from": current.get(k), "to": new_weights.get(k)}
        for k in sorted(set(current) | set(new_weights))
        if current.get(k) != new_weights.get(k)
    }

    report = OptimizationReport(
        generated_at=datetime.now(UTC).isoformat(),
        lookback_days=LOOKBACK_DAYS,
        total_trades=len(signals),
        decisive_trades=decisive,
        baseline_win_rate=round(baseline, 4) if baseline is not None else None,
        feature_importance=importance,
        old_weights=current,
        new_weights=new_weights,
        weight_changes=changes,
        notes=notes,
        applied=applied,
    )

    _publish_event(report)

    log.info(
        "optimization complete — applied=%s trades=%s changes=%s",
        applied,
        decisive,
        changes,
    )
    return report


if __name__ == "__main__":
    abort_if_paused("self-optimization")
    dry = "--dry-run" in sys.argv
    r = run(dry_run=dry)
    print(json.dumps(asdict(r), indent=2, default=str))
