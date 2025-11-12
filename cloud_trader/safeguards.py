"""Trading safeguards including circuit breakers, heat limits, and kill switches."""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .config import Settings
from .risk import PortfolioState

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerState:
    """Circuit breaker state tracking."""
    service_name: str
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    is_open: bool = False
    opened_at: Optional[datetime] = None
    half_open_attempts: int = 0


@dataclass
class HeatMetrics:
    """Portfolio heat and risk metrics."""
    total_exposure: float = 0.0
    position_count: int = 0
    daily_loss: float = 0.0
    max_drawdown: float = 0.0
    last_updated: datetime = field(default_factory=datetime.utcnow)


class CircuitBreaker:
    """Circuit breaker pattern for API and trading failures."""
    
    def __init__(self, name: str, failure_threshold: int = 3, 
                 timeout_seconds: int = 60, half_open_max: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max = half_open_max
        self.state = CircuitBreakerState(service_name=name)
        
    def record_success(self) -> None:
        """Record successful operation."""
        if self.state.is_open and self.state.half_open_attempts > 0:
            # Success in half-open state, close the breaker
            logger.info(f"Circuit breaker {self.name} closing after successful half-open attempt")
            self.state.is_open = False
            self.state.failure_count = 0
            self.state.half_open_attempts = 0
            self.state.opened_at = None
    
    def record_failure(self) -> None:
        """Record failed operation."""
        self.state.failure_count += 1
        self.state.last_failure = datetime.utcnow()
        
        if self.state.is_open:
            # Failed in half-open state
            self.state.half_open_attempts += 1
            if self.state.half_open_attempts >= self.half_open_max:
                # Reset timeout
                self.state.opened_at = datetime.utcnow()
                logger.warning(f"Circuit breaker {self.name} failed in half-open state, resetting timeout")
        else:
            # Check if we should open
            if self.state.failure_count >= self.failure_threshold:
                self.state.is_open = True
                self.state.opened_at = datetime.utcnow()
                logger.error(f"Circuit breaker {self.name} OPENED after {self.state.failure_count} failures")
    
    def can_proceed(self) -> bool:
        """Check if operation can proceed."""
        if not self.state.is_open:
            return True
        
        # Check if timeout has elapsed
        if self.state.opened_at:
            elapsed = (datetime.utcnow() - self.state.opened_at).total_seconds()
            if elapsed >= self.timeout_seconds:
                # Move to half-open state
                logger.info(f"Circuit breaker {self.name} moving to half-open state")
                self.state.half_open_attempts = 0
                return True
        
        return False
    
    def get_state(self) -> str:
        """Get current circuit breaker state."""
        if self.state.is_open:
            if self.state.half_open_attempts > 0:
                return "HALF_OPEN"
            return "OPEN"
        return "CLOSED"


class TradingSafeguards:
    """Comprehensive trading safeguards and risk controls."""
    
    def __init__(self, settings: Settings):
        self._settings = settings
        
        # Circuit breakers
        self._breakers = {
            'api': CircuitBreaker('api', failure_threshold=3, timeout_seconds=60),
            'orders': CircuitBreaker('orders', failure_threshold=5, timeout_seconds=120),
            'market_data': CircuitBreaker('market_data', failure_threshold=3, timeout_seconds=30)
        }
        
        # Heat metrics
        self._heat = HeatMetrics()
        
        # Kill switch
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        
        # Daily P&L tracking
        self._daily_pnl_start = 0.0
        self._daily_pnl_history: deque = deque(maxlen=100)  # Last 100 P&L updates
        
        # Drawdown tracking
        self._portfolio_peak = 0.0
        self._max_drawdown_threshold = 0.05  # 5% max drawdown
        self._daily_loss_threshold = 0.03    # 3% daily loss limit
        
        # Rate limiting
        self._order_timestamps: deque = deque(maxlen=100)
        self._max_orders_per_minute = 20
        
    def check_circuit_breaker(self, breaker_name: str) -> bool:
        """Check if circuit breaker allows operation."""
        if breaker_name in self._breakers:
            return self._breakers[breaker_name].can_proceed()
        return True
    
    def record_success(self, breaker_name: str) -> None:
        """Record successful operation for circuit breaker."""
        if breaker_name in self._breakers:
            self._breakers[breaker_name].record_success()
    
    def record_failure(self, breaker_name: str) -> None:
        """Record failed operation for circuit breaker."""
        if breaker_name in self._breakers:
            self._breakers[breaker_name].record_failure()
    
    def update_heat_metrics(self, portfolio: PortfolioState) -> None:
        """Update portfolio heat metrics."""
        self._heat.total_exposure = portfolio.total_exposure
        self._heat.position_count = len([p for p in portfolio.positions.values() if p.notional != 0])
        self._heat.last_updated = datetime.utcnow()
        
        # Update portfolio peak for drawdown calculation
        current_value = portfolio.balance + portfolio.total_exposure
        if current_value > self._portfolio_peak:
            self._portfolio_peak = current_value
        
        # Calculate drawdown
        if self._portfolio_peak > 0:
            drawdown = (self._portfolio_peak - current_value) / self._portfolio_peak
            self._heat.max_drawdown = max(self._heat.max_drawdown, drawdown)
    
    def update_daily_pnl(self, current_pnl: float) -> None:
        """Update daily P&L tracking."""
        self._daily_pnl_history.append((datetime.utcnow(), current_pnl))
        
        # Calculate daily loss
        if self._daily_pnl_start == 0.0:
            self._daily_pnl_start = current_pnl
        
        daily_change = current_pnl - self._daily_pnl_start
        if self._daily_pnl_start != 0:
            self._heat.daily_loss = daily_change / abs(self._daily_pnl_start)
    
    def reset_daily_metrics(self) -> None:
        """Reset daily metrics (call at start of trading day)."""
        self._daily_pnl_start = 0.0
        self._heat.daily_loss = 0.0
        logger.info("Daily trading metrics reset")
    
    def check_portfolio_heat(self) -> bool:
        """Check if portfolio heat is within limits."""
        if self._kill_switch_active:
            return False
        
        # Check max exposure (leverage)
        if self._heat.total_exposure > self._settings.max_portfolio_leverage * 100:
            logger.error(f"Portfolio heat too high: {self._heat.total_exposure}% exposure")
            return False
        
        # Check position count
        max_positions = getattr(self._settings, 'max_concurrent_positions', 10)
        if self._heat.position_count > max_positions:
            logger.warning(f"Too many positions: {self._heat.position_count} > {max_positions}")
            return False
        
        return True
    
    def check_drawdown_limits(self) -> bool:
        """Check if drawdown is within acceptable limits."""
        if self._heat.max_drawdown > self._max_drawdown_threshold:
            logger.error(f"Max drawdown exceeded: {self._heat.max_drawdown*100:.2f}% > {self._max_drawdown_threshold*100}%")
            self.activate_kill_switch(f"Drawdown limit exceeded: {self._heat.max_drawdown*100:.2f}%")
            return False
        
        if self._heat.daily_loss < -self._daily_loss_threshold:
            logger.error(f"Daily loss limit exceeded: {self._heat.daily_loss*100:.2f}%")
            self.activate_kill_switch(f"Daily loss limit exceeded: {self._heat.daily_loss*100:.2f}%")
            return False
        
        return True
    
    def check_rate_limits(self) -> bool:
        """Check if order rate is within limits."""
        now = datetime.utcnow()
        
        # Remove timestamps older than 1 minute
        cutoff = now - timedelta(minutes=1)
        while self._order_timestamps and self._order_timestamps[0] < cutoff:
            self._order_timestamps.popleft()
        
        # Check rate
        if len(self._order_timestamps) >= self._max_orders_per_minute:
            logger.warning(f"Order rate limit reached: {len(self._order_timestamps)}/min")
            return False
        
        return True
    
    def record_order(self) -> None:
        """Record order timestamp for rate limiting."""
        self._order_timestamps.append(datetime.utcnow())
    
    def can_trade(self) -> Tuple[bool, Optional[str]]:
        """Comprehensive check if trading can proceed."""
        if self._kill_switch_active:
            return False, f"Kill switch active: {self._kill_switch_reason}"
        
        if not self.check_circuit_breaker('orders'):
            return False, "Orders circuit breaker is open"
        
        if not self.check_portfolio_heat():
            return False, "Portfolio heat limits exceeded"
        
        if not self.check_drawdown_limits():
            return False, "Drawdown limits exceeded"
        
        if not self.check_rate_limits():
            return False, "Order rate limit exceeded"
        
        return True, None
    
    def activate_kill_switch(self, reason: str) -> None:
        """Activate emergency kill switch."""
        self._kill_switch_active = True
        self._kill_switch_reason = reason
        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
    
    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch (manual intervention required)."""
        self._kill_switch_active = False
        self._kill_switch_reason = ""
        logger.warning("Kill switch deactivated")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current safeguard status."""
        return {
            'kill_switch': {
                'active': self._kill_switch_active,
                'reason': self._kill_switch_reason
            },
            'circuit_breakers': {
                name: {
                    'state': breaker.get_state(),
                    'failures': breaker.state.failure_count,
                    'last_failure': breaker.state.last_failure.isoformat() if breaker.state.last_failure else None
                }
                for name, breaker in self._breakers.items()
            },
            'heat_metrics': {
                'exposure': self._heat.total_exposure,
                'positions': self._heat.position_count,
                'daily_loss': f"{self._heat.daily_loss*100:.2f}%",
                'max_drawdown': f"{self._heat.max_drawdown*100:.2f}%",
                'last_updated': self._heat.last_updated.isoformat()
            },
            'limits': {
                'max_exposure': f"{self._settings.max_portfolio_leverage * 100}%",
                'max_positions': getattr(self._settings, 'max_concurrent_positions', 10),
                'max_drawdown': f"{self._max_drawdown_threshold*100}%",
                'daily_loss_limit': f"{self._daily_loss_threshold*100}%",
                'orders_per_minute': self._max_orders_per_minute,
                'current_order_rate': len(self._order_timestamps)
            }
        }
    
    async def monitor_health(self, check_interval: int = 10) -> None:
        """Background task to monitor system health."""
        while True:
            try:
                # Check various health metrics
                status = self.get_status()
                
                # Log warnings if approaching limits
                if self._heat.max_drawdown > self._max_drawdown_threshold * 0.8:
                    logger.warning(f"Approaching drawdown limit: {self._heat.max_drawdown*100:.2f}%")
                
                if self._heat.daily_loss < -self._daily_loss_threshold * 0.8:
                    logger.warning(f"Approaching daily loss limit: {self._heat.daily_loss*100:.2f}%")
                
                # Check circuit breaker states
                for name, breaker_status in status['circuit_breakers'].items():
                    if breaker_status['state'] != 'CLOSED':
                        logger.warning(f"Circuit breaker {name} is {breaker_status['state']}")
                
                await asyncio.sleep(check_interval)
                
            except Exception as e:
                logger.error(f"Error in safeguard monitoring: {e}")
                await asyncio.sleep(check_interval)


# Telegram command integration
async def handle_kill_switch_command(safeguards: TradingSafeguards, action: str, reason: str = "") -> str:
    """Handle kill switch commands from Telegram."""
    if action.lower() == "activate":
        safeguards.activate_kill_switch(reason or "Manual activation via Telegram")
        return "🚨 KILL SWITCH ACTIVATED - All trading halted"
    elif action.lower() == "deactivate":
        safeguards.deactivate_kill_switch()
        return "✅ Kill switch deactivated - Trading resumed"
    elif action.lower() == "status":
        status = safeguards.get_status()
        if status['kill_switch']['active']:
            return f"🚨 Kill switch ACTIVE: {status['kill_switch']['reason']}"
        return "✅ Kill switch inactive - Trading enabled"
    else:
        return "❌ Invalid action. Use: activate, deactivate, or status"
