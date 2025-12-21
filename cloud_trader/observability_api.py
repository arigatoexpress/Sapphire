import asyncio
import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from .experiment_tracker import get_experiment_tracker
from .safety import get_safety_switch
from .state_manager import get_state_manager

router = APIRouter(prefix="/api/system", tags=["System Observability"])


@router.get("/health")
async def get_system_health():
    """Get comprehensive system health status."""
    safety = get_safety_switch()
    tracker = get_experiment_tracker()

    return {
        "status": "healthy" if safety.check_health() else "degraded",
        "safety_switch": {"healthy": safety.check_health(), "last_heartbeats": safety._heartbeats},
        "active_experiment": {
            "id": tracker.current_experiment.id if tracker.current_experiment else None,
            "name": (
                tracker.current_experiment.name
                if tracker.current_experiment
                else "Continuous Monitoring"
            ),
            "metrics_count": (
                len(tracker.current_experiment.metrics) if tracker.current_experiment else 0
            ),
        },
        "server_time": asyncio.get_event_loop().time(),
    }


@router.get("/metrics/recent")
async def get_recent_metrics(limit: int = 100):
    """Get recent performance metrics for visualization."""
    tracker = get_experiment_tracker()
    # In a real impl, we'd query Firestore or an in-memory buffer
    # For now, return what's in memory for the current experiment
    if tracker.current_experiment:
        return tracker.current_experiment.metrics
    return {}


@router.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Real-time telemetry stream for Mission Control."""
    await websocket.accept()

    safety = get_safety_switch()
    tracker = get_experiment_tracker()

    try:
        while True:
            # Gather real-time state
            telemetry = {
                "timestamp": asyncio.get_event_loop().time(),
                "health": safety.check_health(),
                "metrics": {
                    # Simulated "live" metrics if not currently generating events
                    "latency_ms": 45 + (asyncio.get_event_loop().time() % 10),
                    "memory_usage": 1024,
                    # Add real metrics here
                },
            }

            await websocket.send_json(telemetry)
            await asyncio.sleep(0.5)  # 2Hz Update Rate

    except WebSocketDisconnect:
        pass
