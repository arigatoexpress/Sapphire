"""
Minimal API - Static Data Only

Extremely simple FastAPI application that returns static data
without any complex imports or dependencies. Used as emergency
fallback when the main APIs can't be loaded.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

app = FastAPI(title="Sapphire Trade - Minimal API", version="1.0.0-minimal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static data for demonstration
PORTFOLIO_DATA = {
    'total_capital': 3500,
    'agent_capital': 500,
    'agent_count': 6,
    'status': 'operational',
    'timestamp': datetime.utcnow().isoformat(),
    'agents': {
        'trend-momentum-agent': {'status': 'active', 'last_trade': None},
        'strategy-optimization-agent': {'status': 'active', 'last_trade': None},
        'financial-sentiment-agent': {'status': 'active', 'last_trade': None},
        'market-prediction-agent': {'status': 'active', 'last_trade': None},
        'volume-microstructure-agent': {'status': 'active', 'last_trade': None},
        'vpin-hft': {'status': 'active', 'last_trade': None}
    }
}

AGENT_ACTIVITIES = [
    {
        'agent_id': f'{agent}-1',
        'agent_type': agent,
        'agent_name': agent.replace('-', ' ').title(),
        'activity_score': 0.5 + (hash(agent) % 50) / 100,
        'communication_count': hash(agent) % 20,
        'trading_count': 0,
        'last_activity': datetime.utcnow().isoformat(),
        'participation_threshold': 0.7,
        'specialization': {
            'trend-momentum-agent': 'Momentum Analysis',
            'strategy-optimization-agent': 'Strategy Optimization',
            'financial-sentiment-agent': 'Sentiment Analysis',
            'market-prediction-agent': 'Market Prediction',
            'volume-microstructure-agent': 'Volume Analysis',
            'vpin-hft': 'VPIN High-Frequency Trading'
        }.get(agent, 'Trading Agent'),
        'color': {
            'trend-momentum-agent': '#06b6d4',
            'strategy-optimization-agent': '#8b5cf6',
            'financial-sentiment-agent': '#ef4444',
            'market-prediction-agent': '#f59e0b',
            'volume-microstructure-agent': '#ec4899',
            'vpin-hft': '#06b6d4'
        }.get(agent, '#6b7280'),
        'status': 'active'
    } for agent in PORTFOLIO_DATA['agents'].keys()
]

@app.get("/healthz")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "minimal_api"}

@app.get("/portfolio-status")
async def get_portfolio_status():
    """Get portfolio status"""
    return PORTFOLIO_DATA

@app.get("/agent-activity")
async def get_agent_activities():
    """Get agent activities"""
    return AGENT_ACTIVITIES

@app.get("/system-status")
async def get_system_status():
    """Get system status"""
    return {
        'service': 'sapphire_trade_minimal',
        'status': 'operational',
        'version': '1.0.0-minimal',
        'uptime': 'N/A',
        'total_capital': 3500,
        'active_agents': 6,
        'features': [
            'Basic portfolio tracking',
            'Agent status monitoring',
            'Static data demonstration',
            'Emergency fallback mode'
        ],
        'limitations': [
            'No real-time trading',
            'Static demonstration data',
            'No complex analytics',
            'Minimal functionality'
        ]
    }

@app.get("/trading-signals")
async def get_trading_signals():
    """Get trading signals (empty for demo)"""
    return {
        "signals": [],
        "message": "Minimal API - demonstration mode",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Sapphire Trade Minimal API",
        "status": "operational",
        "capital": "$3,500 allocated",
        "agents": "6 AI agents configured"
    }
