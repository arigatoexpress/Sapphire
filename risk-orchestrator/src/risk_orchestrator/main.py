from __future__ import annotations

import asyncio
import contextlib
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from loguru import logger
import httpx

from .aster_client import AsterClient
from .config import settings
from .mcp import (
    MCPConsensusPayload,
    MCPExecutionPayload,
    MCPManager,
    MCPManagerSingleton,
    MCPMessage,
    MCPMessageType,
    MCPObservationPayload,
    MCPQueryPayload,
    MCPRole,
    get_mcp_router,
)
from .mcp.consensus import get_consensus_engine
from .models import OrderIntent, RiskCheckResponse
from .pubsub_client import PubSubClient
from .risk_engine import RiskEngine
from .utils import generate_order_id

app = FastAPI(title="Risk Orchestrator", version="0.1.0")
prefixed_router = APIRouter(prefix="/orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
Instrumentator().instrument(app).expose(app)

aster_client: Optional[AsterClient] = None
pubsub_client: Optional[PubSubClient] = None
mcp_manager: MCPManager = MCPManagerSingleton.manager
_portfolio_task: Optional[asyncio.Task] = None

app.include_router(get_mcp_router())

async def _broadcast_message(message: MCPMessage) -> None:
    session_id = message.session_id
    await mcp_manager.broadcast(session_id, message)

async def _broadcast_observation(account: dict) -> None:
    session_id = MCPManagerSingleton.default_session_id
    if not session_id:
        return
    payload = MCPObservationPayload(
        market={
            "totalWalletBalance": account.get("totalWalletBalance"),
            "availableBalance": account.get("availableBalance"),
            "positions": len(account.get("positions", [])),
        },
        risk_state={
            "maxWithdrawAmount": account.get("maxWithdrawAmount"),
            "marginRatio": account.get("marginRatio"),
        },
        telemetry={
            "source": "portfolio_watcher",
        },
    )
    message = MCPMessage(
        session_id=session_id,
        sender_id="risk-orchestrator",
        sender_role=MCPRole.COORDINATOR,
        message_type=MCPMessageType.OBSERVATION,
        payload=payload.model_dump(),
    )
    await _broadcast_message(message)

async def _broadcast_query(intent: OrderIntent, bot_id: str) -> Optional[str]:
    session_id = MCPManagerSingleton.default_session_id
    if not session_id:
        return None
    reference_id = generate_order_id(bot_id, intent.symbol)
    payload = MCPQueryPayload(
        reference_id=reference_id,
        question=f"Should we execute {intent.side} {intent.symbol}?",
        topic="trade_proposal",
        context={
            "bot_id": bot_id,
            "notional": intent.notional,
            "take_profit": intent.take_profit,
            "stop_loss": intent.stop_loss,
        },
    )
    message = MCPMessage(
        session_id=session_id,
        sender_id="risk-orchestrator",
        sender_role=MCPRole.COORDINATOR,
        message_type=MCPMessageType.QUERY,
        payload=payload.model_dump(),
    )
    await _broadcast_message(message)
    return reference_id

async def _broadcast_consensus(reference_id: Optional[str], approved: bool, participants: list[str], notes: str | None = None) -> None:
    """Broadcast consensus result with voting algorithm integration."""
    session_id = MCPManagerSingleton.default_session_id
    if not session_id:
        return

    # If this is from a proposal, check consensus engine
    consensus_engine = await get_consensus_engine()
    if reference_id:
        proposal_state = await consensus_engine.get_proposal_state(reference_id)
        if proposal_state:
            # Use consensus engine results
            consensus_result = await consensus_engine._check_consensus(proposal_state)
            if consensus_result:
                payload = consensus_result
            else:
                # Fallback to simple approval
                payload = MCPConsensusPayload(
                    approved=approved,
                    consensus_score=1.0 if approved else 0.0,
                    participants=participants,
                    notes=notes,
                )
        else:
            payload = MCPConsensusPayload(
                approved=approved,
                consensus_score=1.0 if approved else 0.0,
                participants=participants,
                notes=notes,
            )
    else:
        payload = MCPConsensusPayload(
            approved=approved,
            consensus_score=1.0 if approved else 0.0,
            participants=participants,
            notes=notes,
        )

    message = MCPMessage(
        session_id=session_id,
        sender_id="risk-orchestrator",
        sender_role=MCPRole.COORDINATOR,
        message_type=MCPMessageType.CONSENSUS,
        payload=payload.model_dump(),
    )
    await _broadcast_message(message)

async def _broadcast_execution(order_id: str, status: str, error: str | None = None) -> None:
    session_id = MCPManagerSingleton.default_session_id
    if not session_id:
        return
    payload = MCPExecutionPayload(order_id=order_id, status=status, error=error)
    message = MCPMessage(
        session_id=session_id,
        sender_id="risk-orchestrator",
        sender_role=MCPRole.COORDINATOR,
        message_type=MCPMessageType.EXECUTION,
        payload=payload.model_dump(),
    )
    await _broadcast_message(message)

@app.on_event("startup")
async def startup() -> None:
    global aster_client, pubsub_client, _portfolio_task
    logger.info("Starting Risk Orchestrator (%s)", settings.ENVIRONMENT)
    aster_client = AsterClient()
    pubsub_client = PubSubClient()
    pubsub_client.connect()
    _portfolio_task = asyncio.create_task(portfolio_watcher())
    session_id = await mcp_manager.create_session()
    MCPManagerSingleton.default_session_id = session_id
    logger.info("MCP coordinator ready (session_id=%s)", session_id)

@app.on_event("shutdown")
async def shutdown() -> None:
    if _portfolio_task:
        _portfolio_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _portfolio_task
    if pubsub_client:
        pubsub_client.close()
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
    if not aster_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    order_id = generate_order_id(bot_id, intent.symbol)
    
    portfolio = await aster_client.get_account()
    if not portfolio:
        raise HTTPException(status_code=503, detail="Portfolio not ready")

    query_reference = await _broadcast_query(intent, bot_id)
    engine = RiskEngine(portfolio, bot_id)
    result = engine.evaluate(intent, bot_id, order_id)
    await _broadcast_consensus(query_reference, result.approved, [bot_id, "risk-engine"], notes=result.reason)
    if not result.approved:
        return result

    order_payload = intent.dict(exclude_none=True)
    order_payload["clientOrderId"] = order_id
    background.add_task(route_to_aster, order_payload, bot_id, order_id)
    return result

@app.get("/portfolio")
async def get_portfolio() -> dict:
    if not aster_client:
        raise HTTPException(status_code=503, detail="Service not ready")

    # Fetch fresh data directly
    try:
        account = await aster_client.get_account()
        return account
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail="Failed to fetch live portfolio")

@prefixed_router.get("/")
async def prefixed_root() -> dict:
    return await root()

@prefixed_router.get("/healthz")
async def prefixed_healthz() -> dict:
    return await healthz()

@prefixed_router.post("/order/{bot_id}")
async def prefixed_submit_order(bot_id: str, intent: OrderIntent, background: BackgroundTasks) -> RiskCheckResponse:
    return await submit_order(bot_id, intent, background)

@prefixed_router.get("/portfolio")
async def prefixed_portfolio() -> dict:
    return await get_portfolio()

@prefixed_router.get("/diagnostics/aster")
async def diagnostics_aster() -> dict:
    """Test Aster API connectivity and authentication."""
    if not aster_client:
        raise HTTPException(status_code=503, detail="Aster client not initialized")

    result = await aster_client.test_connectivity()
    return result

@prefixed_router.get("/diagnostics/egress")
async def diagnostics_egress() -> dict:
    """Show current egress IP address."""
    try:
        async with httpx.AsyncClient() as client:
            # Use the text endpoint to get just the IP address
            response = await client.get("https://ifconfig.me/ip")
            egress_ip = response.text.strip()

        return {
            "status": "ok",
            "egress_ip": egress_ip,
            "expected_nat_ip": "34.172.187.70",
            "using_static_nat": egress_ip == "34.172.187.70"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@prefixed_router.get("/diagnostics/aster-debug")
async def diagnostics_aster_debug() -> dict:
    """Debug Aster API authentication with different methods."""
    if not aster_client:
        raise HTTPException(status_code=503, detail="Aster client not initialized")

    import base64

    results = {}

    # Test 1: Current implementation
    try:
        result = await aster_client.test_connectivity()
        results["current_method"] = result
    except Exception as e:
        results["current_method"] = {"error": str(e)}

    # Test 2: Try base64 decoding the secret
    try:
        # Get raw secret value
        raw_secret = settings.ASTER_SECRET_KEY

        # Check if it might be base64 encoded
        try:
            decoded_secret = base64.b64decode(raw_secret).decode('utf-8')
            results["secret_appears_base64"] = True
            results["decoded_length"] = len(decoded_secret)
        except Exception:
            results["secret_appears_base64"] = False
            results["raw_length"] = len(raw_secret)
    except Exception as e:
        results["secret_check"] = {"error": str(e)}

    # Get our egress IP
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://ifconfig.me/ip")
            results["egress_ip"] = response.text.strip()
    except Exception:
        results["egress_ip"] = "unknown"

    return results

app.include_router(prefixed_router)

async def route_to_aster(order: dict, bot_id: str, order_id: str) -> None:
    if not aster_client or not pubsub_client:
        logger.error("Route attempted before startup initialisation")
        return
    try:
        await aster_client.place_order(order)
        await pubsub_client.log_event(
            {
                "bot_id": bot_id,
                "event": "order_placed",
                "order_id": order_id,
                "symbol": order.get("symbol", ""),
                "side": order.get("side", ""),
            }
        )
        await _broadcast_execution(order_id, "submitted")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Order placement failed [%s]: %s", bot_id, exc)
        await pubsub_client.log_event(
            {"bot_id": bot_id, "event": "order_failed", "order_id": order_id, "error": str(exc)}
        )
        await _broadcast_execution(order_id, "failed", error=str(exc))

async def portfolio_watcher() -> None:
    assert aster_client
    base_interval = max(0.5, settings.PORTFOLIO_REFRESH_SECONDS)
    while True:
        try:
            account = await aster_client.get_account()
            # We don't need to set the portfolio in a cache anymore
            await _broadcast_observation(account)
            await asyncio.sleep(base_interval)
            continue
        except httpx.HTTPStatusError as exc:  # pragma: no cover - defensive logging
            status_code = exc.response.status_code if exc.response else None
            if status_code == 429:
                backoff = min(base_interval * 2, base_interval * 6)
                logger.warning("Portfolio sync rate limited (429). Backing off for %.1fs", backoff)
                await asyncio.sleep(backoff)
                continue
            logger.error("Portfolio sync failed (%s): %s", status_code, exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Portfolio sync failed: %s", exc)
        await asyncio.sleep(base_interval)
