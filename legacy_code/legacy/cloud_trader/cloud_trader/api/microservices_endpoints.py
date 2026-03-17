"""API endpoints for microservices architecture.

These endpoints provide aggregated data from all trading services
when running on the sapphire-web service.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


def _get_aggregator():
    """Get the state aggregator instance."""
    from ..microservices.web_aggregator import get_web_aggregator

    aggregator = get_web_aggregator()
    if not aggregator:
        raise HTTPException(
            status_code=503, detail="State aggregator not initialized (web service only)"
        )
    return aggregator


@router.get("/summary")
async def get_fleet_summary() -> Dict[str, Any]:
    """Get summary of all microservices in the fleet.

    Returns:
        - total_equity: Combined equity across all services
        - total_positions: Total open positions
        - services: Per-service breakdowns
        - timestamp: Latest update time
    """
    try:
        aggregator = _get_aggregator()
        return aggregator.get_fleet_summary()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fleet summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_all_fleet_positions() -> Dict[str, Any]:
    """Get all positions across all trading services.

    Returns:
        List of positions with service attribution.
    """
    try:
        aggregator = _get_aggregator()
        positions = aggregator.get_all_positions()

        return {
            "success": True,
            "positions": positions,
            "count": len(positions),
            "services": list(set(p.get("service") for p in positions)),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fleet positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_fleet_health() -> Dict[str, Any]:
    """Get health status of all services.

    Returns:
        Health metrics for each service including last heartbeat.
    """
    try:
        aggregator = _get_aggregator()
        health = aggregator.get_service_health()

        # Calculate overall fleet health
        all_healthy = all(
            svc.get("status") == "healthy" for svc in health.values()
        )
        any_down = any(svc.get("status") == "down" for svc in health.values())

        overall_status = (
            "healthy"
            if all_healthy
            else "degraded"
            if not any_down
            else "critical"
        )

        return {
            "overall_status": overall_status,
            "services": health,
            "total_services": len(health),
            "healthy_count": sum(
                1 for svc in health.values() if svc.get("status") == "healthy"
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fleet health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balances")
async def get_fleet_balances() -> Dict[str, Any]:
    """Get balance breakdown by service.

    Returns:
        Per-service balances and total equity.
    """
    try:
        aggregator = _get_aggregator()
        summary = aggregator.get_fleet_summary()

        return {
            "total_equity": summary["total_equity"],
            "services": {
                name: svc["balance"]
                for name, svc in summary["services"].items()
            },
            "timestamp": summary["timestamp"],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get fleet balances: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/events/recent")
async def get_recent_events(limit: int = 100) -> Dict[str, Any]:
    """Get recent events from all services.

    Args:
        limit: Maximum number of events to return

    Returns:
        Recent events across the fleet.
    """
    try:
        aggregator = _get_aggregator()

        # Get recent events (stored in aggregator)
        events = aggregator._events[-limit:] if aggregator._events else []

        return {
            "events": [e.to_dict() for e in events],
            "count": len(events),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent events: {e}")
        raise HTTPException(status_code=500, detail=str(e))
