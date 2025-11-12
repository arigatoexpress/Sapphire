# Multi-Agent AI Trading Features

## Overview

Sapphire AI implements advanced multi-agent collaboration for trading decisions, leveraging parallel queries to FinGPT and Lag-Llama agents for enhanced accuracy and robustness.

## Key Features

### 1. Parallel Agent Queries

For optimized symbols (AVAX and ARB), the system queries multiple AI agents simultaneously:

- **AVAX (Avalanche)**: Queries both FinGPT (primary) and Lag-Llama (time-series) in parallel
- **ARB (Arbitrum)**: Queries both Lag-Llama (primary) and FinGPT (sentiment) in parallel
- **Other symbols**: Use assigned agent based on configuration

This parallel approach provides:
- **Faster response times**: Queries happen concurrently using `asyncio.gather()`
- **Better accuracy**: Multiple perspectives inform final decision
- **Resilience**: If one agent fails, the other can still provide analysis

### 2. Intelligent Thesis Selection

When multiple agents respond, the system selects the best thesis using a scoring algorithm:

```
score = confidence × (1 - risk_score)
```

Higher confidence and lower risk = better thesis. The system automatically:
- Compares all agent responses
- Selects the highest-scoring thesis
- Falls back gracefully if agents fail

### 3. Risk Threshold Enforcement

All agent theses must meet a minimum risk threshold (default: 0.7) to be accepted:

- **Above threshold**: Thesis is used for trading decisions
- **Below threshold**: Falls back to deterministic thesis based on market data
- **Configurable**: Set via `RISK_THRESHOLD` environment variable

### 4. Enhanced Prompts with DeFi Context

Agent prompts are enriched with:

- **Volatility regime detection**: Low/Moderate/High based on ATR percentage
- **Chain-specific context**: 
  - AVAX: High-throughput chain (1K+ TPS), DeFi yield farming risks
  - ARB: Layer-2 scaling, rollup volumes, gas fee dynamics
- **DeFi market structure**: Focus on TVL spikes, yield risks, bridge flows

### 5. Response Caching

Agent responses are cached to reduce redundant API calls:

- **Cache TTL**: 10 seconds (configurable via `AGENT_CACHE_TTL_SECONDS`)
- **Cache key**: Based on agent_id, symbol, side, and rounded price
- **Automatic cleanup**: Cache limited to last 100 entries

### 6. Retry Logic with Exponential Backoff

Failed agent queries are automatically retried:

- **Default attempts**: 3 retries (configurable via `AGENT_RETRY_ATTEMPTS`)
- **Backoff**: Exponential (0.5s, 1s, 2s)
- **Graceful degradation**: Falls back to deterministic thesis if all retries fail

### 7. Hallucination Guards

Built-in validation prevents bad agent outputs:

- **FinGPT validation**: Checks for NaN, undefined, and obvious errors
- **Lag-Llama validation**: Rejects forecasts >50% away from current price
- **CI span validation**: Rejects Lag-Llama forecasts with >20% confidence interval span

## Configuration

### Environment Variables

```bash
# Agent endpoints
FINGPT_ENDPOINT="https://your-fingpt-endpoint"
FINGPT_API_KEY="your-api-key"
LAGLLAMA_ENDPOINT="https://your-lagllama-endpoint"
LAGLLAMA_API_KEY="your-api-key"

# Risk controls
RISK_THRESHOLD="0.7"  # Minimum risk score (0-1)
FINGPT_MIN_RISK_SCORE="0.4"  # FinGPT-specific minimum
LAGLLAMA_MAX_CI_SPAN="0.25"  # Maximum confidence interval span

# Performance tuning
MAX_PARALLEL_AGENTS="4"  # Max concurrent agent queries
AGENT_RETRY_ATTEMPTS="3"  # Retry attempts
AGENT_CACHE_TTL_SECONDS="10.0"  # Cache TTL in seconds
```

### Code Configuration

See `cloud_trader/config.py` for all available settings:

```python
from cloud_trader.config import Settings

settings = Settings(
    risk_threshold=0.7,
    max_parallel_agents=4,
    agent_retry_attempts=3,
    agent_cache_ttl_seconds=10.0,
)
```

## Usage

### Automatic (Recommended)

The system automatically uses multi-agent collaboration for AVAX and ARB symbols. No code changes needed!

### Manual Agent Selection

```python
from cloud_trader.open_source import OpenSourceAnalyst
from cloud_trader.config import Settings

settings = Settings()
analyst = OpenSourceAnalyst(settings)

# Query single agent
thesis = await analyst.generate_thesis(
    agent_id="fingpt-alpha",
    symbol="AVAXUSDT",
    side="BUY",
    price=25.0,
    market_context={"change_24h": 2.5, "volume": 1000000, "atr": 0.5}
)

# Query multiple agents in parallel (internal to service)
# The service automatically handles this for AVAX/ARB
```

## Performance

### Latency

- **Sequential queries**: ~2-4 seconds (2 agents × 1-2s each)
- **Parallel queries**: ~1-2 seconds (both agents queried simultaneously)
- **With cache**: ~0ms (instant response from cache)

### Throughput

- **Parallel queries**: Up to 4 agents simultaneously (configurable)
- **Rate limiting**: 2-second minimum interval per agent (prevents API abuse)
- **Caching**: Reduces API calls by ~50-70% for repeated queries

## Monitoring

### Logs

The system logs:
- Parallel agent queries: `INFO` level
- Risk threshold rejections: `INFO` level with details
- Cache hits: `DEBUG` level
- Retry attempts: `DEBUG` level with timing
- Validation failures: `WARNING` level

### Metrics

Prometheus metrics available:
- `llm_inference_time` - Time spent on agent queries
- `llm_confidence` - Confidence scores from agents
- `trade_execution_success` - Successful trades using agent theses

## Troubleshooting

### Agents Not Responding

1. Check endpoint URLs are correct
2. Verify API keys are valid
3. Check network connectivity
4. Review logs for specific error messages

### Theses Being Rejected

1. Check `RISK_THRESHOLD` setting (default 0.7)
2. Review agent responses in logs
3. Adjust `FINGPT_MIN_RISK_SCORE` or `LAGLLAMA_MAX_CI_SPAN` if needed

### High Latency

1. Enable caching: Set `AGENT_CACHE_TTL_SECONDS` appropriately
2. Reduce `AGENT_RETRY_ATTEMPTS` if retries are slow
3. Check agent endpoint performance
4. Consider using fewer parallel agents

### Cache Not Working

1. Verify cache TTL is > 0
2. Check that queries use same parameters (price rounded to 4 decimals)
3. Review cache hit logs at DEBUG level

## Future Enhancements

- [ ] Grok 4 Heavy orchestration for meta-reasoning
- [ ] Sui Nautilus integration for on-chain data enrichment
- [ ] Dynamic agent weighting based on historical performance
- [ ] A/B testing framework for agent combinations
- [ ] Real-time agent performance monitoring dashboard

