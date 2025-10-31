#!/usr/bin/env python3
"""
FinGPT LLM Serving with vLLM on GCP TPU
Finance-specialized model for trading decisions
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

# Model configuration for FinGPT
MODEL_CONFIG = {
    "model": "FinGPT/fingpt-mt_llama2-7b_lora",  # Finance-tuned LLaMA model
    "tensor_parallel_size": 1,
    "max_model_len": 2048,  # Shorter context for focused financial analysis
    "enforce_eager": False,
    "gpu_memory_utilization": 0.85,
    "max_num_seqs": 12,  # Higher concurrency for financial queries
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

class FinGPTTrader:
    """FinGPT-powered trading decision engine"""

    def __init__(self):
        self.llm: Optional[LLM] = None
        self.redis_client: Optional[redis.Redis] = None
        self.decision_stream = "trader:decisions"
        self.reasoning_stream = "trader:reasoning"

    async def initialize(self):
        """Initialize the LLM and Redis connections"""
        try:
            # Initialize vLLM with FinGPT model
            logger.info("Initializing FinGPT model...")
            engine_args = EngineArgs(**MODEL_CONFIG)
            self.llm = LLM(engine_args)

            # Initialize Redis
            logger.info("Connecting to Redis...")
            self.redis_client = redis.from_url(REDIS_URL)
            await self.redis_client.ping()

            logger.info("✅ FinGPT LLM and Redis initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            raise

    async def generate_trading_decision(self, request: TradingDecisionRequest) -> InferenceResponse:
        """Generate trading decision using FinGPT"""

        # Craft financial analysis prompt
        prompt = self._build_fingpt_prompt(request)

        try:
            # Configure sampling for financial decisions
            sampling_params = SamplingParams(
                temperature=0.2,  # Conservative for financial decisions
                max_tokens=768,  # Focused responses
                stop=["</analysis>", "\n\n##", "\n\n###"],
                presence_penalty=0.1,
                frequency_penalty=0.1
            )

            # Generate response
            outputs = self.llm.generate([prompt], sampling_params)
            response_text = outputs[0].outputs[0].text.strip()

            # Parse decision from response
            decision_data = self._parse_fingpt_decision(response_text, request)

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

    def _build_fingpt_prompt(self, request: TradingDecisionRequest) -> str:
        """Build optimized prompt for FinGPT financial analysis"""

        context = request.context
        position_info = ""

        if request.current_position:
            pos = request.current_position
            position_info = f"""
Position Details:
- Symbol: {request.symbol}
- Position Size: {pos.get('positionAmt', '0')} contracts
- Average Entry: ${pos.get('entryPrice', 'N/A')}
- Unrealized P&L: ${pos.get('unrealizedProfit', '0')}
- Maintenance Margin: ${pos.get('maintMargin', '0')}
"""

        prompt = f"""You are a professional financial analyst specializing in cryptocurrency trading for {request.symbol}.

Market Intelligence:
- Current Price: ${context.get('price', 'N/A')}
- Daily Change: {context.get('priceChangePercent', '0')}%
- 24h Volume: {context.get('volume', 'N/A')} contracts
- Funding Rate: {context.get('fundingRate', '0')}% (annualized)
- Market Sentiment: {context.get('sentiment', 'Neutral')}

{position_info}
Risk Management:
- Maximum Position: {request.risk_limits.get('max_position_pct', 2)}% of portfolio
- Stop Loss Threshold: {request.risk_limits.get('max_drawdown_pct', 10)}% drawdown limit
- Required Risk/Reward: {request.risk_limits.get('reward_to_risk', 2.0)}:1 minimum

Financial Analysis Task:
Conduct a comprehensive analysis considering:
1. Price momentum and trend analysis
2. Volume profile and market participation
3. Funding rate impact on directional bias
4. Risk-adjusted position sizing
5. Technical and fundamental confluence

Structure your response as a professional financial report:

<analysis>
Executive Summary: [2-3 sentence market overview]

Technical Analysis:
- Price Action: [trend, support/resistance levels]
- Momentum Indicators: [RSI, MACD, moving averages]
- Volume Analysis: [accumulation/distribution patterns]

Sentiment & Fundamentals:
- Market Structure: [bullish/bearish bias]
- Funding Dynamics: [impact on price direction]
- Risk Assessment: [volatility and position sizing]

Recommendation: [BUY/SELL/HOLD/CLOSE]
Confidence Level: [0.0-1.0]
Rationale: [detailed explanation of trade thesis]
</analysis>

Market Analysis:"""

        return prompt

    def _parse_fingpt_decision(self, response: str, request: TradingDecisionRequest) -> Dict[str, Any]:
        """Parse FinGPT's financial analysis into structured decision data"""

        try:
            # Extract analysis section
            analysis_start = response.find("<analysis>")
            if analysis_start == -1:
                raise ValueError("No analysis section found")

            analysis_text = response[analysis_start + 10:].strip()

            # Parse recommendation
            action = "HOLD"  # Default
            rec_match = analysis_text.find("Recommendation:")
            if rec_match != -1:
                rec_line = analysis_text[rec_match:].split("\n")[0]
                action = rec_line.replace("Recommendation:", "").strip().upper()

            # Validate action
            if action not in ["BUY", "SELL", "HOLD", "CLOSE"]:
                action = "HOLD"

            # Parse confidence
            confidence = 0.7  # Default higher for financial expertise
            conf_match = analysis_text.find("Confidence Level:")
            if conf_match != -1:
                conf_line = analysis_text[conf_match:].split("\n")[0]
                try:
                    confidence = float(conf_line.replace("Confidence Level:", "").strip())
                    confidence = max(0.0, min(1.0, confidence))
                except:
                    pass

            # Extract rationale
            reasoning = "FinGPT financial analysis"
            rationale_match = analysis_text.find("Rationale:")
            if rationale_match != -1:
                rationale_end = analysis_text.find("</analysis>", rationale_match)
                if rationale_end != -1:
                    reasoning = analysis_text[rationale_match + 10:rationale_end].strip()
                else:
                    reasoning = analysis_text[rationale_match + 10:].strip()

            return {
                "action": action,
                "confidence": confidence,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.warning(f"Failed to parse FinGPT decision response: {e}")
            return {
                "action": "HOLD",
                "confidence": 0.5,
                "reasoning": "Unable to parse FinGPT financial analysis, maintaining current position"
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
                "model": "fingpt",
                "timestamp": response.timestamp,
                "context": json.dumps(request.context)
            }

            reasoning_event = {
                "bot_id": response.bot_id,
                "symbol": request.symbol,
                "reasoning": response.reasoning,
                "confidence": response.confidence,
                "model": "fingpt",
                "timestamp": response.timestamp
            }

            await self.redis_client.xadd(self.decision_stream, decision_event)
            await self.redis_client.xadd(self.reasoning_stream, reasoning_event)

            logger.info(f"📊 FinGPT decision streamed for {response.bot_id}: {response.decision}")

        except Exception as e:
            logger.error(f"Failed to stream FinGPT decision: {e}")

# Global instance
fingpt_trader = FinGPTTrader()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    await fingpt_trader.initialize()
    yield
    if fingpt_trader.redis_client:
        await fingpt_trader.redis_client.close()

# Create FastAPI app
app = FastAPI(
    title="FinGPT Trading LLM",
    description="Finance-specialized FinGPT model for professional trading analysis",
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
        "service": "fingpt-trading-llm",
        "model": MODEL_CONFIG["model"]
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": fingpt_trader.llm is not None,
        "redis_connected": fingpt_trader.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/decide", response_model=InferenceResponse)
async def make_trading_decision(
    request: TradingDecisionRequest,
    background_tasks: BackgroundTasks
):
    """Generate trading decision using FinGPT"""
    return await fingpt_trader.generate_trading_decision(request)

@app.get("/models")
async def list_models():
    """Get available models"""
    return {
        "models": [MODEL_CONFIG["model"]],
        "current": MODEL_CONFIG["model"],
        "specialization": "financial_analysis"
    }

if __name__ == "__main__":
    uvicorn.run(
        "vllm_fingpt:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
