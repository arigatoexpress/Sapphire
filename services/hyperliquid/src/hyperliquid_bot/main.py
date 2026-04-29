"""Hyperliquid trading bot — subscribes to Sapphire signals and executes via the
risk-managed :class:`HyperliquidLiveExecutor`.

Signal flow:
    TradingView → webhook → signal_logger appends to data/trading_signals.jsonl
        → :class:`SignalSubscriber` tails the jsonl from a persisted offset
        → :class:`HyperliquidLiveExecutor` (caps + killswitch) → client

Caps (see ``hyperliquid_bot.risk.HyperliquidLivePolicy``):
    - $5/order notional
    - 3x max leverage
    - 5 max open positions
    - $25/day realized-loss auto-pause
    - killswitch file ``~/.sapphire/hyperliquid_trading_pause``
    - ``HYPERLIQUID_TRADING_ENABLED=0`` default → all orders dry-run
    - mainnet refused until signing is verified on testnet
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Load .env from service directory (dev convenience)
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except ImportError:
    pass

# Add shared lib to path (monorepo structure)
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "lib" / "core" / "src"))

from sapphire_core.logging_config import setup_logging  # noqa: E402

from .client import HyperliquidClient  # noqa: E402
from .risk import (  # noqa: E402
    HyperliquidLiveExecutor,
    HyperliquidLivePolicy,
    load_private_key,
)
from .signal_subscriber import (  # noqa: E402
    DEFAULT_OFFSET_PATH,
    DEFAULT_SIGNAL_PATH,
    SignalSubscriber,
)

logger = logging.getLogger(__name__)


def _resolve_testnet() -> bool:
    raw = os.getenv("HYPERLIQUID_TESTNET", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _resolve_signal_path() -> Path:
    override = os.getenv("HYPERLIQUID_SIGNAL_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return ROOT / DEFAULT_SIGNAL_PATH


def _resolve_offset_path() -> Path:
    override = os.getenv("HYPERLIQUID_SIGNAL_OFFSET_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return ROOT / DEFAULT_OFFSET_PATH


class HyperliquidBot:
    """Sapphire signal executor for Hyperliquid."""

    def __init__(
        self,
        *,
        policy: HyperliquidLivePolicy | None = None,
        testnet: bool | None = None,
    ) -> None:
        self.policy = policy or HyperliquidLivePolicy()
        private_key = load_private_key(self.policy)
        if not private_key:
            raise RuntimeError(
                "no Hyperliquid private key found — store one in macOS keychain "
                f"(account={self.policy.keychain_account!r} "
                f"service={self.policy.keychain_service!r}) "
                "or export HYPERLIQUID_PRIVATE_KEY for dev"
            )
        self.testnet = _resolve_testnet() if testnet is None else testnet
        self._client = HyperliquidClient(private_key, testnet=self.testnet)
        self._executor: HyperliquidLiveExecutor | None = None
        self._subscriber: SignalSubscriber | None = None
        self.running = False

    async def start(self) -> None:
        self.running = True
        logger.info("HyperliquidBot starting (testnet=%s)", self.testnet)
        async with self._client:
            self._executor = HyperliquidLiveExecutor(
                self._client, policy=self.policy, testnet=self.testnet
            )
            status = await self._executor.status()
            logger.info(
                "Account: address=%s open_positions=%d trading_enabled=%s",
                status.get("address"),
                status["state"]["open_positions"],
                status["trading_enabled"],
            )
            self._subscriber = SignalSubscriber(
                self._handle_signal,
                signal_path=_resolve_signal_path(),
                offset_path=_resolve_offset_path(),
                default_size_usd=self.policy.max_order_notional_usd,
            )
            await self._run_loop()

    async def _run_loop(self) -> None:
        """Tail the trading-signals jsonl and feed each entry to the executor."""
        assert self._subscriber is not None
        subscriber_task = asyncio.create_task(self._subscriber.run())
        try:
            while self.running:
                await asyncio.sleep(0.5)
        finally:
            self._subscriber.stop()
            subscriber_task.cancel()
            try:
                await subscriber_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _handle_signal(self, signal_payload: dict) -> None:
        """Subscriber callback — dispatch one translated signal to the executor."""
        if self._executor is None:
            logger.warning("signal received before executor ready; dropping")
            return
        result = await self._executor.execute_signal(signal_payload)
        logger.info(
            "signal handled symbol=%s action=%s status=%s",
            signal_payload.get("symbol"),
            signal_payload.get("action"),
            result.status,
        )

    async def execute(self, signal: dict) -> dict:
        """Execute a trading signal through the risk-managed executor.

        Args:
            signal: ``{symbol, action: 'buy'|'sell'|'close', size_usd, confidence,
                       leverage?}``

        Returns:
            ``ExecutionResult.to_dict()`` — includes status, verdict, response.
        """
        if self._executor is None:
            raise RuntimeError("bot not started — call start() first")
        result = await self._executor.execute_signal(signal)
        return result.to_dict()

    def stop(self) -> None:
        self.running = False


async def main() -> None:
    setup_logging()
    bot = HyperliquidBot()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.stop)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
