"""
Initialization helper for autonomous trading components.
Separated to keep trading_service.py cleaner.
"""

from typing import List

from .autonomous_agent import AutonomousAgent
from .data_store import DataStore
from .market_scanner import MarketScanner
from .platform_router import AsterAdapter, PlatformRouter, SymphonyAdapter
from .symphony_config import AGENTS_CONFIG


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

    # 4. Initialize Autonomous Agents (3 specialized agents)
    autonomous_agents = [
        AutonomousAgent(
            agent_id="tech_agent_001",
            name="Technical Analyst",
            data_store=data_store,
            specialization="technical",
        ),
        AutonomousAgent(
            agent_id="sentiment_agent_001",
            name="Sentiment Analyst",
            data_store=data_store,
            specialization="sentiment",
        ),
        AutonomousAgent(
            agent_id="hybrid_agent_001",
            name="Hybrid Strategist",
            data_store=data_store,
            specialization="hybrid",
        ),
    ]

    return data_store, autonomous_agents, platform_router, market_scanner
