#!/usr/bin/env python3
"""
Unified Model Router for Multiple LLM Trading Agents
Routes requests to appropriate specialized models
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import httpx
import redis.asyncio as redis
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelType(str, Enum):
    """Available model types"""
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    FINGPT = "fingpt"
    PHI3 = "phi3"

class TradingDecisionRequest(BaseModel):
    """Request model for trading decisions"""
    context: Dict[str, Any] = Field(..., description="Market context and data")
    bot_id: str = Field(..., description="Bot identifier")
    symbol: str = Field(..., description="Trading symbol")
    current_position: Optional[Dict[str, Any]] = Field(None, description="Current position data")
    risk_limits: Dict[str, float] = Field(..., description="Risk management parameters")
    model_preference: Optional[ModelType] = Field(None, description="Preferred model for decision")

class InferenceResponse(BaseModel):
    """Response model for LLM inferences"""
    decision: str
    confidence: float
    reasoning: str
    timestamp: str
    bot_id: str
    model_used: str

class ModelRouter:
    """Routes requests to appropriate LLM models"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.model_endpoints = {
            ModelType.DEEPSEEK: os.getenv("DEEPSEEK_ENDPOINT", "https://deepseek-trader-880429861698.us-central1.run.app"),
            ModelType.QWEN: os.getenv("QWEN_ENDPOINT", "https://qwen-trader-880429861698.us-central1.run.app"),
            ModelType.FINGPT: os.getenv("FINGPT_ENDPOINT", "https://fingpt-trader-880429861698.us-central1.run.app"),
            ModelType.PHI3: os.getenv("PHI3_ENDPOINT", "https://phi3-trader-880429861698.us-central1.run.app"),
        }

    async def initialize(self):
        """Initialize Redis connection"""
        try:
            REDIS_URL = os.getenv("REDIS_URL", "redis://10.161.118.219:6379")
            self.redis_client = redis.from_url(REDIS_URL)
            await self.redis_client.ping()
            logger.info("✅ Model Router initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Model Router: {e}")
            raise

    def select_model(self, request: TradingDecisionRequest) -> ModelType:
        """Select the most appropriate model for the request"""

        # If model preference is specified, use it
        if request.model_preference:
            return request.model_preference

        # Intelligent model selection based on context
        symbol = request.symbol
        context = request.context
        has_position = request.current_position is not None

        # FinGPT for complex financial analysis
        if has_position and context.get('volume', 0) > 1000000:  # High volume
            return ModelType.FINGPT

        # Qwen for algorithmic/coding heavy analysis
        if context.get('volatility', 'medium') == 'high':
            return ModelType.QWEN

        # Phi-3 for efficient, fast decisions
        if not has_position and context.get('sentiment') in ['bullish', 'bearish']:
            return ModelType.PHI3

        # DeepSeek as default for balanced analysis
        return ModelType.DEEPSEEK

    async def route_decision(self, request: TradingDecisionRequest) -> InferenceResponse:
        """Route decision request to appropriate model"""

        # Select model
        selected_model = self.select_model(request)
        endpoint = self.model_endpoints[selected_model]

        try:
            # Prepare request data
            request_data = {
                "context": request.context,
                "bot_id": request.bot_id,
                "symbol": request.symbol,
                "current_position": request.current_position,
                "risk_limits": request.risk_limits,
            }

            # Make request to selected model
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{endpoint}/decide",
                    json=request_data,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                result = response.json()

            # Add model information to response
            result["model_used"] = selected_model.value

            # Log routing decision
            logger.info(f"🎯 Routed {request.bot_id} request to {selected_model.value} model")

            return InferenceResponse(**result)

        except httpx.RequestError as e:
            logger.error(f"Failed to route to {selected_model.value}: {e}")
            # Try fallback to DeepSeek
            if selected_model != ModelType.DEEPSEEK:
                logger.info("🔄 Falling back to DeepSeek model")
                return await self._route_to_model(request, ModelType.DEEPSEEK)
            raise HTTPException(status_code=503, detail=f"Model service unavailable: {selected_model.value}")

        except Exception as e:
            logger.error(f"Routing failed: {e}")
            raise HTTPException(status_code=500, detail=f"Routing failed: {str(e)}")

    async def _route_to_model(self, request: TradingDecisionRequest, model: ModelType) -> InferenceResponse:
        """Route to specific model as fallback"""
        endpoint = self.model_endpoints[model]
        request_data = {
            "context": request.context,
            "bot_id": request.bot_id,
            "symbol": request.symbol,
            "current_position": request.current_position,
            "risk_limits": request.risk_limits,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{endpoint}/decide",
                json=request_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            result = response.json()
            result["model_used"] = model.value
            return InferenceResponse(**result)

    async def get_model_status(self) -> Dict[str, Any]:
        """Get status of all models"""
        status = {}
        async with httpx.AsyncClient(timeout=5.0) as client:
            for model, endpoint in self.model_endpoints.items():
                try:
                    response = await client.get(f"{endpoint}/health")
                    status[model.value] = {
                        "status": "healthy" if response.status_code == 200 else "unhealthy",
                        "endpoint": endpoint
                    }
                except Exception as e:
                    status[model.value] = {
                        "status": "unavailable",
                        "endpoint": endpoint,
                        "error": str(e)
                    }

        return status

# Global instance
model_router = ModelRouter()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    await model_router.initialize()
    yield
    if model_router.redis_client:
        await model_router.redis_client.close()

# Create FastAPI app
app = FastAPI(
    title="Multi-Model Trading LLM Router",
    description="Intelligent router for multiple specialized trading LLMs",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "multi-model-trading-router",
        "models": list(model_router.model_endpoints.keys())
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "redis_connected": model_router.redis_client is not None,
        "models": await model_router.get_model_status(),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/decide", response_model=InferenceResponse)
async def make_trading_decision(
    request: TradingDecisionRequest,
    background_tasks: BackgroundTasks
):
    """Generate trading decision using intelligent model routing"""
    return await model_router.route_decision(request)

@app.get("/models")
async def list_models():
    """Get available models and their status"""
    return {
        "models": {
            model.value: {
                "endpoint": endpoint,
                "specialization": {
                    ModelType.DEEPSEEK: "balanced_analysis",
                    ModelType.QWEN: "algorithmic_trading",
                    ModelType.FINGPT: "financial_analysis",
                    ModelType.PHI3: "efficient_trading"
                }[model]
            }
            for model, endpoint in model_router.model_endpoints.items()
        },
        "router": "intelligent_selection"
    }

@app.get("/status")
async def get_status():
    """Get comprehensive system status"""
    return {
        "router": {
            "status": "healthy",
            "redis_connected": model_router.redis_client is not None,
        },
        "models": await model_router.get_model_status(),
        "endpoints": model_router.model_endpoints,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(
        "model_router:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
