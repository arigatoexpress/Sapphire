#!/usr/bin/env python3
"""
Pair Trading Signal Interpreter
Converts pair chart signals (ETHBTC) into actionable trades on individual assets
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class PairSignal(Enum):
    """Types of pair trading signals"""
    ETH_OVERVALUED = "eth_overvalued"      # ETHBTC high - sell ETH or buy BTC
    ETH_UNDERVALUED = "eth_undervalued"    # ETHBTC low - buy ETH or sell BTC
    SOL_OVERVALUED = "sol_overvalued"      # SOLBTC high - sell SOL or buy BTC
    SOL_UNDERVALUED = "sol_undervalued"    # SOLBTC low - buy SOL or sell BTC
    NEUTRAL = "neutral"


@dataclass
class TradeRecommendation:
    """Recommended trade based on pair signal"""
    primary_action: str  # "buy" or "sell"
    primary_symbol: str  # The main symbol to trade
    secondary_action: Optional[str]  # Hedge action (optional)
    secondary_symbol: Optional[str]
    confidence: float
    reasoning: str


# Tradable symbols on Lighter
TRADABLE_SYMBOLS = {
    'ETH': {'type': 'perp', 'max_leverage': 10},
    'BTC': {'type': 'perp', 'max_leverage': 10},
    'SOL': {'type': 'perp', 'max_leverage': 10},
    'HYPE': {'type': 'spot', 'max_leverage': 1},
}

# Pair analysis symbols (for TradingView charts)
PAIR_SYMBOLS = {
    'ETHBTC': {
        'base': 'ETH',
        'quote': 'BTC',
        'description': 'ETH vs BTC relative strength'
    },
    'SOLBTC': {
        'base': 'SOL', 
        'quote': 'BTC',
        'description': 'SOL vs BTC relative strength'
    },
    'ZECBTC': {
        'base': 'ZEC',
        'quote': 'BTC', 
        'description': 'ZEC vs BTC relative strength'
    }
}


def interpret_pair_signal(pair_symbol: str, z_score: float, side: str) -> TradeRecommendation:
    """
    Interpret a pair trading signal and convert to individual asset trade
    
    Args:
        pair_symbol: e.g., "ETHBTC"
        z_score: Current Z-score of the pair
        side: Signal side (buy/sell on the pair chart)
    
    Returns:
        TradeRecommendation for individual asset
    """
    pair = pair_symbol.upper()
    
    if pair not in PAIR_SYMBOLS:
        # Not a pair - treat as direct trade
        return TradeRecommendation(
            primary_action=side.lower(),
            primary_symbol=pair,
            secondary_action=None,
            secondary_symbol=None,
            confidence=0.7,
            reasoning=f"Direct {side} signal on {pair}"
        )
    
    pair_info = PAIR_SYMBOLS[pair]
    base = pair_info['base']  # e.g., ETH
    quote = pair_info['quote']  # e.g., BTC
    
    # Interpret the pair signal
    if side.lower() == 'buy':
        # Buy signal on pair = expect pair to go up
        # This means base (ETH) is undervalued or quote (BTC) is overvalued
        if z_score < -2.0:
            # Strong mean reversion signal - ETH very undervalued
            return TradeRecommendation(
                primary_action="buy",
                primary_symbol=base,
                secondary_action=None,
                secondary_symbol=None,
                confidence=min(abs(z_score) / 3.0, 0.95),
                reasoning=f"{base} significantly undervalued vs {quote} (Z: {z_score:.2f}). Buying {base} for mean reversion."
            )
        else:
            # Moderate signal
            return TradeRecommendation(
                primary_action="buy",
                primary_symbol=base,
                secondary_action=None,
                secondary_symbol=None,
                confidence=0.6,
                reasoning=f"{base} showing strength vs {quote}. Buying {base}."
            )
    
    else:  # sell signal
        # Sell signal on pair = expect pair to go down
        # This means base (ETH) is overvalued or quote (BTC) is undervalued
        if z_score > 2.0:
            # Strong mean reversion signal - ETH very overvalued
            return TradeRecommendation(
                primary_action="sell",
                primary_symbol=base,
                secondary_action=None,
                secondary_symbol=None,
                confidence=min(z_score / 3.0, 0.95),
                reasoning=f"{base} significantly overvalued vs {quote} (Z: {z_score:.2f}). Selling {base} for mean reversion."
            )
        else:
            return TradeRecommendation(
                primary_action="sell",
                primary_symbol=base,
                secondary_action=None,
                secondary_symbol=None,
                confidence=0.6,
                reasoning=f"{base} showing weakness vs {quote}. Selling {base}."
            )


def get_tradable_symbol(pair_signal: str) -> str:
    """
    Convert pair analysis symbol to tradable symbol
    
    Examples:
        ETHBTC -> ETH (trade ETH-PERP)
        SOLBTC -> SOL (trade SOL-PERP)
        BTCUSDT -> BTC (trade BTC-PERP)
    """
    pair = pair_signal.upper()
    
    # Check if it's a pair symbol
    if pair in PAIR_SYMBOLS:
        # Return the base asset (the one we actually trade)
        return PAIR_SYMBOLS[pair]['base']
    
    # Check if it's already a tradable symbol
    for symbol in TRADABLE_SYMBOLS.keys():
        if pair.startswith(symbol):
            return symbol
    
    # Default: return as-is
    return pair


def validate_trade_symbol(symbol: str) -> Tuple[bool, str, str]:
    """
    Validate that a symbol is tradable
    
    Returns:
        (is_valid, tradable_symbol, message)
    """
    sym = symbol.upper()
    
    # Direct tradable symbol
    if sym in TRADABLE_SYMBOLS:
        return True, sym, f"{sym} is tradable"
    
    # Check if it's a pair
    if sym in PAIR_SYMBOLS:
        base = PAIR_SYMBOLS[sym]['base']
        return True, base, f"{sym} is pair analysis → trading {base}"
    
    # Check with USDT suffix
    if sym + 'USDT' in ['ETHUSDT', 'BTCUSDT', 'SOLUSDT', 'HYPEUSDT']:
        return True, sym, f"Trading {sym}-PERP"
    
    return False, sym, f"{sym} is not a recognized tradable symbol"


# Updated favorite symbols configuration
FAVORITE_TRADABLE_SYMBOLS = {
    # Direct tradable assets
    'ETH': {
        'name': 'Ethereum',
        'type': 'perp',
        'description': 'ETH-PERP perpetual futures',
        'tradingview_symbol': 'BINANCE:ETHUSDT',
        'category': 'major',
        'min_confidence': 0.70
    },
    'BTC': {
        'name': 'Bitcoin',
        'type': 'perp', 
        'description': 'BTC-PERP perpetual futures',
        'tradingview_symbol': 'BINANCE:BTCUSDT',
        'category': 'major',
        'min_confidence': 0.70
    },
    'SOL': {
        'name': 'Solana',
        'type': 'perp',
        'description': 'SOL-PERP perpetual futures',
        'tradingview_symbol': 'BINANCE:SOLUSDT',
        'category': 'alt',
        'min_confidence': 0.75
    },
    'HYPE': {
        'name': 'Hyperliquid',
        'type': 'spot',
        'description': 'HYPE spot trading',
        'tradingview_symbol': 'BINANCE:HYPEUSDT',
        'category': 'alt',
        'min_confidence': 0.75
    },
}

# Pair analysis symbols (for charting only, not direct trading)
PAIR_ANALYSIS_SYMBOLS = {
    'ETHBTC': {
        'name': 'ETH/BTC Ratio',
        'type': 'pair_analysis',
        'description': 'Relative strength of ETH vs BTC',
        'tradingview_symbol': 'BINANCE:ETHBTC',
        'tradable_base': 'ETH',
        'tradable_quote': 'BTC',
        'strategy': 'When Z < -2.0: Buy ETH. When Z > 2.0: Sell ETH'
    },
    'SOLBTC': {
        'name': 'SOL/BTC Ratio',
        'type': 'pair_analysis',
        'description': 'Relative strength of SOL vs BTC',
        'tradingview_symbol': 'BINANCE:SOLBTC',
        'tradable_base': 'SOL',
        'tradable_quote': 'BTC',
        'strategy': 'When Z < -2.0: Buy SOL. When Z > 2.0: Sell SOL'
    },
    'ZECBTC': {
        'name': 'ZEC/BTC Ratio',
        'type': 'pair_analysis',
        'description': 'Relative strength of ZEC vs BTC',
        'tradingview_symbol': 'BINANCE:ZECBTC',
        'tradable_base': 'ZEC',  # Not available on Lighter, for analysis only
        'tradable_quote': 'BTC',
        'strategy': 'Analysis only - ZEC not tradable on Lighter'
    }
}


def get_all_symbols() -> list:
    """Get list of all tradable symbols"""
    return list(FAVORITE_TRADABLE_SYMBOLS.keys())


def get_all_pairs() -> list:
    """Get list of pair analysis symbols"""
    return list(PAIR_ANALYSIS_SYMBOLS.keys())


def get_symbol_info(symbol: str) -> dict:
    """Get info for any symbol (tradable or pair)"""
    sym = symbol.upper()
    
    if sym in FAVORITE_TRADABLE_SYMBOLS:
        info = FAVORITE_TRADABLE_SYMBOLS[sym].copy()
        info['tradable'] = True
        return info
    
    if sym in PAIR_ANALYSIS_SYMBOLS:
        info = PAIR_ANALYSIS_SYMBOLS[sym].copy()
        info['tradable'] = False
        info['tradable_alternative'] = PAIR_ANALYSIS_SYMBOLS[sym]['tradable_base']
        return info
    
    return {'tradable': False, 'error': 'Unknown symbol'}


if __name__ == '__main__':
    # Test
    print("Pair Trading Logic Test:")
    print("=" * 60)
    
    test_cases = [
        ('ETHBTC', -2.5, 'buy'),   # ETH undervalued - should buy ETH
        ('ETHBTC', 2.5, 'sell'),   # ETH overvalued - should sell ETH
        ('SOLBTC', -2.2, 'buy'),   # SOL undervalued - should buy SOL
        ('ETH', 0, 'buy'),         # Direct trade
    ]
    
    for pair, z, side in test_cases:
        rec = interpret_pair_signal(pair, z, side)
        print(f"\n{pair} Z={z:.2f} {side.upper()}:")
        print(f"  → {rec.primary_action.upper()} {rec.primary_symbol}")
        print(f"  Confidence: {rec.confidence:.0%}")
        print(f"  Reason: {rec.reasoning}")
    
    print("\n" + "=" * 60)
    print("\nSymbol Validation:")
    for sym in ['ETH', 'BTC', 'ETHBTC', 'SOLBTC', 'UNKNOWN']:
        valid, tradable, msg = validate_trade_symbol(sym)
        print(f"  {sym}: {'✅' if valid else '❌'} {tradable} - {msg}")
