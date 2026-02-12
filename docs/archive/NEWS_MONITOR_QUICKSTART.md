# 🚀 Telegram News Monitor - Quick Start

Get your Sapphire trading system responding to market news in 5 minutes.

---

## 1. Add Credentials to `.env`

```bash
# Add these to your .env file
API_ID=20785477
API_HASH=331de234a1c2b2937a054912379b91e1
```

---

## 2. Authenticate (One-Time)

```bash
cd /Users/aribs/Documents/Sapphire_Claude_V1.0/sapphire_repo
python configure_news_monitor.py list
```

Follow the prompts:
- Enter your phone number (e.g., +1234567890)
- Enter the 2FA code from Telegram
- Session saved to `client_session.session`

---

## 3. Find Your Alpha Groups

From step 2, you'll see all your chats. Look for:

```
📋 Available Chats/Channels:

ID              Type         Name
-1001234567890  📢 Channel   Crypto Alpha Signals
-1009876543210  👥 Group     DeFi Research Group
-1007654321098  📢 Channel   Breaking Crypto News
```

Copy the IDs of channels you want to monitor.

---

## 4. Test Locally

```bash
python configure_news_monitor.py test -1001234567890 -1009876543210
```

Watch as it processes messages and generates trading insights!

Press Ctrl+C when done.

---

## 5. Enable in Production

Add to your `.env`:

```bash
# Enable news monitor
ENABLE_NEWS_MONITOR=true

# Channels to monitor (comma-separated)
NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210
```

---

## 6. Deploy

The news monitor will automatically start with your trading system.

```bash
# Deploy to Cloud Run
gcloud builds submit --config=cloudbuild_singapore_backend.yaml
```

---

## ✅ You're Done!

Your trading agents now react to news from your alpha groups in real-time.

**Next Steps:**
- Review [NEWS_MONITOR_GUIDE.md](NEWS_MONITOR_GUIDE.md) for advanced configuration
- Add more high-quality news sources
- Monitor performance and adjust confidence thresholds

---

## 📊 Check Status

```bash
# View news monitor stats
curl https://your-deployment.run.app/news/stats

# View monitored chats
curl https://your-deployment.run.app/news/chats
```

---

## 🛑 Troubleshooting

**Can't authenticate?**
- Make sure API_ID and API_HASH are correct
- Check your phone number format (+1234567890)

**No insights generated?**
- Messages might not be trading-related (AI filters them)
- Try test mode first: `python configure_news_monitor.py test <chat_id>`

**"Session file not found" in production?**
- Copy `client_session.session` to your Docker container
- Or add to Secret Manager (see full guide)

---

## 📚 Full Documentation

See [NEWS_MONITOR_GUIDE.md](NEWS_MONITOR_GUIDE.md) for:
- Security best practices
- API endpoints
- Integration with trading agents
- Advanced configuration
- Troubleshooting guide
