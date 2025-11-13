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
    'agent_count': 7,
    'status': 'operational',
    'timestamp': datetime.utcnow().isoformat(),
    'agents': {
        'trend_momentum_agent': {'status': 'active', 'last_trade': None},
        'strategy_optimization_agent': {'status': 'active', 'last_trade': None},
        'financial_sentiment_agent': {'status': 'active', 'last_trade': None},
        'market_prediction_agent': {'status': 'active', 'last_trade': None},
        'volume_microstructure_agent': {'status': 'active', 'last_trade': None},
        'freqtrade': {'status': 'standby', 'last_trade': None},
        'hummingbot': {'status': 'standby', 'last_trade': None}
    }
}

AGENT_ACTIVITIES = [
    {
        'agent_id': f'{agent.replace("_", "-")}-1',
        'agent_type': agent,
        'agent_name': agent.replace('_', ' ').title(),
        'activity_score': 0.5 + (hash(agent) % 50) / 100,
        'communication_count': hash(agent) % 20,
        'trading_count': 0,
        'last_activity': datetime.utcnow().isoformat(),
        'participation_threshold': 0.7,
        'specialization': {
            'trend_momentum_agent': 'Momentum Analysis',
            'strategy_optimization_agent': 'Strategy Optimization',
            'financial_sentiment_agent': 'Sentiment Analysis',
            'market_prediction_agent': 'Market Prediction',
            'volume_microstructure_agent': 'Volume Analysis',
            'freqtrade': 'Algorithmic Trading',
            'hummingbot': 'Market Making'
        }.get(agent, 'Trading Agent'),
        'color': {
            'trend_momentum_agent': '#3b82f6',
            'strategy_optimization_agent': '#8b5cf6',
            'financial_sentiment_agent': '#10b981',
            'market_prediction_agent': '#f59e0b',
            'volume_microstructure_agent': '#ef4444',
            'freqtrade': '#06b6d4',
            'hummingbot': '#84cc16'
        }.get(agent, '#6b7280'),
        'status': 'active' if agent != 'freqtrade' and agent != 'hummingbot' else 'standby'
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
        'active_agents': 5,
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
        "agents": "7 AI agents configured"
    }
