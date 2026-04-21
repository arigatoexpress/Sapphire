"""Paper-only alpha agent built on the multi-agent harness."""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from lib.agents.base import Action, BaseAgent, Result
from lib.core.event_bus import EventBus

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SIGNALS_DIR = ROOT / "data" / "signals"
PORTFOLIO_FILE = ROOT / "data" / "paper_portfolio.json"
MARKET_TOOL = ROOT / "plugins" / "claw-sapphire" / "tools" / "market.py"
STOP_LOSS_ATR_MULT = 1.5
TAKE_PROFIT_ATR_MULT = 2.5
FEE_RATE_PER_LEG = 0.004

QuoteFetcher = Callable[[Iterable[str]], dict[str, float]]
CloseHook = Callable[[Action], dict[str, Any] | None]


class AlphaAgent(BaseAgent):
    """Scores paper positions and proposes closes when ATR exits are crossed."""

    def __init__(
        self,
        interval_sec: int = 300,
        event_bus: EventBus | None = None,
        signals_dir: Path = SIGNALS_DIR,
        portfolio_file: Path = PORTFOLIO_FILE,
        market_tool: Path = MARKET_TOOL,
        quote_fetcher: QuoteFetcher | None = None,
        close_hook: CloseHook | None = None,
    ) -> None:
        """Initialize the paper-only alpha agent.

        Args:
            interval_sec: Cycle interval in seconds.
            event_bus: Optional bus override for tests.
            signals_dir: Directory containing signal JSONL files.
            portfolio_file: Paper portfolio state file.
            market_tool: Market data CLI used for quote lookup.
            quote_fetcher: Optional quote loader for tests.
            close_hook: Optional close proposal hook.
        """
        super().__init__(
            name="alpha",
            interval_sec=interval_sec,
            event_bus=event_bus or EventBus(source="agent:alpha"),
        )
        self.signals_dir = signals_dir
        self.portfolio_file = portfolio_file
        self.market_tool = market_tool
        self._quote_fetcher = quote_fetcher or self._fetch_quotes_via_market_tool
        self._close_hook = close_hook or self._todo_close_hook
        self._planned_signal_ids: list[str] = []

    def plan(self) -> list[Action]:
        """Read open paper positions and translate them into scoring actions."""
        signal_index = self._load_signal_index()
        portfolio = self._load_portfolio()
        positions = [pos for pos in portfolio.get("positions", []) if isinstance(pos, dict)]
        quotes = self._quote_fetcher(
            position["symbol"] for position in positions if position.get("symbol")
        )

        actions: list[Action] = []
        planned_signal_ids: list[str] = []
        for position in positions:
            evaluation = self._evaluate_position(position, signal_index, quotes)
            if evaluation is None:
                continue
            planned_signal_ids.append(evaluation["signal_id"])
            actions.append(Action(kind="score_signal", payload=evaluation))
            if evaluation["action"] == "close":
                actions.append(Action(kind="close_position", payload=evaluation))

        self._planned_signal_ids = planned_signal_ids
        return actions

    def act(self, actions: list[Action]) -> list[Result]:
        """Emit score and close proposal events for the planned actions."""
        results: list[Result] = []
        for action in actions:
            payload = action.payload
            if action.kind == "score_signal":
                event_payload = {
                    "signal_id": payload["signal_id"],
                    "score": payload["score"],
                    "action": payload["action"],
                }
                self.emit_event("agent.alpha.signal_scored", event_payload)
                results.append(Result(action=action, status="scored", payload=event_payload))
                continue

            if action.kind == "close_position":
                event_payload = {
                    "signal_id": payload["signal_id"],
                    "pnl_usd": payload["pnl_usd"],
                }
                hook_payload = self._close_hook(action) or {}
                self.emit_event("agent.alpha.position_closed", event_payload)
                results.append(
                    Result(
                        action=action,
                        status="close_proposed",
                        payload={**event_payload, **hook_payload},
                    )
                )
                continue

            results.append(Result(action=action, status="ignored", payload={}))
        return results

    def observe(self, results: list[Result]) -> dict[str, Any]:
        """Summarize the last cycle for the next planning step."""
        scored = [result for result in results if result.action.kind == "score_signal"]
        closed = [result for result in results if result.action.kind == "close_position"]
        return {
            "agent": self.name,
            "cycle_count": self.cycle_count + 1,
            "scored_positions": len(scored),
            "close_candidates": len(closed),
            "planned_signal_ids": self._planned_signal_ids,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def _load_signal_index(self) -> dict[str, dict[str, Any]]:
        """Load the latest signal records keyed by signal or pipeline identifier."""
        index: dict[str, dict[str, Any]] = {}
        if not self.signals_dir.exists():
            return index

        for path in sorted(self.signals_dir.glob("*.jsonl")):
            try:
                raw_lines = path.read_text().splitlines()
            except OSError:
                continue
            for raw_line in raw_lines:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                signal_id = str(record.get("signal_id") or record.get("pipeline_id") or "")
                if signal_id:
                    index[signal_id] = record
        return index

    def _load_portfolio(self) -> dict[str, Any]:
        """Load the paper portfolio from disk."""
        if not self.portfolio_file.exists():
            return {"positions": []}
        try:
            return json.loads(self.portfolio_file.read_text())
        except (OSError, json.JSONDecodeError):
            return {"positions": []}

    def _evaluate_position(
        self,
        position: dict[str, Any],
        signal_index: dict[str, dict[str, Any]],
        quotes: dict[str, float],
    ) -> dict[str, Any] | None:
        """Convert a position snapshot into an evaluation payload."""
        symbol = str(position.get("symbol") or "").strip()
        if not symbol:
            return None
        current_price = quotes.get(symbol)
        if current_price is None:
            return None

        entry_price = float(position.get("entry_price") or 0.0)
        if entry_price <= 0:
            return None

        signal_id = self._resolve_signal_id(position, signal_index)
        stop_loss, take_profit, atr = self._resolve_levels(position)
        side = self._normalize_side(position)
        close_reason = self._close_reason(side, current_price, stop_loss, take_profit)
        action_name = "close" if close_reason else "hold"

        return {
            "signal_id": signal_id,
            "symbol": symbol,
            "side": side,
            "score": self._score_position(side, entry_price, current_price, stop_loss, take_profit),
            "action": action_name,
            "reason": close_reason,
            "current_price": round(current_price, 4),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": atr,
            "pnl_usd": self._net_pnl_usd(position, current_price),
        }

    def _resolve_signal_id(
        self,
        position: dict[str, Any],
        signal_index: dict[str, dict[str, Any]],
    ) -> str:
        """Return the best available signal identifier for a position."""
        direct_id = str(position.get("signal_id") or position.get("pipeline_id") or "").strip()
        if direct_id:
            return direct_id

        symbol = str(position.get("symbol") or "")
        for signal_id, record in reversed(signal_index.items()):
            if record.get("symbol") == symbol:
                return signal_id

        opened_at = str(position.get("opened_at") or "unknown")
        return f"{symbol}:{opened_at}"

    def _resolve_levels(self, position: dict[str, Any]) -> tuple[float, float, float]:
        """Resolve stop-loss, take-profit, and ATR values for a position."""
        entry_price = float(position.get("entry_price") or 0.0)
        side = self._normalize_side(position)
        stop_loss = float(position.get("stop_loss") or 0.0)
        take_profit = float(position.get("take_profit") or 0.0)
        atr = float(position.get("atr") or 0.0)

        if atr <= 0:
            atr = self._derive_atr(entry_price, side, stop_loss, take_profit)

        if stop_loss <= 0:
            stop_loss = (
                entry_price - atr * STOP_LOSS_ATR_MULT
                if side == "long"
                else entry_price + atr * STOP_LOSS_ATR_MULT
            )
        if take_profit <= 0:
            take_profit = (
                entry_price + atr * TAKE_PROFIT_ATR_MULT
                if side == "long"
                else entry_price - atr * TAKE_PROFIT_ATR_MULT
            )
        return round(stop_loss, 4), round(take_profit, 4), round(atr, 4)

    def _derive_atr(
        self,
        entry_price: float,
        side: str,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        """Derive ATR from known levels when it is missing in the portfolio."""
        if entry_price <= 0:
            return 0.0
        if stop_loss > 0:
            return abs(entry_price - stop_loss) / STOP_LOSS_ATR_MULT
        if take_profit > 0:
            return abs(take_profit - entry_price) / TAKE_PROFIT_ATR_MULT
        return entry_price * 0.03

    def _normalize_side(self, position: dict[str, Any]) -> str:
        """Normalize various long/short encodings into a simple label."""
        raw_side = str(position.get("side") or position.get("direction") or "").upper()
        return "short" if raw_side in {"SELL", "SHORT"} else "long"

    def _close_reason(
        self,
        side: str,
        current_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> str | None:
        """Return the close reason when the price crosses SL or TP."""
        if side == "long":
            if current_price <= stop_loss:
                return "stop_loss"
            if current_price >= take_profit:
                return "take_profit"
            return None

        if current_price >= stop_loss:
            return "stop_loss"
        if current_price <= take_profit:
            return "take_profit"
        return None

    def _score_position(
        self,
        side: str,
        entry_price: float,
        current_price: float,
        stop_loss: float,
        take_profit: float,
    ) -> float:
        """Score the health of an open position on a 0-100 scale."""
        if self._close_reason(side, current_price, stop_loss, take_profit):
            return 100.0

        if side == "long":
            reward_span = max(take_profit - entry_price, 1e-9)
            risk_span = max(entry_price - stop_loss, 1e-9)
            reward_progress = (current_price - entry_price) / reward_span
            risk_progress = (entry_price - current_price) / risk_span
        else:
            reward_span = max(entry_price - take_profit, 1e-9)
            risk_span = max(stop_loss - entry_price, 1e-9)
            reward_progress = (entry_price - current_price) / reward_span
            risk_progress = (current_price - entry_price) / risk_span

        raw_score = 50.0 + 50.0 * (reward_progress - risk_progress)
        return round(max(0.0, min(100.0, raw_score)), 2)

    def _net_pnl_usd(self, position: dict[str, Any], current_price: float) -> float:
        """Estimate net PnL, including round-trip friction."""
        qty = float(position.get("qty") or 0.0)
        entry_price = float(position.get("entry_price") or 0.0)
        if qty <= 0 or entry_price <= 0:
            return 0.0

        side = self._normalize_side(position)
        gross = (
            (current_price - entry_price) * qty
            if side == "long"
            else (entry_price - current_price) * qty
        )
        entry_fee = float(
            position.get("remaining_entry_fee_usd")
            or position.get("estimated_entry_fee_usd")
            or entry_price * qty * FEE_RATE_PER_LEG
        )
        exit_fee = current_price * qty * FEE_RATE_PER_LEG
        return round(gross - entry_fee - exit_fee, 2)

    def _fetch_quotes_via_market_tool(self, symbols: Iterable[str]) -> dict[str, float]:
        """Fetch quotes through the existing market CLI over stdin JSON."""
        quotes: dict[str, float] = {}
        for symbol in sorted(set(symbols)):
            price = self._fetch_quote(symbol)
            if price is not None:
                quotes[symbol] = price
        return quotes

    def _fetch_quote(self, symbol: str) -> float | None:
        """Fetch a single quote using the market tool."""
        payload = (
            {
                "action": "crypto",
                "symbol": f"{symbol[:-4]}-USD",
                "start_date": date.today().isoformat(),
            }
            if symbol.endswith("USDT")
            else {"action": "quote", "symbol": symbol}
        )

        try:
            proc = subprocess.run(
                ["python3", str(self.market_tool)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            log.warning("Alpha quote lookup failed for %s: %s", symbol, exc)
            return None

        if proc.returncode != 0 or not proc.stdout.strip():
            log.warning("Alpha quote lookup returned no data for %s", symbol)
            return None

        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            log.warning("Alpha quote lookup returned invalid JSON for %s", symbol)
            return None

        if isinstance(parsed, list) and parsed:
            last_bar = parsed[-1]
            price = last_bar.get("close")
            return float(price) if isinstance(price, (int, float)) else None
        if isinstance(parsed, dict):
            price = parsed.get("price")
            return float(price) if isinstance(price, (int, float)) else None
        return None

    def _todo_close_hook(self, action: Action) -> dict[str, Any]:
        """Return the placeholder payload for the eventual paper close hook."""
        # TODO: wire this action into the paper portfolio mutation path.
        return {
            "status": "pending_hook",
            "note": "paper portfolio write hook not wired yet",
            "proposed_at": datetime.now(UTC).isoformat(),
            "signal_id": action.payload["signal_id"],
        }


__all__ = ["AlphaAgent"]
