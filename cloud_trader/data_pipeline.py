"""Background data pipeline for archiving and maintaining historical data."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .config import Settings, get_settings
from .storage import TradingStorage, get_storage

logger = logging.getLogger(__name__)


class DataPipeline:
    """Background pipeline for archiving Redis streams and maintaining historical data."""
    
    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._storage: Optional[TradingStorage] = None
        self._redis: Optional[redis.Redis] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
        
        # Pipeline configuration
        self.archive_interval_seconds = 300  # Archive every 5 minutes
        self.batch_size = 1000  # Process in batches
        self.retention_days = 90  # Keep raw data for 90 days
    
    async def initialize(self) -> None:
        """Initialize pipeline connections."""
        # Initialize storage
        self._storage = await get_storage()
        
        # Initialize Redis if available
        if self._settings.redis_url:
            try:
                pool = ConnectionPool.from_url(
                    self._settings.redis_url,
                    max_connections=10,
                    decode_responses=False
                )
                self._redis = redis.Redis(connection_pool=pool)
                await self._redis.ping()
                logger.info("Data pipeline: Redis connected")
            except Exception as e:
                logger.warning(f"Data pipeline: Failed to connect to Redis: {e}")
    
    async def close(self) -> None:
        """Close pipeline connections."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self._redis:
            await self._redis.close()
        
        logger.info("Data pipeline closed")
    
    async def start(self) -> None:
        """Start the background pipeline task."""
        if self._running:
            logger.warning("Data pipeline already running")
            return
        
        await self.initialize()
        
        if not self._storage:
            logger.warning("Data pipeline: No storage available, pipeline disabled")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._pipeline_loop())
        logger.info("Data pipeline started")
    
    async def _pipeline_loop(self) -> None:
        """Main pipeline loop."""
        while self._running:
            try:
                # Archive Redis streams
                await self._archive_redis_streams()
                
                # Clean up old data (retention policy)
                await self._apply_retention_policy()
                
                # Wait before next iteration
                await asyncio.sleep(self.archive_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Data pipeline error: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def _archive_redis_streams(self) -> None:
        """Archive data from Redis streams to persistent storage."""
        if not self._redis or not self._storage:
            return
        
        try:
            streams = {
                "trader:decisions": "decision",
                "trader:positions": "position",
                "trader:reasoning": "reasoning",
            }
            
            for stream_name, stream_type in streams.items():
                try:
                    # Read new entries from stream
                    entries = await self._redis.xread(
                        {stream_name: "0"},
                        count=self.batch_size,
                        block=0
                    )
                    
                    if not entries:
                        continue
                    
                    # Process entries
                    for stream, messages in entries:
                        for msg_id, data in messages:
                            await self._process_stream_message(stream_type, data)
                    
                    logger.debug(f"Archived {len(entries)} entries from {stream_name}")
                except Exception as e:
                    logger.warning(f"Failed to archive stream {stream_name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to archive Redis streams: {e}")
    
    async def _process_stream_message(self, stream_type: str, data: Dict[bytes, bytes]) -> None:
        """Process a single stream message and write to storage."""
        if not self._storage:
            return
        
        try:
            # Decode message data
            payload_data = data.get(b"payload")
            if not payload_data:
                return
            
            payload = json.loads(payload_data)
            timestamp = datetime.fromisoformat(payload.get("timestamp", datetime.utcnow().isoformat()))
            
            if stream_type == "decision":
                # Store agent decision for training data
                await self._storage.insert_agent_decision(
                    timestamp=timestamp,
                    agent_id=payload.get("bot_id", "unknown"),
                    symbol=payload.get("symbol", ""),
                    decision=payload.get("action", "HOLD"),
                    confidence=payload.get("confidence"),
                    strategy=payload.get("strategy"),
                    state_features=payload.get("features"),
                    market_context=payload.get("context"),
                    executed=payload.get("executed", False),
                    metadata=payload,
                )
            elif stream_type == "position":
                # Store position snapshot
                await self._storage.insert_position(
                    timestamp=timestamp,
                    symbol=payload.get("symbol", ""),
                    agent_id=payload.get("bot_id"),
                    side=payload.get("side", "LONG"),
                    size=float(payload.get("size", 0) or 0),
                    entry_price=float(payload.get("entry_price", 0) or 0),
                    current_price=float(payload.get("current_price", 0) or 0),
                    notional=float(payload.get("notional", 0) or 0),
                    unrealized_pnl=float(payload.get("pnl", 0) or 0),
                    unrealized_pnl_pct=float(payload.get("pnl_percent", 0) or 0),
                    leverage=payload.get("leverage"),
                    status=payload.get("status", "open"),
                    metadata=payload,
                )
            elif stream_type == "reasoning":
                # Store reasoning for analysis
                # This could be stored in a separate reasoning table or as metadata
                logger.debug(f"Processing reasoning message for {payload.get('symbol')}")
        
        except Exception as e:
            logger.warning(f"Failed to process stream message: {e}")
    
    async def _apply_retention_policy(self) -> None:
        """Apply data retention policies to clean up old data."""
        # This would be implemented in the database layer with retention policies
        # For TimescaleDB, we can use continuous aggregates and retention policies
        logger.debug("Applying retention policies (would be implemented with database retention)")
    
    async def archive_trades_batch(self, trades: List[Dict[str, Any]]) -> int:
        """Archive a batch of trades to storage."""
        if not self._storage:
            return 0
        
        archived = 0
        for trade in trades:
            try:
                await self._storage.insert_trade(
                    timestamp=datetime.fromisoformat(trade.get("timestamp", datetime.utcnow().isoformat())),
                    symbol=trade.get("symbol", ""),
                    side=trade.get("side", "BUY"),
                    price=float(trade.get("price", 0) or 0),
                    quantity=float(trade.get("quantity", 0) or 0),
                    notional=float(trade.get("notional", 0) or 0),
                    agent_id=trade.get("agent_id"),
                    agent_model=trade.get("model"),
                    strategy=trade.get("strategy"),
                    metadata=trade,
                )
                archived += 1
            except Exception as e:
                logger.warning(f"Failed to archive trade: {e}")
        
        return archived


# Global pipeline instance
_pipeline: Optional[DataPipeline] = None


async def get_pipeline() -> DataPipeline:
    """Get or create pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = DataPipeline()
        await _pipeline.initialize()
    return _pipeline


async def close_pipeline() -> None:
    """Close pipeline connection."""
    global _pipeline
    if _pipeline:
        await _pipeline.close()
        _pipeline = None

