"""
LLM Trading Bots for Aster Vibe Trading Arena
6 AI models competing in live cryptocurrency trading.
"""

import asyncio
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from .llm_prompts import LLMPromptTemplates

logger = logging.getLogger(__name__)


class BotStatus(Enum):
    """Trading bot status."""
    INITIALIZING = "initializing"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class Position:
    """Trading position."""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0


@dataclass
class TradingDecision:
    """LLM trading decision."""
    action: str  # 'buy', 'sell', 'hold', 'close'
    symbol: str
    confidence: float
    position_size_percent: float = 2.0
    entry_price: float = 0.0
    stop_loss_percent: float = 1.0
    take_profit_percent: float = 3.0
    reasoning: str = ""
    key_factors: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BotPerformance:
    """Bot performance metrics."""
    bot_id: str
    bot_name: str
    starting_balance: float = 100.0
    current_balance: float = 100.0
    total_pnl: float = 0.0
    pnl_percent: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    current_positions: int = 0
    total_fees_paid: float = 0.0
    last_trade_time: Optional[datetime] = None
    
    def update_metrics(self):
        """Recalculate performance metrics."""
        self.pnl_percent = (self.total_pnl / self.starting_balance) * 100
        self.current_balance = self.starting_balance + self.total_pnl
        
        if self.total_trades > 0:
            self.win_rate = (self.winning_trades / self.total_trades) * 100
        
        if self.losing_trades > 0:
            self.profit_factor = abs(self.avg_win * self.winning_trades) / abs(self.avg_loss * self.losing_trades)


class BaseLLMTradingBot(ABC):
    """Base class for all LLM trading bots."""
    
    def __init__(
        self,
        bot_id: str,
        bot_name: str,
        model_name: str,
        api_key: str,
        starting_balance: float = 100.0,
        max_positions: int = 3,
        max_risk_per_trade: float = 2.0
    ):
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.model_name = model_name
        self.api_key = api_key
        self.starting_balance = starting_balance
        self.max_positions = max_positions
        self.max_risk_per_trade = max_risk_per_trade
        
        # Portfolio state
        self.positions: Dict[str, Position] = {}
        self.performance = BotPerformance(
            bot_id=bot_id,
            bot_name=bot_name,
            starting_balance=starting_balance,
            current_balance=starting_balance
        )
        
        # Status
        self.status = BotStatus.INITIALIZING
        self.last_decision: Optional[TradingDecision] = None
        self.decision_history: List[TradingDecision] = []
        
        # Rate limiting
        self.last_api_call: Optional[datetime] = None
        self.api_calls_count = 0
        self.tokens_used = 0
        self.api_cost = 0.0
        
        logger.info(f"Initialized {self.bot_name} ({self.bot_id})")
    
    @abstractmethod
    async def call_llm_api(self, prompt: str) -> str:
        """Call the specific LLM API. Must be implemented by each bot."""
        pass
    
    async def make_trading_decision(
        self,
        market_data: Dict[str, Any],
        leaderboard: List[Dict[str, Any]]
    ) -> Optional[TradingDecision]:
        """Generate a trading decision using the LLM."""
        try:
            # Check rate limits
            if not self._check_rate_limit():
                logger.warning(f"{self.bot_name}: Rate limit reached, skipping decision")
                return None
            
            # Prepare portfolio context
            portfolio = self._get_portfolio_context()
            
            # Create trading prompt
            prompt = LLMPromptTemplates.create_trading_prompt(
                model_name=self.model_name,
                market_data=market_data,
                portfolio=portfolio,
                leaderboard=leaderboard
            )
            
            # Call LLM API
            logger.info(f"{self.bot_name}: Requesting trading decision...")
            response = await self.call_llm_api(prompt)
            
            # Parse decision
            decision = self._parse_decision(response, market_data)
            
            if decision:
                self.last_decision = decision
                self.decision_history.append(decision)
                logger.info(
                    f"{self.bot_name}: Decision = {decision.action.upper()} {decision.symbol} "
                    f"(confidence: {decision.confidence:.2f})"
                )
            
            return decision
            
        except Exception as e:
            logger.error(f"{self.bot_name}: Error making decision: {e}")
            self.status = BotStatus.ERROR
            return None
    
    def _check_rate_limit(self) -> bool:
        """Check if we can make another API call."""
        if self.last_api_call is None:
            return True
        
        # Allow 1 call per minute (conservative)
        time_since_last = datetime.now() - self.last_api_call
        return time_since_last > timedelta(seconds=60)
    
    def _get_portfolio_context(self) -> Dict[str, Any]:
        """Get current portfolio state for prompt."""
        positions_list = []
        for pos in self.positions.values():
            positions_list.append({
                'symbol': pos.symbol,
                'side': pos.side,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'quantity': pos.quantity,
                'pnl': pos.pnl,
                'pnl_percent': pos.pnl_percent
            })
        
        return {
            'balance': self.performance.current_balance,
            'positions': positions_list,
            'total_pnl': self.performance.total_pnl,
            'win_rate': self.performance.win_rate
        }
    
    def _parse_decision(self, response: str, market_data: Dict[str, Any]) -> Optional[TradingDecision]:
        """Parse LLM response into TradingDecision."""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error(f"{self.bot_name}: No JSON found in response")
                return None
            
            json_str = response[json_start:json_end]
            data = json.loads(json_str)
            
            # Validate required fields
            if 'action' not in data or 'symbol' not in data:
                logger.error(f"{self.bot_name}: Missing required fields in decision")
                return None
            
            # Create decision object
            decision = TradingDecision(
                action=data.get('action', 'hold').lower(),
                symbol=data.get('symbol', market_data.get('symbol', 'UNKNOWN')),
                confidence=float(data.get('confidence', 0.5)),
                position_size_percent=float(data.get('position_size_percent', 2.0)),
                entry_price=float(data.get('entry_price', market_data.get('price', 0))),
                stop_loss_percent=float(data.get('stop_loss_percent', 1.0)),
                take_profit_percent=float(data.get('take_profit_percent', 3.0)),
                reasoning=data.get('reasoning', ''),
                key_factors=data.get('key_factors', []),
                timestamp=datetime.now()
            )
            
            # Validate decision
            if not self._validate_decision(decision):
                return None
            
            return decision
            
        except json.JSONDecodeError as e:
            logger.error(f"{self.bot_name}: Failed to parse JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"{self.bot_name}: Error parsing decision: {e}")
            return None
    
    def _validate_decision(self, decision: TradingDecision) -> bool:
        """Validate trading decision against rules."""
        # Check if we have room for more positions
        if decision.action in ['buy', 'sell'] and len(self.positions) >= self.max_positions:
            logger.warning(f"{self.bot_name}: Max positions reached, cannot open new position")
            return False
        
        # Check risk limits
        if decision.position_size_percent > self.max_risk_per_trade:
            logger.warning(
                f"{self.bot_name}: Position size {decision.position_size_percent}% exceeds "
                f"max risk {self.max_risk_per_trade}%"
            )
            return False
        
        # Check confidence threshold
        if decision.confidence < 0.3:
            logger.warning(f"{self.bot_name}: Confidence too low ({decision.confidence:.2f})")
            return False
        
        return True
    
    def update_position_prices(self, market_data: Dict[str, Any]):
        """Update current prices and P&L for all positions."""
        symbol = market_data.get('symbol')
        current_price = market_data.get('price', 0)
        
        for pos_key, pos in self.positions.items():
            if pos.symbol == symbol:
                pos.current_price = current_price
                
                # Calculate P&L
                if pos.side == 'long':
                    pos.pnl = (current_price - pos.entry_price) * pos.quantity
                else:  # short
                    pos.pnl = (pos.entry_price - current_price) * pos.quantity
                
                pos.pnl_percent = (pos.pnl / (pos.entry_price * pos.quantity)) * 100
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status and performance."""
        return {
            'bot_id': self.bot_id,
            'bot_name': self.bot_name,
            'model_name': self.model_name,
            'status': self.status.value,
            'performance': {
                'current_balance': self.performance.current_balance,
                'total_pnl': self.performance.total_pnl,
                'pnl_percent': self.performance.pnl_percent,
                'total_trades': self.performance.total_trades,
                'win_rate': self.performance.win_rate,
                'profit_factor': self.performance.profit_factor,
                'max_drawdown': self.performance.max_drawdown
            },
            'positions': len(self.positions),
            'api_calls': self.api_calls_count,
            'tokens_used': self.tokens_used,
            'api_cost': self.api_cost,
            'last_decision': {
                'action': self.last_decision.action if self.last_decision else None,
                'symbol': self.last_decision.symbol if self.last_decision else None,
                'confidence': self.last_decision.confidence if self.last_decision else None,
                'reasoning': self.last_decision.reasoning if self.last_decision else None
            } if self.last_decision else None
        }


# ============================================================================
# Concrete LLM Bot Implementations
# ============================================================================

class GPT5TradingBot(BaseLLMTradingBot):
    """OpenAI GPT-5 Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="gpt5",
            bot_name="GPT-5 Wizard",
            model_name="gpt5",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call OpenAI GPT-5 API."""
        try:
            import openai
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            client = openai.AsyncOpenAI(api_key=self.api_key)
            
            response = await client.chat.completions.create(
                model="gpt-4-turbo-preview",  # Will use gpt-5 when available
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            self.tokens_used += response.usage.total_tokens
            self.api_cost += (response.usage.total_tokens / 1000) * 0.01  # Estimate
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"GPT-5 API error: {e}")
            raise


class Gemini25ProTradingBot(BaseLLMTradingBot):
    """Google Gemini 2.5 Pro Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="gemini",
            bot_name="Gemini Twin Dragon",
            model_name="gemini",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call Google Gemini API."""
        try:
            import google.generativeai as genai
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-pro')
            
            response = await asyncio.to_thread(model.generate_content, prompt)
            
            self.tokens_used += len(prompt.split()) + len(response.text.split())
            self.api_cost += (self.tokens_used / 1000) * 0.005  # Estimate
            
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise


class Claude45SonnetTradingBot(BaseLLMTradingBot):
    """Anthropic Claude 4.5 Sonnet Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="claude",
            bot_name="Claude Scholar",
            model_name="claude",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        try:
            import anthropic
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",  # Will use 4.5 when available
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            self.tokens_used += response.usage.input_tokens + response.usage.output_tokens
            self.api_cost += ((response.usage.input_tokens / 1000) * 0.003 + 
                             (response.usage.output_tokens / 1000) * 0.015)
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            raise


class Grok4TradingBot(BaseLLMTradingBot):
    """xAI Grok 4 Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="grok",
            bot_name="Grok Rebel",
            model_name="grok",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call xAI Grok API."""
        try:
            # Note: Using OpenAI-compatible endpoint for Grok
            import openai
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://api.x.ai/v1"
            )
            
            response = await client.chat.completions.create(
                model="grok-beta",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,  # Higher temp for rebellious nature
                max_tokens=1000
            )
            
            self.tokens_used += response.usage.total_tokens
            self.api_cost += (response.usage.total_tokens / 1000) * 0.01
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Grok API error: {e}")
            raise


class DeepSeekTradingBot(BaseLLMTradingBot):
    """DeepSeek Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="deepseek",
            bot_name="DeepSeek Diver",
            model_name="deepseek",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call DeepSeek API."""
        try:
            import aiohttp
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7
                    }
                ) as response:
                    data = await response.json()
                    
                    self.tokens_used += data['usage']['total_tokens']
                    self.api_cost += (data['usage']['total_tokens'] / 1000) * 0.002
                    
                    return data['choices'][0]['message']['content']
            
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise


class QwenTradingBot(BaseLLMTradingBot):
    """Alibaba Qwen Trading Bot."""
    
    def __init__(self, api_key: str, **kwargs):
        super().__init__(
            bot_id="qwen",
            bot_name="Qwen Scholar",
            model_name="qwen",
            api_key=api_key,
            **kwargs
        )
    
    async def call_llm_api(self, prompt: str) -> str:
        """Call Qwen API."""
        try:
            import aiohttp
            
            self.last_api_call = datetime.now()
            self.api_calls_count += 1
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "qwen-max",
                        "input": {"messages": [{"role": "user", "content": prompt}]},
                        "parameters": {"temperature": 0.7}
                    }
                ) as response:
                    data = await response.json()
                    
                    self.tokens_used += data['usage']['total_tokens']
                    self.api_cost += (data['usage']['total_tokens'] / 1000) * 0.002
                    
                    return data['output']['text']
            
        except Exception as e:
            logger.error(f"Qwen API error: {e}")
            raise

