"""
Simplified Trading Service - Emergency Fallback

This is a minimal version of the trading service that bypasses complex
initializations to ensure the system can run even with container issues.
Provides basic trading functionality with essential features only.
"""

import asyncio
import logging
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

from .vertex_ai_client import VertexAIClient
from .config import TradingConfig

logger = logging.getLogger(__name__)


class SimplifiedTradingService:
    """
    Minimal trading service for emergency deployment.
    Provides core functionality without complex dependencies.
    """

    def __init__(self):
        self.config = TradingConfig()
        self.vertex_client = VertexAIClient()
        self.is_running = False
        self.agent_status = {
            'trend_momentum_agent': {'status': 'active', 'last_trade': None},
            'strategy_optimization_agent': {'status': 'active', 'last_trade': None},
            'financial_sentiment_agent': {'status': 'active', 'last_trade': None},
            'market_prediction_agent': {'status': 'active', 'last_trade': None},
            'volume_microstructure_agent': {'status': 'active', 'last_trade': None},
            'freqtrade': {'status': 'standby', 'last_trade': None},
            'hummingbot': {'status': 'standby', 'last_trade': None}
        }

        # Simplified capital allocation
        self.total_capital = float(os.getenv('TOTAL_CAPITAL', '3500'))
        self.agent_capital = self.total_capital / 7  # $500 per agent

        logger.info(f"🟢 Simplified Trading Service initialized with ${self.total_capital} capital")

    async def start(self):
        """Start the simplified trading service"""
        self.is_running = True
        logger.info("🚀 Simplified Trading Service started")

        # Basic health check loop
        while self.is_running:
            try:
                await self._health_check()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(60)

    async def stop(self):
        """Stop the trading service"""
        self.is_running = False
        logger.info("🛑 Simplified Trading Service stopped")

    async def _health_check(self):
        """Basic health check"""
        # Simple connectivity test
        try:
            # Test Vertex AI connectivity
            await self.vertex_client.health_check()
            logger.debug("✅ Vertex AI connection healthy")
        except Exception as e:
            logger.warning(f"⚠️ Vertex AI health check failed: {e}")

    async def get_portfolio_status(self) -> Dict[str, Any]:
        """Get simplified portfolio status"""
        return {
            'total_capital': self.total_capital,
            'agent_capital': self.agent_capital,
            'agent_count': 7,
            'status': 'operational' if self.is_running else 'stopped',
            'timestamp': datetime.utcnow().isoformat(),
            'agents': self.agent_status
        }

    async def get_agent_activities(self) -> List[Dict[str, Any]]:
        """Get simplified agent activities"""
        activities = []
        for agent_id, status in self.agent_status.items():
            activities.append({
                'agent_id': f'{agent_id.replace("_", "-")}-1',
                'agent_type': agent_id,
                'agent_name': agent_id.replace('_', ' ').title(),
                'activity_score': 0.5 + (hash(agent_id) % 50) / 100,  # Pseudo-random score
                'communication_count': hash(agent_id) % 20,
                'trading_count': 0,  # No real trading yet
                'last_activity': datetime.utcnow().isoformat(),
                'participation_threshold': 0.7,
                'specialization': self._get_agent_specialization(agent_id),
                'color': self._get_agent_color(agent_id),
                'status': status['status']
            })
        return activities

    def _get_agent_specialization(self, agent_type: str) -> str:
        """Get agent specialization description"""
        specializations = {
            'trend_momentum_agent': 'Momentum Analysis',
            'strategy_optimization_agent': 'Strategy Optimization',
            'financial_sentiment_agent': 'Sentiment Analysis',
            'market_prediction_agent': 'Market Prediction',
            'volume_microstructure_agent': 'Volume Analysis',
            'freqtrade': 'Algorithmic Trading',
            'hummingbot': 'Market Making'
        }
        return specializations.get(agent_type, 'Trading Agent')

    def _get_agent_color(self, agent_type: str) -> str:
        """Get agent color"""
        colors = {
            'trend_momentum_agent': '#3b82f6',
            'strategy_optimization_agent': '#8b5cf6',
            'financial_sentiment_agent': '#10b981',
            'market_prediction_agent': '#f59e0b',
            'volume_microstructure_agent': '#ef4444',
            'freqtrade': '#06b6d4',
            'hummingbot': '#84cc16'
        }
        return colors.get(agent_type, '#6b7280')

    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            'service': 'simplified_trading_service',
            'status': 'operational' if self.is_running else 'stopped',
            'version': '1.0.0-simplified',
            'uptime': 'N/A',  # Would need to track this
            'total_capital': self.total_capital,
            'active_agents': len([a for a in self.agent_status.values() if a['status'] == 'active']),
            'features': [
                'Basic portfolio tracking',
                'Agent status monitoring',
                'Health checks',
                'Emergency fallback mode'
            ],
            'limitations': [
                'No complex trading logic',
                'No rate limiting',
                'No advanced analytics',
                'Simplified agent coordination'
            ]
        }
