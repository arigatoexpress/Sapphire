"""Coordinating service that glues together client, strategy, and risk controls."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal, ROUND_DOWN
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import structlog

from .config import Settings, get_settings
from .credentials import CredentialManager, load_credentials
from .enums import OrderSide, OrderStatus
from .exchange import AsterClient, Ticker, Trade, TrailingStop, Execution, Order
from .mcp import MCPClient
from .optimization.bandit import EpsilonGreedyBandit
from .pubsub import PubSubClient
from .order_tags import generate_order_tag, parse_order_tag
from .risk import PortfolioState, RiskManager, Position
from .schemas import InferenceRequest
from .strategy import MarketSnapshot, MomentumStrategy, parse_market_payload
from .telegram import TelegramService, create_telegram_service
from .telegram_commands import TelegramCommandHandler

RiskOrchestratorClientType = Any
OrderIntent = None  # type: ignore[assignment]
# Temporarily disable MCP to fix deployment
# from .mcp import MCPClient, MCPMessageType, MCPProposalPayload, MCPResponsePayload
MCPClient = None
MCPMessageType = None
MCPProposalPayload = None
MCPResponsePayload = None
from .metrics import (
    ASTER_API_REQUESTS,
    LLM_CONFIDENCE,
    LLM_INFERENCE_TIME,
    PORTFOLIO_BALANCE,
    PORTFOLIO_LEVERAGE,
    POSITION_SIZE,
    RATE_LIMIT_EVENTS,
    RISK_LIMITS_BREACHED,
    SLIPPAGE_VIOLATIONS,
    LAST_TRADE_UNREALIZED_PNL,
    TRADE_EXECUTION_SUCCESS,
    TRADE_EXECUTION_FAILURE,
    DASHBOARD_SNAPSHOT_TIME,
    TELEGRAM_NOTIFICATIONS_SENT,
    TRADING_DECISIONS,
    REDIS_STREAM_FAILURES,
    MARKET_FEED_LATENCY,
    MARKET_FEED_ERRORS,
    POSITION_VERIFICATION_TIME,
    TRADE_EXECUTION_TIME,
    MCP_MESSAGES_TOTAL,
)


logger = structlog.get_logger("cloud_trader.service")


def _reward_for(side: str, change: float) -> float:
    if side == "BUY":
        return change
    if side == "SELL":
        return -change
    return 0.0


@dataclass
class HealthStatus:
    running: bool
    paper_trading: bool
    last_error: Optional[str]


AGENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "deepseek-v3",
        "name": "DeepSeek Momentum",
        "model": "DeepSeek-V3",
        "emoji": "💎",
        "symbols": ["BTCUSDT"],
        "description": "High-conviction BTC momentum execution powered by DeepSeek-V3.",
        "baseline_win_rate": 0.68,
    },
    {
        "id": "qwen-7b",
        "name": "Qwen Adaptive",
        "model": "Qwen2.5-7B",
        "emoji": "🜂",
        "symbols": ["ETHUSDT"],
        "description": "Adaptive ETH mean-reversion routing using Qwen2.5-7B.",
        "baseline_win_rate": 0.64,
    },
    {
        "id": "deepseek-v3-alt",
        "name": "DeepSeek Strategist",
        "model": "DeepSeek-V3",
        "emoji": "🔷",
        "symbols": ["SOLUSDT"],
        "description": "SOL breakout specialist using DeepSeek-V3.",
        "baseline_win_rate": 0.66,
    },
    {
        "id": "qwen-7b-alt",
        "name": "Qwen Guardian",
        "model": "Qwen2.5-7B",
        "emoji": "💠",
        "symbols": ["SUIUSDT"],
        "description": "SUI risk-balanced swing trading using Qwen2.5-7B.",
        "baseline_win_rate": 0.62,
    },
]


@dataclass
class AgentState:
    id: str
    name: str
    model: str
    emoji: str
    symbols: List[str]
    description: str
    baseline_win_rate: float
    status: str = "monitoring"
    total_trades: int = 0
    total_notional: float = 0.0
    total_pnl: float = 0.0
    exposure: float = 0.0
    last_trade: Optional[datetime] = None
    open_positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    equity_curve: Deque[Tuple[datetime, float]] = field(default_factory=lambda: deque(maxlen=96))


class TradingService:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._credential_manager = CredentialManager()
        self._exchange = AsterClient(
            self._credential_manager.get_credentials(),
            base_url=self._settings.rest_base_url,
        )
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._risk = RiskManager(self._settings)
        self._strategy = MomentumStrategy(
            threshold=self._settings.momentum_threshold,
            notional_fraction=self._settings.notional_fraction,
        )
        self._task = None
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)
        self._portfolio = PortfolioState(balance=1_000.0, total_exposure=0.0, positions={})
        self._bandit = EpsilonGreedyBandit(self._settings.bandit_epsilon, min_reward=-0.5)
        self._streams = PubSubClient(self._settings)
        self._orchestrator: Optional[RiskOrchestratorClientType] = None
        if self._settings.orchestrator_url:
            logger.warning(
                "Orchestrator URL configured but orchestrator client is not bundled; integration disabled"
            )
        self._mcp: Optional[MCPClient] = None
        # Temporarily disable MCP to get trading working ASAP
        # if self._settings.mcp_url:
        #     self._mcp = MCPClient(self._settings.mcp_url, self._settings.mcp_session_id)
        self._mcp = None

        # Initialize Telegram service for notifications
        self._telegram: Optional[TelegramService] = None
        self._telegram_commands: Optional[TelegramCommandHandler] = None

        # Agent tracking for live-only dashboards
        self._agent_states: Dict[str, AgentState] = {}
        self._symbol_to_agent: Dict[str, str] = {}
        for agent_def in AGENT_DEFINITIONS:
            agent_id = agent_def["id"]
            state = AgentState(
                id=agent_id,
                name=agent_def["name"],
                model=agent_def["model"],
                emoji=agent_def["emoji"],
                symbols=[symbol.upper() for symbol in agent_def["symbols"]],
                description=agent_def["description"],
                baseline_win_rate=agent_def["baseline_win_rate"],
            )
            self._agent_states[agent_id] = state
            for symbol in state.symbols:
                self._symbol_to_agent[symbol] = agent_id

        # Market data cache with timestamps for validation
        self._market_cache: Dict[str, Tuple[MarketSnapshot, float]] = {}
        self._market_cache_ttl = 60.0  # 60 seconds max age

        self._recent_trades: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._latest_portfolio_raw: Dict[str, Any] = {}
        self._latest_portfolio_frontend: Dict[str, Any] = {}
        self._price_cache: Dict[str, float] = {}
        self._symbol_filters: Dict[str, Dict[str, Decimal]] = {}

    async def _get_symbol_filters(self, symbol: str) -> Dict[str, Decimal]:
        symbol_key = symbol.upper()
        if symbol_key not in self._symbol_filters:
            filters = await self._exchange.get_symbol_filters(symbol_key)
            self._symbol_filters[symbol_key] = filters
        return self._symbol_filters[symbol_key]

    async def _prepare_order_quantities(
        self, symbol: str, price: float, desired_notional: float
    ) -> Optional[Tuple[Dict[str, Decimal], Decimal, Decimal]]:
        filters = await self._get_symbol_filters(symbol)

        price_dec = Decimal(str(price))
        notional_dec = Decimal(str(desired_notional))

        min_notional = filters.get("min_notional", Decimal("0"))
        if min_notional > 0 and notional_dec < min_notional:
            logger.info(
                "Notional %.2f below exchange minimum %.2f for %s; skipping",
                desired_notional,
                float(min_notional),
                symbol,
            )
            return None

        step = filters.get("step_size", Decimal("1"))
        min_qty = filters.get("min_qty", Decimal("0"))
        max_qty = filters.get("max_qty", Decimal("0"))

        quantity_dec = notional_dec / price_dec if price_dec > 0 else Decimal("0")
        if quantity_dec <= 0:
            return None

        if step > 0:
            quantity_dec = (quantity_dec / step).to_integral_value(rounding=ROUND_DOWN) * step
            quantity_dec = quantity_dec.quantize(step)

        if quantity_dec <= 0:
            return None

        if quantity_dec < min_qty:
            logger.info(
                "Quantity %.8f below exchange minimum %.8f for %s; skipping",
                float(quantity_dec),
                float(min_qty),
                symbol,
            )
            return None

        if max_qty > 0 and quantity_dec > max_qty:
            logger.info(
                "Quantity %.8f above exchange maximum %.8f for %s; capping",
                float(quantity_dec),
                float(max_qty),
                symbol,
            )
            quantity_dec = (max_qty / step).to_integral_value(rounding=ROUND_DOWN) * step

        resulting_notional = quantity_dec * price_dec
        if min_notional > 0 and resulting_notional < min_notional:
            logger.info(
                "Resulting notional %.2f below exchange minimum %.2f for %s; skipping",
                float(resulting_notional),
                float(min_notional),
                symbol,
            )
            return None

        return filters, quantity_dec, resulting_notional

    async def _validate_slippage(self, symbol: str, reference_price: float) -> Tuple[bool, float]:
        """Ensure live market price does not exceed configured slippage tolerance."""
        tolerance_bps = self._settings.max_slippage_bps
        if tolerance_bps <= 0 or reference_price <= 0:
            return True, reference_price

        if not self._exchange:
            return True, reference_price

        try:
            ticker = await self._exchange.get_ticker_price(symbol)
            market_price = float(ticker.get("price", reference_price))
        except Exception as exc:
            logger.debug("Unable to fetch live price for %s: %s", symbol, exc)
            return True, reference_price

        if market_price <= 0:
            return True, reference_price

        slippage_bps = abs(market_price - reference_price) / reference_price * 10_000
        if slippage_bps > tolerance_bps:
            SLIPPAGE_VIOLATIONS.labels(symbol=symbol.upper()).inc()
            logger.warning(
                "Skipping %s order due to slippage %.2f bps (tolerance %.2f bps)",
                symbol,
                slippage_bps,
                tolerance_bps,
            )
            await self._streams.publish_reasoning(
                {
                    "bot_id": self._settings.bot_id,
                    "symbol": symbol,
                    "strategy": "execution_guard",
                    "message": "slippage_rejection",
                    "context": json.dumps(
                        {
                            "reference_price": round(reference_price, 6),
                            "market_price": round(market_price, 6),
                            "slippage_bps": round(slippage_bps, 2),
                            "tolerance_bps": tolerance_bps,
                        }
                    ),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            return False, market_price

        return True, market_price

    async def _init_telegram(self) -> None:
        """Initialize Telegram notification service and command handler."""
        self._telegram = await create_telegram_service(self._settings)
        
        # Initialize command handler if credentials are available
        if self._settings.telegram_bot_token and self._settings.telegram_chat_id:
            try:
                self._telegram_commands = TelegramCommandHandler(
                    bot_token=self._settings.telegram_bot_token,
                    chat_id=self._settings.telegram_chat_id,
                    trading_service=self,
                )
                await self._telegram_commands.start()
            except Exception as exc:
                logger.warning(f"Failed to start Telegram command handler: {exc}")

    async def dashboard_snapshot(self) -> Dict[str, Any]:
        """Aggregate a lightweight view for the dashboard endpoint."""
        logger.info("Dashboard snapshot requested")
        snapshot_start = time.time()
        try:
            try:
                raw_portfolio, orchestrator_status = await self._resolve_portfolio()
                logger.info("Dashboard: portfolio resolved")
            except Exception as exc:
                logger.exception("Dashboard: failed to resolve portfolio")
                raise

            # Transform portfolio data for frontend
            try:
                portfolio = self._transform_portfolio_for_frontend(raw_portfolio)
                self._latest_portfolio_frontend = portfolio
                self._update_agent_snapshots(portfolio)
            except Exception as exc:
                logger.exception("Dashboard: failed to transform portfolio")
                raise

            try:
                reasoning = await self._streams.publish_reasoning({
                    "bot_id": self._settings.bot_id,
                    "symbol": "dashboard",
                    "strategy": "snapshot",
                    "message": "dashboard_snapshot_generated",
                    "context": json.dumps({
                        "portfolio_balance": portfolio.get("balance"),
                        "positions": len(portfolio.get("positions", {})),
                        "timestamp": datetime.utcnow().isoformat(),
                    }),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except Exception as exc:
                logger.debug("Dashboard: failed to publish reasoning event: %s", exc)
                reasoning = None

            response = {
                "portfolio": portfolio,
                "positions": list(portfolio.get("positions", {}).values()),
                "recent_trades": list(self._recent_trades)[:50],
                "model_performance": self._collect_model_performance(),
                "agents": self._serialize_agents(),
                "model_reasoning": await self._collect_model_reasoning(),
                "system_status": self._build_system_status(orchestrator_status),
                "targets": self._targets,
                "reasoning": reasoning,
            }
            return response
        finally:
            DASHBOARD_SNAPSHOT_TIME.observe(time.time() - snapshot_start)

    @property
    def paper_trading(self) -> bool:
        return self._health.paper_trading

    async def start(self) -> None:
        """Start the trading service."""
        logger.warning("--- ENTERING start() ---")
        if self._health.running:
            logger.warning("Trading service already running.")
            return

        credentials = self._credential_manager.get_credentials()
        if not (credentials.api_key and credentials.api_secret) and not self._settings.enable_paper_trading:
            self._health.last_error = "API credentials are not configured for live trading."
            logger.error(self._health.last_error)
            return

        self._stop_event.clear()
        self._health = HealthStatus(running=True, paper_trading=self._settings.enable_paper_trading, last_error=None)

        # Initialize the Aster client with credentials
        self._exchange = AsterClient(
            credentials=credentials,
            base_url=self._settings.rest_base_url,
        )
        logger.info("Aster client initialized.")

        try:
            await self._streams.connect()
            logger.info("PubSub client connected.")
            await self._init_telegram()
            logger.info("Telegram service initialized.")
            if self._orchestrator:
                await self._sync_portfolio()
                logger.info("Portfolio synced with orchestrator.")
            if self._mcp:
                try:
                    await self._mcp.ensure_session()
                    logger.info("MCP session ensured.")
                except Exception as exc:
                    logger.warning("Failed to ensure MCP session at startup: %s", exc)
            
            logger.info("Creating _run_loop task...")
            self._task = asyncio.create_task(self._run_loop())

            # Start periodic market observation task (every 2 hours)
            self._observation_task = asyncio.create_task(self._periodic_market_observations())
            logger.info("Market observation task started.")

            logger.warning("--- EXITING start() ---")
        except Exception as exc:
            logger.exception("Exception during service start: %s", exc)
            self._health.last_error = str(exc)
            self._health.running = False


    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        if hasattr(self, '_observation_task') and self._observation_task:
            self._observation_task.cancel()
            try:
                await self._observation_task
            except asyncio.CancelledError:
                pass
        if self._exchange:
            await self._exchange.close()
        await self._streams.close()
        if self._orchestrator:
            await self._orchestrator.close()
        if self._mcp:
            await self._mcp.close()
        self._health = HealthStatus(running=False, paper_trading=self.paper_trading, last_error=self._health.last_error)

    async def _run_loop(self) -> None:
        logger.warning("--- ENTERING _run_loop() ---")
        try:
            while not self._stop_event.is_set():
                logger.info("Calling _tick()")
                await self._tick()
                logger.info("Sleeping for %s seconds...", self._settings.decision_interval_seconds)
                await asyncio.sleep(self._settings.decision_interval_seconds)
        except asyncio.CancelledError:
            logger.warning("_run_loop task cancelled.")
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Trading loop error: %s", exc)
            self._health.last_error = str(exc)
        finally:
            logger.warning("--- EXITING _run_loop() ---")
            self._health.running = False
            await self._publish_portfolio_state()

    async def _tick(self) -> None:
        """Execute trading tick with enhanced error handling per symbol."""
        try:
            market = await self._fetch_market()
            
            if not market:
                logger.warning("No market data available, skipping tick")
                return
        except Exception as exc:
            logger.exception("Failed to fetch market data in tick: %s", exc)
            self._health.last_error = str(exc)[:200]
            return

        # Process each symbol independently to continue on failures
        for symbol, snapshot in market.items():
            try:
                decision = self._strategy.should_enter(symbol, snapshot)
                if decision == "HOLD":
                    await self._streams.publish_reasoning(
                        {
                            "bot_id": self._settings.bot_id,
                            "symbol": symbol,
                            "strategy": "momentum",
                            "message": "hold_position",
                            "context": json.dumps(
                                {
                                    "change_24h": round(snapshot.change_24h, 4),
                                    "volume": round(snapshot.volume, 2),
                                }
                            ),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue
                if not decision:
                    continue

                base_notional = self._strategy.allocate_notional(
                    portfolio_balance=self._portfolio.balance,
                    expected_return=self._settings.expected_win_rate,
                    volatility=0.15,
                )
                if base_notional <= 0:
                    continue

                if self._mcp:
                    proposal = MCPProposalPayload(
                        symbol=symbol,
                        side=decision,
                        notional=base_notional,
                        confidence=0.5,
                        rationale="momentum_threshold_crossed",
                    )
                    await self._mcp.publish(
                        {
                            "session_id": self._settings.mcp_session_id or "",
                            "sender_id": self._settings.bot_id,
                            "sender_role": "agent",
                            "message_type": MCPMessageType.PROPOSAL.value,
                            "payload": proposal.model_dump(),
                        }
                    )
                    MCP_MESSAGES_TOTAL.labels(message_type="proposal", direction="outbound").inc()

                # Send MCP proposal notification via Telegram
                if self._telegram:
                    await self._telegram.send_mcp_notification(
                        session_id=self._settings.mcp_session_id or "default",
                        sender_id=self._settings.bot_id,
                        message_type="proposal",
                        content=f"Proposing {decision.upper()} trade on {symbol} with ${base_notional:.2f} notional",
                        context=f"Momentum strategy triggered at {snapshot.price:.4f}"
                    )

                if not self._bandit.allow(symbol):
                    await self._streams.publish_reasoning(
                        {
                            "bot_id": self._settings.bot_id,
                            "symbol": symbol,
                            "strategy": "bandit",
                            "message": "bandit_suppressed_trade",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue

                # Use Kelly Criterion for position sizing if enabled
                notional = await self._auto_delever(symbol, snapshot, base_notional)
                if notional <= 0:
                    continue
                if not self._risk.can_open_position(self._portfolio, notional):
                    logger.info("Risk limits prevent new %s position", symbol)
                    RISK_LIMITS_BREACHED.labels(limit_type="position_size").inc()
                    await self._streams.publish_reasoning(
                        {
                            "bot_id": self._settings.bot_id,
                            "symbol": symbol,
                            "strategy": "risk",
                            "message": "risk_limit_block",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue

                TRADING_DECISIONS.labels(
                    bot_id=self._settings.bot_id,
                    symbol=symbol,
                    action=decision,
                ).inc()

                order_tag = generate_order_tag(self._settings.bot_id, symbol)
                buffer = self._settings.trailing_stop_buffer
                trail_step = self._settings.trailing_step
                
                # Use ATR-based stop loss if available, otherwise fallback to buffer
                if snapshot.atr and snapshot.atr > 0:
                    stop_loss = self._strategy.calculate_stop_loss(
                        entry_price=snapshot.price,
                        atr=snapshot.atr,
                        is_long=(decision == "BUY"),
                    )
                else:
                    # Fallback to buffer-based stop loss
                    if decision == "BUY":
                        stop_loss = snapshot.price * (1 - buffer)
                    else:
                        stop_loss = snapshot.price * (1 + buffer)
                
                # Calculate take profit
                if decision == "BUY":
                    take_profit = snapshot.price * (1 + buffer)
                else:
                    take_profit = snapshot.price * (1 - buffer)
                decision_event = {
                    "bot_id": self._settings.bot_id,
                    "symbol": symbol,
                    "side": decision,
                    "notional": f"{notional:.2f}",
                    "paper": str(self.paper_trading).lower(),
                    "strategy": "momentum",
                    "price": f"{snapshot.price:.2f}",
                    "order_id": order_tag,
                    "take_profit": f"{take_profit:.4f}",
                    "stop_loss": f"{stop_loss:.4f}",
                    "trail_step": f"{trail_step:.4f}",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await self._streams.publish_decision(decision_event)
                await self._streams.publish_reasoning(
                    {
                        "bot_id": self._settings.bot_id,
                        "symbol": symbol,
                        "strategy": "momentum",
                        "message": "24h_change_crossed_threshold",
                        "context": json.dumps(
                            {
                                "change_24h": round(snapshot.change_24h, 4),
                                "take_profit": round(take_profit, 4),
                                "stop_loss": round(stop_loss, 4),
                                "trail_step": trail_step,
                            }
                        ),
                        "timestamp": decision_event["timestamp"],
                    }
                )

                if self.paper_trading:
                    logger.info("[PAPER] %s %s @ %.2f", decision, symbol, snapshot.price)
                    agent_id_for_symbol = self._symbol_to_agent.get(symbol.upper())
                    agent_model_for_symbol = (
                        self._agent_states[agent_id_for_symbol].model
                        if agent_id_for_symbol and agent_id_for_symbol in self._agent_states
                        else "momentum_strategy"
                    )
                    paper_quantity = notional / snapshot.price if snapshot.price else 0.0
                    if self._telegram:
                        try:
                            await self._telegram.send_trade_notification(
                                symbol=symbol,
                                side=decision,
                                price=snapshot.price,
                                quantity=paper_quantity,
                                notional=notional,
                                decision_reason="AI momentum strategy (Paper Trading)",
                                model_used=agent_model_for_symbol,
                                confidence=self._settings.expected_win_rate,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                                portfolio_balance=self._portfolio.balance,
                                risk_percentage=(notional / self._portfolio.balance) * 100 if self._portfolio.balance > 0 else 0,
                            )
                            TELEGRAM_NOTIFICATIONS_SENT.labels(category="trade", status="success").inc()
                        except Exception as exc:
                            TELEGRAM_NOTIFICATIONS_SENT.labels(category="trade", status="error").inc()
                            logger.warning("Failed to send paper trade notification: %s", exc)
                    self._portfolio = self._risk.register_fill(self._portfolio, symbol, notional)
                    await self._publish_portfolio_state()
                    await self._publish_trade_execution(
                        symbol=symbol,
                        side=decision,
                        price=snapshot.price,
                        notional=notional,
                        quantity=paper_quantity,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        trail_step=trail_step,
                        position_snapshot=None,
                        agent_id=agent_id_for_symbol,
                        agent_model=agent_model_for_symbol,
                        source="momentum",
                    )
                    self._bandit.update(symbol, _reward_for(decision, snapshot.change_24h))
                    continue

                await self._execute_order(
                    symbol,
                    decision,
                    snapshot.price,
                    notional,
                    order_tag,
                    take_profit,
                    stop_loss,
                    trail_step,
                )
                self._bandit.update(symbol, _reward_for(decision, snapshot.change_24h))
            except Exception as exc:
                # Log error but continue processing other symbols
                logger.exception("Error processing symbol %s in tick: %s", symbol, exc)
                self._health.last_error = f"{symbol}: {str(exc)[:100]}"
                # Continue to next symbol
                continue

    def _generate_trade_thesis(self, symbol: str, side: str, price: float, market_context: dict) -> str:
        """Generate an intelligent trading thesis based on market conditions."""
        change_24h = market_context.get('change_24h', 0)
        volume = market_context.get('volume', 0)
        atr = market_context.get('atr')

        # Analyze market conditions
        trend_strength = abs(change_24h)
        volume_level = "high" if volume > 1000000 else "moderate" if volume > 100000 else "low"
        volatility = "high" if atr and atr > price * 0.02 else "moderate" if atr and atr > price * 0.01 else "low"

        # Generate thesis based on conditions
        if side == "BUY":
            if trend_strength > 5:
                thesis = f"Strong bullish momentum with {change_24h:.1f}% 24h gain. "
            elif trend_strength > 2:
                thesis = f"Moderate bullish trend with {change_24h:.1f}% 24h gain. "
            else:
                thesis = f"Early bullish signal despite {change_24h:.1f}% 24h change. "

            if volume_level == "high":
                thesis += f"High volume confirms buying pressure. "
            elif volume_level == "moderate":
                thesis += f"Moderate volume supports the bullish case. "

            if volatility == "high":
                thesis += f"High volatility suggests potential for quick moves. "
            elif volatility == "low":
                thesis += f"Low volatility environment favors steady accumulation. "

            thesis += f"Targeting ${take_profit:.2f} take-profit with calculated risk management."

        else:  # SELL
            if trend_strength > 5:
                thesis = f"Strong bearish momentum with {change_24h:.1f}% 24h decline. "
            elif trend_strength > 2:
                thesis = f"Moderate bearish trend with {change_24h:.1f}% 24h decline. "
            else:
                thesis = f"Early bearish signal despite {change_24h:.1f}% 24h change. "

            if volume_level == "high":
                thesis += f"High volume confirms selling pressure. "
            elif volume_level == "moderate":
                thesis += f"Moderate volume supports the bearish case. "

            if volatility == "high":
                thesis += f"High volatility suggests potential for quick downside moves. "
            elif volatility == "low":
                thesis += f"Low volatility environment favors steady position reduction. "

            thesis += f"Targeting ${take_profit:.2f} take-profit with disciplined risk controls."

        return thesis

    async def _periodic_market_observations(self) -> None:
        """Send periodic market observations and portfolio updates via Telegram."""
        observation_interval = 7200  # 2 hours in seconds

        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(observation_interval)

                if not self._telegram:
                    continue

                # Collect market summary
                market_summary = {}
                for symbol, data in self._market_cache.items():
                    if isinstance(data, dict):
                        market_summary[symbol] = {
                            'change_24h': data.get('change_24h', 0),
                            'volume': data.get('volume', 0)
                        }

                # Collect active positions
                active_positions = []
                for symbol, position in self._portfolio.positions.items():
                    if position.size != 0:
                        current_price = self._market_cache.get(symbol.upper(), {}).get('price', position.entry_price)
                        pnl = (current_price - position.entry_price) * position.size if position.side.upper() == 'BUY' else (position.entry_price - current_price) * position.size

                        active_positions.append({
                            'symbol': symbol,
                            'side': position.side,
                            'notional': abs(position.notional),
                            'pnl': pnl
                        })

                # Calculate trading activity (simplified for now)
                # In a full implementation, you'd track this over time
                trading_activity = {
                    'trades_today': 0,  # Would be calculated from recent trades
                    'win_rate': self._settings.expected_win_rate * 100,
                    'avg_return': 0.0  # Would be calculated from trade history
                }

                # Send market observation
                try:
                    await self._telegram.send_market_observation(
                        portfolio_balance=self._portfolio.balance,
                        active_positions=active_positions,
                        total_pnl=sum(pos['pnl'] for pos in active_positions),
                        market_summary=market_summary,
                        trading_activity=trading_activity
                    )
                    logger.info("Sent periodic market observation via Telegram")
                except Exception as exc:
                    logger.warning("Failed to send market observation: %s", exc)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Error in periodic market observations: %s", exc)
                await asyncio.sleep(60)  # Wait a minute before retrying

    async def _execute_order(
        self,
        symbol: str,
        side: str,
        price: float,
        notional: float,
        order_tag: str,
        take_profit: float,
        stop_loss: float,
        trail_step: float,
    ) -> None:
        try:
            prepared = await self._prepare_order_quantities(symbol, price, notional)
            if not prepared:
                logger.info("Skipping %s order due to exchange filter constraints", symbol)
                TRADE_EXECUTION_FAILURE.labels(symbol=symbol.upper(), reason="exchange_filters").inc()
                return

            if not self._exchange:
                logger.warning("Exchange client unavailable; cannot execute %s order", symbol)
                TRADE_EXECUTION_FAILURE.labels(symbol=symbol.upper(), reason="client_unavailable").inc()
                return

            filters, quantity_dec, notional_dec = prepared
            agent_id = self._symbol_to_agent.get(symbol.upper())
            agent_model = None
            if agent_id and agent_id in self._agent_states:
                agent_model = self._agent_states[agent_id].model
            else:
                agent_model = "momentum_strategy"

            price_dec = Decimal(str(price))
            quantity_precision = filters.get("quantity_precision", 6)

            final_quantity_dec = quantity_dec
            final_notional_dec = notional_dec
            final_quantity = float(quantity_dec)
            slippage_ok, market_price = await self._validate_slippage(symbol, price)
            if not slippage_ok:
                TRADE_EXECUTION_FAILURE.labels(symbol=symbol.upper(), reason="slippage_guard").inc()
                return

            execution_price = market_price if market_price > 0 else price
            reference_price_dec = Decimal(str(execution_price))
            final_notional_dec = final_quantity_dec * reference_price_dec
            final_notional = float(final_quantity_dec)

            for attempt in range(2):
                quantity_str = format(final_quantity_dec.normalize(), "f")
                if "." in quantity_str:
                    decimals = len(quantity_str.split(".")[1])
                    if decimals > quantity_precision:
                        quantity_str = format(final_quantity_dec, f".{quantity_precision}f")

                order_payload = {
                    "symbol": symbol,
                    "side": side.upper(),
                    "order_type": "MARKET",
                    "quantity": quantity_str,
                    "new_client_order_id": order_tag,
                }

                try:
                    logger.info("Submitting order payload: %s", order_payload)
                    await self._exchange.place_order(**order_payload)
                    final_quantity = float(final_quantity_dec)
                    final_notional = float(final_quantity_dec * reference_price_dec)
                    logger.info(
                        "Placed %s order for %s (notional %.2f)",
                        side,
                        symbol,
                        final_notional,
                    )
                    break
                except RuntimeError as exc:
                    error_msg = str(exc)
                    if "Precision is over the maximum" in error_msg and attempt == 0:
                        adjusted_quantity_dec = final_quantity_dec.quantize(
                            Decimal("1"), rounding=ROUND_DOWN
                        )
                        if adjusted_quantity_dec <= 0 or adjusted_quantity_dec == final_quantity_dec:
                            raise
                        logger.warning(
                            "Precision error for %s; retrying with integer quantity %s",
                            symbol,
                            adjusted_quantity_dec,
                        )
                        final_quantity_dec = adjusted_quantity_dec
                        final_notional_dec = adjusted_quantity_dec * reference_price_dec
                        continue
                    raise

            quantity = final_quantity
            notional = final_notional
 
            execution_start = time.time()
            position_verified, position_snapshot = await self._verify_position_execution(
                symbol, side, order_tag, timeout=30.0
            )
 
            execution_duration = time.time() - execution_start
            TRADE_EXECUTION_TIME.labels(symbol=symbol, side=side).observe(execution_duration)
 
            if position_verified:
                self._portfolio = self._risk.register_fill(
                    self._portfolio, symbol, notional
                )
                await self._publish_portfolio_state()
                await self._publish_trade_execution(
                    symbol=symbol,
                    side=side,
                    price=execution_price,
                    notional=notional,
                    quantity=quantity,
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                    trail_step=trail_step,
                    position_snapshot=position_snapshot,
                    agent_id=agent_id,
                    agent_model=agent_model,
                    source="momentum",
                )
            else:
                logger.warning(
                    "Position verification failed or timed out for %s %s order %s. "
                    "Portfolio state not updated.",
                    side,
                    symbol,
                    order_tag,
                )
                TRADE_EXECUTION_FAILURE.labels(symbol=symbol.upper(), reason="verification_failed").inc()
                self._register_trade_event(
                    symbol=symbol,
                    side=side,
                    price=price,
                    notional=notional,
                    quantity=quantity,
                    metadata={"position_verified": False, "execution_price": execution_price},
                )
 
            if self._telegram:
                risk_pct = (notional / self._portfolio.balance) * 100 if self._portfolio.balance else 0.0

                # Get market context for the trade
                market_context = {}
                if symbol.upper() in self._market_cache:
                    cached = self._market_cache[symbol.upper()]
                    market_context = {
                        'change_24h': cached.get('change_24h', 0),
                        'volume': cached.get('volume', 0),
                        'atr': cached.get('atr')
                    }

                # Generate trading thesis based on market conditions
                trade_thesis = self._generate_trade_thesis(symbol, side, execution_price, market_context)

                # Calculate risk/reward ratio
                risk_amount = abs(execution_price - stop_loss) if stop_loss > 0 else 0
                reward_amount = abs(take_profit - execution_price) if take_profit > 0 else 0
                risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

                try:
                    await self._telegram.send_trade_notification(
                        symbol=symbol,
                        side=side,
                        price=execution_price,
                        quantity=quantity,
                        notional=notional,
                        decision_reason=f"Advanced momentum analysis with {confidence:.1%} confidence",
                        model_used=agent_model,
                        confidence=self._settings.expected_win_rate,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        portfolio_balance=self._portfolio.balance,
                        risk_percentage=risk_pct,
                        market_context=market_context,
                        trade_thesis=trade_thesis,
                        risk_reward_ratio=risk_reward_ratio,
                    )
                    TELEGRAM_NOTIFICATIONS_SENT.labels(category="trade", status="success").inc()
                except Exception as exc:
                    TELEGRAM_NOTIFICATIONS_SENT.labels(category="trade", status="error").inc()
                    logger.warning("Failed to send trade notification: %s", exc)
 
            if self._mcp:
                response_payload = MCPResponsePayload(
                    reference_id=order_tag,
                    answer=f"Executed {side} {symbol}",
                    confidence=1.0,
                    supplementary={
                        "price": price,
                        "notional": notional,
                        "quantity": quantity,
                    },
                )
                await self._mcp.publish(
                    {
                        "session_id": self._settings.mcp_session_id or "",
                        "sender_id": self._settings.bot_id,
                        "sender_role": "agent",
                        "message_type": MCPMessageType.RESPONSE.value,
                        "payload": response_payload.model_dump(),
                    }
                )
 
        except Exception as exc:
            logger.error("Order failed for %s: %s", symbol, exc)
            TRADE_EXECUTION_FAILURE.labels(symbol=symbol.upper(), reason=type(exc).__name__).inc()
            self._health.last_error = str(exc)
            await self._streams.publish_reasoning(
                {
                    "bot_id": self._settings.bot_id,
                    "symbol": symbol,
                    "strategy": "momentum",
                    "message": "order_error",
                    "context": json.dumps({"error": str(exc)}),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

    async def _verify_position_execution(
        self,
        symbol: str,
        side: str,
        order_id: str,
        timeout: float = 30.0,
    ) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Verify that a position was actually created after order execution.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            order_id: Client order ID to track
            timeout: Maximum time to wait for verification (seconds)

        Returns:
            Tuple of (verified flag, position snapshot dict if available)
        """
        if not self._exchange:
            logger.warning("No client available for position verification")
            return False, None
        
        start_time = time.time()
        max_polls = 10
        poll_interval = timeout / max_polls
        symbol_upper = symbol.upper()
        logger.info("Verifying position execution for %s %s (order: %s)", side, symbol, order_id)
        
        for attempt in range(max_polls):
            try:
                # Poll position risk endpoint
                positions = await self._exchange.get_position_risk()
                
                # Look for matching position
                for position in positions:
                    pos_symbol = position.get("symbol", "")
                    pos_size = float(position.get("positionAmt", 0.0))
                    
                    if pos_symbol.upper() == symbol_upper and abs(pos_size) > 1e-8:
                        # Position exists, verify direction matches
                        verification_duration = time.time() - start_time
                        if side == "BUY" and pos_size > 0:
                            logger.info(
                                "Verified %s position for %s (size=%s) after %.2fs",
                                side,
                                symbol,
                                pos_size,
                                verification_duration,
                            )
                            POSITION_VERIFICATION_TIME.labels(symbol=symbol_upper, status="verified").observe(verification_duration)
                            return True, position
                        if side == "SELL" and pos_size < 0:
                            logger.info(
                                "Verified %s position for %s (size=%s) after %.2fs",
                                side,
                                symbol,
                                pos_size,
                                verification_duration,
                            )
                            POSITION_VERIFICATION_TIME.labels(symbol=symbol_upper, status="verified").observe(verification_duration)
                            return True, position
            except Exception as exc:
                logger.debug(
                    "Attempt %s/%s - unable to verify position for %s: %s",
                    attempt + 1,
                    max_polls,
                    symbol,
                    exc,
                )
 
            await asyncio.sleep(poll_interval)
        POSITION_VERIFICATION_TIME.labels(symbol=symbol_upper, status="timeout").observe(time.time() - start_time)
        return False, None

    async def _fetch_market(self) -> Dict[str, MarketSnapshot]:
        """Fetch market data with validation, retry logic, and caching."""
        if self.paper_trading:
            return self._generate_fake_market()

        assert self._exchange is not None
        result: Dict[str, MarketSnapshot] = {}
        current_time = time.time()
        
        try:
            fetch_start = time.time()
            all_tickers = await self._exchange.get_all_tickers()
            fetch_duration = time.time() - fetch_start
            logger.info("Fetched %d tickers in %.2fs", len(all_tickers), fetch_duration)
            MARKET_FEED_LATENCY.labels(symbol="ALL").observe(fetch_duration)
 
            for payload in all_tickers:
                symbol = payload.get("symbol")
                if not symbol or symbol.upper() not in self._settings.symbols:
                    continue

                try:
                    price = _safe_float(payload.get("lastPrice"), 0.0)
                    volume = _safe_float(payload.get("volume"), 0.0)
                    change_24h = _safe_float(payload.get("priceChangePercent"), 0.0)

                    if price <= 0:
                        logger.warning("Invalid price for %s: %s", symbol, price)
                        continue

                    snapshot = parse_market_payload({
                        "price": price,
                        "volume": volume,
                        "change_24h": change_24h,
                    })

                    self._market_cache[symbol] = (snapshot, current_time)
                    result[symbol] = snapshot
                except Exception as exc:
                    logger.warning("Failed to parse market snapshot for %s: %s", symbol, exc)
                    MARKET_FEED_ERRORS.labels(symbol=symbol, error_type=type(exc).__name__).inc()

        except Exception as exc:
            MARKET_FEED_ERRORS.labels(symbol="ALL", error_type=type(exc).__name__).inc()
            logger.exception("Failed to fetch all tickers: %s", exc)
            self._health.last_error = f"Failed to fetch market data: {str(exc)[:100]}"
            # Fallback to cache for all symbols if API call fails
            for symbol in self._settings.symbols:
                if symbol in self._market_cache:
                    cached_snapshot, cached_time = self._market_cache[symbol]
                    age = current_time - cached_time
                    if age <= self._market_cache_ttl:
                        logger.warning("Using cached market data for %s after fetch failure (age: %.1fs)", symbol, age)
                        result[symbol] = cached_snapshot
        
        return result

    def _generate_fake_market(self) -> Dict[str, MarketSnapshot]:
        import random

        market: Dict[str, MarketSnapshot] = {}
        for symbol in self._settings.symbols:
            price = random.uniform(10, 1000)
            change = random.uniform(-5, 5)
            volume = random.uniform(1_000, 50_000)
            market[symbol] = parse_market_payload({"price": price, "change_24h": change, "volume": volume})
        return market

    def health(self) -> HealthStatus:
        return self._health

    async def _resolve_portfolio(self) -> Tuple[Dict[str, Any], str]:
        if self._orchestrator:
            try:
                logger.info("Resolving portfolio from orchestrator")
                portfolio = await self._orchestrator.portfolio()
                portfolio.setdefault("source", "orchestrator")
                
                # Temporarily disable asset price refresh to isolate timeout
                # await self._refresh_asset_prices(portfolio)
                logger.info("Portfolio successfully resolved from orchestrator")
                
                return portfolio, "healthy"
            except Exception as exc:
                logger.warning("Failed to fetch orchestrator portfolio: %s", exc)
                self._health.last_error = self._health.last_error or str(exc)
                return self._serialize_portfolio_state(alert="Orchestrator service unavailable - using local portfolio data"), "unreachable"
        return self._serialize_portfolio_state(), "not_configured"

    async def _refresh_asset_prices(self, portfolio: Dict[str, Any]) -> None:
        """Ensure we have USD conversion prices for any collateral assets."""

        assets = portfolio.get("assets", [])
        if not isinstance(assets, list) or not assets:
            return

        desired_symbols: List[str] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            try:
                wallet_balance = float(asset.get("walletBalance", 0.0) or 0.0)
                margin_balance = float(asset.get("marginBalance", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue

            if wallet_balance <= 0.0 and margin_balance <= 0.0:
                continue

            asset_code = str(asset.get("asset", "")).upper()
            symbol = self._asset_to_symbol(asset_code)
            if symbol and symbol not in self._price_cache:
                desired_symbols.append(symbol)

        if not desired_symbols:
            return

        client = self._exchange
        temp_client: Optional[AsterClient] = None

        if client is None:
            try:
                temp_client = AsterClient(self._credential_manager.get_credentials())
                await temp_client.ensure_session()
                client = temp_client
            except Exception as exc:
                logger.debug("Unable to instantiate temporary Aster client for pricing: %s", exc)
                return

        assert client is not None

        try:
            for symbol in desired_symbols:
                try:
                    ticker = await client.ticker(symbol)
                    price = float(ticker.get("lastPrice", 0.0) or 0.0)
                    if price > 0:
                        self._price_cache[symbol] = price
                except Exception as exc:
                    logger.debug("Failed to refresh price for %s: %s", symbol, exc)
        finally:
            if temp_client is not None:
                await temp_client.close()

    @staticmethod
    def _asset_to_symbol(asset_code: str) -> Optional[str]:
        if not asset_code:
            return None

        stable_assets = {"USDT", "USDC", "BUSD", "USD", "USD1"}
        if asset_code in stable_assets:
            return "USDTUSDT"  # dummy sentinel to indicate 1:1 conversion

        if asset_code.startswith("AS") and len(asset_code) > 2:
            base = asset_code[2:]
        else:
            base = asset_code

        if base.endswith("USDT"):
            return base

        return f"{base}USDT"

    def _convert_asset_to_usd(self, asset_code: str, amount: float) -> float:
        if amount == 0.0:
            return 0.0

        asset_code = asset_code.upper()
        stable_assets = {"USDT", "USDC", "BUSD", "USD", "USD1"}
        if asset_code in stable_assets:
            return amount

        symbol = self._asset_to_symbol(asset_code)
        if symbol is None:
            return 0.0

        if symbol == "USDTUSDT":
            return amount

        price = self._price_cache.get(symbol, 0.0)
        if price <= 0:
            return 0.0

        return amount * price

    def _transform_portfolio_for_frontend(self, raw_portfolio: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw portfolio data into frontend-expected format."""
        # If it's already in the right format (from local state), return as-is
        if "balance" in raw_portfolio:
            return raw_portfolio

        # Transform Binance futures account data
        try:
            total_wallet_balance = 0.0
            total_margin_balance = 0.0
            total_unrealized_pnl = 0.0
            available_balance = 0.0

            assets = raw_portfolio.get("assets", [])
            if isinstance(assets, list):
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    try:
                        wallet_balance = float(asset.get("walletBalance", 0.0) or 0.0)
                        margin_balance = float(asset.get("marginBalance", wallet_balance) or 0.0)
                        unrealized_profit = float(asset.get("unrealizedProfit", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        logger.debug("Skipping asset with invalid numeric values: %s", asset)
                        continue

                    # Only count assets with actual balances (not margin limits)
                    if wallet_balance > 0 or margin_balance > 0:
                        # Convert crypto assets to USD equivalent
                        usd_value = self._convert_asset_to_usd(asset.get("asset", ""), margin_balance)
                        total_wallet_balance += usd_value if usd_value > 0 else margin_balance
                        total_margin_balance += usd_value if usd_value > 0 else margin_balance
                        total_unrealized_pnl += unrealized_profit

            # For futures accounts, available balance is the margin available for trading
            # Use the account-level availableBalance from the raw portfolio
            account_available = raw_portfolio.get("availableBalance", 0.0)
            try:
                available_balance = float(account_available)
            except (TypeError, ValueError):
                available_balance = total_wallet_balance

            if total_margin_balance <= 0.0 and total_wallet_balance > 0.0:
                total_margin_balance = total_wallet_balance + total_unrealized_pnl

            total_exposure = 0.0
            positions_dict: Dict[str, Any] = {}

            positions = raw_portfolio.get("positions", [])
            if isinstance(positions, list):
                for position in positions:
                    if not isinstance(position, dict):
                        continue

                    raw_amt = position.get("positionAmt") or position.get("position_amount")
                    try:
                        position_amount = float(raw_amt)
                    except (TypeError, ValueError):
                        logger.debug("Skipping position with invalid amount: %s", position)
                        continue

                    if abs(position_amount) < 1e-6:
                        continue

                    symbol = str(position.get("symbol", "UNKNOWN")).upper()

                    raw_notional = position.get("notional")
                    notional = 0.0
                    if raw_notional is not None:
                        try:
                            notional = abs(float(raw_notional))
                        except (TypeError, ValueError):
                            notional = 0.0

                    mark_price = 0.0
                    if notional == 0.0:
                        try:
                            mark_price = float(position.get("markPrice") or position.get("entryPrice") or 0.0)
                            notional = abs(position_amount) * mark_price
                        except (TypeError, ValueError):
                            mark_price = 0.0
                            notional = 0.0
                    else:
                        try:
                            mark_price = float(position.get("markPrice") or position.get("entryPrice") or 0.0)
                        except (TypeError, ValueError):
                            mark_price = 0.0

                    total_exposure += notional

                    try:
                        entry_price = float(position.get("entryPrice", 0.0))
                    except (TypeError, ValueError):
                        entry_price = 0.0

                    try:
                        unrealized = float(position.get("unrealizedProfit", 0.0))
                    except (TypeError, ValueError):
                        unrealized = 0.0

                    pnl_percent = (unrealized / notional * 100.0) if notional else 0.0
                    side = "LONG" if position_amount >= 0 else "SHORT"
                    agent_id = self._symbol_to_agent.get(symbol, "")

                    positions_dict[symbol] = {
                        "symbol": symbol,
                        "size": round(position_amount, 6),
                        "notional": round(notional, 2),
                        "entry_price": round(entry_price, 4),
                        "current_price": round(mark_price, 4),
                        "pnl": round(unrealized, 2),
                        "pnl_percent": round(pnl_percent, 2),
                        "side": side,
                        "agent_id": agent_id,
                        "leverage": position.get("leverage"),
                    }

            balance = max(total_margin_balance, total_wallet_balance)

            return {
                "balance": round(balance, 2),
                "available_balance": round(available_balance, 2),
                "total_exposure": round(total_exposure, 2),
                "positions": positions_dict,
                "source": raw_portfolio.get("source", "orchestrator"),
                "alerts": raw_portfolio.get("alerts", []),
            }

        except Exception as exc:
            logger.warning("Failed to transform portfolio data: %s", exc)
            # Return a safe fallback
            return {
                "balance": 1000.0,
                "total_exposure": 0.0,
                "positions": {},
                "source": "fallback",
                "alerts": [f"Portfolio data parsing error: {str(exc)}"],
            }

    def _update_agent_snapshots(self, portfolio: Dict[str, Any]) -> None:
        if not isinstance(portfolio, dict):
            return

        timestamp = datetime.utcnow()
        positions_payload = portfolio.get("positions", {})
        total_balance = float(portfolio.get("balance", self._portfolio.balance))
        total_exposure = float(portfolio.get("total_exposure", self._portfolio.total_exposure))

        for state in self._agent_states.values():
            state.open_positions = {}
            state.total_pnl = 0.0
            state.exposure = 0.0

        if isinstance(positions_payload, dict):
            for symbol, position in positions_payload.items():
                if not isinstance(position, dict):
                    continue
                agent_id = self._symbol_to_agent.get(str(symbol).upper())
                if not agent_id:
                    continue
                state = self._agent_states[agent_id]
                cloned = dict(position)
                pnl = float(cloned.get("pnl", 0.0) or 0.0)
                notional = float(cloned.get("notional", 0.0) or 0.0)
                state.open_positions[str(symbol).upper()] = cloned
                state.total_pnl += pnl
                state.exposure += max(notional, 0.0)

        agent_count = max(len(self._agent_states), 1)
        for state in self._agent_states.values():
            if state.exposure > 0:
                state.status = "active"
            elif state.total_trades > 0:
                state.status = "monitoring"
            else:
                state.status = "idle"

            if total_exposure > 0 and state.exposure > 0:
                allocation_ratio = state.exposure / max(total_exposure, 1e-6)
                allocated_balance = total_balance * allocation_ratio
            else:
                allocated_balance = total_balance / agent_count if total_balance else 0.0

            state.equity_curve.append((timestamp, allocated_balance + state.total_pnl))

    def _serialize_agents(self) -> List[Dict[str, Any]]:
        agents: List[Dict[str, Any]] = []
        for state in self._agent_states.values():
            open_positions: List[Dict[str, Any]] = []
            positive = 0
            negative = 0
            for symbol, payload in state.open_positions.items():
                pnl = float(payload.get("pnl", 0.0) or 0.0)
                if pnl > 0:
                    positive += 1
                elif pnl < 0:
                    negative += 1
                entry = {
                    "symbol": symbol,
                    "size": payload.get("size"),
                    "notional": payload.get("notional"),
                    "entry_price": payload.get("entry_price"),
                    "current_price": payload.get("current_price"),
                    "pnl": pnl,
                    "pnl_percent": payload.get("pnl_percent"),
                    "side": payload.get("side"),
                }
                open_positions.append(entry)

            if positive + negative > 0:
                win_rate = (positive / (positive + negative)) * 100.0
            elif state.total_trades > 0:
                win_rate = state.baseline_win_rate * 100.0
            else:
                win_rate = state.baseline_win_rate * 100.0

            agents.append(
                {
                    "id": state.id,
                    "name": state.name,
                    "model": state.model,
                    "emoji": state.emoji,
                    "status": state.status,
                    "symbols": state.symbols,
                    "description": state.description,
                    "total_pnl": round(state.total_pnl, 2),
                    "exposure": round(state.exposure, 2),
                    "total_trades": state.total_trades,
                    "win_rate": round(win_rate, 2),
                    "last_trade": state.last_trade.isoformat() if state.last_trade else None,
                    "positions": open_positions,
                    "performance": [
                        {"timestamp": ts.isoformat(), "equity": round(value, 2)}
                        for ts, value in list(state.equity_curve)
                    ],
                }
            )

        return agents

    def _register_trade_event(
        self,
        symbol: str,
        side: str,
        price: float,
        notional: float,
        quantity: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        timestamp_value = datetime.utcnow()
        agent_id = self._symbol_to_agent.get(symbol.upper())
        agent_model = None
        if agent_id and agent_id in self._agent_states:
            state = self._agent_states[agent_id]
            state.total_trades += 1
            state.total_notional += notional
            state.last_trade = timestamp_value
            state.status = "active"
            agent_model = state.model

        event = {
            "symbol": symbol.upper(),
            "side": side,
            "price": round(price, 4),
            "quantity": round(quantity, 6),
            "notional": round(notional, 2),
            "agent_id": agent_id,
            "model": agent_model,
            "timestamp": timestamp_value.isoformat(),
        }
        if metadata:
            event.update(metadata)
        self._recent_trades.appendleft(event)

    def _serialize_portfolio_state(self, alert: str | None = None) -> Dict[str, Any]:
        portfolio = {
            "balance": round(self._portfolio.balance, 2),
            "total_exposure": round(self._portfolio.total_exposure, 2),
            "positions": {
                symbol: {
                    "symbol": position.symbol,
                    "notional": position.notional,
                }
                for symbol, position in self._portfolio.positions.items()
            },
            "source": "local",
        }
        if alert:
            portfolio["alerts"] = [f"⚠️ {alert}"]
        return portfolio

    async def _safe_read_stream(self, stream: str, count: int) -> List[Dict[str, Any]]:
        try:
            entries = await self._streams.read_latest(stream, count=count)
            return entries
        except Exception as exc:
            logger.debug("Failed to read stream %s: %s", stream, exc)
            return []

    async def accept_inference_decision(self, request: InferenceRequest) -> None:
        """Process LLM-generated trading decisions and execute orders"""
        try:
            decision = request.decision
            confidence = request.confidence or 0.5
            symbol = request.context.symbol
            decision_side = (decision.side or "").upper()
            decision.side = decision_side

            # Only execute high-confidence decisions
            min_confidence = getattr(self._settings, 'min_llm_confidence', 0.7)
            if confidence < min_confidence:
                logger.info(f"🤖 LLM decision confidence {confidence:.2f} below threshold {min_confidence}, skipping")
                decision_side = "HOLD"
                decision.side = decision_side

            # Convert LLM decision to executable order
            if decision_side in ["BUY", "SELL"] and confidence >= min_confidence:
                # Calculate position size based on Kelly criterion and risk limits
                position_size = self._calculate_position_size(decision, request.context, confidence)

                if position_size > 0:
                    if not self._orchestrator or OrderIntent is None:
                        logger.warning("No orchestrator configured or OrderIntent unavailable; cannot execute LLM order")
                    else:
                        order_intent = OrderIntent(
                            symbol=symbol,
                            side=decision_side,
                            notional=position_size,
                            order_type="MARKET",
                        )

                        await self._orchestrator.submit_order(request.bot_id, order_intent)
                        context_price = getattr(request.context, "price", None) or getattr(request.context, "current_price", 0.0)
                        quantity = position_size / max(context_price, 1e-8) if context_price else 0.0
                        self._register_trade_event(
                            symbol=symbol,
                            side=decision_side,
                            price=float(context_price or 0.0),
                            notional=position_size,
                            quantity=quantity,
                            metadata={"source": "llm"},
                        )
                        logger.info(f"✅ LLM trade executed: {decision_side} {position_size} {symbol} (confidence: {confidence:.2f})")
                else:
                    logger.info(f"LLM decision {decision_side} blocked by risk management (size: {position_size})")

            elif decision_side == "CLOSE" and getattr(request.context, "current_position", None):
                # Close existing position
                await self._close_position(request.bot_id, symbol)
                logger.info(f"✅ Position closed via LLM decision for {symbol}")

            else:
                logger.info(f"🤖 LLM decision: {decision_side} {symbol} (confidence: {confidence:.2f})")

        except Exception as exc:
            logger.error(f"Failed to process LLM inference decision: {exc}")

        # Update Prometheus metrics
        if request.confidence is not None:
            LLM_CONFIDENCE.observe(request.confidence)
        TRADING_DECISIONS.labels(
            bot_id=request.bot_id,
            symbol=request.context.symbol,
            action=request.decision.side
        ).inc()

        # Log which model was used
        model_used = getattr(request, 'model_used', 'unknown')
        logger.info(f"🤖 LLM Decision from {model_used}: {request.decision.side} {request.context.symbol} (confidence: {request.confidence:.2f})")

        # Always publish decision for telemetry
        decision_payload = {
            "bot_id": request.bot_id,
            "symbol": request.context.symbol,
            "decision": json.dumps(request.decision.model_dump()),
            "context": json.dumps(request.context.model_dump()),
            "confidence": f"{request.confidence:.4f}" if request.confidence is not None else "",
            "timestamp": request.timestamp.isoformat(),
        }
        if self._orchestrator:
            try:
                await self._orchestrator.register_decision(request.model_dump(mode="json"))
            except Exception as exc:
                logger.debug("Failed to register decision with orchestrator: %s", exc)
        await self._streams.publish_decision(decision_payload)

        if request.reasoning:
            await self._streams.publish_reasoning(
                {
                    "bot_id": request.bot_id,
                    "symbol": request.context.symbol,
                    "strategy": "inference",
                    "message": "model_reasoning",
                    "context": json.dumps([slice.model_dump() for slice in request.reasoning]),
                    "timestamp": request.timestamp.isoformat(),
                }
            )

    def _calculate_position_size(self, decision: Any, context: Any, confidence: float) -> float:
        """Calculate position size using Kelly criterion with risk limits"""
        try:
            # Get portfolio information
            portfolio_value = self._portfolio.balance + self._portfolio.total_exposure
            max_position_pct = getattr(self._settings, 'max_position_pct', 0.02)  # 2% default

            # Kelly fraction (simplified)
            kelly_fraction = min(confidence * 0.5, 0.25)  # Cap at 25% Kelly

            # Calculate base position size
            base_size = portfolio_value * max_position_pct * kelly_fraction

            # Adjust for volatility and leverage
            volatility_factor = 1.0  # Could be calculated from price data
            leverage = context.get('leverage', 1)

            position_size = base_size * volatility_factor / leverage

            # Apply risk limits
            max_size = portfolio_value * max_position_pct
            position_size = min(position_size, max_size)

            # Ensure minimum viable position
            min_size = getattr(self._settings, 'min_position_size', 0.001)
            position_size = max(position_size, min_size)

            return position_size

        except Exception as exc:
            logger.warning(f"Failed to calculate position size: {exc}")
            return 0.0

    async def _close_position(self, bot_id: str, symbol: str) -> None:
        """Close existing position for a symbol"""
        try:
            # Get current position
            position = self._portfolio.positions.get(symbol)
            if not position or position.notional == 0:
                logger.info(f"No position to close for {symbol}")
                return

            if not self._orchestrator or OrderIntent is None:
                logger.warning("Orchestrator integration unavailable; cannot programmatically close position for %s", symbol)
                return

            # Create closing order (opposite side)
            close_side = "SELL" if position.notional > 0 else "BUY"
            close_quantity = abs(position.notional)

            order_intent = OrderIntent(
                symbol=symbol,
                side=close_side,
                notional=abs(position.notional),
                order_type="MARKET",
            )

            await self._orchestrator.submit_order(bot_id, order_intent)
            self._register_trade_event(
                symbol=symbol,
                side=close_side,
                price=0.0,
                notional=abs(position.notional),
                quantity=close_quantity,
                metadata={"source": "llm_close"},
            )
            logger.info(f"Position closed: {close_side} {close_quantity} {symbol}")

        except Exception as exc:
            logger.error(f"Failed to close position for {symbol}: {exc}")

    async def _publish_portfolio_state(self) -> None:
        positions = {symbol: position.notional for symbol, position in self._portfolio.positions.items()}
        await self._streams.publish_position(
            {
                "bot_id": self._settings.bot_id,
                "paper": str(self.paper_trading).lower(),
                "balance": f"{self._portfolio.balance:.2f}",
                "total_exposure": f"{self._portfolio.total_exposure:.2f}",
                "positions": json.dumps(positions),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    async def _publish_trade_execution(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        notional: float,
        quantity: float,
        take_profit: float,
        stop_loss: float,
        trail_step: float,
        position_snapshot: Optional[Dict[str, Any]],
        agent_id: Optional[str],
        agent_model: Optional[str],
        source: str,
    ) -> None:
        snapshot = position_snapshot or {}
        entry_price = _safe_float(snapshot.get("entryPrice"), price)
        mark_price = _safe_float(snapshot.get("markPrice"), price)
        unrealized_pnl = _safe_float(snapshot.get("unRealizedProfit"), 0.0)
        leverage = _safe_float(snapshot.get("leverage"), 0.0)
        isolated_margin = _safe_float(snapshot.get("isolatedWallet"), 0.0)

        LAST_TRADE_UNREALIZED_PNL.labels(symbol=symbol.upper()).set(unrealized_pnl)
        mode_label = "paper" if self.paper_trading else "live"
        TRADE_EXECUTION_SUCCESS.labels(symbol=symbol.upper(), mode=mode_label, source=source).inc()

        trade_payload = {
            "event": "trade_execution",
            "bot_id": self._settings.bot_id,
            "symbol": symbol.upper(),
            "side": side.upper(),
            "quantity": round(quantity, 6),
            "notional": round(notional, 2),
            "execution_price": round(price, 4),
            "entry_price": round(entry_price, 4),
            "mark_price": round(mark_price, 4),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "leverage": leverage,
            "isolated_margin": round(isolated_margin, 2),
            "take_profit": round(take_profit, 4),
            "stop_loss": round(stop_loss, 4),
            "trail_step": round(trail_step, 4),
            "agent_id": agent_id,
            "agent_model": agent_model,
            "source": source,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self._streams.publish_trade_execution(trade_payload)

        metadata = {
            "entry_price": round(entry_price, 4),
            "mark_price": round(mark_price, 4),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "leverage": leverage,
            "take_profit": round(take_profit, 4),
            "stop_loss": round(stop_loss, 4),
            "trail_step": round(trail_step, 4),
            "position_verified": True,
            "agent_id": agent_id,
            "agent_model": agent_model,
            "source": source,
        }
        self._register_trade_event(
            symbol=symbol,
            side=side,
            price=price,
            notional=notional,
            quantity=quantity,
            metadata=metadata,
        )
 
    async def _auto_delever(self, symbol: str, snapshot: MarketSnapshot, notional: float) -> float:
        threshold = self._settings.volatility_delever_threshold
        factor = self._settings.auto_delever_factor
        if threshold <= 0 or factor >= 1:
            return notional

        if abs(snapshot.change_24h) < threshold:
            return notional

        adjusted = max(notional * factor, 0.0)
        await self._streams.publish_reasoning(
            {
                "bot_id": self._settings.bot_id,
                "symbol": symbol,
                "strategy": "auto_delever",
                "message": "volatility_threshold_triggered",
                "context": json.dumps(
                    {
                        "change_24h": round(snapshot.change_24h, 4),
                        "factor": factor,
                    }
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }
        )
        return adjusted

    @property
    def settings(self) -> Settings:
        return self._settings

    async def stream_events(self, stream: str, limit: int = 50) -> list[dict[str, str]]:
        return await self._streams.read_latest(stream, count=limit)

    async def _sync_portfolio(self) -> None:
        if not self._orchestrator:
            return
        try:
            payload = await self._orchestrator.portfolio()
        except Exception as exc:
            logger.debug("Unable to sync orchestrator portfolio: %s", exc)
            return

        self._latest_portfolio_raw = payload
        positions_payload = payload.get("positions") or []
        positions: Dict[str, Position] = {}
        for raw_position in positions_payload:
            if not isinstance(raw_position, dict):
                continue
            symbol = raw_position.get("symbol")
            if not symbol:
                continue
            try:
                notional = float(raw_position.get("notional", 0.0))
            except (TypeError, ValueError):
                notional = 0.0

            raw_size = raw_position.get("positionAmt") or raw_position.get("position_amount")
            try:
                size = float(raw_size) if raw_size is not None else 0.0
            except (TypeError, ValueError):
                size = 0.0

            if abs(size) < 1e-6 and abs(notional) < 1e-4:
                continue

            if notional == 0.0:
                try:
                    mark_price = float(raw_position.get("markPrice") or raw_position.get("entryPrice") or 0.0)
                    notional = abs(size) * mark_price
                except (TypeError, ValueError):
                    notional = 0.0

            if notional == 0.0:
                continue

            positions[symbol] = Position(symbol=symbol, notional=abs(notional))

        balance = 0.0
        for key in ("availableBalance", "totalWalletBalance", "total_wallet_balance", "totalMarginBalance"):
            value = payload.get(key)
            if value is not None:
                try:
                    balance = float(value)
                except (TypeError, ValueError):
                    balance = 0.0
            if balance > 0:
                break

        if balance <= 0:
            assets = payload.get("assets", [])
            if isinstance(assets, list):
                running = 0.0
                for asset in assets:
                    if isinstance(asset, dict):
                        try:
                            running += float(asset.get("walletBalance", 0.0))
                        except (TypeError, ValueError):
                            continue
                balance = running

        if balance <= 0:
            balance = self._portfolio.balance

        total_exposure_payload = payload.get("totalPositionInitialMargin") or payload.get("total_initial_margin")
        if total_exposure_payload is not None:
            try:
                total_exposure = float(total_exposure_payload)
            except (TypeError, ValueError):
                total_exposure = sum(position.notional for position in positions.values())
        else:
            total_exposure = sum(position.notional for position in positions.values())

        self._portfolio = PortfolioState(balance=balance, total_exposure=total_exposure, positions=positions)

        derived_portfolio = self._transform_portfolio_for_frontend(payload)
        self._latest_portfolio_frontend = derived_portfolio
        self._update_agent_snapshots(derived_portfolio)

        # Update Prometheus metrics
        PORTFOLIO_BALANCE.set(balance)
        leverage_ratio = (total_exposure / balance) if balance > 0 else 0
        PORTFOLIO_LEVERAGE.set(leverage_ratio)

        # Update position metrics
        for symbol, position in positions.items():
            POSITION_SIZE.labels(symbol=symbol).set(position.notional)

        await self._publish_portfolio_state()

    async def send_test_telegram_message(self) -> None:
        """Sends a test message to the configured Telegram channel."""
        logger.info("Sending test Telegram message...")
        if not self._telegram:
            logger.warning("Telegram service not initialized; skipping test message send.")
            return
        try:
            await self._telegram.send_message(
                "✅ Test message from the Sapphire trading bot — all systems operational",
                parse_mode=None,
            )
            TELEGRAM_NOTIFICATIONS_SENT.labels(category="test", status="success").inc()
        except Exception as exc:
            TELEGRAM_NOTIFICATIONS_SENT.labels(category="test", status="error").inc()
            logger.warning("Failed to dispatch test Telegram message: %s", exc)


def _safe_float(value: Any, default: float = 0.0) -> float:
    raw_value = value
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default
        cleaned = cleaned.replace('%', '').replace(',', '')
        value = cleaned
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning("Unable to parse numeric value", raw_value=raw_value, default=default)
        return default
