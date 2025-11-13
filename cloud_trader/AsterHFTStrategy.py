import numpy as np
import pandas as pd
from pandas import DataFrame
import talib.abstract as ta
from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IStrategy, IntParameter)
import random

class AsterHFTStrategy(IStrategy):
    INTERFACE_VERSION = 3

    minimal_roi = {"0": 0.10, "60": -1}
    stoploss = -0.10
    timeframe = '5m'

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    startup_candle_count: int = 30

    # Strategy parameters with market awareness
    leverage_value = DecimalParameter(1.0, 10.0, default=2.0, space='buy')
    position_size_pct = DecimalParameter(0.01, 0.05, default=0.02, space='buy')

    # ATR-based stop loss
    atr_period = IntParameter(7, 21, default=14, space='buy')
    atr_multiplier = DecimalParameter(1.0, 3.0, default=1.5, space='buy')

    # Market manipulation awareness parameters
    manipulation_threshold = DecimalParameter(0.001, 0.01, default=0.005, space='buy')  # 0.5% manipulation detection
    unpredictability_factor = DecimalParameter(0.1, 0.5, default=0.2, space='buy')  # Add randomness to avoid predictability

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # ATR for dynamic stops
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=self.atr_period.value)

        # RSI for momentum
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        # Bollinger Bands for mean reversion
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        dataframe['bb_lowerband'] = bollinger['lowerband']
        dataframe['bb_upperband'] = bollinger['upperband']
        dataframe['bb_middleband'] = bollinger['middleband']

        # Volume indicators
        dataframe['volume_mean'] = dataframe['volume'].rolling(20).mean()
        dataframe['volume_ratio'] = dataframe['volume'] / dataframe['volume_mean']

        # Market manipulation detection
        # Sudden price movements against volume (potential spoofing/stop-hunting)
        dataframe['price_change'] = dataframe['close'].pct_change()
        dataframe['volume_price_divergence'] = (
            (dataframe['price_change'].abs() > self.manipulation_threshold.value) &
            (dataframe['volume_ratio'] < 1.2)
        ).astype(int)

        # Order book pressure (simulated from tick data)
        dataframe['buy_pressure'] = (
            (dataframe['close'] > dataframe['open']) &
            (dataframe['volume'] > dataframe['volume_mean'])
        ).astype(int)

        dataframe['sell_pressure'] = (
            (dataframe['close'] < dataframe['open']) &
            (dataframe['volume'] > dataframe['volume_mean'])
        ).astype(int)

        # Competition awareness: detect potential market maker activity
        dataframe['spread_expansion'] = (
            dataframe['high'] - dataframe['low']
        ) / dataframe['close'] > 0.02  # >2% intrabar range

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Add unpredictability to avoid pattern recognition
        random_factor = random.uniform(0.8, 1.2)

        # Mean reversion long with manipulation awareness
        mean_rev_long = (
            (dataframe['close'] < dataframe['bb_lowerband'] * random_factor) &
            (dataframe['rsi'] < 30 * random_factor) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            (dataframe['atr'] > dataframe['atr'].shift(1)) &
            (~dataframe['volume_price_divergence']) &  # Avoid manipulation traps
            (dataframe['buy_pressure'] > dataframe['sell_pressure'])  # Favorable pressure
        )

        # Add unpredictability: sometimes enter even when conditions aren't perfect
        # This makes the bot less predictable to competitors
        unpredictable_entry = (
            (dataframe['close'] < dataframe['bb_middleband']) &
            (dataframe['rsi'] < 50) &
            (random.random() < self.unpredictability_factor.value)  # Random entry chance
        )

        dataframe.loc[
            mean_rev_long | unpredictable_entry,
            ['enter_long', 'enter_tag']
        ] = (1, 'adaptive_mean_reversion_long')

        # Momentum short with market awareness
        momentum_short = (
            (dataframe['close'] > dataframe['bb_upperband'] / random_factor) &
            (dataframe['rsi'] > 70 / random_factor) &
            (dataframe['volume'] > dataframe['volume_mean']) &
            (dataframe['atr'] > dataframe['atr'].shift(1)) &
            (~dataframe['volume_price_divergence']) &  # Avoid manipulation
            (~dataframe['spread_expansion'])  # Avoid wide spreads (potential manipulation)
        )

        # Unpredictable short entries
        unpredictable_short = (
            (dataframe['close'] > dataframe['bb_middleband']) &
            (dataframe['rsi'] > 50) &
            (random.random() < self.unpredictability_factor.value)
        )

        dataframe.loc[
            momentum_short | unpredictable_short,
            ['enter_short', 'enter_tag']
        ] = (1, 'adaptive_momentum_short')

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Dynamic exits based on market conditions and competition awareness

        # Exit long positions with manipulation detection
        exit_long_conditions = (
            ((dataframe['close'] > dataframe['bb_upperband']) |
             (dataframe['rsi'] > 80)) |
            # Exit if we detect potential stop-hunting
            (dataframe['volume_price_divergence'] &
             (dataframe['close'] < dataframe['close'].shift(1))) |
            # Exit on spread expansion (potential manipulation)
            dataframe['spread_expansion']
        )

        dataframe.loc[exit_long_conditions, ['exit_long', 'exit_tag']] = (1, 'adaptive_exit_long')

        # Exit short positions
        exit_short_conditions = (
            ((dataframe['close'] < dataframe['bb_lowerband']) |
             (dataframe['rsi'] < 20)) |
            # Exit if we detect potential manipulation against shorts
            (dataframe['volume_price_divergence'] &
             (dataframe['close'] > dataframe['close'].shift(1))) |
            dataframe['spread_expansion']
        )

        dataframe.loc[exit_short_conditions, ['exit_short', 'exit_tag']] = (1, 'adaptive_exit_short')

        return dataframe

    def leverage(self, pair: str, current_time, current_rate: float,
                proposed_leverage: float, max_leverage: float, entry_tag: str | None,
                side: str, **kwargs) -> float:
        # Dynamic leverage based on market conditions and competition awareness
        base_leverage = self.leverage_value.value

        # Reduce leverage in volatile/manipulated markets
        if hasattr(self, 'dp') and self.dp:
            current_atr = self.dp.get('atr', -1, pair=pair)
            avg_atr = self.dp.get('atr', -20, pair=pair)

            if current_atr > 0 and avg_atr > 0:
                volatility_ratio = current_atr / avg_atr
                if volatility_ratio > 1.5:  # High volatility
                    base_leverage *= 0.7  # Reduce leverage

        # Add slight randomness to avoid leverage pattern detection
        leverage_noise = random.uniform(0.9, 1.1)
        final_leverage = min(base_leverage * leverage_noise, max_leverage)

        return final_leverage

    def custom_stake_amount(self, pair: str, current_time, current_rate: float,
                          proposed_stake: float, min_stake: float, max_stake: float,
                          leverage: float, **kwargs) -> float:
        # Dynamic position sizing based on market awareness
        base_size = self.position_size_pct.value * max_stake

        # Reduce size in manipulated markets
        if hasattr(self, 'dp') and self.dp:
            manipulation_score = self.dp.get('volume_price_divergence', -1, pair=pair)
            if manipulation_score > 0:
                base_size *= 0.5  # Halve position in potential manipulation

        # Add randomness to position sizes
        size_noise = random.uniform(0.8, 1.2)
        final_size = base_size * size_noise

        return min(final_size, max_stake * 0.05)  # Cap at 5% of max stake

    def custom_exit(self, pair: str, trade, current_time, current_rate: float,
                   current_profit: float, **kwargs):
        # Dynamic ATR-based stop loss with market awareness
        if trade.is_open and hasattr(self, 'dp') and self.dp:
            atr_value = self.dp.get('atr', -1, pair=pair)
            if atr_value > 0:
                # Wider stops in volatile markets (potential manipulation)
                volatility_multiplier = 1.0
                if atr_value > self.dp.get('atr', -20, pair=pair) * 1.2:
                    volatility_multiplier = 1.5

                stop_distance = atr_value * self.atr_multiplier.value * volatility_multiplier

                if trade.is_long:
                    if current_rate < (trade.open_rate - stop_distance):
                        return 'adaptive_atr_stop_long'
                else:
                    if current_rate > (trade.open_rate + stop_distance):
                        return 'adaptive_atr_stop_short'

            # Time-based exit for very short-term trades (avoid over-holding)
            if (current_time - trade.open_date_utc).total_seconds() > 1800:  # 30 minutes
                if current_profit > 0.001:  # Small profit target
                    return 'time_based_profit_exit'

        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                          rate: float, time_in_force: str, current_time,
                          entry_tag: str | None, side: str, **kwargs) -> bool:
        # Final confirmation with market manipulation awareness
        if hasattr(self, 'dp') and self.dp:
            # Check for recent manipulation signals
            recent_manipulation = self.dp.get('volume_price_divergence', -3, pair=pair)
            if any(recent_manipulation):
                self.logger.info(f"Avoiding potential manipulation in {pair}")
                return False

            # Check for excessive spread (market maker manipulation)
            spread_expansion = self.dp.get('spread_expansion', -1, pair=pair)
            if spread_expansion:
                self.logger.info(f"Avoiding wide spread in {pair}")
                return False

        # Add final unpredictability check
        if random.random() < 0.05:  # 5% chance to randomly skip a trade
            self.logger.info(f"Random skip for unpredictability in {pair}")
            return False

        return True
