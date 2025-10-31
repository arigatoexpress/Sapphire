#!/usr/bin/env python3
"""
Qwen2.5-Coder LLM Serving with vLLM on GCP TPU
Optimized for coding-heavy trading tasks
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

# Model configuration for Qwen2.5-Coder
MODEL_CONFIG = {
    "model": "Qwen/Qwen2.5-Coder-7B-Instruct",  # 7B parameter model
    "tensor_parallel_size": 1,  # Single TPU chip for now
    "max_model_len": 8192,  # Longer context for code generation
    "enforce_eager": False,
    "gpu_memory_utilization": 0.9,
    "max_num_seqs": 8,  # Fewer concurrent requests (more complex processing)
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

class QwenTrader:
    """Qwen-powered trading decision engine"""

    def __init__(self):
        self.llm: Optional[LLM] = None
        self.redis_client: Optional[redis.Redis] = None
        self.decision_stream = "trader:decisions"
        self.reasoning_stream = "trader:reasoning"

    async def initialize(self):
        """Initialize the LLM and Redis connections"""
        try:
            # Initialize vLLM with Qwen model
            logger.info("Initializing Qwen2.5-Coder model...")
            engine_args = EngineArgs(**MODEL_CONFIG)
            self.llm = LLM(engine_args)

            # Initialize Redis
            logger.info("Connecting to Redis...")
            self.redis_client = redis.from_url(REDIS_URL)
            await self.redis_client.ping()

            logger.info("✅ Qwen2.5-Coder LLM and Redis initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            raise

    async def generate_trading_decision(self, request: TradingDecisionRequest) -> InferenceResponse:
        """Generate trading decision using Qwen"""

        # Craft trading prompt optimized for Qwen
        prompt = self._build_qwen_prompt(request)

        try:
            # Configure sampling for trading decisions
            sampling_params = SamplingParams(
                temperature=0.3,  # Slightly higher for more creative solutions
                max_tokens=1024,  # More tokens for detailed reasoning
                stop=["</think>", "\n\n##", "\n\n###"],
                presence_penalty=0.2,
                frequency_penalty=0.2
            )

            # Generate response
            outputs = self.llm.generate([prompt], sampling_params)
            response_text = outputs[0].outputs[0].text.strip()

            # Parse decision from response
            decision_data = self._parse_qwen_decision(response_text, request)

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

    def _build_qwen_prompt(self, request: TradingDecisionRequest) -> str:
        """Build optimized prompt for Qwen model"""

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
- Leverage: {pos.get('leverage', '1x')}
"""

        prompt = f"""You are an expert quantitative trader using advanced coding algorithms to analyze {request.symbol}.

Market Analysis Context:
- Current Price: {context.get('price', 'N/A')}
- 24h Change: {context.get('priceChangePercent', '0')}%
- Volume (24h): {context.get('volume', 'N/A')}
- Funding Rate: {context.get('fundingRate', '0')}
- Volatility (24h): {context.get('volatility', 'Medium')}

{position_info}
Risk Parameters:
- Max Position Size: {request.risk_limits.get('max_position_pct', 2)}% of portfolio
- Max Drawdown Limit: {request.risk_limits.get('max_drawdown_pct', 10)}%
- Risk/Reward Ratio: {request.risk_limits.get('reward_to_risk', 2.0)}

Task: Analyze the market data and determine the optimal trading action.

Think step-by-step like a professional quant developer:
1. Analyze price action and momentum
2. Evaluate technical indicators and market microstructure
3. Consider position sizing and risk management
4. Calculate optimal entry/exit points
5. Determine confidence level based on signal strength

Provide your analysis in this format:

<think>
[Your detailed algorithmic analysis and reasoning]
</think>

<decision>
Action: [BUY/SELL/HOLD/CLOSE]
Confidence: [0.0-1.0]
Reasoning: [2-3 sentence explanation of your decision]
Risk Assessment: [Position sizing and risk evaluation]
</decision>

Analysis:"""

        return prompt

    def _parse_qwen_decision(self, response: str, request: TradingDecisionRequest) -> Dict[str, Any]:
        """Parse Qwen's response into structured decision data"""

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
            confidence = 0.6  # Default medium-high for Qwen
            conf_match = decision_text.find("Confidence:")
            if conf_match != -1:
                conf_line = decision_text[conf_match:].split("\n")[0]
                try:
                    confidence = float(conf_line.replace("Confidence:", "").strip())
                    confidence = max(0.0, min(1.0, confidence))
                except:
                    pass

            # Extract reasoning
            reasoning = "Qwen algorithmic analysis"
            reason_match = decision_text.find("Reasoning:")
            if reason_match != -1:
                reasoning = decision_text[reason_match + 10:].split("Risk Assessment:")[0].strip()

            return {
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.warning(f"Failed to parse Qwen decision response: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.4,
                "reasoning": "Unable to parse Qwen response, defaulting to hold position"
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
                "model": "qwen2.5-coder",
                "timestamp": response.timestamp,
                "context": json.dumps(request.context)
            }

            reasoning_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "reasoning": response.reasoning,
                "confidence": response.confidence,
                "model": "qwen2.5-coder",
                "timestamp": response.timestamp
            }

            await self.redis_client.xadd(self.decision_stream, decision_event)
            await self.redis_client.xadd(self.reasoning_stream, reasoning_event)

            logger.info(f"🤖 Qwen decision streamed for {response.bot_id}: {response.decision}")

        except Exception as e:
            logger.error(f"Failed to stream Qwen decision: {e}")

# Global instance
qwen_trader = QwenTrader()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    await qwen_trader.initialize()
    yield
    if qwen_trader.redis_client:
        await qwen_trader.redis_client.close()

# Create FastAPI app
app = FastAPI(
    title="Qwen Trading LLM",
    description="Qwen2.5-Coder powered trading decisions with algorithmic analysis",
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
        "service": "qwen-trading-llm",
        "model": MODEL_CONFIG["model"]
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": qwen_trader.llm is not None,
        "redis_connected": qwen_trader.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/decide", response_model=InferenceResponse)
async def make_trading_decision(
    request: TradingDecisionRequest,
    background_tasks: BackgroundTasks
):
    """Generate trading decision using Qwen2.5-Coder"""
    return await qwen_trader.generate_trading_decision(request)

@app.get("/models")
async def list_models():
    """Get available models"""
    return {
        "models": [MODEL_CONFIG["model"]],
        "current": MODEL_CONFIG["model"],
        "specialization": "algorithmic_trading"
    }

if __name__ == "__main__":
    uvicorn.run(
        "vllm_qwen:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
