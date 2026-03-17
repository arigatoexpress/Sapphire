"""
LLM Arena Orchestrator
Coordinates 6 LLM trading bots competing in the Aster Vibe Trading Arena.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field

from .llm_trading_bots import (
    BaseLLMTradingBot,
    GPT5TradingBot,
    Gemini25ProTradingBot,
    Claude45SonnetTradingBot,
    Grok4TradingBot,
    DeepSeekTradingBot,
    QwenTradingBot,
    Position,
    TradingDecision,
    BotStatus
)

logger = logging.getLogger(__name__)


@dataclass
class BattleEvent:
    """Battle event for visualization."""
    event_type: str  # 'attack', 'critical_hit', 'dodge', 'ko', 'victory'
    attacker_id: str
    attacker_name: str
    defender_id: str
    defender_name: str
    symbol: str
    damage: float  # P&L change
    timestamp: datetime = field(default_factory=datetime.now)
    description: str = ""


@dataclass
class ArenaConfig:
    """Configuration for the trading arena."""
    starting_balance_per_bot: float = 100.0
    trading_interval_seconds: int = 300  # 5 minutes
    max_positions_per_bot: int = 3
    max_risk_per_trade: float = 2.0
    enable_battle_events: bool = True
    battle_threshold_percent: float = 1.0  # Trigger battle at 1% lead
    
    # API Keys
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    xai_api_key: str = ""
    deepseek_api_key: str = ""
    alibaba_api_key: str = ""
    
    # Aster API
    aster_api_key: str = ""
    aster_api_secret: str = ""


class LLMArenaOrchestrator:
    """Orchestrates 6 LLM trading bots in competitive arena."""
    
    def __init__(self, config: ArenaConfig):
        self.config = config
        self.bots: Dict[str, BaseLLMTradingBot] = {}
        self.battle_events: List[BattleEvent] = []
        self.is_running = False
        self.current_cycle = 0
        
        # Performance tracking
        self.leaderboard: List[Dict[str, Any]] = []
        self.last_rankings: Dict[str, int] = {}
        
        # Market data cache
        self.market_data_cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info("LLM Arena Orchestrator initialized")
    
    async def initialize(self):
        """Initialize all 6 trading bots and test Aster API connection."""
        logger.info("Initializing 6 LLM trading bots...")
        
        try:
            # Test Aster API connection first
            if self.config.aster_api_key and self.config.aster_api_secret:
                logger.info("Testing Aster API connection...")
                try:
                    from ..execution.aster_client import AsterClient
                    
                    async with AsterClient(
                        self.config.aster_api_key,
                        self.config.aster_api_secret
                    ) as aster_client:
                        # Test connectivity
                        connected = await aster_client.test_connectivity()
                        if connected:
                            logger.info("✅ Aster API connection successful")
                            
                            # Get account info
                            account_info = await aster_client.get_account_info()
                            logger.info(
                                f"📊 Aster Account: Balance = ${account_info.total_balance:.2f}, "
                                f"Available = ${account_info.available_balance:.2f}"
                            )
                        else:
                            logger.warning("⚠️  Aster API connectivity test failed, will use simulation mode")
                            
                except Exception as e:
                    logger.warning(f"⚠️  Aster API connection failed: {e}. Will use simulation mode.")
            else:
                logger.info("ℹ️  Aster API credentials not configured, using simulation mode")
            
            # Initialize GPT-5
            self.bots['gpt5'] = GPT5TradingBot(
                api_key=self.config.openai_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Initialize Gemini 2.5 Pro
            self.bots['gemini'] = Gemini25ProTradingBot(
                api_key=self.config.google_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Initialize Claude 4.5 Sonnet
            self.bots['claude'] = Claude45SonnetTradingBot(
                api_key=self.config.anthropic_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Initialize Grok 4
            self.bots['grok'] = Grok4TradingBot(
                api_key=self.config.xai_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Initialize DeepSeek
            self.bots['deepseek'] = DeepSeekTradingBot(
                api_key=self.config.deepseek_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Initialize Qwen
            self.bots['qwen'] = QwenTradingBot(
                api_key=self.config.alibaba_api_key,
                starting_balance=self.config.starting_balance_per_bot,
                max_positions=self.config.max_positions_per_bot,
                max_risk_per_trade=self.config.max_risk_per_trade
            )
            
            # Set all bots to active
            for bot in self.bots.values():
                bot.status = BotStatus.ACTIVE
            
            logger.info(f"Successfully initialized {len(self.bots)} trading bots")
            
        except Exception as e:
            logger.error(f"Failed to initialize bots: {e}")
            raise
    
    async def start_arena(self):
        """Start the trading arena main loop."""
        logger.info("🏟️  Starting Aster Vibe Trading Arena!")
        self.is_running = True
        
        try:
            while self.is_running:
                self.current_cycle += 1
                logger.info(f"\n{'='*60}")
                logger.info(f"🔄 Arena Cycle #{self.current_cycle}")
                logger.info(f"{'='*60}\n")
                
                # Execute trading cycle
                await self._execute_trading_cycle()
                
                # Update leaderboard
                self._update_leaderboard()
                
                # Check for battle events
                if self.config.enable_battle_events:
                    await self._check_battle_events()
                
                # Log cycle results
                self._log_cycle_results()
                
                # Wait for next cycle
                await asyncio.sleep(self.config.trading_interval_seconds)
                
        except Exception as e:
            logger.error(f"Arena error: {e}")
            self.is_running = False
            raise
    
    async def stop_arena(self):
        """Stop the trading arena."""
        logger.info("Stopping arena...")
        self.is_running = False
    
    async def _execute_trading_cycle(self):
        """Execute one trading cycle for all bots."""
        try:
            # Fetch market data for all symbols
            await self._fetch_market_data()
            
            # Update all bot positions with current prices
            self._update_all_positions()
            
            # Get current leaderboard for context
            leaderboard_context = self._get_leaderboard_context()
            
            # Execute trading decisions for all bots in parallel
            tasks = []
            for symbol in self.market_data_cache.keys():
                market_data = self.market_data_cache[symbol]
                
                for bot in self.bots.values():
                    if bot.status == BotStatus.ACTIVE:
                        task = self._execute_bot_decision(bot, market_data, leaderboard_context)
                        tasks.append(task)
            
            # Wait for all decisions
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log results
            successful = sum(1 for r in results if not isinstance(r, Exception))
            logger.info(f"✅ Executed {successful}/{len(tasks)} bot decisions")
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {e}")
    
    async def _execute_bot_decision(
        self,
        bot: BaseLLMTradingBot,
        market_data: Dict[str, Any],
        leaderboard: List[Dict[str, Any]]
    ):
        """Execute trading decision for a single bot."""
        try:
            # Get bot's trading decision
            decision = await bot.make_trading_decision(market_data, leaderboard)
            
            if decision and decision.action != 'hold':
                # Execute trade via Aster API
                await self._execute_trade(bot, decision, market_data)
            
        except Exception as e:
            logger.error(f"Error executing decision for {bot.bot_name}: {e}")
    
    async def _fetch_market_data(self):
        """Fetch market data for trading pairs."""
        symbols = ['SOLUSDT', 'SUIUSDT', 'DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT']
        
        # Try to fetch from actual Aster API if configured
        if self.config.aster_api_key and self.config.aster_api_secret:
            try:
                from ..execution.aster_client import AsterClient
                
                async with AsterClient(
                    self.config.aster_api_key,
                    self.config.aster_api_secret
                ) as aster_client:
                    for symbol in symbols:
                        try:
                            # Get 24hr ticker data
                            ticker = await aster_client.get_24hr_ticker(symbol)
                            
                            self.market_data_cache[symbol] = {
                                'symbol': symbol,
                                'price': float(ticker.get('lastPrice', 0)),
                                'change_24h': float(ticker.get('priceChangePercent', 0)),
                                'volume_24h': float(ticker.get('volume', 0)),
                                'high_24h': float(ticker.get('highPrice', 0)),
                                'low_24h': float(ticker.get('lowPrice', 0)),
                                # Technical indicators would be calculated from klines
                                'rsi': 50.0,  # TODO: Calculate from klines
                                'macd': 0.0,
                                'macd_signal': 0.0,
                                'bb_upper': float(ticker.get('highPrice', 0)),
                                'bb_lower': float(ticker.get('lowPrice', 0)),
                                'bid_depth': 0,  # TODO: Get from order book
                                'ask_depth': 0
                            }
                        except Exception as e:
                            logger.warning(f"Failed to fetch {symbol} from Aster API: {e}")
                            # Fall back to mock data
                            self._set_mock_market_data(symbol)
            except Exception as e:
                logger.error(f"Aster API connection failed: {e}. Using mock data.")
                self._use_mock_market_data(symbols)
        else:
            logger.info("Aster API credentials not configured, using mock data")
            self._use_mock_market_data(symbols)
    
    def _use_mock_market_data(self, symbols):
        """Use mock market data when Aster API is unavailable."""
        for symbol in symbols:
            self._set_mock_market_data(symbol)
    
    def _set_mock_market_data(self, symbol):
        """Set mock market data for a symbol."""
        import random
        base_price = {'SOLUSDT': 50.0, 'SUIUSDT': 1.2, 'DOGEUSDT': 0.08, 
                     'SHIBUSDT': 0.000015, 'PEPEUSDT': 0.0000012}.get(symbol, 50.0)
        
        self.market_data_cache[symbol] = {
            'symbol': symbol,
            'price': base_price * (1 + random.uniform(-0.02, 0.02)),
            'change_24h': random.uniform(-5, 5),
            'volume_24h': random.randint(500000, 2000000),
            'rsi': random.uniform(30, 70),
            'macd': random.uniform(-1, 1),
            'macd_signal': random.uniform(-1, 1),
            'bb_upper': base_price * 1.02,
            'bb_lower': base_price * 0.98,
            'bid_depth': random.randint(300000, 700000),
            'ask_depth': random.randint(300000, 700000)
        }
    
    def _update_all_positions(self):
        """Update current prices for all bot positions."""
        for bot in self.bots.values():
            for symbol, market_data in self.market_data_cache.items():
                bot.update_position_prices(market_data)
            
            # Update performance metrics
            bot.performance.update_metrics()
    
    async def _execute_trade(
        self,
        bot: BaseLLMTradingBot,
        decision: TradingDecision,
        market_data: Dict[str, Any]
    ):
        """Execute trade via Aster API."""
        try:
            logger.info(
                f"💎 {bot.bot_name}: {decision.action.upper()} {decision.symbol} "
                f"@ ${decision.entry_price:.6f}"
            )
            
            # Calculate position size
            position_value = (bot.performance.current_balance * decision.position_size_percent / 100)
            quantity = position_value / decision.entry_price
            
            # Try to execute on Aster API if configured
            aster_order_placed = False
            if self.config.aster_api_key and self.config.aster_api_secret:
                try:
                    from ..execution.aster_client import AsterClient, OrderRequest, OrderType, Side
                    
                    async with AsterClient(
                        self.config.aster_api_key,
                        self.config.aster_api_secret
                    ) as aster_client:
                        if decision.action in ['buy', 'sell']:
                            # Place order on Aster
                            order_request = OrderRequest(
                                symbol=decision.symbol,
                                side=Side.BUY if decision.action == 'buy' else Side.SELL,
                                order_type=OrderType.MARKET,
                                quantity=quantity,
                                client_order_id=f"{bot.bot_id}_{decision.symbol}_{int(datetime.now().timestamp())}"
                            )
                            
                            response = await aster_client.place_order(order_request)
                            logger.info(f"✅ Aster order placed: {response.order_id}")
                            aster_order_placed = True
                            
                            # Use actual fill price if available
                            if hasattr(response, 'avg_price') and response.avg_price:
                                decision.entry_price = float(response.avg_price)
                        
                except Exception as e:
                    logger.warning(f"Aster API order failed, using simulation: {e}")
            
            if decision.action in ['buy', 'sell']:
                # Create new position (simulated or real)
                position = Position(
                    symbol=decision.symbol,
                    side='long' if decision.action == 'buy' else 'short',
                    entry_price=decision.entry_price,
                    quantity=quantity,
                    entry_time=datetime.now(),
                    stop_loss=decision.entry_price * (1 - decision.stop_loss_percent / 100),
                    take_profit=decision.entry_price * (1 + decision.take_profit_percent / 100),
                    current_price=decision.entry_price
                )
                
                # Add to bot's positions
                pos_key = f"{decision.symbol}_{datetime.now().timestamp()}"
                bot.positions[pos_key] = position
                
                # Update performance
                bot.performance.total_trades += 1
                bot.performance.last_trade_time = datetime.now()
                
            elif decision.action == 'close':
                # Close existing position
                for pos_key, pos in list(bot.positions.items()):
                    if pos.symbol == decision.symbol:
                        # Try to close on Aster if it was a real trade
                        if aster_order_placed and self.config.aster_api_key:
                            try:
                                from ..execution.aster_client import AsterClient, OrderRequest, OrderType, Side
                                
                                async with AsterClient(
                                    self.config.aster_api_key,
                                    self.config.aster_api_secret
                                ) as aster_client:
                                    # Place closing order
                                    close_order = OrderRequest(
                                        symbol=decision.symbol,
                                        side=Side.SELL if pos.side == 'long' else Side.BUY,
                                        order_type=OrderType.MARKET,
                                        quantity=pos.quantity,
                                        client_order_id=f"{bot.bot_id}_close_{decision.symbol}_{int(datetime.now().timestamp())}"
                                    )
                                    await aster_client.place_order(close_order)
                            except Exception as e:
                                logger.warning(f"Aster close order failed: {e}")
                        
                        # Record trade result
                        if pos.pnl > 0:
                            bot.performance.winning_trades += 1
                            bot.performance.avg_win = (
                                (bot.performance.avg_win * (bot.performance.winning_trades - 1) + pos.pnl)
                                / bot.performance.winning_trades
                            )
                        else:
                            bot.performance.losing_trades += 1
                            bot.performance.avg_loss = (
                                (bot.performance.avg_loss * (bot.performance.losing_trades - 1) + pos.pnl)
                                / bot.performance.losing_trades
                            )
                        
                        bot.performance.total_pnl += pos.pnl
                        del bot.positions[pos_key]
                        
                        logger.info(
                            f"✅ {bot.bot_name}: Closed {pos.symbol} "
                            f"| P&L: ${pos.pnl:+.2f} ({pos.pnl_percent:+.2f}%)"
                        )
            
            # Update metrics
            bot.performance.update_metrics()
            
        except Exception as e:
            logger.error(f"Failed to execute trade for {bot.bot_name}: {e}")
    
    def _update_leaderboard(self):
        """Update performance leaderboard."""
        self.leaderboard = []
        
        for bot in self.bots.values():
            self.leaderboard.append({
                'bot_id': bot.bot_id,
                'name': bot.bot_name,
                'balance': bot.performance.current_balance,
                'pnl': bot.performance.total_pnl,
                'pnl_percent': bot.performance.pnl_percent,
                'total_trades': bot.performance.total_trades,
                'win_rate': bot.performance.win_rate,
                'profit_factor': bot.performance.profit_factor,
                'positions': len(bot.positions)
            })
        
        # Sort by P&L percentage
        self.leaderboard.sort(key=lambda x: x['pnl_percent'], reverse=True)
        
        # Track ranking changes
        new_rankings = {bot['bot_id']: i for i, bot in enumerate(self.leaderboard)}
        self.last_rankings = new_rankings
    
    def _get_leaderboard_context(self) -> List[Dict[str, Any]]:
        """Get leaderboard context for bot prompts."""
        return self.leaderboard
    
    async def _check_battle_events(self):
        """Check for battle events between bots."""
        if len(self.leaderboard) < 2:
            return
        
        # Compare top 2 bots
        leader = self.leaderboard[0]
        runner_up = self.leaderboard[1]
        
        pnl_diff = leader['pnl_percent'] - runner_up['pnl_percent']
        
        # Trigger attack event if lead > threshold
        if pnl_diff > self.config.battle_threshold_percent:
            event = BattleEvent(
                event_type='attack',
                attacker_id=leader['bot_id'],
                attacker_name=leader['name'],
                defender_id=runner_up['bot_id'],
                defender_name=runner_up['name'],
                symbol='ARENA',
                damage=pnl_diff,
                description=f"{leader['name']} strikes with {pnl_diff:.2f}% advantage!"
            )
            self.battle_events.append(event)
            logger.info(f"⚔️  {event.description}")
        
        # Check for critical hit (>5% lead)
        if pnl_diff > 5.0:
            event = BattleEvent(
                event_type='critical_hit',
                attacker_id=leader['bot_id'],
                attacker_name=leader['name'],
                defender_id=runner_up['bot_id'],
                defender_name=runner_up['name'],
                symbol='ARENA',
                damage=pnl_diff,
                description=f"💥 CRITICAL HIT! {leader['name']} dominates with {pnl_diff:.2f}% lead!"
            )
            self.battle_events.append(event)
            logger.info(f"💥 {event.description}")
        
        # Check for KO (any bot below -10%)
        for bot_data in self.leaderboard:
            if bot_data['pnl_percent'] < -10.0:
                event = BattleEvent(
                    event_type='ko',
                    attacker_id=leader['bot_id'],
                    attacker_name=leader['name'],
                    defender_id=bot_data['bot_id'],
                    defender_name=bot_data['name'],
                    symbol='ARENA',
                    damage=abs(bot_data['pnl_percent']),
                    description=f"☠️  K.O.! {bot_data['name']} is down {abs(bot_data['pnl_percent']):.2f}%!"
                )
                self.battle_events.append(event)
                logger.info(f"☠️  {event.description}")
    
    def _log_cycle_results(self):
        """Log results of current cycle."""
        logger.info("\n📊 LEADERBOARD:")
        logger.info("=" * 80)
        
        for i, bot_data in enumerate(self.leaderboard, 1):
            rank_symbol = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            logger.info(
                f"{rank_symbol} {bot_data['name']:<20} | "
                f"Balance: ${bot_data['balance']:>7.2f} | "
                f"P&L: {bot_data['pnl_percent']:>+6.2f}% | "
                f"Trades: {bot_data['total_trades']:>3} | "
                f"WR: {bot_data['win_rate']:>5.1f}% | "
                f"Positions: {bot_data['positions']}"
            )
        
        logger.info("=" * 80 + "\n")
    
    def get_arena_status(self) -> Dict[str, Any]:
        """Get current arena status."""
        return {
            'is_running': self.is_running,
            'current_cycle': self.current_cycle,
            'total_bots': len(self.bots),
            'active_bots': sum(1 for b in self.bots.values() if b.status == BotStatus.ACTIVE),
            'leaderboard': self.leaderboard,
            'recent_battle_events': self.battle_events[-10:],  # Last 10 events
            'bots': {bot_id: bot.get_status() for bot_id, bot in self.bots.items()}
        }
    
    def get_bot_status(self, bot_id: str) -> Optional[Dict[str, Any]]:
        """Get status of specific bot."""
        bot = self.bots.get(bot_id)
        if bot:
            return bot.get_status()
        return None
    
    def get_battle_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent battle events."""
        events = self.battle_events[-limit:]
        return [
            {
                'event_type': e.event_type,
                'attacker': e.attacker_name,
                'defender': e.defender_name,
                'symbol': e.symbol,
                'damage': e.damage,
                'description': e.description,
                'timestamp': e.timestamp.isoformat()
            }
            for e in events
        ]

