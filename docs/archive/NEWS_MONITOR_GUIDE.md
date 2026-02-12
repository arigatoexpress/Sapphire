# Telegram News Monitor for Sapphire V2.3

## Overview

The Telegram News Monitor is a second Telegram bot that listens to your news/alpha groups and uses AI to extract actionable trading intelligence for your autonomous trading agents.

**Key Features:**
- 📡 Monitors Telegram channels/groups for crypto news and alpha
- 🧠 AI-powered analysis using Gemini 2.0 Flash Experimental
- 🎯 Extracts trading signals (tokens, sentiment, suggested action)
- ⚡ Real-time integration with autonomous trading agents
- 🔒 Uses User Client (not bot) - can access all groups you're in

---

## Architecture

```
Telegram Groups/Channels
         ↓
TelegramNewsMonitor (Telethon User Client)
         ↓
NewsIntelligenceAgent (Gemini AI Analysis)
         ↓
NewsInsight (Structured Trading Signal)
         ↓
TradingOrchestrator → Autonomous Agents
```

**Components:**

1. **TelegramNewsMonitor** (`telegram_news_monitor.py`)
   - Connects to Telegram as user client
   - Listens to configured channels/groups
   - Forwards messages to intelligence agent

2. **NewsIntelligenceAgent** (`news_intelligence_agent.py`)
   - Uses Gemini 2.0 Flash to analyze messages
   - Extracts: tokens, sentiment, urgency, confidence
   - Deduplicates and filters noise

3. **NewsTradingIntegration** (`news_trading_integration.py`)
   - Connects monitor + intelligence agent
   - Forwards insights to trading system
   - Manages lifecycle

---

## Setup

### 1. Get Telegram API Credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Click "API development tools"
4. Create a new application
5. Copy your `API_ID` and `API_HASH`

### 2. Add to Environment Variables

Add to your `.env` file:

```bash
# Telegram News Monitor Credentials
API_ID=20785477
API_HASH=331de234a1c2b2937a054912379b91e1

# Optional: Specific chat IDs to monitor (comma-separated)
# Leave empty to monitor ALL chats
NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210

# Enable news monitor in production
ENABLE_NEWS_MONITOR=true
```

### 3. First-Time Authentication

The first time you run the monitor, you'll need to authenticate:

```bash
python configure_news_monitor.py list
```

This will:
- Prompt you for your phone number
- Send a 2FA code to Telegram
- Save session to `client_session.session`

**Important:** Keep `client_session.session` secure! It's your authentication token.

---

## Usage

### List Available Chats

Find chat IDs to monitor:

```bash
python configure_news_monitor.py list
```

Output:
```
📋 Available Chats/Channels:

ID              Type         Name                                     Unread
--------------------------------------------------------------------------------
-1001234567890  📢 Channel   Crypto Alpha Signals                     5
-1009876543210  👥 Group     DeFi Research Group                      12
-1007654321098  📢 Channel   Breaking Crypto News                     0
```

### Test News Monitor

Test monitoring specific chats with AI analysis:

```bash
python configure_news_monitor.py test -1001234567890 -1009876543210
```

This will:
- Connect to Telegram
- Monitor specified chats
- Analyze messages with AI
- Print trading insights in real-time

Example output:
```
================================================================================
💡 TRADING INSIGHT #1
================================================================================
Source: Crypto Alpha Signals
Tokens: SOL, ETH
Sentiment: BULLISH | Action: BUY
Urgency: HIGH | Confidence: 85%

Reasoning: Message indicates strong bullish momentum for SOL/ETH pair with
technical breakout confirmed. Volume surge supports upward movement.

Key Points:
  1. SOL broke resistance at $125 with high volume
  2. ETH/SOL ratio showing strength
  3. On-chain metrics bullish (increased DEX activity)

Original Message: 🚨 BREAKING: SOL just broke $125 resistance with massive...
================================================================================
```

### Test Monitoring ALL Chats

Monitor everything (useful for discovery):

```bash
python configure_news_monitor.py test-all
```

⚠️ **Warning:** This processes ALL your Telegram messages. Consider using specific chat IDs for production.

---

## Production Deployment

### Enable in Production

The news monitor automatically starts when deployed if `ENABLE_NEWS_MONITOR=true` is set.

Add to `cloudbuild_singapore_backend.yaml` environment variables:

```yaml
env:
  - ENABLE_NEWS_MONITOR=true
  - NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210
```

### Add Secrets to GCP

Store Telegram credentials in Secret Manager:

```bash
# Store API_ID
echo -n "20785477" | gcloud secrets create telegram-api-id \
  --data-file=- \
  --project=sapphire-479610

# Store API_HASH
echo -n "331de234a1c2b2937a054912379b91e1" | gcloud secrets create telegram-api-hash \
  --data-file=- \
  --project=sapphire-479610
```

Update credentials loader to fetch these secrets.

### Deploy Session File

The `client_session.session` file must be deployed with your container.

**Option 1:** Add to Docker image
```dockerfile
COPY client_session.session /app/client_session.session
```

**Option 2:** Store in Secret Manager (recommended)
```bash
# Upload session file
gcloud secrets create telegram-session-file \
  --data-file=client_session.session \
  --project=sapphire-479610

# Download in startup script
gcloud secrets versions access latest \
  --secret=telegram-session-file \
  --project=sapphire-479610 > /app/client_session.session
```

---

## Configuration

### Monitored Chats

**Option 1:** Monitor specific chats (recommended)
```bash
NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210,-1007654321098
```

**Option 2:** Monitor ALL chats
```bash
# Don't set NEWS_MONITOR_CHAT_IDS or leave it empty
```

### AI Analysis Tuning

Edit `news_intelligence_agent.py` to adjust:

- **Relevance threshold**: Only forward high-quality signals
- **Urgency classification**: Define what counts as "critical"
- **Token extraction**: Add custom token mappings
- **Sentiment analysis**: Customize bullish/bearish detection

Example customization:

```python
# In _build_analysis_prompt():
**Guidelines:**
- Only set is_relevant=true if confidence > 70%
- urgency=critical only for exchange listings, major hacks, or regulatory news
- Map common names: "solana" → "SOL", "ethereum" → "ETH"
```

---

## API Endpoints

The news monitor exposes these endpoints:

### Get News Monitor Stats

```bash
GET /news/stats
```

Response:
```json
{
  "running": true,
  "monitored_chats": 3,
  "intelligence": {
    "total_processed": 45,
    "active_callbacks": 1,
    "model": "gemini-2.0-flash-exp"
  }
}
```

### Get Monitored Chats

```bash
GET /news/chats
```

Response:
```json
{
  "chats": [
    {
      "id": -1001234567890,
      "name": "Crypto Alpha Signals",
      "type": "Channel",
      "username": "cryptoalphasignals"
    }
  ]
}
```

### Add/Remove Monitored Chats

```bash
POST /news/chats/add
{
  "chat_id": -1001234567890
}
```

```bash
POST /news/chats/remove
{
  "chat_id": -1001234567890
}
```

---

## Integration with Trading Agents

News insights are forwarded to your autonomous trading agents via the `on_news_insight` callback in the orchestrator.

Current implementation logs insights. To enable trading:

1. **Forward to AgentOrchestrator**:
```python
async def on_news_insight(insight):
    # Forward to specific platform agents
    for token in insight.affected_tokens:
        if insight.suggested_action == "buy" and insight.confidence > 0.7:
            await self.agent_orchestrator.process_news_signal(
                token=token,
                action=insight.suggested_action,
                reasoning=insight.reasoning
            )
```

2. **Create News-Based Strategies**:
   - Momentum trading on "high" urgency signals
   - Counter-trading on "critical" FUD signals
   - Position sizing based on confidence scores

3. **Risk Management**:
   - Set max allocation per news signal (e.g., 5% of portfolio)
   - Require multiple confirmations for large trades
   - Implement cooldown periods between news-driven trades

---

## Troubleshooting

### "Could not connect to Telegram"

**Solution:** Check credentials:
```bash
echo $API_ID
echo $API_HASH
```

If empty, add to `.env` and reload.

### "Session file not found"

**Solution:** Authenticate first:
```bash
python configure_news_monitor.py list
```

This creates `client_session.session`.

### "Too many requests from Telegram"

**Solution:** Telegram has rate limits. Wait 1 hour and try again.

### "Gemini API error"

**Solution:** Check Gemini API key:
```bash
echo $GEMINI_API_KEY
```

Ensure it's configured in Secret Manager.

### "No insights generated"

**Possible causes:**
1. Messages not trading-related (AI filters them out)
2. Relevance threshold too high
3. Model not initialized properly

**Debug:**
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python configure_news_monitor.py test -1001234567890
```

---

## Best Practices

### 1. Start with High-Quality Sources

Monitor channels known for accurate alpha:
- Established analysts
- Project official announcements
- Reputable news outlets

Avoid:
- Shill groups
- Pump & dump channels
- Unverified "insider" groups

### 2. Use Confidence Thresholds

Only trade on high-confidence signals:
```python
if insight.confidence > 0.75 and insight.urgency in ["high", "critical"]:
    # Take action
```

### 3. Combine with On-Chain Data

News should confirm what you see on-chain:
```python
if insight.sentiment == "bullish":
    # Check if volume is actually increasing
    # Verify with DEX metrics
    # Confirm with technical analysis
```

### 4. Monitor Performance

Track which sources generate profitable signals:
```python
# Log news-driven trades
{
  "source": insight.source_chat,
  "token": token,
  "pnl": +$125.50,
  "confidence": 0.85
}
```

### 5. Implement Circuit Breakers

Stop trading on news if losing money:
```python
if news_driven_trades_pnl < -$500:
    # Disable news monitor for 24h
    await news_monitor.stop()
```

---

## Security Considerations

### Session File Protection

The `client_session.session` file is equivalent to your Telegram password.

**Best practices:**
- Never commit to Git (add to `.gitignore`)
- Store in Secret Manager for production
- Rotate periodically by deleting and re-authenticating

### API Credentials

- Store `API_ID` and `API_HASH` in Secret Manager
- Never hardcode in source code
- Use environment variables for local development

### Access Control

- News monitor has access to ALL your Telegram messages
- Only deploy to trusted infrastructure
- Monitor logs for suspicious activity

---

## Future Enhancements

### Planned Features

1. **Multi-Model Analysis**: Combine Gemini + GPT-4 for consensus
2. **Sentiment Scoring**: Historical accuracy tracking per source
3. **Auto-Discovery**: Suggest new alpha channels based on performance
4. **Alert Filtering**: Reduce noise with learned user preferences
5. **Multi-Language Support**: Translate non-English alpha
6. **Image Analysis**: OCR for chart screenshots
7. **Telegram Bot Interface**: Control monitor via Telegram commands

### Integration Ideas

1. **Twitter/X Monitoring**: Add Twitter API for broader coverage
2. **Discord Integration**: Monitor Discord alpha channels
3. **On-Chain Alerts**: Combine with whale wallet tracking
4. **News Aggregation**: Fetch from CoinDesk, CoinTelegraph APIs
5. **Backtesting**: Test historical news signals against price data

---

## Support

For issues or questions:
1. Check logs: `docker logs sapphire-backend`
2. Review this guide
3. Test with `configure_news_monitor.py`
4. Check Telegram session validity

---

## License

Part of Sapphire V2.3 Autonomous Trading System.
All rights reserved.
