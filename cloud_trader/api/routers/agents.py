"""
Agents API Router
Endpoints for AI agent management and performance.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/agents", tags=["Agents"])


@router.get("/list")
async def list_agents():
    """List all registered agents."""
    from ...main_v2 import orchestrator

    agents_list = []
    if orchestrator and orchestrator.agent_orchestrator:
        for agent_id, agent in orchestrator.agent_orchestrator.agents.items():
            agents_list.append(
                {
                    "id": agent_id,
                    "name": agent.name,
                    "status": "active",  # Assuming active if loaded
                    "type": agent.config.type,
                    "system": agent.config.system,
                }
            )

    return {"agents": agents_list}


@router.get("/performance")
async def get_all_performance():
    """Get performance metrics for all agents."""
    # Will be wired to performance tracker
    return {"agents": [], "summary": {"total_trades": 0, "win_rate": 0.0}}


@router.get("/performance/{agent_id}")
async def get_agent_performance(agent_id: str):
    """Get detailed performance for a specific agent."""
    return {
        "agent_id": agent_id,
        "total_trades": 0,
        "winning_trades": 0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
    }


@router.get("/consensus/{symbol}")
async def get_consensus(symbol: str):
    """Get current agent consensus for a symbol."""
    return {"symbol": symbol, "consensus": "HOLD", "confidence": 0.0, "votes": []}


@router.post("/consensus/history")
async def get_consensus_history(limit: int = 20):
    """Get recent consensus decisions."""
    return {"decisions": [], "total": 0}


@router.get("/intel/{symbol}")
async def get_market_intel(symbol: str):
    """Get DegenIntel for a symbol."""
    # Will be wired to DegenIntel service
    return {
        "symbol": symbol,
        "sentiment_score": 0.0,
        "whale_activity": "neutral",
        "trending_rank": None,
        "recommendation": {"signal": "HOLD", "confidence": 0.0},
    }


@router.get("/trending")
async def get_trending_tokens(limit: int = 10):
    """Get currently trending tokens."""
    return {"trending": [], "updated_at": None}
