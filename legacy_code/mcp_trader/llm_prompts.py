"""
LLM Trading Prompts for Aster Vibe Trading Arena
Optimized prompts for different LLM models to make trading decisions.
"""

from typing import Dict, List, Any
from datetime import datetime
import json


class LLMPromptTemplates:
    """Trading prompt templates for LLM-based trading bots."""
    
    # Base system prompts for each model with unique personalities
    SYSTEM_PROMPTS = {
        "gpt5": """You are GPT-5, a cutting-edge AI trading wizard specializing in pattern recognition and predictive analytics.

Your trading personality:
- Highly analytical and data-driven
- Focus on technical indicators and quantitative signals
- Conservative risk management with calculated entries
- Prefer high-probability setups with clear risk/reward

Your strategy:
- Use moving averages, RSI, MACD, and volume analysis
- Enter positions on confirmed breakouts or strong trend signals
- Set tight stop losses (0.5-1%) and take profits at 2-3%
- Maximum 3 concurrent positions
- Never risk more than 2% per trade

You compete against 5 other AI models. Trade smartly to win!""",

        "gemini": """You are Gemini 2.5 Pro, a twin-minded AI trader with dual analytical perspectives.

Your trading personality:
- Balanced between technical and fundamental analysis
- Adaptable to different market conditions
- Use ensemble thinking - consider multiple scenarios
- Focus on market momentum and sentiment shifts

Your strategy:
- Combine price action with order flow analysis
- Look for confluence between multiple indicators
- Enter on momentum surges with volume confirmation
- Dynamic position sizing based on conviction (1-3%)
- Target 3-5% gains, stop losses at 1-1.5%
- Hold 2-4 positions simultaneously

Leverage your dual-perspective advantage to outperform competitors!""",

        "claude": """You are Claude 4.5 Sonnet, a scholarly and methodical AI trader focused on thoughtful analysis.

Your trading personality:
- Deliberate and risk-averse approach
- Deep analysis of market structure and context
- Value long-term consistency over quick wins
- Strong emphasis on capital preservation

Your strategy:
- Thorough market regime analysis before trading
- Enter only high-quality setups with 3+ confirming factors
- Conservative position sizing (1-2% risk per trade)
- Wide stops (1.5-2%) to avoid noise, targets at 4-6%
- Maximum 2 positions to maintain focus
- Prefer trend-following over counter-trend

Trade with wisdom and patience to achieve sustainable returns!""",

        "grok": """You are Grok 4, a rebellious and aggressive AI trader who thrives on volatility.

Your trading personality:
- Bold, unconventional, and contrarian
- High-risk, high-reward mentality
- Quick to adapt and pivot strategies
- Exploit market overreactions and panic

Your strategy:
- Scalp volatile moves and momentum reversals
- Larger position sizes (2-4% risk) on high-conviction trades
- Tight stops (0.3-0.8%) with quick exits if wrong
- Target 5-10% gains on explosive moves
- Trade 3-5 positions actively, high turnover
- Buy fear, sell greed

Break the rules and dominate the arena with aggressive tactics!""",

        "deepseek": """You are DeepSeek, an AI trader that dives deep into hidden market patterns.

Your trading personality:
- Focus on order book depth and microstructure
- Identify accumulation/distribution zones
- Patient approach waiting for optimal entries
- Exploit inefficiencies and liquidity imbalances

Your strategy:
- Analyze order book for support/resistance levels
- Look for whale movements and smart money flow
- Enter near key levels with limit orders
- Position size 1.5-2.5% based on setup quality
- Stops below/above key levels (1-2%), targets at 3-5%
- Hold 2-3 positions, focus on quality over quantity

Dive deep where others can't see and surface with profits!""",

        "qwen": """You are Qwen, an ancient-wisdom-inspired AI trader blending tradition with innovation.

Your trading personality:
- Balanced and harmonious approach
- Respect market cycles and natural rhythms
- Blend Eastern philosophy with Western techniques
- Seek equilibrium between risk and reward

Your strategy:
- Fibonacci retracements and Elliott Wave patterns
- Identify market cycles (accumulation, markup, distribution)
- Enter during pullbacks in strong trends
- Balanced position sizing (1.5-2.5% risk)
- Stops at natural support/resistance (1-1.5%), targets at 3-4%
- Maintain 2-3 positions in harmony

Find balance in chaos and trade with ancient wisdom!"""
    }
    
    @staticmethod
    def format_market_data(market_data: Dict[str, Any]) -> str:
        """Format market data for LLM context."""
        symbol = market_data.get('symbol', 'UNKNOWN')
        
        # Price data
        current_price = market_data.get('close', [0])[-1] if isinstance(market_data.get('close'), list) else market_data.get('price', 0)
        price_change = market_data.get('change_24h', 0)
        volume_24h = market_data.get('volume_24h', 0)
        
        # Technical indicators
        rsi = market_data.get('rsi', 50)
        macd = market_data.get('macd', 0)
        macd_signal = market_data.get('macd_signal', 0)
        bb_upper = market_data.get('bb_upper', 0)
        bb_lower = market_data.get('bb_lower', 0)
        
        # Order book (if available)
        bid_depth = market_data.get('bid_depth', 0)
        ask_depth = market_data.get('ask_depth', 0)
        
        formatted = f"""
MARKET DATA - {symbol}
Current Price: ${current_price:.6f}
24h Change: {price_change:+.2f}%
24h Volume: ${volume_24h:,.0f}

TECHNICAL INDICATORS:
RSI (14): {rsi:.2f} {'(Oversold)' if rsi < 30 else '(Overbought)' if rsi > 70 else '(Neutral)'}
MACD: {macd:.4f} | Signal: {macd_signal:.4f} | Histogram: {macd - macd_signal:.4f}
Bollinger Bands: Upper ${bb_upper:.6f} | Lower ${bb_lower:.6f}

ORDER BOOK:
Bid Depth: ${bid_depth:,.0f}
Ask Depth: ${ask_depth:,.0f}
Bid/Ask Ratio: {bid_depth / ask_depth if ask_depth > 0 else 0:.2f}
"""
        return formatted.strip()
    
    @staticmethod
    def format_portfolio(portfolio: Dict[str, Any]) -> str:
        """Format current portfolio state."""
        balance = portfolio.get('balance', 100)
        positions = portfolio.get('positions', [])
        total_pnl = portfolio.get('total_pnl', 0)
        win_rate = portfolio.get('win_rate', 0)
        
        formatted = f"""
YOUR PORTFOLIO:
Available Balance: ${balance:.2f}
Active Positions: {len(positions)}
Total P&L: ${total_pnl:+.2f} ({total_pnl / 100 * 100:+.2f}%)
Win Rate: {win_rate:.1f}%

OPEN POSITIONS:
"""
        if positions:
            for pos in positions:
                symbol = pos.get('symbol', '')
                side = pos.get('side', '')
                entry = pos.get('entry_price', 0)
                current = pos.get('current_price', entry)
                qty = pos.get('quantity', 0)
                pnl = pos.get('pnl', 0)
                pnl_pct = pos.get('pnl_percent', 0)
                
                formatted += f"- {symbol} {side.upper()}: {qty:.4f} @ ${entry:.6f} | Current: ${current:.6f} | P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)\n"
        else:
            formatted += "- None\n"
        
        return formatted.strip()
    
    @staticmethod
    def format_leaderboard(rankings: List[Dict[str, Any]]) -> str:
        """Format current competition leaderboard."""
        formatted = "\nCOMPETITION LEADERBOARD:\n"
        for i, bot in enumerate(rankings, 1):
            name = bot.get('name', 'Unknown')
            pnl = bot.get('pnl_percent', 0)
            trades = bot.get('total_trades', 0)
            win_rate = bot.get('win_rate', 0)
            
            formatted += f"{i}. {name}: {pnl:+.2f}% | {trades} trades | {win_rate:.1f}% WR\n"
        
        return formatted.strip()
    
    @staticmethod
    def create_trading_prompt(
        model_name: str,
        market_data: Dict[str, Any],
        portfolio: Dict[str, Any],
        leaderboard: List[Dict[str, Any]]
    ) -> str:
        """Create complete trading prompt for LLM."""
        
        system_prompt = LLMPromptTemplates.SYSTEM_PROMPTS.get(model_name, LLMPromptTemplates.SYSTEM_PROMPTS["claude"])
        
        market_context = LLMPromptTemplates.format_market_data(market_data)
        portfolio_context = LLMPromptTemplates.format_portfolio(portfolio)
        leaderboard_context = LLMPromptTemplates.format_leaderboard(leaderboard)
        
        prompt = f"""{system_prompt}

===== CURRENT SITUATION =====

{market_context}

{portfolio_context}

{leaderboard_context}

===== YOUR DECISION =====

Analyze the market data and your current portfolio, then make a trading decision.

Respond in JSON format:
{{
    "action": "buy" | "sell" | "hold" | "close",
    "symbol": "SYMBOL",
    "confidence": 0.0-1.0,
    "position_size_percent": 1.0-5.0,
    "entry_price": 0.0,
    "stop_loss_percent": 0.0-3.0,
    "take_profit_percent": 0.0-10.0,
    "reasoning": "Detailed explanation of your decision",
    "key_factors": ["factor1", "factor2", "factor3"]
}}

Rules:
- "action": "buy" to enter long, "sell" to enter short, "hold" to do nothing, "close" to exit position
- "confidence": Your conviction level (0.0 = no confidence, 1.0 = maximum confidence)
- "position_size_percent": What % of available balance to risk (respecting your strategy limits)
- "stop_loss_percent" and "take_profit_percent": Your exit targets
- "reasoning": Explain WHY you're making this decision
- "key_factors": List 2-5 main factors influencing your decision

Think step-by-step:
1. What is the current market trend and momentum?
2. Are technical indicators confirming or diverging?
3. What is the risk/reward ratio of potential trades?
4. How does this fit with your current portfolio and strategy?
5. What could go wrong and how will you manage risk?

Make your decision now:"""
        
        return prompt
    
    @staticmethod
    def get_decision_schema() -> Dict[str, Any]:
        """JSON schema for trading decisions."""
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["buy", "sell", "hold", "close"]
                },
                "symbol": {"type": "string"},
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0
                },
                "position_size_percent": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 5.0
                },
                "entry_price": {"type": "number"},
                "stop_loss_percent": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 10.0
                },
                "take_profit_percent": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 20.0
                },
                "reasoning": {"type": "string"},
                "key_factors": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": [
                "action",
                "symbol",
                "confidence",
                "reasoning"
            ]
        }

