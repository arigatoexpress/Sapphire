"""
Database migration for advanced data infrastructure.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, BigInteger, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class MarketCandle(Base):
    __tablename__ = 'market_candles'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False) # 1m, 5m, 1h, 1d
    timestamp = Column(BigInteger, nullable=False) # Unix ms
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('symbol', 'interval', 'timestamp', name='uix_candle'),
        Index('idx_candle_lookup', 'symbol', 'interval', 'timestamp'),
    )

class TechnicalIndicator(Base):
    __tablename__ = 'technical_indicators'
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    interval = Column(String, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    indicator_name = Column(String, nullable=False) # RSI, MACD, BB_UPPER
    value = Column(Float, nullable=False)
    metadata = Column(JSON, nullable=True) # Additional params used

    __table_args__ = (
        Index('idx_ta_lookup', 'symbol', 'interval', 'timestamp', 'indicator_name'),
    )

class TradeHistory(Base):
    __tablename__ = 'trade_history_detailed'
    
    id = Column(Integer, primary_key=True)
    exchange_trade_id = Column(String, nullable=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    fee = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    agent_id = Column(String, nullable=False)
    strategy_name = Column(String, nullable=True)
    timestamp = Column(BigInteger, nullable=False)
    
    # Context at time of trade
    market_context = Column(JSON, nullable=True) # Price, Volatility, etc.
    agent_reasoning = Column(String, nullable=True)

class AgentLearning(Base):
    __tablename__ = 'agent_learning'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(String, nullable=False)
    timestamp = Column(BigInteger, nullable=False)
    intervention_type = Column(String, nullable=False) # TUNE, BOOST, COOLDOWN
    parameters_before = Column(JSON, nullable=False)
    parameters_after = Column(JSON, nullable=False)
    outcome_metric = Column(String, nullable=True) # Win Rate, PnL
    outcome_value = Column(Float, nullable=True)
    notes = Column(String, nullable=True)

