from __future__ import annotations

import asyncio
import contextlib
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger

from .aster_client import AsterClient
from .config import settings
from .models import OrderIntent, RiskCheckResponse
from .redis_client import RedisClient
from .risk_engine import RiskEngine
from .utils import generate_order_id


app = FastAPI(title="Risk Orchestrator", version="0.1.0")
Instrumentator().instrument(app).expose(app)

aster_client: Optional[AsterClient] = None
redis_client: Optional[RedisClient] = None
_portfolio_task: Optional[asyncio.Task] = None


@app.on_event("startup")
async def startup() -> None:
    global aster_client, redis_client, _portfolio_task
    logger.info("Starting Risk Orchestrator (%s)", settings.ENVIRONMENT)
    aster_client = AsterClient()
    redis_client = RedisClient()
    _portfolio_task = asyncio.create_task(portfolio_watcher())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _portfolio_task
    if _portfolio_task:
        _portfolio_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _portfolio_task
    if redis_client:
        await redis_client.close()
    if aster_client:
        await aster_client.close()


@app.get("/")
async def root() -> dict:
    return {"status": "ok", "service": "risk-orchestrator"}

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.post("/order/{bot_id}", response_model=RiskCheckResponse)
async def submit_order(bot_id: str, intent: OrderIntent, background: BackgroundTasks) -> RiskCheckResponse:
    if not redis_client or not aster_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    order_id = generate_order_id(bot_id, intent.symbol)
    if await redis_client.is_duplicate(order_id):
        return RiskCheckResponse(approved=False, reason="duplicate")

    portfolio = await redis_client.get_portfolio()
    if not portfolio:
        raise HTTPException(status_code=503, detail="Portfolio not ready")

    engine = RiskEngine(portfolio)
    result = engine.evaluate(intent, bot_id, order_id)
    if not result.approved:
        return result

    await redis_client.add_pending_order(order_id)
    order_payload = intent.dict(exclude_none=True)
    order_payload["clientOrderId"] = order_id
    background.add_task(route_to_aster, order_payload, bot_id, order_id)
    return result


@app.post("/emergency_stop")
async def emergency_stop() -> dict:
    if not aster_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    await aster_client.cancel_all()
    logger.critical("Emergency stop triggered. All open orders cancelled.")
    return {"status": "stopped"}

@app.get("/portfolio")
async def get_portfolio() -> dict:
    if not aster_client:
        raise HTTPException(status_code=503, detail="Service not ready")
    account = await aster_client.get_account()
    return account


async def route_to_aster(order: dict, bot_id: str, order_id: str) -> None:
    if not aster_client or not redis_client:
        logger.error("Route attempted before startup initialisation")
        return
    try:
        await aster_client.place_order(order)
        await redis_client.log_event(
            {
                "bot_id": bot_id,
                "event": "order_placed",
                "order_id": order_id,
                "symbol": order.get("symbol", ""),
                "side": order.get("side", ""),
            }
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Order placement failed [%s]: %s", bot_id, exc)
        await redis_client.log_event(
            {"bot_id": bot_id, "event": "order_failed", "order_id": order_id, "error": str(exc)}
        )


async def portfolio_watcher() -> None:
    assert aster_client and redis_client
    interval = max(0.5, settings.PORTFOLIO_REFRESH_SECONDS)
    while True:
        try:
            account = await aster_client.get_account()
            await redis_client.set_portfolio(account)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Portfolio sync failed: %s", exc)
        await asyncio.sleep(interval)

