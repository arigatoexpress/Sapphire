# Sapphire Workbench (Windows PC — RTX 5070 Ti)

Local AI compute node: RTX 5070 Ti (16GB VRAM), 64GB RAM.
Tailscale IP: 100.71.10.48

## Services

### TradingView Webhook Receiver (port 9090)
Receives TradingView alerts, enriches with Ollama AI analysis, forwards to rari1.
- `tradingview/webhook_receiver.py` — FastAPI server (run: `python webhook_receiver.py`)
- `tradingview/tradingview_handler.py` — Core alert parsing and routing logic
- `tradingview/pair_trading_logic.py` — Pair trading signal processing
- `tradingview/alphastream_integration.py` — Alpha Vantage + signal aggregation

Public URL (ephemeral): https://presents-exploration-grocery-retirement.trycloudflare.com
Production URL (planned): webhook.sapphirealpha.xyz

### Ollama Local LLM (port 11434)
- Model: gemma3:27b (15.5GB VRAM, Google's flagship open model)
- Secondary: deepseek-r1:14b (math/reasoning for trading analysis)
- Embedding: nomic-embed-text (RAG over trading data)
- Start: Run start_ollama.bat from Startup folder or Startup folder auto-starts it

### AI Self-Improvement Engine (AsterAI harvest)
- `../alpha-engine/src/self_improvement/` — Genetic algorithm strategy optimizer
- `../alpha-engine/src/risk/` — Kelly criterion, Monte Carlo, dynamic position sizing

## Startup
Both Ollama and webhook receiver have startup bat files in:
`C:\Users\aribs\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\`

## Environment
- Python 3.13.3 (FastAPI, uvicorn, aiohttp, ccxt, lighter-sdk, pandas, numpy)
- Cloudflared 2025.8.1 (for tunneling)
- Tailscale v1.94.2
- Ollama 0.17.0
