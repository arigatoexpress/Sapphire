#!/usr/bin/env python3
"""Lag-Llama Degenerate agent service for Vertex AI deployment."""
import os
import random
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from models.common.mcp_adapter import MCPAdapter

app = FastAPI(title="Lag-Llama Degenerate", version="1.0.0")

MODEL_NAME = "Lag-Llama Degenerate"
MODEL_TRAITS = {
    "strengths": [
        "high-volatility pattern detection",
        "microstructure anomaly spotting",
        "degen momentum timing",
    ],
    "personality": "High-volatility specialist embracing fat-tail regimes",
}

MCP_URL = os.getenv("MCP_URL")
MCP_SESSION_ID = os.getenv("MCP_SESSION_ID")
SERVICE_AGENT_ID = os.getenv("AGENT_ID", MODEL_NAME)
MARKET_DATA_ENDPOINT = os.getenv("MARKET_DATA_ENDPOINT")

mcp_adapter: Optional[MCPAdapter] = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InferenceRequest(BaseModel):
    prompt: str
    context: Dict[str, Any] = {}
    max_tokens: int = 128
    temperature: float = 0.8


class InferenceResponse(BaseModel):
    text: str
    confidence: float
    reasoning: str
    model_used: str


def _fetch_volatility_context(symbol: str) -> Dict[str, Any]:
    if not MARKET_DATA_ENDPOINT:
        return {}
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{MARKET_DATA_ENDPOINT}/volatility/{symbol}")
            response.raise_for_status()
            return response.json()
    except Exception:
        return {}


def _generate_response(prompt: str, context: Dict[str, Any]) -> InferenceResponse:
    symbol = context.get("symbol", "UNKNOWN")
    side_bias = "BUY" if "long" in prompt.lower() else "SELL" if "short" in prompt.lower() else random.choice(["BUY", "SELL"])
    volatility = context.get("atr", random.uniform(0.01, 0.05))
    funding_rate = context.get("funding_rate", random.uniform(-0.01, 0.01))

    additional_context = _fetch_volatility_context(symbol)
    anomaly_score = additional_context.get("anomaly_score", random.uniform(0.1, 0.6))
    ci_span = additional_context.get("ci_span", random.uniform(0.05, 0.25))

    confidence = min(0.6 + (volatility * 4) + (abs(funding_rate) * 5), 0.95)
    reasoning = (
        f"Lag-Llama sees {symbol} in {volatility*100:.1f}% volatility regime with funding {funding_rate*100:.2f}%.
"
        f"Anomaly score {anomaly_score:.2f} and CI span {ci_span:.2%} favour {side_bias.lower()} positioning."
    )

    return InferenceResponse(
        text=f"Decision: {side_bias}",
        confidence=round(confidence, 2),
        reasoning=reasoning,
        model_used=MODEL_NAME,
    )


async def _handle_mcp(payload: Dict[str, Any]) -> Dict[str, Any]:
    symbol = payload.get("symbol") or payload.get("instrument", "UNKNOWN")
    context = payload.get("context", {})
    context.setdefault("symbol", symbol)
    prompt = payload.get("question", "Evaluate positioning")
    result = _generate_response(prompt, context)
    return {
        "answer": result.reasoning,
        "confidence": result.confidence,
        "supplementary": {
            "decision": result.text,
            "model": result.model_used,
        },
    }


@app.on_event("startup")
async def startup_event() -> None:
    global mcp_adapter
    if MCP_URL:
        mcp_adapter = MCPAdapter(
            MCP_URL,
            SERVICE_AGENT_ID,
            session_id=MCP_SESSION_ID,
            handle_query=_handle_mcp,
        )
        await mcp_adapter.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if mcp_adapter:
        await mcp_adapter.stop()


@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "status": "running",
        "service": MODEL_NAME,
        "strengths": MODEL_TRAITS["strengths"],
        "personality": MODEL_TRAITS["personality"],
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/infer", response_model=InferenceResponse)
async def infer(request: InferenceRequest) -> InferenceResponse:
    try:
        enriched_context = dict(request.context)
        enriched_context.setdefault("symbol", enriched_context.get("symbol", "UNKNOWN"))
        return _generate_response(request.prompt, enriched_context)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc
