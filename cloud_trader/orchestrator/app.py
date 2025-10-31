from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import Dict

from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis

from ..client import AsterClient
from ..config import Settings, get_settings
from ..messaging import RedisStreamsClient, timestamp
from ..order_tags import generate_order_tag
from ..schemas import InferenceRequest
from .risk import PortfolioSnapshot, kelly_fraction, potential_loss
from .schemas import OrderIntent


class RiskOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        if not (settings.aster_api_key and settings.aster_api_secret):
            raise RuntimeError("Aster credentials must be configured for the orchestrator")

        self._client = AsterClient(settings, settings.aster_api_key, settings.aster_api_secret)
        if settings.redis_url:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        else:
            self._redis = None
        self._streams = RedisStreamsClient(settings)

        self._stop = asyncio.Event()
        self._watch_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._client.ensure_session()
        await self._streams.connect()
        if self._redis:
            self._watch_task = asyncio.create_task(self._watch_portfolio())

    async def stop(self) -> None:
        self._stop.set()
        if self._watch_task:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task
        await self._client.close()
        await self._streams.close()
        if self._redis:
            await self._redis.close()

    async def submit_order(self, bot_id: str, intent: OrderIntent) -> Dict[str, str]:
        portfolio = await self._snapshot()
        self._enforce_guardrails(intent, portfolio)

        order_id = generate_order_tag(bot_id, intent.symbol)
        pending_key = f"{self._settings.pending_order_set}:{order_id}"
        if self._redis and await self._redis.exists(pending_key):
            return {"status": "duplicate", "order_id": order_id}

        payload = self._decorate_order(intent, order_id)
        await self._client.place_order(payload)

        await self._streams.publish_decision(
            {
                "bot_id": bot_id,
                "order_id": order_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "notional": f"{intent.notional:.2f}",
                "metadata": json.dumps(payload),
                "timestamp": timestamp(),
            }
        )

        if self._redis:
            await self._redis.set(pending_key, "1", ex=120)

        return {"status": "submitted", "order_id": order_id}

    async def emergency_stop(self) -> Dict[str, str]:
        for symbol in self._settings.symbols:
            try:
                await self._client.cancel_all_orders(symbol)
            except Exception:
                continue
        await self._streams.publish_reasoning(
            {
                "bot_id": "orchestrator",
                "strategy": "kill_switch",
                "message": "Emergency stop executed",
                "context": json.dumps({"symbols": self._settings.symbols}),
                "timestamp": timestamp(),
            }
        )
        return {"status": "halted"}

    async def record_inference(self, payload: InferenceRequest) -> None:
        await self._streams.publish_decision(
            {
                "bot_id": payload.bot_id,
                "symbol": payload.context.symbol,
                "decision": json.dumps(payload.decision.model_dump()),
                "context": json.dumps(payload.context.model_dump()),
                "confidence": f"{payload.confidence:.4f}" if payload.confidence else "",
                "timestamp": payload.timestamp.isoformat(),
            }
        )
        if payload.reasoning:
            await self._streams.publish_reasoning(
                {
                    "bot_id": payload.bot_id,
                    "symbol": payload.context.symbol,
                    "strategy": "model",
                    "message": "reasoning",
                    "context": json.dumps([slice.model_dump() for slice in payload.reasoning]),
                    "timestamp": payload.timestamp.isoformat(),
                }
            )

    async def _snapshot(self) -> PortfolioSnapshot:
        balance_payload = await self._client.account_balance()
        positions_payload = await self._client.position_risk()

        balance = 0.0
        if isinstance(balance_payload, list):
            for entry in balance_payload:
                balance += float(entry.get("balance", 0))

        positions: Dict[str, float] = {}
        total_exposure = 0.0
        unrealized = 0.0
        if isinstance(positions_payload, list):
            for entry in positions_payload:
                symbol = entry.get("symbol", "")
                position_amt = float(entry.get("positionAmt", 0))
                mark_price = float(entry.get("markPrice", 0))
                if position_amt == 0:
                    continue
                notional = abs(position_amt * mark_price)
                positions[symbol] = notional
                total_exposure += notional
                unrealized += float(entry.get("unRealizedProfit", 0))

        snapshot = PortfolioSnapshot(
            balance=balance,
            total_exposure=total_exposure,
            positions=positions,
            unrealized_pnl=unrealized,
        )
        await self._streams.publish_position(
            {
                "bot_id": "orchestrator",
                "balance": f"{snapshot.balance:.2f}",
                "total_exposure": f"{snapshot.total_exposure:.2f}",
                "positions": json.dumps(snapshot.positions),
                "unrealized_pnl": f"{snapshot.unrealized_pnl:.2f}",
                "timestamp": timestamp(),
            }
        )
        return snapshot

    async def _watch_portfolio(self) -> None:
        try:
            while not self._stop.is_set():
                await self._snapshot()
                await asyncio.sleep(self._settings.portfolio_poll_interval_seconds)
        except asyncio.CancelledError:  # pragma: no cover - shutdown guard
            pass

    def _decorate_order(self, intent: OrderIntent, order_id: str) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "clientOrderId": order_id,
        }
        notional = intent.notional
        price = intent.price or intent.client_metadata.get("entry_price")
        if intent.quantity:
            payload["quantity"] = intent.quantity
        elif price:
            payload["quantity"] = round(notional / price, 6)
        else:
            raise HTTPException(status_code=422, detail="quantity or price required to size order")

        if intent.order_type == "LIMIT" and price:
            payload["price"] = price
        if intent.take_profit:
            payload["stopPrice"] = intent.take_profit
        if intent.stop_loss:
            payload["closePosition"] = False
            payload["stopLossPrice"] = intent.stop_loss
        payload.update(intent.client_metadata)
        return payload

    def _enforce_guardrails(self, intent: OrderIntent, portfolio: PortfolioSnapshot) -> None:
        balance = max(portfolio.balance, 1.0)

        kelly = kelly_fraction(intent.expected_win_rate, intent.reward_to_risk)
        kelly = min(kelly, self._settings.kelly_fraction_cap)
        if intent.notional > balance * max(kelly, 1e-3):
            raise HTTPException(status_code=400, detail="kelly_fraction_exceeded")

        if intent.notional > balance * self._settings.max_position_risk:
            raise HTTPException(status_code=400, detail="position_risk_limit")

        if portfolio.total_exposure + intent.notional > balance * self._settings.max_portfolio_leverage:
            raise HTTPException(status_code=400, detail="portfolio_exposure_limit")

        entry_price = intent.price or intent.client_metadata.get("entry_price")
        risk_amount = potential_loss(intent.notional, entry_price, intent.stop_loss)
        drawdown_floor = balance * (1 - self._settings.max_drawdown)
        if risk_amount and (balance + portfolio.unrealized_pnl - risk_amount) < drawdown_floor:
            raise HTTPException(status_code=400, detail="drawdown_guardrail")

def build_orchestrator(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    orchestrator = RiskOrchestrator(settings)
    app = FastAPI(title="Wallet Risk Orchestrator", version="1.0")

    @app.on_event("startup")
    async def _startup() -> None:
        await orchestrator.start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        await orchestrator.stop()

    @app.post("/order/{bot_id}")
    async def order(bot_id: str, intent: OrderIntent) -> Dict[str, str]:
        return await orchestrator.submit_order(bot_id, intent)

    @app.post("/emergency_stop")
    async def emergency_stop() -> Dict[str, str]:
        return await orchestrator.emergency_stop()

    @app.post("/register_decision")
    async def register_decision(payload: InferenceRequest) -> Dict[str, str]:
        await orchestrator.record_inference(payload)
        return {"status": "recorded"}

    @app.get("/portfolio")
    async def portfolio() -> Dict[str, object]:
        snapshot = await orchestrator._snapshot()
        return {
            "balance": snapshot.balance,
            "total_exposure": snapshot.total_exposure,
            "positions": snapshot.positions,
            "unrealized_pnl": snapshot.unrealized_pnl,
        }

    return app

