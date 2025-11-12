#!/usr/bin/env python3
"""
Central Trading Dashboard Service
Aggregates data from all trading services
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service endpoints
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "https://api.sapphiretrade.xyz/orchestrator")
CLOUD_TRADER_URL = os.getenv("CLOUD_TRADER_URL", "https://cloud-trader-880429861698.us-central1.run.app")

class ModelPerformance(BaseModel):
    """Model performance metrics"""
    model_name: str
    total_decisions: int = 0
    successful_trades: int = 0
    avg_confidence: float = 0.0
    avg_response_time: float = 0.0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    last_decision: Optional[datetime] = None

class LivePosition(BaseModel):
    """Live position data"""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_percent: float
    leverage: int
    model_used: str
    timestamp: datetime

class TradeRecord(BaseModel):
    """Trade execution record"""
    id: str
    symbol: str
    side: str
    quantity: float
    price: float
    timestamp: datetime
    model_used: str
    confidence: float
    pnl: Optional[float] = None
    status: str

class ModelReasoning(BaseModel):
    """Model reasoning data"""
    model_name: str
    decision: str
    reasoning: str
    confidence: float
    context: Dict[str, Any]
    timestamp: datetime
    symbol: str

class DashboardData(BaseModel):
    """Complete dashboard data"""
    portfolio: Dict[str, Any]
    positions: List[LivePosition]
    recent_trades: List[TradeRecord]
    model_performance: List[ModelPerformance]
    model_reasoning: List[ModelReasoning]
    system_status: Dict[str, Any]
    targets: Dict[str, Any]

class DashboardService:
    """Central dashboard aggregator service"""

    def __init__(self):
        self.model_performance: Dict[str, ModelPerformance] = {}
        self.recent_trades: List[TradeRecord] = []
        self.model_reasoning: List[ModelReasoning] = []
        self.positions: List[LivePosition] = []

        # Initialize model performance tracking
        self.model_performance = {
            "deepseek": ModelPerformance(model_name="DeepSeek-Coder-V2"),
            "qwen": ModelPerformance(model_name="Qwen2.5-Coder"),
            "fingpt": ModelPerformance(model_name="FinGPT"),
            "phi3": ModelPerformance(model_name="Phi-3"),
        }

    async def get_portfolio_data(self) -> Dict[str, Any]:
        """Get current portfolio data from orchestrator"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{ORCHESTRATOR_URL}/portfolio")
                if response.status_code == 200:
                    return response.json()
                return {"error": "Failed to fetch portfolio"}
        except Exception as e:
            logger.error(f"Error fetching portfolio: {e}")
            return {"error": str(e)}

    async def get_system_status(self) -> Dict[str, Any]:
        """Get overall system status"""
        status = {
            "services": {},
            "models": {},
            "redis_connected": self.redis_client is not None,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Check service health
        services = {
            "cloud_trader": CLOUD_TRADER_URL,
            "orchestrator": ORCHESTRATOR_URL,
        }

        async with httpx.AsyncClient(timeout=3.0) as client:
            for name, url in services.items():
                try:
                    response = await client.get(f"{url}/health")
                    status["services"][name] = "healthy" if response.status_code == 200 else "unhealthy"
                except:
                    status["services"][name] = "unreachable"

        # Model status (placeholder - would need actual endpoints)
        model_urls = {
            "deepseek": "https://deepseek-trader-880429861698.us-central1.run.app",
            "qwen": "https://qwen-trader-880429861698.us-central1.run.app",
            "fingpt": "https://fingpt-trader-880429861698.us-central1.run.app",
            "phi3": "https://phi3-trader-880429861698.us-central1.run.app",
        }

        for model, url in model_urls.items():
            try:
                async with httpx.AsyncClient(timeout=2.0) as client:
                    response = await client.get(f"{url}/health")
                    status["models"][model] = "healthy" if response.status_code == 200 else "unhealthy"
            except:
                status["models"][model] = "unreachable"

        return status

    async def get_dashboard_data(self) -> DashboardData:
        """Get complete dashboard data"""
        portfolio = await self.get_portfolio_data()
        system_status = await self.get_system_status()

        # Mock some sample data for now
        self._generate_mock_data()

        # Calculate targets based on current performance
        targets = self._calculate_targets()

        return DashboardData(
            portfolio=portfolio,
            positions=self.positions,
            recent_trades=self.recent_trades,
            model_performance=list(self.model_performance.values()),
            model_reasoning=self.model_reasoning,
            system_status=system_status,
            targets=targets
        )

    def _generate_mock_data(self):
        """Generate mock data for demonstration"""
        import random

        # Mock positions
        self.positions = [
            LivePosition(
                symbol="BTCUSDT",
                side="LONG",
                size=0.05,
                entry_price=45000,
                current_price=46500,
                pnl=750,
                pnl_percent=3.33,
                leverage=5,
                model_used="DeepSeek-Coder-V2",
                timestamp=datetime.utcnow()
            ),
            LivePosition(
                symbol="ETHUSDT",
                side="SHORT",
                size=1.2,
                entry_price=2800,
                current_price=2750,
                pnl=600,
                pnl_percent=2.14,
                leverage=3,
                model_used="Qwen2.5-Coder",
                timestamp=datetime.utcnow()
            )
        ]

        # Mock recent trades
        self.recent_trades = [
            TradeRecord(
                id=f"trade_{i}",
                symbol="BTCUSDT" if i % 2 == 0 else "ETHUSDT",
                side="BUY" if i % 3 == 0 else "SELL",
                quantity=random.uniform(0.01, 0.1),
                price=random.uniform(40000, 50000),
                timestamp=datetime.utcnow(),
                model_used=random.choice(["DeepSeek-Coder-V2", "Qwen2.5-Coder", "FinGPT", "Phi-3"]),
                confidence=random.uniform(0.7, 0.95),
                status="completed",
                pnl=random.uniform(-100, 500) if i % 4 != 0 else None
            ) for i in range(10)
        ]

        # Mock reasoning
        self.model_reasoning = [
            ModelReasoning(
                model_name=random.choice(["DeepSeek-Coder-V2", "Qwen2.5-Coder", "FinGPT", "Phi-3"]),
                decision=random.choice(["BUY", "SELL", "HOLD"]),
                reasoning=f"Analysis of market conditions shows {random.choice(['bullish', 'bearish', 'neutral'])} momentum",
                confidence=random.uniform(0.7, 0.95),
                context={"rsi": random.uniform(30, 70), "volume": random.uniform(1000, 5000)},
                timestamp=datetime.utcnow(),
                symbol=random.choice(["BTCUSDT", "ETHUSDT"])
            ) for _ in range(5)
        ]

    def _calculate_targets(self) -> Dict[str, Any]:
        """Calculate performance targets and alerts"""
        targets = {
            "daily_pnl_target": 50.0,  # $50 daily target
            "max_drawdown_limit": -100.0,  # -$100 max loss
            "min_confidence_threshold": 0.7,
            "target_win_rate": 0.55,
            "alerts": []
        }

        # Generate alerts based on current performance
        total_pnl = sum(p.pnl for p in self.positions)
        avg_confidence = sum(p.avg_confidence for p in self.model_performance.values()) / len(self.model_performance)

        if total_pnl < targets["max_drawdown_limit"]:
            targets["alerts"].append("⚠️ Max drawdown limit exceeded")

        if avg_confidence < targets["min_confidence_threshold"]:
            targets["alerts"].append("⚠️ Average confidence below threshold")

        if total_pnl > targets["daily_pnl_target"]:
            targets["alerts"].append("🎯 Daily P&L target achieved")

        return targets

# Global instance
dashboard_service = DashboardService()

# Create FastAPI app
app = FastAPI(
    title="Trading Dashboard API",
    description="Central dashboard for multi-model trading system",
    version="1.0.0"
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
        "service": "trading-dashboard-api",
        "version": "1.0.0"
    }

@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "redis_connected": dashboard_service.redis_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/dashboard", response_model=DashboardData)
async def get_dashboard():
    """Get complete dashboard data"""
    return await dashboard_service.get_dashboard_data()

@app.get("/portfolio")
async def get_portfolio():
    """Get current portfolio data"""
    return await dashboard_service.get_portfolio_data()

@app.get("/trades")
async def get_trades(limit: int = 20):
    """Get recent trades"""
    return dashboard_service.recent_trades[:limit]

@app.get("/models")
async def get_models():
    """Get model performance data"""
    return list(dashboard_service.model_performance.values())

@app.get("/reasoning")
async def get_reasoning(limit: int = 10):
    """Get recent model reasoning"""
    return dashboard_service.model_reasoning[:limit]

@app.get("/status")
async def get_status():
    """Get system status"""
    return await dashboard_service.get_system_status()

@app.get("/targets")
async def get_targets():
    """Get performance targets and alerts"""
    return dashboard_service._calculate_targets()

if __name__ == "__main__":
    uvicorn.run(
        "dashboard_service:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=False
    )
