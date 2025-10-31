#!/usr/bin/env python3
"""
Phi-3 LLM Serving with vLLM on GCP TPU
Efficient edge deployment for trading decisions
"""

import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
from vllm import LLM, SamplingParams
from vllm.engine.arg_utils import EngineArgs
import redis.asyncio as redis
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://10.161.118.219:6379")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "https://wallet-orchestrator-880429861698.us-central1.run.app")

# Model configuration for Phi-3
MODEL_CONFIG = {
    "model": "microsoft/Phi-3-mini-128k-instruct",  # 3.8B parameter efficient model
    "tensor_parallel_size": 1,
    "max_model_len": 4096,  # Balanced context length
    "enforce_eager": False,
    "gpu_memory_utilization": 0.8,
    "max_num_seqs": 16,  # Higher concurrency for efficiency
    "trust_remote_code": True,
}

class TradingDecisionRequest(BaseModel):
    """Request model for trading decisions"""
    context: Dict[str, Any] = Field(..., description="Market context and data")
    bot_id: str = Field(..., description="Bot identifier")
    symbol: str = Field(..., description="Trading symbol")
    current_position: Optional[Dict[str, Any]] = Field(None, description="Current position data")
    risk_limits: Dict[str, float] = Field(..., description="Risk management parameters")

class InferenceResponse(BaseModel):
    """Response model for LLM inferences"""
    decision: str
    confidence: float
    reasoning: str
    timestamp: str
    bot_id: str

class Phi3Trader:
    """Phi-3-powered trading decision engine"""

    def __init__(self):
        self.llm: Optional[LLM] = None
        self.redis_client: Optional[redis.Redis] = None
        self.decision_stream = "trader:decisions"
        self.reasoning_stream = "trader:reasoning"

    async def initialize(self):
        """Initialize the LLM and Redis connections"""
        try:
            # Initialize vLLM with Phi-3 model
            logger.info("Initializing Phi-3 model...")
            engine_args = EngineArgs(**MODEL_CONFIG)
            self.llm = LLM(engine_args)

            # Initialize Redis
            logger.info("Connecting to Redis...")
            self.redis_client = redis.from_url(REDIS_URL)
            await self.redis_client.ping()

            logger.info("✅ Phi-3 LLM and Redis initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            raise

    async def generate_trading_decision(self, request: TradingDecisionRequest) -> InferenceResponse:
        """Generate trading decision using Phi-3"""

        # Craft efficient prompt for Phi-3
        prompt = self._build_phi3_prompt(request)

        try:
            # Configure sampling for efficient decisions
            sampling_params = SamplingParams(
                temperature=0.4,  # Balanced creativity and consistency
                max_tokens=512,  # Efficient responses
                stop=["</decision>", "\n\n##", "\n\n###"],
                presence_penalty=0.3,
                frequency_penalty=0.3
            )

            # Generate response
            outputs = self.llm.generate([prompt], sampling_params)
            response_text = outputs[0].outputs[0].text.strip()

            # Parse decision from response
            decision_data = self._parse_phi3_decision(response_text, request)

            # Create response
            response = InferenceResponse(
                decision=decision_data["action"],
                confidence=decision_data["confidence"],
                reasoning=decision_data["reasoning"],
                timestamp=datetime.utcnow().isoformat(),
                bot_id=request.bot_id
            )

            # Stream to Redis for telemetry
            await self._stream_decision(response, request)

            return response

        except Exception as e:
            logger.error(f"Decision generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")

    def _build_phi3_prompt(self, request: TradingDecisionRequest) -> str:
        """Build efficient prompt for Phi-3 model"""

        context = request.context
        position_info = ""

        if request.current_position:
            pos = request.current_position
            position_info = f"""
Position Status:
- Asset: {request.symbol}
- Amount: {pos.get('positionAmt', '0')}
- Entry: ${pos.get('entryPrice', '0')}
- P&L: ${pos.get('unrealizedProfit', '0')}
"""

        prompt = f"""Analyze this trading opportunity for {request.symbol}:

Market Data:
- Price: ${context.get('price', 'N/A')}
- Change: {context.get('priceChangePercent', '0')}%
- Volume: {context.get('volume', 'N/A')}

{position_info}
Risk Rules:
- Max Size: {request.risk_limits.get('max_position_pct', 2)}% of capital
- Max Loss: {request.risk_limits.get('max_drawdown_pct', 10)}%

As an efficient trading AI, provide a clear decision:

<think>
Brief analysis of market conditions and position.
</think>

<decision>
Action: [BUY/SELL/HOLD/CLOSE]
Confidence: [0.0-1.0]
Reason: [1-2 sentence explanation]
</decision>

Analysis:"""

        return prompt

    def _parse_phi3_decision(self, response: str, request: TradingDecisionRequest) -> Dict[str, Any]:
        """Parse Phi-3's response into structured decision data"""

        try:
            # Extract decision section
            decision_start = response.find("<decision>")
            if decision_start == -1:
                raise ValueError("No decision section found")

            decision_text = response[decision_start + 10:].strip()

            # Parse action
            action = "HOLD"  # Default
            action_match = decision_text.find("Action:")
            if action_match != -1:
                action_line = decision_text[action_match:].split("\n")[0]
                action = action_line.replace("Action:", "").strip().upper()

            # Validate action
            if action not in ["BUY", "SELL", "HOLD", "CLOSE"]:
                action = "HOLD"

            # Parse confidence
            confidence = 0.5  # Default balanced
            conf_match = decision_text.find("Confidence:")
            if conf_match != -1:
                conf_line = decision_text[conf_match:].split("\n")[0]
                try:
                    confidence = float(conf_line.replace("Confidence:", "").strip())
                    confidence = max(0.0, min(1.0, confidence))
                except:
                    pass

            # Extract reasoning
            reasoning = "Phi-3 analysis"
            reason_match = decision_text.find("Reason:")
            if reason_match != -1:
                reasoning = decision_text[reason_match + 7:].strip()

            return {
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.warning(f"Failed to parse Phi-3 decision response: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.4,
                "reasoning": "Unable to parse Phi-3 response, defaulting to hold"
            }

    async def _stream_decision(self, response: InferenceResponse, request: TradingDecisionRequest):
        """Stream decision data to Redis for telemetry"""

        if not self.redis_client:
            return

        try:
            decision_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "decision": response.decision,
                "confidence": response.confidence,
                "model": "phi-3",
                "timestamp": response.timestamp,
                "context": json.dumps(request.context)
            }

            reasoning_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "reasoning": response.reasoning,
                "confidence": response.confidence,
                "model": "phi-3",
                "timestamp": response.timestamp
            }

            await self.redis_client.xadd(self.decision_stream, decision_event)
            await self.redis_client.xadd(self.reasoning_stream, reasoning_event)

            logger.info(f"⚡ Phi-3 decision streamed for {response.bot_id}: {response.decision}")

        except Exception as e:
            logger.error(f"Failed to stream Phi-3 decision: {e}")

# Global instance
phi3_trader = Phi3Trader()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    await phi3_trader.initialize()
    yield
    if phi3_trader.redis_client:
        await phi3_trader.redis_client.close()

# Create FastAPI app
app = FastAPI(
    title="Phi-3 Trading LLM",
    description="Efficient Phi-3 model for fast, reliable trading decisions",
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
        "service": "phi3-trading-llm",
        "model": MODEL_CONFIG["model"]
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": phi3_trader.llm is not None,
        "redis_connected": phi3_trader.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/decide", response_model=InferenceResponse)
async def make_trading_decision(
    request: TradingDecisionRequest,
    background_tasks: BackgroundTasks
):
    """Generate trading decision using Phi-3"""
    return await phi3_trader.generate_trading_decision(request)

@app.get("/models")
async def list_models():
    """Get available models"""
    return {
        "models": [MODEL_CONFIG["model"]],
        "current": MODEL_CONFIG["model"],
        "specialization": "efficient_trading"
    }

if __name__ == "__main__":
    uvicorn.run(
        "vllm_phi3:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
