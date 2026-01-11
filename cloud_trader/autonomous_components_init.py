"""
Initialization helper for autonomous trading components.
Separated to keep trading_service.py cleaner.
"""

import logging
from typing import List

from .autonomous_agent import AutonomousAgent
from .data_store import DataStore
from .market_scanner import MarketScanner
from .symphony_config import AGENTS_CONFIG

logger = logging.getLogger(__name__)


def init_autonomous_components(
    feature_pipeline, exchange_client, symphony_client, settings, hl_client=None, drift_client=None
) -> tuple:
    """
    Initialize all autonomous trading components.

    Returns:
        tuple: (data_store, autonomous_agents, market_scanner, vpin_agent)
    """
    # 1. Initialize DataStore (unified data access layer)
    data_store = DataStore(feature_pipeline=feature_pipeline)

    # 2. (Deleted) PlatformRouter initialization removed

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
            "financial-sentiment-agent",
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

    # 5. Initialize VPIN HFT Agent (Phase 6 Enhancement)
    # This agent uses volume-synchronized probability of informed trading for HFT signals
    vpin_agent = None
    try:
        from .agents.vpin_hft_agent import VpinHFTAgent

        vpin_agent = VpinHFTAgent(
            exchange_client=exchange_client,
            pubsub_client=None,  # Can be connected to GCP PubSub if available
            risk_manager_topic="sapphire-hft-risk",
        )
        logger.info("✅ VpinHFTAgent initialized (HFT microstructure agent)")
    except ImportError:
        logger.warning("⚠️ VpinHFTAgent not available (missing dependency)")
    except Exception as e:
        logger.warning(f"⚠️ VpinHFTAgent initialization failed: {e}")

    return data_store, autonomous_agents, market_scanner, vpin_agent
