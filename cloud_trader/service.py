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
from .open_source import OpenSourceAnalyst
from .pubsub import PubSubClient
from .order_tags import generate_order_tag, parse_order_tag
from .risk import PortfolioState, RiskManager, Position
from .schemas import InferenceRequest
from .strategy import MarketSnapshot, MomentumStrategy, parse_market_payload
from .strategies import StrategySelector, StrategySignal
from .arbitrage import ArbitrageEngine
from .cache import get_cache, close_cache, BaseCache
from .safeguards import TradingSafeguards, handle_kill_switch_command
from .enhanced_telegram import EnhancedTelegramService, create_enhanced_telegram_service
from .ai_analyzer import AITradingAnalyzer
from .market_sentiment import MarketSentimentAnalyzer
from .risk_analyzer import RiskAnalyzer
from .storage import get_storage, close_storage, TradingStorage
from .bigquery_streaming import get_bigquery_streamer, close_bigquery_streamer, BigQueryStreamer
from .feature_store import get_feature_store, TradingFeatureStore

RiskOrchestratorClientType = Any
OrderIntent = None  # type: ignore[assignment]
from .mcp import MCPClient, MCPMessageType, MCPProposalPayload, MCPResponsePayload
# Temporarily disable Vertex AI imports for service stability
# from .vertex_ai_client import get_vertex_client, VertexAIClient
from .open_source import OpenSourceAnalyst
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
    AGENT_MARGIN_REMAINING,
    AGENT_MARGIN_UTILIZATION,
    PORTFOLIO_DRAWDOWN,
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
        "symbols": [],
        "description": "High-conviction momentum execution powered by DeepSeek-V3.",
        "personality": "Aggressive trend follower, high conviction",
        "baseline_win_rate": 0.68,
        "risk_multiplier": 1.0,
        "profit_target": 0.015,
        "margin_allocation": 200000.0,
        "specialization": "momentum",
        # Dynamic configuration parameters
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 5.0,
        "min_position_size_pct": 0.01,
        "max_position_size_pct": 0.15,
        "risk_tolerance": "high",  # high, medium, low
        "time_horizon": "short",   # short, medium, long
        "market_regime_preference": "bull",  # bull, bear, neutral
    },
    {
        "id": "qwen-7b",
        "name": "Qwen Adaptive",
        "model": "Qwen2.5-7B",
        "emoji": "🜂",
        "symbols": [],
        "description": "Adaptive mean-reversion routing using Qwen2.5-7B.",
        "personality": "Conservative mean-reversion with disciplined hedging",
        "baseline_win_rate": 0.64,
        "risk_multiplier": 1.0,
        "profit_target": 0.015,
        "margin_allocation": 200000.0,
        "specialization": "mean_reversion",
        # Dynamic configuration parameters
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 3.0,
        "min_position_size_pct": 0.005,
        "max_position_size_pct": 0.08,
        "risk_tolerance": "medium",
        "time_horizon": "medium",
        "market_regime_preference": "neutral",
    },
    {
        "id": "fingpt-alpha",
        "name": "FinGPT Alpha",
        "model": "FinGPT-8B",
        "emoji": "📊",
        "symbols": [],
        "description": "FinGPT open-source finance agent covering momentum regimes.",
        "personality": "Fundamental-driven, sentiment analysis focused",
        "baseline_win_rate": 0.63,
        "risk_multiplier": 1.0,
        "profit_target": 0.015,
        "margin_allocation": 200000.0,
        "specialization": "fundamental_sentiment",
        # Dynamic configuration parameters
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 4.0,
        "min_position_size_pct": 0.008,
        "max_position_size_pct": 0.12,
        "risk_tolerance": "medium",
        "time_horizon": "long",
        "market_regime_preference": "bull",
    },
    {
        "id": "lagllama-degen",
        "name": "Lag-Llama Degenerate",
        "model": "Lag-Llama",
        "emoji": "🎰",
        "symbols": [],
        "description": "High-risk, high-reward Lag-Llama degenerate trader taking massive positions.",
        "personality": "High-volatility specialist embracing fat-tail regimes",
        "baseline_win_rate": 0.45,
        "risk_multiplier": 2.5,
        "profit_target": 0.025,
        "margin_allocation": 300000.0,
        "specialization": "volatility",
        # Dynamic configuration parameters - MAXIMUM PROFIT MODE
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 10.0,
        "min_position_size_pct": 0.02,
        "max_position_size_pct": 0.25,
        "risk_tolerance": "extreme",
        "time_horizon": "short",
        "market_regime_preference": "volatile",
    },
    # NEW: Ultra-aggressive profit maximizer
    {
        "id": "profit-maximizer",
        "name": "Profit Maximizer",
        "model": "Multi-Model Ensemble",
        "emoji": "💰",
        "symbols": [],
        "description": "AI-powered profit maximization using all available strategies autonomously.",
        "personality": "Pure profit-seeking algorithm with adaptive risk management",
        "baseline_win_rate": 0.60,
        "risk_multiplier": 1.8,
        "profit_target": 0.02,
        "margin_allocation": 400000.0,
        "specialization": "profit_maximization",
        # Dynamic configuration parameters - AUTONOMOUS PROFIT MODE
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 8.0,
        "min_position_size_pct": 0.01,
        "max_position_size_pct": 0.20,
        "risk_tolerance": "high",
        "time_horizon": "adaptive",
        "market_regime_preference": "adaptive",
    },
    # NEW: Kimi agent for news and sentiment analysis
    {
        "id": "kimi-chat",
        "name": "Kimi Chat",
        "model": "kimi-chat-v1",
        "emoji": "🦉",
        "symbols": [],
        "description": "News-driven sentiment analysis and event-based trading using the Kimi model.",
        "personality": "Analytical, news-focused, and event-driven",
        "baseline_win_rate": 0.65,
        "risk_multiplier": 1.1,
        "profit_target": 0.016,
        "margin_allocation": 150000.0,
        "specialization": "sentiment_analysis",
        "dynamic_position_sizing": True,
        "adaptive_leverage": True,
        "intelligence_tp_sl": True,
        "max_leverage_limit": 4.0,
        "risk_tolerance": "medium",
        "time_horizon": "medium",
        "market_regime_preference": "neutral",
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
    personality: str
    baseline_win_rate: float
    margin_allocation: float
    status: str = "monitoring"
    total_trades: int = 0
    total_notional: float = 0.0
    total_pnl: float = 0.0
    exposure: float = 0.0
    last_trade: Optional[datetime] = None
    open_positions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    equity_curve: Deque[Tuple[datetime, float]] = field(default_factory=lambda: deque(maxlen=96))
    # Dynamic agent configuration parameters
    dynamic_position_sizing: bool = True
    adaptive_leverage: bool = True
    intelligence_tp_sl: bool = True
    max_leverage_limit: float = 3.0
    min_position_size_pct: float = 0.005
    max_position_size_pct: float = 0.08
    risk_tolerance: str = "medium"
    time_horizon: str = "medium"
    market_regime_preference: str = "neutral"


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
        # Enable MCP for agent council functionality
        if self._settings.mcp_url:
            try:
                self._mcp = MCPClient(self._settings.mcp_url, self._settings.mcp_session_id)
                logger.info(f"MCP client initialized with URL: {self._settings.mcp_url}")
            except Exception as e:
                logger.error(f"Failed to initialize MCP client: {e}")
                self._mcp = None
        else:
            logger.info("MCP URL not configured, MCP disabled")
            self._mcp = None

        # Initialize Vertex AI client
        self._vertex_client: Optional[Any] = None
        if self._settings.enable_vertex_ai:
            try:
                from .vertex_ai_client import get_vertex_client
                self._vertex_client = get_vertex_client()
                logger.info("Vertex AI client initialized")
            except Exception as exc:
                logger.warning(f"Failed to initialize Vertex AI client: {exc}")
        else:
            logger.info("Vertex AI client disabled by settings.")

        # Initialize Telegram service for notifications
        self._telegram: Optional[EnhancedTelegramService] = None
        self._ai_analyzer: Optional[AITradingAnalyzer] = None
        self._sentiment_analyzer: Optional[MarketSentimentAnalyzer] = None
        self._risk_analyzer: Optional[RiskAnalyzer] = None

        # Fetch all available symbols from Aster DEX
        self._available_symbols: List[str] = []
        self._symbol_refresh_task: Optional[asyncio.Task[None]] = None
        self._observation_task: Optional[asyncio.Task[None]] = None

        # Agent tracking for live-only dashboards
        self._agent_states: Dict[str, AgentState] = {}
        self._symbol_to_agent: Dict[str, str] = {}
        # Agents will be initialized in start() method

        # Market data cache with timestamps for validation
        self._market_cache: Dict[str, Tuple[MarketSnapshot, float]] = {}
        self._market_cache_ttl = 60.0  # 60 seconds max age

        self._recent_trades: Deque[Dict[str, Any]] = deque(maxlen=200)
        self._latest_portfolio_raw: Dict[str, Any] = {}
        self._latest_portfolio_frontend: Dict[str, Any] = {}
        self._price_cache: Dict[str, float] = {}
        self._symbol_filters: Dict[str, Dict[str, Decimal]] = {}
        self._notification_windows: Dict[str, Dict[str, float]] = {}
        self._open_source_analyst = OpenSourceAnalyst(self._settings)
        self._strategy_selector = StrategySelector(enable_rl=self._settings.enable_rl_strategies)
        self._arbitrage_engine = ArbitrageEngine(self._exchange, self._settings)
        self._cache: Optional[BaseCache] = None
        self._cache_connected: bool = False
        self._cache_backend: str = "memory"
        self._safeguards = TradingSafeguards(self._settings)
        self._storage: Optional[TradingStorage] = None
        self._feature_store: Optional[TradingFeatureStore] = None
        self._bigquery: Optional[BigQueryStreamer] = None
        self._storage_ready: bool = False
        self._feature_store_ready: bool = False
        self._bigquery_ready: bool = False
        self._pubsub_connected: bool = False
        self._peak_balance = self._portfolio.balance
        self._targets = {
            "daily_pnl_target": 350.0,
            "max_drawdown_limit": -float(self._settings.max_drawdown * 100),
            "min_confidence_threshold": self._settings.risk_threshold,
            "target_win_rate": self._settings.expected_win_rate,
            "alerts": [],
        }

    async def _fetch_historical_klines(self, symbol: str, interval: str = "1h", limit: int = 100) -> Optional[Any]:
        """Fetch historical kline data for technical analysis with caching."""
        # Check cache first
        if self._cache:
            cached_data = await self._cache.get_historical_data(symbol, interval, limit)
            if cached_data is not None:
                logger.debug(f"Using cached historical data for {symbol}")
                import pandas as pd
                return pd.DataFrame(cached_data)
                
        try:
            klines = await self._exchange.get_historical_klines(symbol, interval, limit)
            if not klines:
                return None
                
            # Convert to DataFrame-like structure for strategies
            import pandas as pd
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                               'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
                                               'taker_buy_quote', 'ignore'])
            
            # Convert string values to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
                
            # Cache the data
            if self._cache:
                await self._cache.set_historical_data(symbol, interval, limit, df.to_dict('records'))
                
            return df
        except Exception as exc:
            logger.debug(f"Failed to fetch historical data for {symbol}: {exc}")
            return None

    async def _fetch_available_symbols(self) -> List[str]:
        """Fetch all available trading symbols from Aster DEX."""
        try:
            logger.info("Fetching all available symbols from Aster DEX...")
            if not hasattr(self._exchange, "get_all_symbols"):
                logger.warning("Exchange client missing get_all_symbols(), falling back to configured symbols")
                return self._settings.symbols

            exchange_symbols = await self._exchange.get_all_symbols()
            
            # Filter for active USDT perpetual pairs with sufficient liquidity
            active_symbols = []
            for symbol_info in exchange_symbols:
                symbol = symbol_info.get("symbol", "")
                status = symbol_info.get("status", "")
                contract_type = symbol_info.get("contractType", "")
                
                # Only include active USDT perpetual contracts
                if (symbol.endswith("USDT") and 
                    status == "TRADING" and 
                    contract_type == "PERPETUAL"):
                    
                    # Check volume filter if available
                    filters = symbol_info.get("filters", [])
                    min_notional = 0
                    for filter_item in filters:
                        if filter_item.get("filterType") == "MIN_NOTIONAL":
                            min_notional = float(filter_item.get("minNotional", 0))
                            break
                    
                    # Only include symbols with reasonable minimum notional (liquidity proxy)
                    if min_notional <= 100:  # $100 min trade size or less
                        active_symbols.append(symbol)
            
            logger.info(f"Found {len(active_symbols)} active USDT perpetual pairs on Aster DEX")
            
            # Apply additional filters based on settings
            max_symbols = self._settings.max_symbols_per_agent * len(AGENT_DEFINITIONS)
            if len(active_symbols) > max_symbols:
                # Prioritize most liquid symbols (could enhance with volume data)
                active_symbols = active_symbols[:max_symbols]
                logger.info(f"Limited to {max_symbols} symbols based on max_symbols_per_agent setting")
            
            return sorted(active_symbols) if active_symbols else self._settings.symbols
            
        except Exception as exc:
            logger.exception(f"Failed to fetch symbols from Aster DEX: {exc}")
            # Fallback to configured symbols
            return self._settings.symbols

    async def _initialize_agents(self) -> None:
        """Initialize agents with dynamic symbol assignment based on available markets."""
        # Fetch all available symbols
        try:
            self._available_symbols = await self._fetch_available_symbols()
        except Exception as exc:
            logger.warning(f"Failed to fetch available symbols: {exc}, using configured defaults")
            self._available_symbols = []

        # Update settings with dynamic symbols
        if not self._available_symbols:
            logger.warning("No symbols fetched, using configured defaults")
            # Use symbols from settings or fallback to common pairs
            if self._settings.symbols:
                self._available_symbols = self._settings.symbols
            else:
                # Fallback to common symbols from agent definitions
                self._available_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "AVAXUSDT", "ARBUSDT"]

        coverage_universe: List[str] = [str(symbol).upper() for symbol in self._available_symbols]
        if not coverage_universe:
            coverage_universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "SUIUSDT", "AVAXUSDT", "ARBUSDT"]

        enabled_agent_ids = set(self._settings.enabled_agents)
        for i, agent_def in enumerate(AGENT_DEFINITIONS):
            if agent_def["id"] not in enabled_agent_ids:
                logger.info(f"Skipping disabled agent: {agent_def['id']}")
                continue
            agent_id = agent_def["id"]

            # All agents now have access to ALL symbols - no token-specific restrictions
            display_symbols = sorted(coverage_universe)[:12]  # Show first 12 for display

            coverage_count = len(coverage_universe)
            specialization = agent_def.get("specialization", "general")
            description = (
                f"{agent_def['description']} Full-market coverage across {coverage_count} symbols."
            )

            state = AgentState(
                id=agent_id,
                name=agent_def["name"],
                model=agent_def["model"],
                emoji=agent_def["emoji"],
                symbols=coverage_universe,  # All symbols available to each agent
                description=description,
                personality=agent_def.get("personality", ""),
                baseline_win_rate=agent_def["baseline_win_rate"],
                margin_allocation=float(agent_def.get("margin_allocation", 1000.0)),
            )

            # Attach additional metadata for downstream consumers
            state.specialization = specialization
            state.full_symbol_universe = coverage_universe.copy()
            state.focus_symbols = coverage_universe.copy()  # All symbols are focus symbols

            # Set dynamic configuration parameters from agent definition
            state.dynamic_position_sizing = agent_def.get("dynamic_position_sizing", True)
            state.adaptive_leverage = agent_def.get("adaptive_leverage", True)
            state.intelligence_tp_sl = agent_def.get("intelligence_tp_sl", True)
            state.max_leverage_limit = agent_def.get("max_leverage_limit", 3.0)
            state.min_position_size_pct = agent_def.get("min_position_size_pct", 0.005)
            state.max_position_size_pct = agent_def.get("max_position_size_pct", 0.08)
            state.risk_tolerance = agent_def.get("risk_tolerance", "medium")
            state.time_horizon = agent_def.get("time_horizon", "medium")
            state.market_regime_preference = agent_def.get("market_regime_preference", "neutral")

            self._agent_states[agent_id] = state
            # All agents can trade any symbol - no exclusive assignment
            for symbol in coverage_universe:
                if symbol not in self._symbol_to_agent:
                    self._symbol_to_agent[symbol] = agent_id  # First agent to register gets preference, but all can trade

            logger.info(
                "Initialized agent %s (%s) with full-market access to all %d symbols",
                agent_id,
                state.name,
                coverage_count,
            )
        
        logger.info(f"Total agents initialized: {len(self._agent_states)}/{len(AGENT_DEFINITIONS)}")

    async def _refresh_symbols(self) -> None:
        """Periodically check for new symbols and reassign if needed."""
        try:
            new_symbols = await self._fetch_available_symbols()
            if set(new_symbols) != set(self._available_symbols):
                logger.info(f"Symbol list changed: {len(self._available_symbols)} -> {len(new_symbols)} symbols")
                added_symbols = set(new_symbols) - set(self._available_symbols)
                removed_symbols = set(self._available_symbols) - set(new_symbols)

                if added_symbols:
                    logger.info(f"New symbols added: {sorted(added_symbols)}")
                if removed_symbols:
                    logger.warning(f"Symbols removed: {sorted(removed_symbols)}")

                # Update available symbols
                self._available_symbols = new_symbols

                # Reinitialize agents with new symbol distribution
                old_states = self._agent_states.copy()
                self._agent_states.clear()
                self._symbol_to_agent.clear()

                await self._initialize_agents()

                # Preserve trading history from old agents to new ones where possible
                for old_agent_id, old_state in old_states.items():
                    if old_agent_id in self._agent_states:
                        new_state = self._agent_states[old_agent_id]
                        # Carry over some stats if the agent still exists
                        new_state.total_trades = old_state.total_trades
                        new_state.total_pnl = old_state.total_pnl
                        new_state.equity_curve.extend(old_state.equity_curve)

        except Exception as exc:
            logger.exception(f"Failed to refresh symbols: {exc}")

    async def _start_symbol_refresh(self) -> None:
        """Start periodic symbol refresh task."""
        if self._symbol_refresh_task and not self._symbol_refresh_task.done():
            return

        async def refresh_loop():
            while not self._stop_event.is_set():
                await asyncio.sleep(3600)  # Check every hour
                await self._refresh_symbols()

        self._symbol_refresh_task = asyncio.create_task(refresh_loop())
        logger.info("Started symbol refresh task (checks every hour)")

    def _calculate_agent_exposure(self, agent_id: str) -> float:
        exposure = 0.0
        for symbol, position in self._portfolio.positions.items():
            mapped_agent = self._symbol_to_agent.get(str(symbol).upper())
            if mapped_agent == agent_id and position:
                exposure += abs(position.notional)
        return exposure

    def _get_agent_margin_remaining(self, agent_id: str) -> float:
        state = self._agent_states.get(agent_id)
        if not state:
            return float("inf")
        used_margin = self._calculate_agent_exposure(agent_id)
        state.exposure = used_margin
        remaining = max(state.margin_allocation - used_margin, 0.0)
        AGENT_MARGIN_REMAINING.labels(agent_id=agent_id).set(remaining)
        utilization = 0.0
        if state.margin_allocation > 0:
            utilization = min(used_margin / state.margin_allocation, 1.0)
        AGENT_MARGIN_UTILIZATION.labels(agent_id=agent_id).set(utilization)
        return remaining

    def _has_agent_margin(self, agent_id: Optional[str], additional_notional: float) -> bool:
        if not agent_id or additional_notional <= 0:
            return True
        remaining = self._get_agent_margin_remaining(agent_id)
        if additional_notional - remaining > 1e-6:
            logger.info(
                "Agent %s margin exhausted: requested %.2f, remaining %.2f",
                agent_id,
                additional_notional,
                remaining,
            )
            return False
        return True

    def _select_agent_for_trade(self, symbol: str, notional: float) -> Optional[str]:
        """Dynamically choose an agent to lead execution for a symbol."""
        symbol_key = str(symbol).upper()
        existing = self._symbol_to_agent.get(symbol_key)
        if existing and existing in self._agent_states:
            return existing

        if not self._agent_states:
            return None

        ranked_states = sorted(
            self._agent_states.values(),
            key=lambda state: self._get_agent_margin_remaining(state.id),
            reverse=True,
        )

        for state in ranked_states:
            if self._has_agent_margin(state.id, notional):
                self._symbol_to_agent[symbol_key] = state.id
                return state.id

        fallback = ranked_states[0].id
        self._symbol_to_agent[symbol_key] = fallback
        return fallback

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
        """Initialize enhanced Telegram notification service and AI components."""
        # Initialize AI analyzers
        self._ai_analyzer = AITradingAnalyzer()
        self._sentiment_analyzer = MarketSentimentAnalyzer()
        self._risk_analyzer = RiskAnalyzer()

        # Initialize enhanced Telegram service
        self._telegram = await create_enhanced_telegram_service(
            self._settings,
            ai_analyzer=self._ai_analyzer,
            sentiment_analyzer=self._sentiment_analyzer,
            risk_analyzer=self._risk_analyzer
        )

        # Start the enhanced Telegram bot if initialized
        if self._telegram:
            try:
                await self._telegram.start()
                logger.info("Enhanced Telegram AI bot started successfully")
            except Exception as exc:
                logger.warning(f"Failed to start enhanced Telegram bot: {exc}")

    async def dashboard_snapshot(self) -> Dict[str, Any]:
        """Aggregate a lightweight view for the dashboard endpoint."""
        logger.info("Dashboard snapshot requested")
        snapshot_start = time.time()
        
        # Ensure agents are initialized even if service hasn't started
        if not self._agent_states and len(AGENT_DEFINITIONS) > 0:
            logger.warning("Agents not initialized, initializing now for dashboard")
            try:
                await self._initialize_agents()
            except Exception as exc:
                logger.warning(f"Failed to initialize agents for dashboard: {exc}")
        
        try:
            try:
                raw_portfolio, orchestrator_status = await self._resolve_portfolio()
                logger.info("Dashboard: portfolio resolved")
            except Exception as exc:
                logger.exception("Dashboard: failed to resolve portfolio")
                # Continue with empty portfolio if we can't resolve it
                raw_portfolio = {}
                orchestrator_status = "unknown"

            # Transform portfolio data for frontend
            try:
                portfolio = self._transform_portfolio_for_frontend(raw_portfolio)
                self._latest_portfolio_frontend = portfolio
                self._update_agent_snapshots(portfolio)
            except Exception as exc:
                logger.exception("Dashboard: failed to transform portfolio")
                # Use empty portfolio as fallback
                portfolio = {
                    "balance": 0.0,
                    "total_exposure": 0.0,
                    "available_balance": 0.0,
                    "positions": {},
                    "source": "unknown"
                }

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

            # Serialize agents - ensure we always return all agents
            agents = self._serialize_agents()
            logger.info(f"Dashboard: returning {len(agents)} agents")

            response = {
            "portfolio": portfolio,
                "positions": list(portfolio.get("positions", {}).values()),
                "recent_trades": list(self._recent_trades)[:50],
                "model_performance": self._collect_model_performance(),
                "agents": agents,
                "model_reasoning": await self._collect_model_reasoning(),
                "system_status": self._build_system_status(orchestrator_status),
                "targets": self._targets,
                "reasoning": reasoning,
            }
            return response
        finally:
            DASHBOARD_SNAPSHOT_TIME.observe(time.time() - snapshot_start)

    def _collect_model_performance(self) -> List[Dict[str, Any]]:
        """Collect performance metrics for all trading agents."""
        performance_data = []

        for agent_id, agent_state in self._agent_states.items():
            agent_def = next((defn for defn in AGENT_DEFINITIONS if defn["id"] == agent_id), None)
            if not agent_def:
                continue

            # Calculate performance metrics
            total_trades = agent_state.total_trades
            total_pnl = agent_state.total_pnl
            win_rate = (total_trades > 0 and total_pnl > 0) or 0.0

            # Calculate Sharpe-like ratio (PnL / sqrt(trades) as proxy)
            sharpe_ratio = total_pnl / max(1, total_trades ** 0.5) if total_trades > 0 else 0.0

            performance_data.append({
                "agent_id": agent_id,
                "agent_name": agent_def.get("name", agent_id),
                "model": agent_def.get("model", "unknown"),
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe_ratio,
                "baseline_win_rate": agent_def.get("baseline_win_rate", 0.5),
                "risk_multiplier": agent_def.get("risk_multiplier", 1.0),
                "specialization": agent_def.get("specialization", "general"),
                "status": agent_state.status,
                "last_trade": agent_state.last_trade.isoformat() if agent_state.last_trade else None,
            })

        return performance_data

    def _build_system_status(self, orchestrator_status: str) -> Dict[str, Any]:
        """Build system status information."""
        services_status = {
            "cloud_trader": "online" if self._health.running else "offline",
            "orchestrator": orchestrator_status or "not_configured",
            "cache": "online" if self._cache_connected else "offline",
            "storage": "online" if self._storage_ready else "offline",
            "pubsub": "online" if self._pubsub_connected else "offline",
            "feature_store": "online" if self._feature_store_ready else "offline",
            "bigquery": "online" if self._bigquery_ready else "offline",
        }
        if self._settings.enable_paper_trading:
            services_status["paper_trading"] = "enabled"

        models_status: Dict[str, str] = {}
        for agent_id, agent_state in self._agent_states.items():
            models_status[agent_id] = agent_state.status or "idle"

        return {
            "running": self._health.running,
            "paper_trading": self._health.paper_trading,
            "last_error": self._health.last_error,
            "orchestrator_status": orchestrator_status,
            "agents_initialized": len(self._agent_states),
            "mcp_enabled": self._mcp is not None,
            "total_symbols": len(self._available_symbols),
            "cache": {
                "backend": self._cache_backend,
                "connected": self._cache_connected,
            },
            "storage_ready": self._storage_ready,
            "pubsub_connected": self._pubsub_connected,
            "feature_store_ready": self._feature_store_ready,
            "bigquery_ready": self._bigquery_ready,
            "services": services_status,
            "models": models_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _collect_model_reasoning(self) -> List[Dict[str, Any]]:
        """Collect recent model reasoning from PubSub streams."""
        try:
            # Get recent reasoning from streams (simplified for now)
            reasoning_data = []

            # This would normally collect from PubSub, but for now return basic structure
            for agent_id, agent_state in self._agent_states.items():
                agent_def = next((defn for defn in AGENT_DEFINITIONS if defn["id"] == agent_id), None)
                if not agent_def:
                    continue

                reasoning_data.append({
                    "agent_id": agent_id,
                    "agent_name": agent_def.get("name", agent_id),
                    "model": agent_def.get("model", "unknown"),
                    "specialization": agent_def.get("specialization", "general"),
                    "last_reasoning": f"Trading with {agent_def.get('risk_multiplier', 1.0)}x risk multiplier",
                    "confidence_level": "high" if agent_def.get("baseline_win_rate", 0) > 0.65 else "medium",
                    "strategy_focus": agent_def.get("specialization", "general").title(),
                })

            return reasoning_data
        except Exception as e:
            logger.warning(f"Failed to collect model reasoning: {e}")
            return []

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

        # Initialize cache
        try:
            self._cache = await get_cache()
            self._cache_backend = getattr(self._cache, "backend", "memory")
            self._cache_connected = self._cache.is_connected()
            logger.info(
                "Cache backend '%s' ready (connected=%s)",
                self._cache_backend,
                self._cache_connected,
            )
        except Exception as e:
            logger.warning(f"Failed to initialize cache: {e}")
            self._cache_connected = False
            self._cache_backend = "memory"
        
        # Initialize database storage
        try:
            self._storage = await get_storage()
            self._storage_ready = self._storage.is_ready()
            logger.info("Database storage initialized (ready=%s)", self._storage_ready)
        except Exception as e:
            logger.warning(f"Failed to initialize database storage: {e}")
            self._storage_ready = False
        
        # Initialize feature store
        try:
            self._feature_store = await get_feature_store()
            self._feature_store_ready = self._feature_store.is_ready()
            logger.info("Feature store initialized (ready=%s)", self._feature_store_ready)
        except Exception as e:
            logger.warning(f"Failed to initialize feature store: {e}")
            self._feature_store_ready = False
        
        # Initialize BigQuery streaming
        try:
            self._bigquery = await get_bigquery_streamer()
            self._bigquery_ready = self._bigquery.is_ready()
            logger.info("BigQuery streaming initialized (ready=%s)", self._bigquery_ready)
        except Exception as e:
            logger.warning(f"Failed to initialize BigQuery streaming: {e}")
            self._bigquery_ready = False
            
        # Initialize agents with dynamic symbol discovery
        await self._initialize_agents()

        # Initialize the Aster client with credentials
        self._exchange = AsterClient(
            credentials=credentials,
            base_url=self._settings.rest_base_url,
        )
        logger.info("Aster client initialized.")

        try:
            await self._streams.connect()
            self._pubsub_connected = self._streams.is_connected()
            logger.info("PubSub client connected (ready=%s).", self._pubsub_connected)
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

        except Exception as exc:
            logger.exception("Exception during service start: %s", exc)
            self._health.last_error = str(exc)

            # Start periodic market observation task if enabled
            if (
                self._settings.telegram_enable_market_observer
                and self._settings.telegram_summary_interval_seconds > 0
            ):
                self._observation_task = asyncio.create_task(self._periodic_market_observations())
                logger.info("Market observation task started.")
            else:
                logger.info("Telegram market observer disabled; skipping periodic summaries.")

            # Start symbol refresh task
            await self._start_symbol_refresh()
            logger.info("Symbol refresh task started.")

            logger.warning("--- EXITING start() ---")
        except Exception as exc:
            logger.exception("Exception during service start: %s", exc)
            self._health.last_error = str(exc)
            self._health.running = False


    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task
        if self._observation_task:
            self._observation_task.cancel()
            try:
                await self._observation_task
            except asyncio.CancelledError:
                pass
        if self._symbol_refresh_task:
            self._symbol_refresh_task.cancel()
            try:
                await self._symbol_refresh_task
            except asyncio.CancelledError:
                pass
        if self._exchange:
            await self._exchange.close()
        await self._streams.close()
        if self._orchestrator:
            await self._orchestrator.close()
        if self._cache:
            await close_cache()
            self._cache_connected = False
        if self._storage:
            await close_storage()
        if self._bigquery:
            await close_bigquery_streamer()
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
        # Check if market data circuit breaker allows operation
        if not self._safeguards.check_circuit_breaker('market_data'):
            logger.warning("Market data circuit breaker is open, skipping tick")
            return
            
        try:
            market = await self._fetch_market()
            
            if not market:
                logger.warning("No market data available, skipping tick")
                self._safeguards.record_failure('market_data')
                return
                
            # Record success for circuit breaker
            self._safeguards.record_success('market_data')
            
        except Exception as exc:
            logger.exception("Failed to fetch market data in tick: %s", exc)
            self._health.last_error = str(exc)[:200]
            self._safeguards.record_failure('market_data')
            return

        # Update safeguard metrics
        self._safeguards.update_heat_metrics(self._portfolio)
        self._safeguards.update_daily_pnl(self._portfolio.balance)
        
        # Check drawdown limits
        if not self._safeguards.check_drawdown_limits():
            logger.error("Drawdown limits exceeded, halting trading")
            return
        
        # First, check existing positions for profit targets and stop losses
        await self._monitor_and_close_positions(market)
        
        # Scan for arbitrage opportunities if enabled
        if self._settings.enable_arbitrage:
            try:
                arb_opportunities = await self._arbitrage_engine.scan_opportunities(market)
                if arb_opportunities:
                    logger.info(f"Found {len(arb_opportunities)} arbitrage opportunities")
                    
                    # Execute the best opportunity if confidence is high enough
                    best_arb = arb_opportunities[0]
                    if best_arb.confidence > 0.7 and best_arb.expected_profit > 0.3:
                        success = await self._arbitrage_engine.execute_arbitrage(best_arb)
                        if success and self._telegram:
                            await self._telegram.send_message(
                                f"💎 **Arbitrage Executed**\n"
                                f"Type: {best_arb.type}\n"
                                f"Symbols: {', '.join(best_arb.symbols)}\n"
                                f"Expected Profit: {best_arb.expected_profit:.3f}%\n"
                                f"Confidence: {best_arb.confidence:.2f}"
                            )
            except Exception as e:
                logger.error(f"Arbitrage scan failed: {e}")

        # Process each symbol independently to continue on failures
        for symbol, snapshot in market.items():
            try:
                # Use multi-strategy evaluation instead of single momentum strategy
                try:
                    historical_data = await self._fetch_historical_klines(symbol)
                    strategy_signal = await self._strategy_selector.select_best_strategy(
                        symbol, snapshot, historical_data
                    )
                except Exception as e:
                    logger.error(f"Strategy evaluation failed for {symbol}: {e}")
                    continue
                
                # Map strategy signal to legacy decision format
                if strategy_signal.direction == "HOLD":
                    await self._streams.publish_reasoning(
                        {
                            "bot_id": self._settings.bot_id,
                            "symbol": symbol,
                            "strategy": strategy_signal.strategy_name,
                            "message": "hold_position",
                            "context": json.dumps(
                                {
                                    "reasoning": strategy_signal.reasoning,
                                    "confidence": strategy_signal.confidence,
                                    "metadata": strategy_signal.metadata
                                }
                            ),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue
                
                decision = strategy_signal.direction
                if not decision:
                    continue

                # Enhanced position sizing with liquidation prevention
                base_position_fraction = strategy_signal.position_size
                base_notional = self._portfolio.balance * base_position_fraction

                # Apply additional Kelly Criterion risk management
                kelly_notional = self._strategy.allocate_notional(
                        portfolio_balance=self._portfolio.balance,
                    expected_return=strategy_signal.confidence,
                        volatility=0.15,
                    )

                # Select agent for this trade first
                agent_id_for_symbol = self._select_agent_for_trade(symbol, base_notional)
                if not agent_id_for_symbol:
                    logger.warning(f"No agent available for {symbol}")
                    continue

                # Dynamic agent-based position sizing and risk management
                volatility_estimate = getattr(strategy_signal, 'volatility', 1.0)
                confidence_score = getattr(strategy_signal, 'confidence', 0.5)
                conviction_score = confidence_score * getattr(strategy_signal, 'momentum_strength', 1.0)

                # Get agent state for dynamic parameters (includes personality and configuration)
                agent_state = self._agent_states.get(agent_id_for_symbol)
                if not agent_state:
                    logger.warning(f"No agent state found for {agent_id_for_symbol}, using fallback")
                    agent_state = type('AgentState', (), {
                        'dynamic_position_sizing': True,
                        'intelligence_tp_sl': True,
                        'max_leverage_limit': 3.0,
                        'min_position_size_pct': 0.005,
                        'max_position_size_pct': 0.08,
                        'risk_tolerance': 'medium',
                        'time_horizon': 'medium',
                        'market_regime_preference': 'neutral'
                    })()

                # Create agent config dict from agent state for risk manager
                agent_config = {
                    'max_leverage_limit': getattr(agent_state, 'max_leverage_limit', 3.0),
                    'min_position_size_pct': getattr(agent_state, 'min_position_size_pct', 0.005),
                    'max_position_size_pct': getattr(agent_state, 'max_position_size_pct', 0.08),
                    'risk_tolerance': getattr(agent_state, 'risk_tolerance', 'medium'),
                    'time_horizon': getattr(agent_state, 'time_horizon', 'medium'),
                    'market_regime_preference': getattr(agent_state, 'market_regime_preference', 'neutral'),
                }

                market_conditions = {
                    "volatility": volatility_estimate,
                    "regime": getattr(strategy_signal, 'market_regime', 'neutral'),
                    "volatility_index": getattr(strategy_signal, 'volatility_index', 1.0),
                }

                # Agent dynamically calculates position size based on their personality
                if getattr(agent_state, 'dynamic_position_sizing', True):
                    dynamic_position_size = self._risk.calculate_agent_position_size(
                        agent_config, self._portfolio, market_conditions, conviction_score
                    )
                    base_notional = min(base_notional, kelly_notional, dynamic_position_size)
                else:
                    # Fallback to asymmetric sizing
                    asymmetric_notional = self._risk.calculate_asymmetric_position_size(
                        self._portfolio, confidence_score, volatility_estimate, conviction_score
                    )
                    safe_max_notional = self._risk.get_safe_position_size(self._portfolio, volatility_estimate)
                    base_notional = min(base_notional, kelly_notional, asymmetric_notional, safe_max_notional)

                if base_notional <= 0:
                    logger.info("Position size too small after agent risk adjustment for %s", symbol)
                    continue

                # Agent dynamically calculates TP/SL based on their personality and market conditions
                if getattr(agent_state, 'intelligence_tp_sl', True):
                    tp_sl_levels = self._risk.calculate_agent_tp_sl(
                        agent_config, market_conditions, snapshot.price, conviction_score
                    )
                else:
                    # Fallback to standard TP/SL calculation
                    tp_sl_levels = self._risk.calculate_optimal_tp_sl(
                        snapshot.price, volatility_estimate, confidence_score
                    )

                if self._mcp:
                    proposal = MCPProposalPayload(
                        symbol=symbol,
                        side=decision,
                        notional=base_notional,
                        confidence=strategy_signal.confidence,
                        rationale=f"{strategy_signal.strategy_name}: {strategy_signal.reasoning}",
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

                # MCP proposals are internal - don't spam Telegram with every proposal
                # Only send notifications for actual executed trades

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

                if not self._has_agent_margin(agent_id_for_symbol, notional):
                    RISK_LIMITS_BREACHED.labels(limit_type="agent_margin").inc()
                    await self._streams.publish_reasoning(
                        {
                            "bot_id": agent_id_for_symbol,
                            "symbol": symbol,
                            "strategy": "margin",
                            "message": "agent_margin_exceeded",
                            "context": json.dumps(
                                {
                                    "requested_notional": round(notional, 2),
                                    "remaining_margin": round(
                                        self._get_agent_margin_remaining(agent_id_for_symbol), 2
                                    ),
                                }
                            ),
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )
                    continue
                # Enhanced risk check with volatility awareness
                volatility_estimate = getattr(strategy_signal, 'volatility', 1.0)
                if not self._risk.can_open_position(self._portfolio, notional, volatility_estimate):
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
                            # Generate AI analysis for the trade
                            ai_analysis = None
                            if self._ai_analyzer:
                                analysis_result = await self._ai_analyzer.analyze_trade(
                                    symbol=symbol,
                                    side=decision,
                                    price=snapshot.price,
                                    volume=paper_quantity,
                                    market_data={
                                        'volatility': snapshot.volatility,
                                        'volume': snapshot.volume_24h,
                                        'trend': 'bullish' if snapshot.price > snapshot.sma_20 else 'bearish'
                                    }
                                )
                                ai_analysis = analysis_result.get('rationale', '')

                            # Create enhanced trade notification
                            from .enhanced_telegram import TradeNotification, NotificationPriority
                            trade_notification = TradeNotification(
                                symbol=symbol,
                                side=decision,
                                price=snapshot.price,
                                quantity=paper_quantity,
                                notional=notional,
                                take_profit=take_profit,
                                stop_loss=stop_loss,
                                confidence=self._settings.expected_win_rate,
                                ai_analysis=ai_analysis
                            )

                            await self._telegram.send_trade_notification(
                                trade_notification,
                                priority=NotificationPriority.MEDIUM
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

    async def _generate_trade_thesis(
        self,
        agent_id: Optional[str],
        symbol: str,
        side: str,
        price: float,
        market_context: dict,
        take_profit: float,
        stop_loss: float,
    ) -> str:
        """Generate a trading thesis using parallel multi-agent collaboration when available."""

        # Determine which agents to query (prioritize the executing agent, then fan out)
        candidate_agent_ids = [agent["id"] for agent in AGENT_DEFINITIONS]
        agents_to_query: List[str] = []
        if agent_id:
            agents_to_query.append(agent_id)
        for candidate in candidate_agent_ids:
            if candidate not in agents_to_query:
                agents_to_query.append(candidate)

        # Query multiple agents in parallel using the open-source analyst
        agent_results: List[Dict[str, Any]] = []
        if agents_to_query:
            tasks = [
                self._open_source_analyst.generate_thesis(
                    agent,
                    symbol,
                    side,
                    price,
                    market_context,
                )
                for agent in agents_to_query
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.debug("Agent %s query failed: %s", agents_to_query[i], result)
                    continue
                if result and isinstance(result, dict):
                    result.setdefault("source", agents_to_query[i])
                    agent_results.append(result)

        # If we have multiple agent results, synthesize them
        if len(agent_results) > 1:
            # Find best thesis based on confidence and risk score
            best_result = None
            best_score = -1.0
            
            for result in agent_results:
                confidence = result.get("confidence", 0.0) or 0.0
                risk_score = result.get("risk_score", 1.0) or 1.0
                # Score = confidence * (1 - risk_score) - higher confidence, lower risk = better
                score = confidence * (1.0 - risk_score)
                if score > best_score:
                    best_score = score
                    best_result = result
            
            if best_result:
                analysis = best_result
            else:
                analysis = agent_results[0] if agent_results else None
        elif len(agent_results) == 1:
            analysis = agent_results[0]
        elif agent_id:
            # Fallback to single agent query
            analysis = await self._open_source_analyst.generate_thesis(
                agent_id,
                symbol,
                side,
                price,
                market_context,
            )
        else:
            analysis = None

        # Process analysis result
        if analysis and isinstance(analysis.get("thesis"), str):
            thesis_text = analysis["thesis"].strip()
            thesis_upper = thesis_text.upper()
            if symbol.upper() not in thesis_upper:
                thesis_text = f"{thesis_text} (instrument: {symbol.upper()})"

            source = analysis.get("source", "Unknown")
            risk_score = analysis.get("risk_score")
            confidence = analysis.get("confidence")

            # Enforce risk threshold (default 0.7)
            risk_rejected = False
            if risk_score is not None:
                if risk_score < self._settings.risk_threshold:
                    logger.info(
                        "Thesis for %s rejected: risk_score %.2f < threshold %.2f (source: %s)",
                        symbol,
                        risk_score,
                        self._settings.risk_threshold,
                        source,
                    )
                    risk_rejected = True
                else:
                    # Include risk and confidence in thesis
                    extras: list[str] = []
                    if isinstance(risk_score, (int, float)):
                        extras.append(f"risk {risk_score:.2f}")
                    if isinstance(confidence, (int, float)):
                        extras.append(f"confidence {confidence:.2f}")
                    if extras:
                        thesis_text = f"{thesis_text} [{' | '.join(extras)}]"
                    return thesis_text

            if not risk_rejected:
                # For FinGPT-specific validation
                if source == "FinGPT":
                    if risk_score is None or risk_score >= self._settings.fingpt_min_risk_score:
                        extras: list[str] = []
                        if isinstance(risk_score, (int, float)):
                            extras.append(f"risk {risk_score:.2f}")
                        if isinstance(confidence, (int, float)):
                            extras.append(f"confidence {confidence:.2f}")
                        if extras:
                            thesis_text = f"{thesis_text} [{' | '.join(extras)}]"
                        return thesis_text
                    logger.info(
                        "FinGPT thesis for %s discarded (risk_score %.2f < %.2f)",
                        symbol,
                        risk_score,
                        self._settings.fingpt_min_risk_score,
                    )
                # For Lag-Llama-specific validation
                elif source == "Lag-LLaMA":
                    ci_span = analysis.get("ci_span")
                    if ci_span is not None and ci_span > self._settings.lagllama_max_ci_span:
                        logger.info(
                            "Lag-LLaMA thesis for %s discarded (CI span %.2f > %.2f)",
                            symbol,
                            ci_span,
                            self._settings.lagllama_max_ci_span,
                        )
                    else:
                        extras = []
                        if isinstance(ci_span, (int, float)):
                            extras.append(f"CI span {ci_span:.2%}")
                        anomaly = analysis.get("anomaly_score")
                        if isinstance(anomaly, (int, float)):
                            extras.append(f"anomaly {anomaly:.2f}")
                        if isinstance(confidence, (int, float)):
                            extras.append(f"confidence {confidence:.2f}")
                        if extras:
                            thesis_text = f"{thesis_text} [{' | '.join(extras)}]"
                        return thesis_text

        change_24h = market_context.get('change_24h', 0)
        volume = market_context.get('volume', 0)
        atr = market_context.get('atr')

        trend_strength = abs(change_24h)
        volume_level = "high" if volume > 1_000_000 else "moderate" if volume > 100_000 else "low"
        volatility = "high" if atr and atr > price * 0.02 else "moderate" if atr and atr > price * 0.01 else "low"

        if side == "BUY":
            if trend_strength > 5:
                thesis = f"Strong bullish momentum with {change_24h:.1f}% 24h gain. "
            elif trend_strength > 2:
                thesis = f"Moderate bullish trend with {change_24h:.1f}% 24h gain. "
            else:
                thesis = f"Early bullish signal despite {change_24h:.1f}% 24h change. "

            thesis += "High volume confirms buying pressure. " if volume_level == "high" else "Moderate participation from buyers. " if volume_level == "moderate" else "Subdued volume, scale entries carefully. "
            thesis += "High volatility implies fast follow-through. " if volatility == "high" else "Moderate volatility, monitor trailing stops. " if volatility == "moderate" else "Low volatility favours staged accumulation. "
            thesis += f"Targets ${take_profit:.2f} with protection near ${stop_loss:.2f}."
        else:
            if trend_strength > 5:
                thesis = f"Strong bearish momentum with {change_24h:.1f}% 24h decline. "
            elif trend_strength > 2:
                thesis = f"Moderate bearish trend with {change_24h:.1f}% 24h decline. "
            else:
                thesis = f"Early bearish signal despite {change_24h:.1f}% 24h change. "

            thesis += "Heavy sell volume validates downside. " if volume_level == "high" else "Moderate volume supports distribution. " if volume_level == "moderate" else "Thin volume—avoid oversizing. "
            thesis += "Volatility elevated—expect sharp moves. " if volatility == "high" else "Controlled volatility, ride trend cautiously. " if volatility == "moderate" else "Low volatility, scaling out methodically. "
            thesis += f"Targets ${take_profit:.2f} with stop near ${stop_loss:.2f}."

        return thesis

    async def _query_vertex_agent(
        self,
        agent_id: str,
        symbol: str,
        side: str,
        price: float,
        market_context: dict,
        take_profit: float,
        stop_loss: float,
    ) -> Dict[str, Any]:
        """Query a Vertex AI agent for trading analysis."""
        # Vertex AI temporarily disabled - return fallback analysis
        return {
            "thesis": f"Agent {agent_id} analysis for {symbol}: {side} position with entry at ${price:.2f}, take profit ${take_profit:.2f}, stop loss ${stop_loss:.2f}",
            "confidence": 0.7,
            "source": agent_id,
            "risk_score": 0.3,
            "inference_time": 0.1,
        }

    def _can_send_notification(
        self,
        category: str,
        scope: Optional[str],
        cooldown_seconds: Optional[float] = None,
    ) -> bool:
        """Return True if a notification can be sent without breaching cooldown."""

        if cooldown_seconds is None or cooldown_seconds <= 0:
            return True

        bucket = self._notification_windows.setdefault(category, {})
        key = scope or "__global__"
        now = time.time()
        last_sent = bucket.get(key, 0.0)
        if now - last_sent < cooldown_seconds:
            return False

        bucket[key] = now
        return True

    async def _periodic_market_observations(self) -> None:
        """Send periodic market observations and portfolio updates via Telegram."""
        cooldown = self._settings.telegram_summary_interval_seconds
        if cooldown <= 0:
            logger.info("Periodic market observations disabled (cooldown <= 0).")
            return
 
        while not self._stop_event.is_set():
            try:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=cooldown)
                    continue
                except asyncio.TimeoutError:
                    pass
 
                if not self._telegram:
                    continue

                if not self._can_send_notification("summary", None, cooldown):
                    logger.debug("Skipping Telegram summary due to cooldown window.")
                    continue
 
                # Collect market summary
                market_summary = {}
                for symbol, data in self._market_cache.items():
                    snapshot = data if isinstance(data, dict) else None
                    if not snapshot and isinstance(data, tuple) and len(data) == 2:
                        snapshot = data[0] if isinstance(data[0], dict) else None
                    if snapshot:
                        market_summary[symbol] = {
                            'change_24h': snapshot.get('change_24h', 0),
                            'volume': snapshot.get('volume', 0),
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

                has_recent_trade = False
                lookback_cutoff = datetime.utcnow().timestamp() - min(cooldown, 86_400)
                for trade in list(self._recent_trades):
                    timestamp_value = trade.get("timestamp")
                    if not timestamp_value:
                        continue
                    try:
                        normalized = timestamp_value.replace("Z", "+00:00")
                        trade_ts = datetime.fromisoformat(normalized).timestamp()
                    except ValueError:
                        continue
                    if trade_ts >= lookback_cutoff:
                        has_recent_trade = True
                        break

                if not active_positions and not has_recent_trade:
                    logger.debug("Skipping Telegram summary due to no new activity in lookback window.")
                    continue

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
        # Check safeguards before executing
        can_trade, reason = self._safeguards.can_trade()
        if not can_trade:
            logger.warning(f"Trading blocked by safeguards: {reason}")
            # Removed frequent blocked trade notifications - only log to console
            return
            
        # Check and record API circuit breaker
        if not self._safeguards.check_circuit_breaker('orders'):
            logger.warning(f"Orders circuit breaker is open, skipping {symbol} order")
            return
            
        try:
            # Record order attempt for rate limiting
            self._safeguards.record_order()
            
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
                    "order_type": OrderType.MARKET,
                    "quantity": quantity_str,
                    "new_client_order_id": order_tag,
                }

                try:
                    logger.info("Submitting order payload: %s", order_payload)
                    await self._exchange.place_order(**order_payload)
                    
                    # Record API success
                    self._safeguards.record_success('api')
                    self._safeguards.record_success('orders')
                    
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
                    # Record API failure
                    self._safeguards.record_failure('api')
                    self._safeguards.record_failure('orders')
                    
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
                await self._register_trade_event(
                    symbol=symbol,
                    side=side,
                    price=price,
                    notional=notional,
                    quantity=quantity,
                    metadata={"position_verified": False, "execution_price": execution_price},
                )
                
                # Update agent decision with execution result and reward
                if self._storage:
                    try:
                        # Calculate reward (simplified - would use actual PnL later)
                        reward = 0.0  # Will be updated when position closes
                        
                        # Update the most recent decision for this symbol/agent
                        # Note: In production, we'd track decision IDs for proper updates
                        asyncio.create_task(self._storage.insert_agent_decision(
                            timestamp=datetime.utcnow(),
                            agent_id=self._symbol_to_agent.get(symbol.upper(), "unknown"),
                            symbol=symbol,
                            decision=side,
                            confidence=metadata.get("confidence", 0.5) if metadata else 0.5,
                            strategy=metadata.get("strategy") if metadata else None,
                            executed=True,
                            reward=reward,
                        ))
                    except Exception as e:
                        logger.debug(f"Failed to update agent decision: {e}")
 
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
                trade_thesis = await self._generate_trade_thesis(
                    agent_id,
                    symbol,
                    side,
                    execution_price,
                    market_context,
                    take_profit,
                    stop_loss,
                )

                # Calculate risk/reward ratio
                risk_amount = abs(execution_price - stop_loss) if stop_loss > 0 else 0
                reward_amount = abs(take_profit - execution_price) if take_profit > 0 else 0
                risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0

                try:
                    # Generate AI analysis for the trade
                    ai_analysis = None
                    if self._ai_analyzer:
                        analysis_result = await self._ai_analyzer.analyze_trade(
                            symbol=symbol,
                            side=side,
                            price=execution_price,
                            volume=quantity,
                            market_data={
                                'volatility': market_context.get('atr', 0.02),
                                'volume': market_context.get('volume', 0),
                                'trend': 'bullish' if market_context.get('change_24h', 0) > 0 else 'bearish'
                            }
                        )
                        ai_analysis = f"{analysis_result.get('rationale', '')}\n\nTrade Thesis: {trade_thesis}"

                    # Create enhanced trade notification
                    from .enhanced_telegram import TradeNotification, NotificationPriority
                    trade_notification = TradeNotification(
                        symbol=symbol,
                        side=side,
                        price=execution_price,
                        quantity=quantity,
                        notional=notional,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        confidence=self._settings.expected_win_rate,
                        ai_analysis=ai_analysis
                    )

                    await self._telegram.send_trade_notification(
                        trade_notification,
                        priority=NotificationPriority.HIGH if notional > 1000 else NotificationPriority.MEDIUM
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
                    
                    # Write market snapshot to storage
                    if self._storage:
                        try:
                            # Helper to safely get optional float values
                            def get_opt_float(key: str) -> Optional[float]:
                                val = payload.get(key)
                                if val is None or val == "":
                                    return None
                                try:
                                    return float(val)
                                except (TypeError, ValueError):
                                    return None
                            
                            asyncio.create_task(self._storage.insert_market_snapshot(
                                timestamp=datetime.utcnow(),
                                symbol=symbol,
                                price=price,
                                volume_24h=volume,
                                change_24h=change_24h,
                                high_24h=get_opt_float("highPrice"),
                                low_24h=get_opt_float("lowPrice"),
                                funding_rate=get_opt_float("fundingRate"),
                                open_interest=get_opt_float("openInterest"),
                            ))
                            
                            # Stream market data to BigQuery
                            if self._bigquery:
                                try:
                                    asyncio.create_task(self._bigquery.stream_market_data(
                                        timestamp=datetime.utcnow(),
                                        symbol=symbol,
                                        price=price,
                                        volume_24h=volume,
                                        change_24h=change_24h,
                                        high_24h=get_opt_float("highPrice"),
                                        low_24h=get_opt_float("lowPrice"),
                                        funding_rate=get_opt_float("fundingRate"),
                                        open_interest=get_opt_float("openInterest"),
                                    ))
                                except Exception as e:
                                    logger.debug(f"Failed to stream market data to BigQuery: {e}")
                        except Exception as e:
                            logger.debug(f"Failed to write market snapshot to storage: {e}")
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
            self._get_agent_margin_remaining(state.id)
            
            # Write agent performance to storage
            if self._storage:
                try:
                    # Calculate win rate
                    positive = sum(1 for pos in state.open_positions.values() if float(pos.get("pnl", 0) or 0) > 0)
                    negative = sum(1 for pos in state.open_positions.values() if float(pos.get("pnl", 0) or 0) < 0)
                    win_rate = (positive / (positive + negative) * 100.0) if (positive + negative) > 0 else None
                    
                    asyncio.create_task(self._storage.insert_agent_performance(
                        timestamp=timestamp,
                        agent_id=state.id,
                        equity=allocated_balance + state.total_pnl,
                        total_trades=state.total_trades,
                        total_pnl=state.total_pnl,
                        exposure=state.exposure,
                        win_rate=win_rate,
                        active_positions=len(state.open_positions),
                    ))
                    
                    # Push agent features to feature store
                    if self._feature_store:
                        try:
                            asyncio.create_task(self._feature_store.push_agent_features(
                                agent_id=state.id,
                                timestamp=timestamp,
                                total_trades=state.total_trades,
                                total_pnl=state.total_pnl,
                                exposure=state.exposure,
                                equity=allocated_balance + state.total_pnl,
                                win_rate=win_rate,
                                active_positions=len(state.open_positions),
                            ))
                        except Exception as e:
                            logger.debug(f"Failed to push agent features to feature store: {e}")
                    
                    # Write position snapshots
                    for symbol, pos in state.open_positions.items():
                        asyncio.create_task(self._storage.insert_position(
                            timestamp=timestamp,
                            symbol=symbol,
                            agent_id=state.id,
                            side=pos.get("side", "LONG"),
                            size=float(pos.get("size", 0) or 0),
                            entry_price=float(pos.get("entry_price", 0) or 0),
                            current_price=float(pos.get("current_price", 0) or 0),
                            notional=float(pos.get("notional", 0) or 0),
                            unrealized_pnl=float(pos.get("pnl", 0) or 0),
                            unrealized_pnl_pct=float(pos.get("pnl_percent", 0) or 0),
                            leverage=pos.get("leverage"),
                            status="open",
                        ))
                        
                        # Stream position to BigQuery
                        if self._bigquery:
                            try:
                                asyncio.create_task(self._bigquery.stream_position(
                                    timestamp=timestamp,
                                    symbol=symbol,
                                    agent_id=state.id,
                                    side=pos.get("side", "LONG"),
                                    size=float(pos.get("size", 0) or 0),
                                    entry_price=float(pos.get("entry_price", 0) or 0),
                                    current_price=float(pos.get("current_price", 0) or 0),
                                    notional=float(pos.get("notional", 0) or 0),
                                    unrealized_pnl=float(pos.get("pnl", 0) or 0),
                                    unrealized_pnl_pct=float(pos.get("pnl_percent", 0) or 0),
                                    leverage=pos.get("leverage"),
                                    status="open",
                                ))
                            except Exception as e:
                                logger.debug(f"Failed to stream position to BigQuery: {e}")
                    
                    # Stream agent performance to BigQuery
                    if self._bigquery:
                        try:
                            asyncio.create_task(self._bigquery.stream_agent_performance(
                                timestamp=timestamp,
                                agent_id=state.id,
                                equity=allocated_balance + state.total_pnl,
                                total_trades=state.total_trades,
                                total_pnl=state.total_pnl,
                                exposure=state.exposure,
                                win_rate=win_rate,
                                active_positions=len(state.open_positions),
                            ))
                        except Exception as e:
                            logger.debug(f"Failed to stream agent performance to BigQuery: {e}")
                except Exception as e:
                    logger.warning(f"Failed to write agent performance to storage: {e}")

    def _serialize_agents(self) -> List[Dict[str, Any]]:
        agents: List[Dict[str, Any]] = []
        logger.info(f"Serializing {len(self._agent_states)} agents: {list(self._agent_states.keys())}")
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
                    "personality": state.personality,
                    "total_pnl": round(state.total_pnl, 2),
                    "exposure": round(state.exposure, 2),
                    "margin_allocation": round(state.margin_allocation, 2),
                    "total_trades": state.total_trades,
                    "win_rate": round(win_rate, 2),
                    "last_trade": state.last_trade.isoformat() if state.last_trade else None,
                    "positions": open_positions,
                    # Dynamic agent configurations
                    "dynamic_position_sizing": state.dynamic_position_sizing,
                    "adaptive_leverage": state.adaptive_leverage,
                    "intelligence_tp_sl": state.intelligence_tp_sl,
                    "max_leverage_limit": state.max_leverage_limit,
                    "min_position_size_pct": state.min_position_size_pct,
                    "max_position_size_pct": state.max_position_size_pct,
                    "risk_tolerance": state.risk_tolerance,
                    "time_horizon": state.time_horizon,
                    "market_regime_preference": state.market_regime_preference,
                    "performance": [
                        {"timestamp": ts.isoformat(), "equity": round(value, 2)}
                        for ts, value in list(state.equity_curve)
                    ],
                }
            )

        return agents

    async def _register_trade_event(
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

        if agent_id:
            self._symbol_to_agent[symbol.upper()] = agent_id

        # Write to persistent storage
        if self._storage:
            try:
                await self._storage.insert_trade(
                    timestamp=timestamp_value,
                    symbol=symbol,
                    side=side,
                    price=price,
                    quantity=quantity,
                    notional=notional,
                    agent_id=agent_id,
                    agent_model=agent_model,
                    strategy=metadata.get("strategy") if metadata else None,
                    order_id=metadata.get("order_id") if metadata else None,
                    execution_id=metadata.get("execution_id") if metadata else None,
                    fee=metadata.get("fee") if metadata else None,
                    slippage_bps=metadata.get("slippage_bps") if metadata else None,
                    metadata=metadata,
                )
            except Exception as e:
                logger.warning(f"Failed to write trade to storage: {e}")

        if agent_id and agent_id in self._agent_states:
            updated_exposure = self._calculate_agent_exposure(agent_id)
            self._agent_states[agent_id].exposure = updated_exposure
            self._get_agent_margin_remaining(agent_id)

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

                if position_size > 0 and not self._has_agent_margin(request.bot_id, position_size):
                    RISK_LIMITS_BREACHED.labels(limit_type="agent_margin").inc()
                    logger.info(
                        "Agent %s margin exhausted for LLM trade request (size %.2f)",
                        request.bot_id,
                        position_size,
                    )
                    return

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
                        await self._register_trade_event(
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
            # Send agent reasoning to Telegram if available
            if self._telegram and request.reasoning:
                reasoning_text = ' '.join([str(slice.get('content', '')) for slice in request.reasoning[:2]])
                if reasoning_text:
                    await self._telegram.send_mcp_notification(
                        message_type="REASONING",
                        sender_id=request.bot_id or "Agent",
                        content=reasoning_text[:200],
                        payload={"rationale": reasoning_text}
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

    async def _monitor_and_close_positions(self, market: Dict[str, MarketSnapshot]) -> None:
        """Monitor existing positions with advanced risk management."""
        current_time = datetime.utcnow()
        
        for symbol, position in list(self._portfolio.positions.items()):
            if position.notional == 0:
                continue
                
            snapshot = market.get(symbol)
            if not snapshot:
                continue
                
            current_price = snapshot.price
            entry_price = position.entry_price
            if entry_price <= 0:
                continue
                
            # Calculate P&L
            is_long = position.notional > 0
            if is_long:
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                pnl_abs = current_price - entry_price
            else:
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
                pnl_abs = entry_price - current_price
            
            # Get or calculate ATR for dynamic stops
            atr = await self._get_atr(symbol, market)
            
            # Dynamic take profit and stop loss based on ATR
            atr_multiplier = self._settings.atr_multiplier if hasattr(self._settings, 'atr_multiplier') else 1.5
            dynamic_tp = atr * 2.0 / entry_price * 100  # 2x ATR for TP
            dynamic_sl = -atr * atr_multiplier / entry_price * 100  # 1.5x ATR for SL
            
            # Use the more conservative of fixed % or ATR-based
            take_profit_pct = min(2.0, dynamic_tp)
            stop_loss_pct = max(-1.0, dynamic_sl)
            
            # Trailing stop logic
            trailing_activated = getattr(position, 'trailing_activated', False)
            highest_pnl = getattr(position, 'highest_pnl', pnl_pct)
            
            if pnl_pct >= 1.0 and not trailing_activated:  # Activate at 1% profit
                position.trailing_activated = True
                position.highest_pnl = pnl_pct
                logger.info(f"Trailing stop activated for {symbol} at {pnl_pct:.2f}%")
            
            if trailing_activated:
                position.highest_pnl = max(position.highest_pnl, pnl_pct)
                trailing_stop = position.highest_pnl - 0.5  # Trail by 0.5%
                
                if pnl_pct <= trailing_stop:
                    await self._close_position_direct(
                        symbol, 
                        f"Trailing stop hit: {pnl_pct:.2f}% (peak: {position.highest_pnl:.2f}%)", 
                        pnl_pct
                    )
                    continue
            
            # Partial position closing
            partial_close_targets = [1.0, 2.0]  # Close 50% at 1%, 25% at 2%
            for i, target in enumerate(partial_close_targets):
                if pnl_pct >= target:
                    partial_key = f"partial_closed_{i}"
                    if not getattr(position, partial_key, False):
                        partial_pct = 0.5 if i == 0 else 0.25
                        await self._close_partial_position(
                            symbol, 
                            partial_pct,
                            f"Partial close {partial_pct*100}% at {pnl_pct:.2f}% profit"
                        )
                        setattr(position, partial_key, True)
            
            # Time decay - reduce position size over time
            position_age = (current_time - position.entry_time).total_seconds() / 3600  # Hours
            if position_age > 24:  # Positions older than 24 hours
                decay_factor = min(position_age / 24 * 0.1, 0.5)  # Max 50% reduction
                if not getattr(position, 'time_decayed', False):
                    await self._close_partial_position(
                        symbol,
                        decay_factor,
                        f"Time decay: reducing {decay_factor*100:.0f}% after {position_age:.0f} hours"
                    )
                    position.time_decayed = True
            
            # Force close after max time
            if position_age > 48:  # 48 hour maximum
                await self._close_position_direct(
                    symbol,
                    f"Max time limit reached: {position_age:.0f} hours (P&L: {pnl_pct:.2f}%)",
                    pnl_pct
                )
                continue
            
            # Standard take profit/stop loss
            if pnl_pct >= take_profit_pct or pnl_pct <= stop_loss_pct:
                await self._close_position_direct(
                    symbol, 
                    f"{'Take profit' if pnl_pct > 0 else 'Stop loss'} hit: {pnl_pct:.2f}%", 
                    pnl_pct
                )
    
    def _construct_rl_state(self, symbol: str, market_data: MarketSnapshot, 
                           historical_data: pd.DataFrame) -> np.ndarray:
        """Construct state vector for RL models."""
        import numpy as np
        
        # Calculate features from historical data
        returns = historical_data['close'].pct_change().fillna(0)
        
        # Features: returns, volume, volatility, trend, etc.
        state = np.array([
            market_data.change_24h / 100,  # Normalized 24h change
            market_data.volume / 1e6,       # Volume in millions
            returns.mean(),                 # Mean return
            returns.std(),                  # Volatility
            returns.iloc[-1],              # Latest return
            returns.iloc[-5:].mean(),      # 5-period mean
            float(returns.iloc[-1] > 0),   # Momentum direction
            float(market_data.price > historical_data['close'].mean()),  # Above MA
            0.5,  # Placeholder
            0.5   # Placeholder
        ])
        
        return state[:10]  # Ensure correct size
    
    async def _get_atr(self, symbol: str, market: Dict[str, MarketSnapshot]) -> float:
        """Calculate or fetch ATR for a symbol with caching."""
        # Check cache first
        if self._cache:
            cached_atr = await self._cache.get_atr(symbol, 14)
            if cached_atr is not None:
                return cached_atr
                
        try:
            # Try to get from historical data
            historical = await self._fetch_historical_klines(symbol, "1h", 14)
            if historical is not None and len(historical) >= 14:
                # Calculate ATR
                high_low = historical['high'] - historical['low']
                high_close = abs(historical['high'] - historical['close'].shift(1))
                low_close = abs(historical['low'] - historical['close'].shift(1))
                
                import pandas as pd
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.rolling(window=14).mean().iloc[-1]
                atr_value = float(atr)
                
                # Cache the ATR
                if self._cache:
                    await self._cache.set_atr(symbol, 14, atr_value)
                    
                return atr_value
        except Exception as e:
            logger.debug(f"Failed to calculate ATR for {symbol}: {e}")
        
        # Fallback: use 2% of current price
        return market[symbol].price * 0.02
    
    async def _close_partial_position(self, symbol: str, fraction: float, reason: str) -> None:
        """Close a fraction of an existing position."""
        try:
            position = self._portfolio.positions.get(symbol)
            if not position or position.notional == 0:
                return
                
            # Calculate partial close quantity
            close_quantity = abs(position.quantity) * fraction
            remaining_quantity = abs(position.quantity) - close_quantity
            
            if close_quantity < 0.001:  # Too small to close
                return
                
            # Determine closing side
            close_side = "SELL" if position.notional > 0 else "BUY"
            
            # Create order for partial close
            order_params = {
                "symbol": symbol,
                "side": close_side,
                "order_type": OrderType.MARKET,
                "quantity": round(close_quantity, 8),
            }
            
            logger.info(f"Partial closing {symbol}: {reason}")

            # Execute the order
            result = await self._exchange.place_order(**order_params)
            
            if result:
                # Update position with remaining quantity
                position.quantity = remaining_quantity if position.notional > 0 else -remaining_quantity
                position.notional = position.notional * (1 - fraction)
                
                # Send notification
                if self._telegram:
                    await self._telegram.send_message(
                        f"⚡ **Partial Position Close**\n"
                        f"Symbol: {symbol}\n"
                        f"Closed: {fraction*100:.0f}%\n"
                        f"Reason: {reason}\n"
                        f"Remaining: {remaining_quantity:.8f}"
                    )
        except Exception as e:
            logger.error(f"Failed to partially close {symbol}: {e}")
    
    async def _close_position_direct(self, symbol: str, reason: str, pnl_pct: float) -> None:
        """Close position directly via exchange API without orchestrator."""
        try:
            position = self._portfolio.positions.get(symbol)
            if not position or position.notional == 0:
                return
                
            # Determine closing side (opposite of current position)
            close_side = "SELL" if position.notional > 0 else "BUY"
            close_quantity = abs(position.quantity)
            
            # Create order directly with exchange
            order_params = {
                "symbol": symbol,
                "side": close_side,
                "order_type": OrderType.MARKET,
                "quantity": close_quantity,
            }

            logger.info(f"Closing {symbol} position: {reason}")

            # Execute the order
            result = await self._exchange.place_order(**order_params)
            
            if result:
                # Update strategy performance
                if hasattr(self, '_strategy_selector'):
                    # Find which strategy opened this position
                    strategy_name = getattr(position, 'strategy', 'momentum')
                    self._strategy_selector.update_performance(strategy_name, pnl_pct / 100)
                    
                    # Update RL models with reward if applicable
                    if self._strategy_selector.rl_manager and strategy_name in ['ml_dqn', 'ml_ppo']:
                        # Construct current state
                        try:
                            historical = await self._fetch_historical_klines(symbol, "1h", 20)
                            if historical is not None:
                                # Need current market data - fetch it
                                tickers = await self._exchange.ticker(symbol)
                                current_price = float(tickers.get("lastPrice", 0))
                                volume = float(tickers.get("volume", 0))
                                change_24h = float(tickers.get("priceChangePercent", 0))
                                
                                market_snapshot = MarketSnapshot(
                                    symbol=symbol,
                                    price=current_price,
                                    volume=volume,
                                    change_24h=change_24h
                                )
                                state = self._construct_rl_state(symbol, market_snapshot, historical)
                                reward = pnl_pct / 100  # Normalize reward
                                
                                agent_type = 'dqn' if strategy_name == 'ml_dqn' else 'ppo'
                                await self._strategy_selector.rl_manager.update_with_reward(
                                    symbol, agent_type, reward, state, done=True
                                )
                        except Exception as e:
                            logger.debug(f"Failed to update RL model: {e}")
                
                # Update local portfolio state
                self._portfolio.positions.pop(symbol, None)
                
                # Send notification
                if self._telegram:
                    emoji = "✅" if pnl_pct > 0 else "🛑"
                    await self._telegram.send_message(
                        f"{emoji} **Position Closed**\n"
                        f"Symbol: {symbol}\n"
                        f"Reason: {reason}\n"
                        f"P&L: {pnl_pct:.2f}%"
                    )
                    
                # Log the trade event
                await self._register_trade_event(
                    symbol=symbol,
                    side=close_side,
                    price=result.get("price", 0.0),
                    notional=abs(position.notional),
                    quantity=close_quantity,
                    metadata={"source": "auto_close", "reason": reason},
                )
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}")

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
            await self._register_trade_event(
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
        await self._register_trade_event(
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
        if balance > self._peak_balance:
            self._peak_balance = balance
        drawdown = 0.0
        if self._peak_balance > 0:
            drawdown = max((self._peak_balance - balance) / self._peak_balance, 0.0)
        PORTFOLIO_DRAWDOWN.set(drawdown)

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

    # Agent Management Methods
    async def enable_agent(self, agent_id: str) -> bool:
        """Enable a specific agent for autonomous trading."""
        if agent_id in [agent["id"] for agent in AGENT_DEFINITIONS]:
            if agent_id not in self._settings.enabled_agents:
                self._settings.enabled_agents.append(agent_id)
                # Reinitialize agents to include the newly enabled one
                await self._initialize_agents()
                logger.info(f"Enabled agent: {agent_id}")
                return True
        return False

    async def disable_agent(self, agent_id: str) -> bool:
        """Disable a specific agent from autonomous trading."""
        if agent_id in self._settings.enabled_agents:
            self._settings.enabled_agents.remove(agent_id)
            # Remove from active agents
            if agent_id in self._agent_states:
                del self._agent_states[agent_id]
            logger.info(f"Disabled agent: {agent_id}")
            return True
        return False

    def get_enabled_agents(self) -> List[str]:
        """Get list of currently enabled agent IDs."""
        return self._settings.enabled_agents.copy()

    def get_available_agents(self) -> List[Dict[str, Any]]:
        """Get list of all available agents with their configurations."""
        return AGENT_DEFINITIONS.copy()


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
