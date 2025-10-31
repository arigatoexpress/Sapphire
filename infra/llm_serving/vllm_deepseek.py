#!/usr/bin/env python3
"""
DeepSeek LLM Serving with vLLM on GCP TPU
Optimized for autonomous trading decisions
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

# Model configuration for DeepSeek
MODEL_CONFIG = {
    "model": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",  # 16B parameter model
    "tensor_parallel_size": 1,  # Single TPU chip for now
    "max_model_len": 4096,  # Optimized for trading prompts
    "enforce_eager": False,
    "gpu_memory_utilization": 0.9,
    "max_num_seqs": 16,  # Concurrent requests
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

class DeepSeekTrader:
    """DeepSeek-powered trading decision engine"""

    def __init__(self):
        self.llm: Optional[LLM] = None
        self.redis_client: Optional[redis.Redis] = None
        self.decision_stream = "trader:decisions"
        self.reasoning_stream = "trader:reasoning"

    async def initialize(self):
        """Initialize the LLM and Redis connections"""
        try:
            # Initialize vLLM with DeepSeek model
            logger.info("Initializing DeepSeek model...")
            engine_args = EngineArgs(**MODEL_CONFIG)
            self.llm = LLM(engine_args)

            # Initialize Redis
            logger.info("Connecting to Redis...")
            self.redis_client = redis.from_url(REDIS_URL)

            # Test connections
            await self.redis_client.ping()
            logger.info("✅ DeepSeek LLM and Redis initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            raise

    async def generate_trading_decision(self, request: TradingDecisionRequest) -> InferenceResponse:
        """Generate trading decision using DeepSeek"""

        # Craft trading prompt
        prompt = self._build_trading_prompt(request)

        try:
            # Configure sampling for trading decisions
            sampling_params = SamplingParams(
                temperature=0.1,  # Low temperature for consistent decisions
                max_tokens=512,
                stop=["</think>", "\n\n"],  # Stop at reasoning end
                presence_penalty=0.1,
                frequency_penalty=0.1
            )

            # Generate response
            outputs = self.llm.generate([prompt], sampling_params)
            response_text = outputs[0].outputs[0].text.strip()

            # Parse decision from response
            decision_data = self._parse_decision_response(response_text, request)

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

    def _build_trading_prompt(self, request: TradingDecisionRequest) -> str:
        """Build optimized prompt for trading decisions"""

        context = request.context
        position_info = ""

        if request.current_position:
            pos = request.current_position
            position_info = f"""
Current Position:
- Symbol: {request.symbol}
- Size: {pos.get('positionAmt', '0')}
- Entry Price: {pos.get('entryPrice', 'N/A')}
- P&L: {pos.get('unrealizedProfit', '0')}
"""

        prompt = f"""You are an expert quantitative trader making real-time decisions for {request.symbol}.

Market Context:
- Price: {context.get('price', 'N/A')}
- 24h Change: {context.get('priceChangePercent', '0')}%
- Volume: {context.get('volume', 'N/A')}
- Funding Rate: {context.get('fundingRate', '0')}

{position_info}
Risk Limits:
- Max Position Size: {request.risk_limits.get('max_position_pct', 2)}% of portfolio
- Max Drawdown: {request.risk_limits.get('max_drawdown_pct', 10)}%
- Kelly Fraction: {request.risk_limits.get('kelly_fraction', 0.5)}

Analyze the market data and current position. Provide a trading decision with reasoning.

Format your response as:
<think>
[Your step-by-step analysis]
</think>

<decision>
Action: [BUY/SELL/HOLD/CLOSE]
Confidence: [0.0-1.0]
Reasoning: [Brief explanation]
</decision>

Market Analysis:"""

        return prompt

    def _parse_decision_response(self, response: str, request: TradingDecisionRequest) -> Dict[str, Any]:
        """Parse the LLM response into structured decision data"""

        try:
            # Extract decision section
            decision_start = response.find("<decision>")
            if decision_start == -1:
                raise ValueError("No decision section found")

            decision_text = response[decision_start + 10:].strip()

            # Parse action
            action_match = decision_text.find("Action:")
            if action_match == -1:
                action = "HOLD"  # Default to hold if unclear
            else:
                action_line = decision_text[action_match:].split("\n")[0]
                action = action_line.replace("Action:", "").strip().upper()

            # Validate action
            if action not in ["BUY", "SELL", "HOLD", "CLOSE"]:
                action = "HOLD"

            # Parse confidence
            confidence = 0.5  # Default medium confidence
            conf_match = decision_text.find("Confidence:")
            if conf_match != -1:
                conf_line = decision_text[conf_match:].split("\n")[0]
                try:
                    confidence = float(conf_line.replace("Confidence:", "").strip())
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1
                except:
                    pass

            # Extract reasoning
            reasoning = "AI-generated decision"
            reason_match = decision_text.find("Reasoning:")
            if reason_match != -1:
                reasoning = decision_text[reason_match + 10:].strip()

            return {
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.warning(f"Failed to parse decision response: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.3,
                "reasoning": "Unable to parse AI response, defaulting to hold"
            }

    async def _stream_decision(self, response: InferenceResponse, request: TradingDecisionRequest):
        """Stream decision data to Redis for telemetry"""

        if not self.redis_client:
            return

        try:
            # Decision event
            decision_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "decision": response.decision,
                "confidence": response.confidence,
                "timestamp": response.timestamp,
                "context": json.dumps(request.context)
            }

            # Reasoning event
            reasoning_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "reasoning": response.reasoning,
                "confidence": response.confidence,
                "timestamp": response.timestamp
            }

            # Stream to Redis
            await self.redis_client.xadd(self.decision_stream, decision_event)
            await self.redis_client.xadd(self.reasoning_stream, reasoning_event)

            logger.info(f"📊 Decision streamed for {response.bot_id}: {response.decision}")

        except Exception as e:
            logger.error(f"Failed to stream decision: {e}")

# Global instance
deepseek_trader = DeepSeekTrader()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    await deepseek_trader.initialize()
    yield
    # Shutdown
    if deepseek_trader.redis_client:
        await deepseek_trader.redis_client.close()

# Create FastAPI app
app = FastAPI(
    title="DeepSeek Trading LLM",
    description="Autonomous trading decisions powered by DeepSeek-Coder-V2",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "running",
        "service": "deepseek-trading-llm",
        "model": MODEL_CONFIG["model"]
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": deepseek_trader.llm is not None,
        "redis_connected": deepseek_trader.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/decide", response_model=InferenceResponse)
async def make_trading_decision(
    request: TradingDecisionRequest,
    background_tasks: BackgroundTasks
):
    """Generate trading decision using DeepSeek"""
    return await deepseek_trader.generate_trading_decision(request)

@app.get("/models")
async def list_models():
    """Get available models"""
    return {
        "models": [MODEL_CONFIG["model"]],
        "current": MODEL_CONFIG["model"]
    }

if __name__ == "__main__":
    uvicorn.run(
        "vllm_deepseek:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
