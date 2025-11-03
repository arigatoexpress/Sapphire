"""Coordinating service that glues together client, strategy, and risk controls."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

import structlog

from .client import AsterClient
from .config import Settings, get_settings
from .messaging import RedisStreamsClient, timestamp
from .optimization.bandit import EpsilonGreedyBandit
from .order_tags import generate_order_tag
from .orchestrator.client import RiskOrchestratorClient
from .orchestrator.schemas import OrderIntent
from .risk import PortfolioState, RiskManager, Position
from .secrets import load_credentials
from .schemas import InferenceRequest
from .strategy import MarketSnapshot, MomentumStrategy, parse_market_payload
from .telegram import TelegramService, create_telegram_service
from .mcp import MCPClient, MCPMessageType, MCPProposalPayload, MCPResponsePayload
from .metrics import (
    ASTER_API_REQUESTS,
    LLM_CONFIDENCE,
    LLM_INFERENCE_TIME,
    PORTFOLIO_BALANCE,
    PORTFOLIO_LEVERAGE,
    POSITION_SIZE,
    RATE_LIMIT_EVENTS,
    RISK_LIMITS_BREACHED,
    TRADING_DECISIONS,
    REDIS_STREAM_FAILURES,
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
        self._creds = load_credentials()
        self._client: Optional[AsterClient] = None
        self._risk = RiskManager(self._settings)
        self._strategy = MomentumStrategy(
            threshold=self._settings.momentum_threshold,
            notional_fraction=self._settings.notional_fraction,
        )
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._health = HealthStatus(running=False, paper_trading=False, last_error=None)
        self._portfolio = PortfolioState(balance=1_000.0, total_exposure=0.0, positions={})
        self._bandit = EpsilonGreedyBandit(self._settings.bandit_epsilon, min_reward=-0.5)
        self._streams = RedisStreamsClient(self._settings)
        self._orchestrator: Optional[RiskOrchestratorClient] = None
        if self._settings.orchestrator_url:
            self._orchestrator = RiskOrchestratorClient(self._settings.orchestrator_url)
        self._mcp: Optional[MCPClient] = None
        if self._settings.mcp_url:
            self._mcp = MCPClient(self._settings.mcp_url, self._settings.mcp_session_id)

        # Initialize Telegram service for notifications
        self._telegram: Optional[TelegramService] = None

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

        self._recent_trades: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._latest_portfolio_raw: Dict[str, Any] = {}
        self._latest_portfolio_frontend: Dict[str, Any] = {}
        self._price_cache: Dict[str, float] = {}

    async def _init_telegram(self) -> None:
        """Initialize Telegram notification service."""
        self._telegram = await create_telegram_service(self._settings)

    async def dashboard_snapshot(self) -> Dict[str, Any]:
        """Aggregate a lightweight view for the dashboard endpoint."""

        raw_portfolio, orchestrator_status = await self._resolve_portfolio()

        # Transform portfolio data for frontend
        portfolio = self._transform_portfolio_for_frontend(raw_portfolio)
        self._latest_portfolio_frontend = portfolio

        portfolio_positions = portfolio.get("positions", {}) if isinstance(portfolio, dict) else {}
        positions: List[Dict[str, Any]] = []
        if isinstance(portfolio_positions, dict):
            for payload in portfolio_positions.values():
                if isinstance(payload, dict):
                    enriched = dict(payload)
                    symbol_key = str(enriched.get("symbol", "")).upper()
                    enriched.setdefault("agent_id", self._symbol_to_agent.get(symbol_key, ""))
                    positions.append(enriched)

        # Update agent snapshots using live portfolio data
        self._update_agent_snapshots(portfolio)
        agents = self._serialize_agents()

        recent_trades = list(self._recent_trades)
        if not recent_trades:
            recent_trades = await self._safe_read_stream(self._settings.decisions_stream, count=20)
        model_reasoning = await self._safe_read_stream(self._settings.reasoning_stream, count=10)

        system_status = {
            "services": {
                "cloud_trader": "running" if self._health.running else "stopped",
                "orchestrator": orchestrator_status,
            },
            "models": {
                "deepseek": "unknown",
                "qwen": "unknown",
                "fingpt": "unknown",
                "phi3": "unknown",
                "mistral": "unknown",
            },
            "redis_connected": self._streams.is_connected(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        targets = {
            "daily_pnl_target": 0.0,
            "max_drawdown_limit": -self._settings.max_drawdown * 100,
            "min_confidence_threshold": self._settings.min_llm_confidence,
            "target_win_rate": self._settings.expected_win_rate,
            "alerts": [],
        }

        if raw_portfolio.get("alerts"):
            targets["alerts"].extend(raw_portfolio["alerts"])

        if agents:
            system_status["models"] = {
                agent["model"].lower(): agent["status"] for agent in agents
            }

        return {
            "portfolio": portfolio,
            "positions": positions,
            "recent_trades": recent_trades,
            "model_performance": [],
            "agents": agents,
            "model_reasoning": model_reasoning,
            "system_status": system_status,
            "targets": targets,
        }

    @property
    def paper_trading(self) -> bool:
        return self._health.paper_trading

    async def start(self) -> None:
        if self._task and not self._task.done():
            logger.info("Trading service already running")
            return

        self._stop_event.clear()
        self._health = HealthStatus(running=True, paper_trading=False, last_error=None)

        if not (self._creds.api_key and self._creds.api_secret) or self._settings.enable_paper_trading:
            logger.warning("Starting in paper trading mode")
            self._health.paper_trading = True
        else:
            self._client = AsterClient(self._settings, self._creds.api_key, self._creds.api_secret)

        await self._streams.connect()
        await self._init_telegram()
        if self._orchestrator:
            await self._sync_portfolio()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        if self._client:
            await self._client.close()
        await self._streams.close()
        if self._orchestrator:
            await self._orchestrator.close()
        if self._mcp:
            await self._mcp.close()
        self._health = HealthStatus(running=False, paper_trading=self.paper_trading, last_error=self._health.last_error)

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                await self._tick()
                await asyncio.sleep(self._settings.decision_interval_seconds)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Trading loop error: %s", exc)
            self._health.last_error = str(exc)
        finally:
            self._health.running = False
            await self._publish_portfolio_state()

    async def _tick(self) -> None:
        market = await self._fetch_market()

        for symbol, snapshot in market.items():
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
                        "timestamp": timestamp(),
                    }
                )
                continue
            if not decision:
                continue

            if self._mcp:
                proposal = MCPProposalPayload(
                    symbol=symbol,
                    side=decision,
                    notional=self._strategy.allocate_notional(self._portfolio.balance),
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

            if not self._bandit.allow(symbol):
                await self._streams.publish_reasoning(
                    {
                        "bot_id": self._settings.bot_id,
                        "symbol": symbol,
                        "strategy": "bandit",
                        "message": "bandit_suppressed_trade",
                        "timestamp": timestamp(),
                    }
                )
                continue

            notional = self._strategy.allocate_notional(self._portfolio.balance)
            notional = await self._auto_delever(symbol, snapshot, notional)
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
                        "timestamp": timestamp(),
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
            if decision == "BUY":
                take_profit = snapshot.price * (1 + buffer)
                stop_loss = snapshot.price * (1 - buffer)
            else:
                take_profit = snapshot.price * (1 - buffer)
                stop_loss = snapshot.price * (1 + buffer)
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
                "timestamp": timestamp(),
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
                self._portfolio = self._risk.register_fill(self._portfolio, symbol, notional)
                await self._publish_portfolio_state()
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
        quantity = notional / max(price, 1e-8)
        agent_id = self._symbol_to_agent.get(symbol.upper())
        agent_model = None
        if agent_id and agent_id in self._agent_states:
            agent_model = self._agent_states[agent_id].model
        else:
            agent_model = "momentum_strategy"
        if self._orchestrator:
            intent_payload = {
                "symbol": symbol,
                "type": "MARKET",
                "side": side,
                "notional": round(notional, 2),
                "quantity": round(quantity, 6),
                "price": round(price, 4),
                "take_profit": round(take_profit, 4),
                "stop_loss": round(stop_loss, 4),
                "expected_win_rate": self._settings.expected_win_rate,
                "reward_to_risk": self._settings.reward_to_risk,
                "client_metadata": {
                    "entry_price": round(price, 4),
                    "trail_step": self._settings.trailing_step,
                    "agent_id": agent_id,
                    "model_used": agent_model,
                },
            }
            try:
                response = await self._orchestrator.submit_order(self._settings.bot_id, intent_payload)
                if response.get("status") not in {"submitted", "approved"}:
                    reason = response.get("reason", "unknown_error")
                    raise RuntimeError(f"orchestrator rejected order: {reason}")
                await self._sync_portfolio()

                self._register_trade_event(
                    symbol=symbol,
                    side=side,
                    price=price,
                    notional=notional,
                    quantity=quantity,
                    metadata={"status": response.get("status")},
                )

                # Send Telegram notification for successful trade
                if self._telegram:
                    await self._telegram.send_trade_notification(
                        symbol=symbol,
                        side=side,
                        price=price,
                        quantity=quantity,
                        notional=notional,
                        decision_reason=f"AI momentum strategy decision via orchestrator",
                        model_used=agent_model,
                        confidence=self._settings.expected_win_rate,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        portfolio_balance=self._portfolio.balance,
                        risk_percentage=(notional / self._portfolio.balance) * 100,
                    )
            except Exception as exc:
                logger.error("Orchestrator route failed for %s: %s", symbol, exc)
                self._health.last_error = str(exc)
                await self._streams.publish_reasoning(
                    {
                        "bot_id": self._settings.bot_id,
                        "symbol": symbol,
                        "strategy": "orchestrator",
                        "message": "order_error",
                        "context": json.dumps({"error": str(exc)}),
                        "timestamp": timestamp(),
                    }
                )
            return

        assert self._client is not None
        order_payload = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": round(quantity, 6),
            "clientOrderId": order_tag,
        }
        try:
            await self._client.place_order(order_payload)
            logger.info("Placed %s order for %s (notional %.2f)", side, symbol, notional)
            self._portfolio = self._risk.register_fill(self._portfolio, symbol, notional)
            await self._publish_portfolio_state()
            self._register_trade_event(
                symbol=symbol,
                side=side,
                price=price,
                notional=notional,
                quantity=quantity,
            )
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
            self._health.last_error = str(exc)
            await self._streams.publish_reasoning(
                {
                    "bot_id": self._settings.bot_id,
                    "symbol": symbol,
                    "strategy": "momentum",
                    "message": "order_error",
                    "context": json.dumps({"error": str(exc)}),
                    "timestamp": timestamp(),
                }
            )

    async def _fetch_market(self) -> Dict[str, MarketSnapshot]:
        if self.paper_trading:
            return self._generate_fake_market()

        assert self._client is not None
        result: Dict[str, MarketSnapshot] = {}
        try:
            for symbol in self._settings.symbols:
                payload = await self._client.ticker(symbol)
                result[symbol] = parse_market_payload(
                    {
                        "price": payload.get("lastPrice", 0.0),
                        "volume": payload.get("volume", 0.0),
                        "change_24h": payload.get("priceChangePercent", 0.0),
                    }
                )
        except Exception as exc:
            logger.error("Failed to fetch market data: %s", exc)
            self._health.last_error = str(exc)
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
                portfolio = await self._orchestrator.portfolio()
                portfolio.setdefault("source", "orchestrator")
                await self._refresh_asset_prices(portfolio)
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

        client = self._client
        temp_client: Optional[AsterClient] = None

        if client is None:
            try:
                temp_client = AsterClient(self._settings, self._creds.api_key, self._creds.api_secret)
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
                    order_intent = OrderIntent(
                        symbol=symbol,
                        side=decision_side,
                        notional=position_size,
                        order_type="MARKET",
                    )

                    # Execute through orchestrator
                    if self._orchestrator:
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
                        logger.warning("No orchestrator configured, cannot execute LLM order")
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

            # Create closing order (opposite side)
            close_side = "SELL" if position.notional > 0 else "BUY"
            close_quantity = abs(position.notional)

            order_intent = OrderIntent(
                symbol=symbol,
                side=close_side,
                notional=abs(position.notional),
                order_type="MARKET",
            )

            # Execute through orchestrator
            if self._orchestrator:
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
            else:
                logger.warning("No orchestrator configured, cannot close position")

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
                "timestamp": timestamp(),
            }
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
                "timestamp": timestamp(),
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
