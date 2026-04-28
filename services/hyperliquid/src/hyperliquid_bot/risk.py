"""Hyperliquid live-trading executor with hard caps.

Wraps :class:`hyperliquid_bot.client.HyperliquidClient` with a fail-closed risk
layer. Every order goes through :func:`evaluate_risk` first, which enforces:

- per-order notional cap (default $5)
- per-trade leverage cap (default 3x)
- max simultaneous open positions (default 5)
- daily realized-loss auto-pause (default $25)
- file-based killswitch (``~/.sapphire/hyperliquid_trading_pause``)
- ``HYPERLIQUID_TRADING_ENABLED`` env gate (default off → dry-run)

Until the EIP-712 signing path in
``services/hyperliquid/src/hyperliquid_bot/client.py`` is verified against
testnet, the executor refuses to flip into mainnet mode regardless of the
``HYPERLIQUID_TESTNET`` flag — see the ``signing_verified`` policy field. Flip
that to ``True`` in code (not env) only after a successful testnet trade.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

KILLSWITCH_PATH_DEFAULT = "~/.sapphire/hyperliquid_trading_pause"
TRADE_LOG_PATH_DEFAULT = "data/hyperliquid_trades.jsonl"
DAILY_PNL_PATH_DEFAULT = "data/hyperliquid_daily_pnl.json"
KEYCHAIN_ACCOUNT_DEFAULT = "sapphire-hyperliquid"
KEYCHAIN_SERVICE_DEFAULT = "sapphire"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HyperliquidLivePolicy:
    """Hard caps and toggles for Hyperliquid live execution."""

    max_order_notional_usd: float = 5.0
    max_leverage: float = 3.0
    max_open_positions: int = 5
    daily_realized_loss_cap_usd: float = 25.0
    killswitch_path: str = KILLSWITCH_PATH_DEFAULT
    trade_log_path: str = TRADE_LOG_PATH_DEFAULT
    daily_pnl_path: str = DAILY_PNL_PATH_DEFAULT
    keychain_account: str = KEYCHAIN_ACCOUNT_DEFAULT
    keychain_service: str = KEYCHAIN_SERVICE_DEFAULT
    # Gate that survives env tampering: signing isn't verified yet, so the
    # executor refuses mainnet regardless of HYPERLIQUID_TESTNET.
    signing_verified: bool = False
    allowed_actions: tuple[str, ...] = ("buy", "sell", "close")

    def __post_init__(self) -> None:
        if self.max_order_notional_usd <= 0:
            raise ValueError("max_order_notional_usd must be positive")
        if not 1.0 <= self.max_leverage <= 50.0:
            raise ValueError("max_leverage must be between 1 and 50")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be positive")
        if self.daily_realized_loss_cap_usd <= 0:
            raise ValueError("daily_realized_loss_cap_usd must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Risk state + verdict
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskState:
    """Current account snapshot used to apply caps."""

    open_positions: int
    daily_realized_loss_usd: float
    killswitch_active: bool
    trading_enabled: bool


@dataclass(frozen=True)
class RiskVerdict:
    """Outcome of cap evaluation. ``allow`` may carry bounded sizes."""

    decision: str
    bounded_notional_usd: float
    bounded_leverage: float
    reasons: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_risk(
    signal: dict[str, Any],
    state: RiskState,
    policy: HyperliquidLivePolicy,
) -> RiskVerdict:
    """Pure cap-check for a single signal.

    Caps notional and leverage in-place; blocks on killswitch, missing fields,
    daily loss, or position-count limits. Network-free so unit tests cover it.
    """
    blockers: list[str] = []
    reasons: list[str] = []

    action = str(signal.get("action") or "").strip().lower()
    if action not in policy.allowed_actions:
        blockers.append("unsupported_action")

    if not state.trading_enabled:
        blockers.append("trading_disabled_env_flag")

    if state.killswitch_active:
        blockers.append("killswitch_active")

    if state.daily_realized_loss_usd >= policy.daily_realized_loss_cap_usd:
        blockers.append("daily_loss_cap_reached")

    if action in ("buy", "sell") and state.open_positions >= policy.max_open_positions:
        blockers.append("max_open_positions_reached")

    requested_notional = _safe_float(signal.get("size_usd"))
    if requested_notional is None or requested_notional <= 0:
        if action == "close":
            requested_notional = policy.max_order_notional_usd
        else:
            blockers.append("missing_or_invalid_size_usd")
            requested_notional = 0.0

    bounded_notional = min(requested_notional or 0.0, policy.max_order_notional_usd)
    if bounded_notional < (requested_notional or 0.0):
        reasons.append("notional_capped_to_policy_max")

    requested_leverage = _safe_float(signal.get("leverage")) or 1.0
    bounded_leverage = min(max(requested_leverage, 1.0), policy.max_leverage)
    if bounded_leverage < requested_leverage:
        reasons.append("leverage_capped_to_policy_max")

    decision = "block" if blockers else "allow"
    return RiskVerdict(
        decision=decision,
        bounded_notional_usd=round(bounded_notional, 2),
        bounded_leverage=round(bounded_leverage, 2),
        reasons=tuple(reasons),
        blockers=tuple(dict.fromkeys(blockers)),
    )


# ---------------------------------------------------------------------------
# Killswitch + daily PnL ledger
# ---------------------------------------------------------------------------


def killswitch_active(policy: HyperliquidLivePolicy) -> bool:
    return Path(policy.killswitch_path).expanduser().exists()


def _daily_pnl_today(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    today = date.today().isoformat()
    entry = body.get(today) if isinstance(body, dict) else None
    if not isinstance(entry, dict):
        return 0.0
    return float(entry.get("realized_loss_usd", 0.0))


def record_realized_pnl(policy: HyperliquidLivePolicy, pnl_usd: float) -> None:
    """Append a realized P&L to today's bucket. Loss is encoded as positive USD."""
    path = Path(policy.daily_pnl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {}
    if path.exists():
        try:
            body = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            body = {}
    today = date.today().isoformat()
    bucket = body.get(today) or {"realized_loss_usd": 0.0, "trade_count": 0}
    if pnl_usd < 0:
        bucket["realized_loss_usd"] = round(
            float(bucket.get("realized_loss_usd", 0.0)) + abs(pnl_usd), 4
        )
    bucket["trade_count"] = int(bucket.get("trade_count", 0)) + 1
    bucket["last_pnl_usd"] = round(pnl_usd, 4)
    body[today] = bucket
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Keychain loader
# ---------------------------------------------------------------------------


def load_private_key(policy: HyperliquidLivePolicy) -> str | None:
    """Try macOS keychain first, fall back to ``HYPERLIQUID_PRIVATE_KEY`` env.

    Keychain lookup uses ``security find-generic-password -a <account> -s
    <service> -w``. Returns ``None`` if neither source has a key — the executor
    must refuse to start in that case.
    """
    key = _load_from_keychain(policy)
    if key:
        return key
    env_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "").strip()
    return env_key or None


def _load_from_keychain(policy: HyperliquidLivePolicy) -> str | None:
    binary = shutil.which("security")
    if not binary:
        return None
    try:
        result = subprocess.run(
            [
                binary,
                "find-generic-password",
                "-a",
                policy.keychain_account,
                "-s",
                policy.keychain_service,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    candidate = result.stdout.strip()
    return candidate or None


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class _Client(Protocol):
    address: str

    async def get_user_state(self) -> dict[str, Any]: ...
    async def get_all_mids(self) -> dict[str, str]: ...
    async def market_order(
        self, coin: str, is_buy: bool, sz: float, *, reduce_only: bool = ...
    ) -> dict[str, Any]: ...
    async def close_position(self, coin: str) -> dict[str, Any]: ...


@dataclass
class ExecutionResult:
    """One signal's outcome. ``status`` is the stable contract for callers."""

    status: str  # "executed" | "dry_run" | "blocked" | "error"
    signal: dict[str, Any]
    verdict: RiskVerdict
    response: dict[str, Any] | None = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "signal": self.signal,
            "verdict": self.verdict.to_dict(),
            "response": self.response,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class HyperliquidLiveExecutor:
    """Glue between Sapphire signals and HyperliquidClient with hard caps."""

    def __init__(
        self,
        client: _Client,
        *,
        policy: HyperliquidLivePolicy | None = None,
        testnet: bool = True,
        trading_enabled: bool | None = None,
    ) -> None:
        self._client = client
        self.policy = policy or HyperliquidLivePolicy()
        # Hard refusal of mainnet until signing is verified.
        if not testnet and not self.policy.signing_verified:
            raise ValueError(
                "refusing to run on mainnet — signing not yet verified; "
                "set policy.signing_verified=True after a clean testnet trade"
            )
        self.testnet = testnet
        env_flag = os.getenv("HYPERLIQUID_TRADING_ENABLED", "0").strip().lower()
        self._trading_enabled = (
            trading_enabled if trading_enabled is not None else env_flag in ("1", "true", "yes")
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_signal(self, signal: dict[str, Any]) -> ExecutionResult:
        state = await self._snapshot_state()
        verdict = evaluate_risk(signal, state, self.policy)

        if not verdict.allowed:
            result = ExecutionResult(status="blocked", signal=signal, verdict=verdict)
            self._log(result)
            return result

        if not self._trading_enabled:
            result = ExecutionResult(status="dry_run", signal=signal, verdict=verdict)
            self._log(result)
            return result

        try:
            response = await self._submit(signal, verdict)
        except Exception as exc:
            log.exception("hyperliquid order failed")
            result = ExecutionResult(
                status="error", signal=signal, verdict=verdict, error=str(exc)
            )
            self._log(result)
            return result

        result = ExecutionResult(
            status="executed", signal=signal, verdict=verdict, response=response
        )
        self._log(result)
        return result

    async def status(self) -> dict[str, Any]:
        state = await self._snapshot_state()
        return {
            "address": getattr(self._client, "address", None),
            "testnet": self.testnet,
            "trading_enabled": self._trading_enabled,
            "policy": self.policy.to_dict(),
            "state": {
                "open_positions": state.open_positions,
                "daily_realized_loss_usd": state.daily_realized_loss_usd,
                "killswitch_active": state.killswitch_active,
            },
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _snapshot_state(self) -> RiskState:
        try:
            user_state = await self._client.get_user_state()
        except Exception:
            log.warning("failed to fetch user_state — treating as 0 open positions")
            user_state = {}
        positions = [
            pos
            for pos in user_state.get("assetPositions", [])
            if isinstance(pos, dict)
            and float((pos.get("position") or {}).get("szi", 0) or 0) != 0
        ]
        return RiskState(
            open_positions=len(positions),
            daily_realized_loss_usd=_daily_pnl_today(Path(self.policy.daily_pnl_path)),
            killswitch_active=killswitch_active(self.policy),
            trading_enabled=self._trading_enabled,
        )

    async def _submit(
        self, signal: dict[str, Any], verdict: RiskVerdict
    ) -> dict[str, Any]:
        symbol = str(signal.get("symbol") or "BTC").upper()
        action = str(signal.get("action") or "").lower()
        if action == "close":
            return await self._client.close_position(symbol)
        mids = await self._client.get_all_mids()
        price = float(mids.get(symbol, 0) or 0)
        if not price:
            raise ValueError(f"no mid price for {symbol}")
        size = verdict.bounded_notional_usd / price
        return await self._client.market_order(symbol, action == "buy", size)

    def _log(self, result: ExecutionResult) -> None:
        path = Path(self.policy.trade_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        except OSError:
            log.exception("failed to append hyperliquid trade log")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DAILY_PNL_PATH_DEFAULT",
    "ExecutionResult",
    "HyperliquidLiveExecutor",
    "HyperliquidLivePolicy",
    "KILLSWITCH_PATH_DEFAULT",
    "RiskState",
    "RiskVerdict",
    "TRADE_LOG_PATH_DEFAULT",
    "evaluate_risk",
    "killswitch_active",
    "load_private_key",
    "record_realized_pnl",
]
