"""
Graceful degradation mechanisms for maintaining system functionality during failures.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)

class DegradationLevel(Enum):
    """Levels of system degradation."""
    NORMAL = "normal"          # All systems operational
    MINOR = "minor"            # Some non-critical systems degraded
    MODERATE = "moderate"      # Critical systems affected but recoverable
    SEVERE = "severe"          # Core functionality impaired
    CRITICAL = "critical"      # System should halt trading

@dataclass
class DegradedComponent:
    """Represents a component that has been degraded."""
    name: str
    degradation_level: DegradationLevel
    fallback_available: bool
    description: str
    impact: str
    timestamp: float = field(default_factory=lambda: asyncio.get_event_loop().time())

@dataclass
class GracefulDegradationConfig:
    """Configuration for graceful degradation behavior."""
    enable_fallbacks: bool = True
    halt_on_critical: bool = True
    max_minor_degradations: int = 3
    max_moderate_degradations: int = 1
    notify_on_degradation: bool = True

class GracefulDegradationManager:
    """Manages graceful degradation of system components."""

    def __init__(self, config: Optional[GracefulDegradationConfig] = None):
        self.config = config or GracefulDegradationConfig()
        self.degraded_components: Dict[str, DegradedComponent] = {}
        self.fallback_functions: Dict[str, Callable] = {}
        self.degradation_listeners: List[Callable[[DegradedComponent], None]] = []

    def register_fallback(self, component_name: str, fallback_func: Callable):
        """Register a fallback function for a component."""
        self.fallback_functions[component_name] = fallback_func
        logger.info(f"Registered fallback for component: {component_name}")

    def add_degradation_listener(self, listener: Callable[[DegradedComponent], None]):
        """Add a listener for degradation events."""
        self.degradation_listeners.append(listener)

    def degrade_component(
        self,
        name: str,
        level: DegradationLevel,
        description: str,
        impact: str,
        fallback_available: bool = False
    ):
        """Mark a component as degraded."""
        component = DegradedComponent(
            name=name,
            degradation_level=level,
            fallback_available=fallback_available,
            description=description,
            impact=impact
        )

        self.degraded_components[name] = component

        # Notify listeners
        for listener in self.degradation_listeners:
            try:
                listener(component)
            except Exception as e:
                logger.error(f"Error in degradation listener: {e}")

        logger.warning(f"Component {name} degraded to {level.value}: {description}")

        # Check if we should halt trading
        if self.config.halt_on_critical and level == DegradationLevel.CRITICAL:
            logger.critical(f"Critical degradation detected for {name}, halting trading")
            # This would trigger an emergency stop

    def restore_component(self, name: str):
        """Restore a degraded component."""
        if name in self.degraded_components:
            del self.degraded_components[name]
            logger.info(f"Component {name} restored to normal operation")

    def get_overall_degradation_level(self) -> DegradationLevel:
        """Get the overall system degradation level."""
        if not self.degraded_components:
            return DegradationLevel.NORMAL

        levels = [comp.degradation_level for comp in self.degraded_components.values()]

        if DegradationLevel.CRITICAL in levels:
            return DegradationLevel.CRITICAL
        elif DegradationLevel.SEVERE in levels:
            return DegradationLevel.SEVERE
        elif DegradationLevel.MODERATE in levels:
            return DegradationLevel.MODERATE
        elif DegradationLevel.MINOR in levels:
            # Check if we have too many minor degradations
            minor_count = sum(1 for level in levels if level == DegradationLevel.MINOR)
            if minor_count > self.config.max_minor_degradations:
                return DegradationLevel.MODERATE
            return DegradationLevel.MINOR

        return DegradationLevel.NORMAL

    def should_halt_trading(self) -> bool:
        """Determine if trading should be halted due to degradation."""
        level = self.get_overall_degradation_level()
        return level in [DegradationLevel.SEVERE, DegradationLevel.CRITICAL]

    def get_fallback_function(self, component_name: str) -> Optional[Callable]:
        """Get the fallback function for a component."""
        return self.fallback_functions.get(component_name)

    def is_component_degraded(self, component_name: str) -> bool:
        """Check if a component is currently degraded."""
        return component_name in self.degraded_components

    def get_degraded_components(self) -> Dict[str, DegradedComponent]:
        """Get all currently degraded components."""
        return self.degraded_components.copy()

    async def execute_with_fallback(self, component_name: str, primary_func: Callable, *args, **kwargs) -> Any:
        """Execute a function with fallback support."""
        if self.is_component_degraded(component_name):
            fallback_func = self.get_fallback_function(component_name)
            if fallback_func and self.config.enable_fallbacks:
                logger.info(f"Using fallback for degraded component: {component_name}")
                try:
                    return await fallback_func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Fallback execution failed for {component_name}: {e}")
                    raise
            else:
                raise RuntimeError(f"Component {component_name} is degraded and no fallback available")

        # Execute primary function
        return await primary_func(*args, **kwargs)

# Global graceful degradation manager
_degradation_manager: Optional[GracefulDegradationManager] = None

def get_graceful_degradation_manager() -> GracefulDegradationManager:
    """Get the global graceful degradation manager."""
    global _degradation_manager
    if _degradation_manager is None:
        _degradation_manager = GracefulDegradationManager()
    return _degradation_manager

# Fallback functions for common components

async def fallback_market_data(symbol: str) -> Dict[str, Any]:
    """Fallback market data provider."""
    # Return cached or synthetic data
    return {
        "symbol": symbol,
        "price": 50000.0,  # Placeholder price
        "volume": 1000.0,
        "change_24h": 0.0,
        "is_fallback": True
    }

async def fallback_ai_analysis(market_data: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback AI analysis when Vertex AI is unavailable."""
    return {
        "thesis": "Market analysis unavailable - using conservative approach",
        "confidence": 0.5,
        "risk_score": 0.7,
        "recommendation": "HOLD",
        "is_fallback": True
    }

async def fallback_notification(message: str) -> bool:
    """Fallback notification system."""
    logger.warning(f"Notification system degraded - logging message: {message}")
    # Could write to a file or send to an alternative system
    return True

# Initialize the global manager with common fallbacks
def initialize_graceful_degradation():
    """Initialize the graceful degradation system with common fallbacks."""
    manager = get_graceful_degradation_manager()

    # Register fallback functions
    manager.register_fallback("market_data", fallback_market_data)
    manager.register_fallback("ai_analysis", fallback_ai_analysis)
    manager.register_fallback("notification", fallback_notification)

    logger.info("Graceful degradation system initialized with fallback functions")
