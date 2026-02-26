"""
Sapphire OS - TradingView Webhook Receiver v2.0
With comprehensive structured logging and metrics
"""

import os
import sys
import json
import time
import asyncio
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, asdict
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import httpx
import uvicorn

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from services.shared.logging_config import get_webhook_logger, get_trading_logger

# Initialize loggers
webhook_logger = get_webhook_logger()
trading_logger = get_trading_logger()

# Configuration
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "sapphire_trading_2024")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma3:27b")
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "projects/sapphire-479610/topics/trading-signals")
GCP_PROJECT = os.environ.get("GCP_PROJECT", "sapphire-479610")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://sapphire-gateway-s77j6bxyra-uc.a.run.app")

# Stats tracking
@dataclass
class WebhookStats:
    total: int = 0
    published: int = 0
    errors: int = 0
    ai_enriched: int = 0
    pubsub_success: int = 0
    gateway_fallback: int = 0
    last_alert: Optional[str] = None
    last_error: Optional[str] = None

stats = WebhookStats()

app = FastAPI(title="Sapphire TradingView Webhook")

# Alert counter for unique IDs
alert_counter = 0

async def enrich_with_ollama(symbol: str, action: str, z_score: float = 0, 
                             confidence: float = 0.85) -> Dict:
    """Enrich signal with Ollama AI analysis"""
    start_time = time.time()
    
    try:
        prompt = f"""Analyze this trading signal:
Symbol: {symbol}
Action: {action}
Z-Score: {z_score}
Confidence: {confidence}

Provide a brief analysis (max 100 words) of whether this signal aligns with typical market conditions. 
Respond with ONLY valid JSON in this exact format:
{{"verdict": "proceed|caution|reject", "confidence": 0.0-1.0, "reason": "brief reason"}}"""
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get("response", "{}")
                
                # Extract JSON from response
                try:
                    # Find JSON in the response text
                    start = response_text.find("{")
                    end = response_text.rfind("}") + 1
                    if start >= 0 and end > start:
                        verdict_data = json.loads(response_text[start:end])
                    else:
                        verdict_data = {"verdict": "proceed", "confidence": 0.5, "reason": "Default"}
                except json.JSONDecodeError:
                    verdict_data = {"verdict": "proceed", "confidence": 0.5, "reason": "Parse error"}
                
                latency_ms = int((time.time() - start_time) * 1000)
                
                webhook_logger.log_ollama_enrichment(
                    request_id=f"enrich_{symbol}_{int(time.time())}",
                    symbol=symbol,
                    verdict=verdict_data.get("verdict", "unknown"),
                    latency_ms=latency_ms
                )
                
                stats.ai_enriched += 1
                return verdict_data
            else:
                webhook_logger.warning(
                    f"Ollama returned {response.status_code}",
                    event_type="ollama_error",
                    status_code=response.status_code
                )
                return {"verdict": "proceed", "confidence": 0.5, "reason": "Ollama unavailable"}
                
    except Exception as e:
        webhook_logger.error(
            f"Ollama enrichment failed: {str(e)}",
            event_type="ollama_exception",
            error=str(e)
        )
        return {"verdict": "proceed", "confidence": 0.5, "reason": f"Error: {str(e)[:50]}"}

async def publish_to_pubsub(signal_data: Dict) -> Dict:
    """Publish signal to GCP Pub/Sub"""
    try:
        from google.cloud import pubsub_v1
        
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(GCP_PROJECT, "trading-signals")
        
        message_data = json.dumps(signal_data).encode("utf-8")
        future = publisher.publish(topic_path, message_data, signal_id=signal_data.get("signal_id", "unknown"))
        message_id = future.result()
        
        trading_logger.log_signal_published(
            signal_id=signal_data.get("signal_id"),
            symbol=signal_data.get("symbol"),
            channel="pubsub",
            message_id=message_id
        )
        
        stats.pubsub_success += 1
        return {"published": True, "channel": "pubsub", "message_id": message_id}
        
    except Exception as e:
        webhook_logger.error(
            f"Pub/Sub publish failed: {str(e)}",
            event_type="pubsub_error",
            error=str(e)
        )
        # Fallback to HTTPS gateway
        return await forward_to_gateway(signal_data)

async def forward_to_gateway(signal_data: Dict) -> Dict:
    """Forward signal to gateway via HTTPS (fallback)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{GATEWAY_URL}/api/signals/create",
                json=signal_data,
                headers={"Content-Type": "application/json"}
            )
            
            stats.gateway_fallback += 1
            
            webhook_logger.info(
                f"Forwarded to gateway: {response.status_code}",
                event_type="gateway_forward",
                status_code=response.status_code
            )
            
            return {
                "published": response.status_code == 200,
                "channel": "gateway",
                "status_code": response.status_code
            }
            
    except Exception as e:
        webhook_logger.error(
            f"Gateway forward failed: {str(e)}",
            event_type="gateway_error",
            error=str(e)
        )
        stats.errors += 1
        return {"published": False, "channel": "none", "error": str(e)}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "webhook-receiver",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/status")
async def status():
    """Detailed status endpoint"""
    return {
        "status": "active",
        "version": "2.0.0",
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "pubsub_topic": PUBSUB_TOPIC,
        "pubsub_available": True,
        "gateway_url": GATEWAY_URL,
        "stats": asdict(stats),
        "supported_actions": [
            "buy", "sell", "long", "short", "exit", "close",
            "entry_long", "entry_short", "exit_long", "exit_short"
        ],
        "symbol_map": {
            "ETHBTC": "ETHBTC",
            "SOLBTC": "SOLBTC",
            "ZECBTC": "ZECBTC",
            "BTCUSDT": "BTCUSDT",
            "ETHUSDT": "ETHUSDT",
            "HYPEUSDT": "HYPEUSDT",
            "SOLUSDT": "SOLUSDT",
            "HYPERUSDT": "HYPEUSDT"
        }
    }

@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs (for debugging)"""
    # In production, this would query Cloud Logging or Firestore
    return {
        "note": "Logs available in Cloud Logging",
        "query": f"resource.labels.service_name=webhook-receiver",
        "limit": limit
    }

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive TradingView webhook alerts"""
    global alert_counter
    alert_counter += 1
    alert_id = alert_counter
    
    client_ip = request.client.host if request.client else "unknown"
    request_id = f"webhook_{alert_id}_{int(time.time())}"
    
    webhook_logger.log_request_received(
        request_id=request_id,
        client_ip=client_ip
    )
    
    try:
        # Parse request
        payload = await request.json()
        
        symbol = payload.get("symbol", "UNKNOWN")
        action = payload.get("action", "unknown")
        
        webhook_logger.log_request_received(
            request_id=request_id,
            client_ip=client_ip,
            symbol=symbol,
            action=action
        )
        
        # Validate secret
        secret = request.headers.get("X-Webhook-Secret")
        if secret != WEBHOOK_SECRET:
            webhook_logger.warning(
                f"Invalid webhook secret from {client_ip}",
                event_type="invalid_secret",
                request_id=request_id,
                client_ip=client_ip
            )
            raise HTTPException(status_code=401, detail="Invalid secret")
        
        webhook_logger.log_request_validated(
            request_id=request_id,
            validation_result=True
        )
        
        stats.total += 1
        
        # Generate signal ID
        signal_id = f"sig_{int(time.time())}_{alert_id}"
        
        # Log signal received
        trading_logger.log_signal_received(
            signal_id=signal_id,
            symbol=symbol,
            action=action,
            source="tradingview",
            price=payload.get("price"),
            confidence=payload.get("confidence")
        )
        
        # Validate signal
        validation = {
            "valid": True,
            "symbol_recognized": symbol in ["ETHBTC", "SOLBTC", "ZECBTC", "BTCUSDT", "ETHUSDT", "HYPEUSDT", "SOLUSDT"],
            "action_recognized": action in ["buy", "sell", "long", "short", "exit", "close", "entry_long", "entry_short", "exit_long", "exit_short"],
            "has_price": payload.get("price") is not None
        }
        
        trading_logger.log_signal_validated(
            signal_id=signal_id,
            symbol=symbol,
            validation_result=validation
        )
        
        # AI enrichment (async in background)
        z_score = payload.get("z_score", 0)
        confidence = payload.get("confidence", 0.85)
        
        ai_verdict = await enrich_with_ollama(symbol, action, z_score, confidence)
        
        # Build signal
        signal = {
            "signal_id": signal_id,
            "alert_id": alert_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": "tradingview",
            "symbol": symbol,
            "action": action,
            "side": "BUY" if action in ["buy", "long", "entry_long"] else "SELL" if action in ["sell", "short", "entry_short"] else "CLOSE",
            "signal_type": "entry" if "entry" in action or action in ["buy", "long"] else "exit" if "exit" in action else "unknown",
            "price": payload.get("price"),
            "z_score": z_score,
            "confidence": confidence,
            "ai_verdict": ai_verdict,
            "exchange": payload.get("exchange", "UNKNOWN"),
            "interval": payload.get("interval", "unknown"),
            "strategy": payload.get("strategy", "manual"),
            "metadata": {
                "webhook_ip": client_ip,
                "request_id": request_id,
                "validated": True
            }
        }
        
        # Publish to Pub/Sub (in background for speed)
        publish_result = await publish_to_pubsub(signal)
        
        if publish_result["published"]:
            stats.published += 1
            stats.last_alert = datetime.utcnow().isoformat()
        else:
            stats.errors += 1
            stats.last_error = f"Failed to publish: {publish_result.get('error', 'unknown')}"
        
        webhook_logger.log_response_sent(
            request_id=request_id,
            status_code=200,
            signal_id=signal_id
        )
        
        return {
            "status": "ok",
            "alert_id": alert_id,
            "signal_id": signal_id,
            "symbol": symbol,
            "action": action,
            "side": signal["side"],
            "signal_type": signal["signal_type"],
            "ai_verdict": ai_verdict,
            "publish": publish_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        webhook_logger.error(
            f"Webhook processing error: {error_msg}",
            event_type="webhook_exception",
            request_id=request_id,
            error=error_msg
        )
        trading_logger.log_signal_error(
            signal_id=f"sig_{int(time.time())}_{alert_id}",
            error=error_msg,
            stage="webhook_processing"
        )
        stats.errors += 1
        stats.last_error = error_msg
        raise HTTPException(status_code=500, detail=f"Processing error: {error_msg}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9090))
    webhook_logger.info(f"Starting webhook receiver on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
