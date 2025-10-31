#!/usr/bin/env python3
"""
Simplified AI Model Services for Testing
These mock services simulate LLM responses for the trading system
"""

import os
import asyncio
import random
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="AI Model Service", version="1.0.0")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class InferenceRequest(BaseModel):
    prompt: str
    context: dict = {}
    max_tokens: int = 100
    temperature: float = 0.7

class InferenceResponse(BaseModel):
    text: str
    confidence: float
    reasoning: str
    model_used: str

# Model-specific behaviors
MODEL_CONFIGS = {
    "deepseek": {
        "name": "DeepSeek-Coder-V2",
        "strengths": ["mathematical reasoning", "technical analysis", "market regime detection"],
        "personality": "analytical and methodical"
    },
    "qwen": {
        "name": "Qwen2.5-Coder",
        "strengths": ["algorithmic trading", "code generation", "pattern recognition"],
        "personality": "precise and systematic"
    },
    "fingpt": {
        "name": "FinGPT",
        "strengths": ["financial sentiment", "market psychology", "news analysis"],
        "personality": "market-savvy and contextual"
    },
    "phi3": {
        "name": "Phi-3",
        "strengths": ["fast decision making", "risk assessment", "trend following"],
        "personality": "agile and responsive"
    }
}

def get_model_from_path(path: str) -> str:
    """Extract model name from URL path"""
    if "deepseek" in path:
        return "deepseek"
    elif "qwen" in path:
        return "qwen"
    elif "fingpt" in path:
        return "fingpt"
    elif "phi3" in path:
        return "phi3"
    return "deepseek"  # default

def generate_trading_decision(model: str, prompt: str, context: dict) -> InferenceResponse:
    """Generate a mock trading decision based on model personality"""
    config = MODEL_CONFIGS[model]

    # Analyze prompt for trading context
    is_buy_signal = any(word in prompt.lower() for word in ["bullish", "buy", "long", "uptrend", "support"])
    is_sell_signal = any(word in prompt.lower() for word in ["bearish", "sell", "short", "downtrend", "resistance"])

    # Model-specific decision logic
    if model == "deepseek":
        # More analytical, considers technical factors
        confidence = random.uniform(0.75, 0.95)
        if is_buy_signal and random.random() > 0.3:
            decision = "BUY"
            reasoning = f"Technical analysis shows strong support levels and momentum indicators suggest upward movement. RSI at {random.randint(30, 50)}, MACD positive crossover detected."
        elif is_sell_signal and random.random() > 0.4:
            decision = "SELL"
            reasoning = f"Resistance levels reached with weakening momentum. RSI at {random.randint(70, 85)}, bearish divergence forming."
        else:
            decision = "HOLD"
            reasoning = f"Market conditions are neutral. Waiting for clearer signals. Current RSI: {random.randint(45, 65)}."

    elif model == "qwen":
        # Algorithmic approach, more systematic
        confidence = random.uniform(0.80, 0.98)
        patterns = ["double bottom", "head and shoulders", "triangle breakout", "volume spike"]
        pattern = random.choice(patterns)

        if random.random() > 0.4:
            decision = "BUY" if random.random() > 0.5 else "SELL"
            reasoning = f"Algorithmic analysis detected {pattern} pattern with {random.randint(75, 95)}% confidence. Statistical backtesting shows {random.randint(60, 85)}% win rate for this setup."
        else:
            decision = "HOLD"
            reasoning = f"No clear algorithmic signals detected. Current market volatility: {random.uniform(0.1, 0.4):.2f}. Awaiting better risk-reward ratio."

    elif model == "fingpt":
        # Financial sentiment focus
        confidence = random.uniform(0.70, 0.90)
        sentiments = ["optimistic", "cautious", "bearish", "bullish", "neutral"]
        sentiment = random.choice(sentiments)
        news_factor = random.choice(["earnings", "fed policy", "geopolitical", "technical"])

        decision = random.choice(["BUY", "SELL", "HOLD"])
        reasoning = f"Financial sentiment analysis shows {sentiment} market mood driven by {news_factor} developments. News flow suggests {decision.lower()}ing pressure with {random.randint(65, 90)}% sentiment confidence."

    elif model == "phi3":
        # Fast, responsive decisions
        confidence = random.uniform(0.65, 0.85)
        timeframes = ["short-term", "medium-term", "immediate"]
        timeframe = random.choice(timeframes)

        decision = random.choice(["BUY", "SELL", "HOLD"])
        reasoning = f"Rapid assessment indicates {timeframe} {decision.lower()} opportunity. Momentum analysis shows {random.randint(55, 80)}% directional strength. Quick execution recommended."

    else:
        decision = random.choice(["BUY", "SELL", "HOLD"])
        confidence = random.uniform(0.6, 0.8)
        reasoning = f"Standard analysis suggests {decision.lower()} position."

    return InferenceResponse(
        text=f"Decision: {decision}",
        confidence=round(confidence, 2),
        reasoning=reasoning,
        model_used=config["name"]
    )

@app.get("/")
async def root():
    model = get_model_from_path(app.url_path_for("root"))
    config = MODEL_CONFIGS[model]
    return {
        "status": "running",
        "service": f"{config['name']} Trading Model",
        "model": config["name"],
        "strengths": config["strengths"],
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    model = get_model_from_path(app.url_path_for("health"))
    return {
        "status": "healthy",
        "model": MODEL_CONFIGS[model]["name"],
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/inference")
async def inference(request: InferenceRequest):
    """Generate trading inference"""
    model = get_model_from_path(app.url_path_for("inference"))
    response = generate_trading_decision(model, request.prompt, request.context)
    return response

@app.post("/chat/completions")
async def chat_completions(request: dict):
    """OpenAI-compatible chat completions endpoint"""
    model = get_model_from_path(app.url_path_for("chat_completions"))

    # Extract prompt from messages
    messages = request.get("messages", [])
    if messages:
        prompt = messages[-1].get("content", "")
    else:
        prompt = request.get("prompt", "")

    inference_response = generate_trading_decision(model, prompt, request)

    # Return OpenAI-compatible format
    return {
        "id": f"chatcmpl-{random.randint(1000, 9999)}",
        "object": "chat.completion",
        "created": int(datetime.utcnow().timestamp()),
        "model": inference_response.model_used,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": f"{inference_response.text}\n\nReasoning: {inference_response.reasoning}"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(inference_response.text.split()),
            "total_tokens": len(prompt.split()) + len(inference_response.text.split())
        }
    }

if __name__ == "__main__":
    import uvicorn
    # When run as app.py, the module name is __main__, so use the app object directly
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
