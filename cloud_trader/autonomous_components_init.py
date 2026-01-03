"""
Initialization helper for autonomous trading components.
Separated to keep trading_service.py cleaner.
"""

import logging
from typing import List

from .autonomous_agent import AutonomousAgent
from .data_store import DataStore
from .market_scanner import MarketScanner
from .platform_router import AsterAdapter, PlatformRouter, SymphonyAdapter
from .symphony_config import AGENTS_CONFIG

logger = logging.getLogger(__name__)


def init_autonomous_components(
    feature_pipeline, exchange_client, symphony_client, settings
) -> tuple:
    """
    Initialize all autonomous trading components.

    Returns:
        tuple: (data_store, autonomous_agents, platform_router, market_scanner)
    """
    # 1. Initialize DataStore (unified data access layer)
    data_store = DataStore(feature_pipeline=feature_pipeline)

    # 2. Initialize Platform Router with adapters
    symphony_adapter = SymphonyAdapter(symphony_client=symphony_client, agents_config=AGENTS_CONFIG)
    aster_adapter = AsterAdapter(aster_client=exchange_client)
    platform_router = PlatformRouter(
        adapters={
            "symphony": symphony_adapter,
            "symphony_swap": symphony_adapter,
            "symphony_perp": symphony_adapter,
            "aster": aster_adapter,
        }
    )

    # 3. Initialize MarketScanner
    # Pass None for market_data if not available (will use feature_pipeline)
    market_scanner = MarketScanner(
        feature_pipeline=feature_pipeline, market_data=None  # Can be injected later if needed
    )

    # 4. Initialize Autonomous Agents (Dynamic based on settings)
    autonomous_agents = []
    
    enabled_agents = getattr(settings, "enabled_agents", [])
    if not enabled_agents:
        logger.warning("No agents enabled in settings, falling back to defaults")
        enabled_agents = [
            "trend-momentum-agent", 
            "strategy-optimization-agent", 
            "financial-sentiment-agent"
        ]

    for agent_id in enabled_agents:
        # Map IDs to human-readable names or just use ID
        name = agent_id.replace("-", " ").title()
        
        # Determine specialization based on ID keywords
        specialization = "technical"
        if "sentiment" in agent_id.lower():
            specialization = "sentiment"
        elif "hybrid" in agent_id.lower() or "strategy" in agent_id.lower():
            specialization = "hybrid"
        elif "market" in agent_id.lower() or "prediction" in agent_id.lower():
            specialization = "predictive"
        elif "volume" in agent_id.lower() or "vpin" in agent_id.lower():
            specialization = "microstructure"

        agent = AutonomousAgent(
            agent_id=agent_id,
            name=name,
            data_store=data_store,
            specialization=specialization,
        )
        autonomous_agents.append(agent)

    return data_store, autonomous_agents, platform_router, market_scanner
