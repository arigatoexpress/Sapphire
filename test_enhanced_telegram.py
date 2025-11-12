#!/usr/bin/env python3
"""Test script for enhanced Telegram AI bot."""
import asyncio
import os
from cloud_trader.enhanced_telegram import (
    EnhancedTelegramService,
    TradeNotification,
    MarketInsight,
    NotificationPriority,
    AITradingAnalyzer,
    MarketSentimentAnalyzer,
    RiskAnalyzer
)

async def test_enhanced_telegram():
    """Test the enhanced Telegram bot functionality."""
    # Get credentials from environment or secrets
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not bot_token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables required")
        return

    print("🤖 Testing Enhanced Telegram AI Bot...")
    print(f"Bot Token: {bot_token[:10]}...")
    print(f"Chat ID: {chat_id}")

    try:
        # Initialize AI components
        ai_analyzer = AITradingAnalyzer()
        sentiment_analyzer = MarketSentimentAnalyzer()
        risk_analyzer = RiskAnalyzer()

        # Create enhanced Telegram service
        telegram_service = EnhancedTelegramService(
            bot_token=bot_token,
            chat_id=chat_id,
            ai_analyzer=ai_analyzer,
            sentiment_analyzer=sentiment_analyzer,
            risk_analyzer=risk_analyzer
        )

        print("✅ Enhanced Telegram service created")

        # Test 1: Send startup notification
        print("📤 Testing startup notification...")
        await telegram_service.send_startup_notification()
        print("✅ Startup notification sent")

        # Test 2: Send trade notification
        print("📤 Testing trade notification...")
        trade = TradeNotification(
            symbol="BTC/USDT",
            side="BUY",
            price=43250.50,
            quantity=0.0234,
            notional=1012.47,
            take_profit=44500.00,
            stop_loss=41800.00,
            confidence=0.85,
            ai_analysis="Strong bullish momentum detected with increasing volume. RSI indicates oversold conditions with positive divergence."
        )

        await telegram_service.send_trade_notification(trade, NotificationPriority.HIGH)
        print("✅ Trade notification sent")

        # Test 3: Send market insight
        print("📤 Testing market insight...")
        insight = MarketInsight(
            symbol="ETH/USDT",
            sentiment="bullish",
            confidence=0.78,
            key_levels={
                "Support": 2847.00,
                "Resistance": 3120.00,
                "Target": 3050.00
            },
            recommendation="Accumulate on dips",
            analysis="Ethereum showing strong accumulation patterns with institutional buying pressure. Network fundamentals remain strong."
        )

        await telegram_service.send_market_insight(insight)
        print("✅ Market insight sent")

        # Test 4: Send risk alert
        print("📤 Testing risk alert...")
        await telegram_service.send_risk_alert(
            alert_type="High Exposure",
            severity="medium",
            message="Portfolio exposure has reached 85% of maximum allowed limit.",
            recommendations=[
                "Consider reducing position sizes",
                "Implement additional stop losses",
                "Monitor market volatility closely"
            ]
        )
        print("✅ Risk alert sent")

        # Test 5: Send performance summary
        print("📤 Testing performance summary...")
        metrics = {
            'total_trades': 15,
            'win_rate': 0.73,
            'total_pnl': 2847.32,
            'sharpe_ratio': 2.34,
            'max_drawdown': 0.023,
            'total_volume': 45670.0,
            'recommendations': [
                "Continue current strategy",
                "Consider increasing position sizes for high-confidence signals",
                "Monitor correlation with BTC"
            ]
        }

        ai_commentary = (
            "Excellent performance this week with 73% win rate and Sharpe ratio of 2.34. "
            "Risk-adjusted returns are outstanding. The strategy is effectively capturing "
            "market opportunities while maintaining strict risk controls."
        )

        await telegram_service.send_performance_summary("weekly", metrics, ai_commentary)
        print("✅ Performance summary sent")

        print("🎉 All enhanced Telegram bot tests completed successfully!")
        print("📱 Check your Telegram for the test notifications")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Load environment variables from secrets if running in GCP
    try:
        import google.cloud.secretmanager as secretmanager
        client = secretmanager.SecretManagerServiceClient()

        project_id = "sapphireinfinite"

        # Get bot token
        name = f"projects/{project_id}/secrets/TELEGRAM_BOT_TOKEN/versions/latest"
        response = client.access_secret_version(request={"name": name})
        os.environ['TELEGRAM_BOT_TOKEN'] = response.payload.data.decode('UTF-8')

        # Get chat ID
        name = f"projects/{project_id}/secrets/TELEGRAM_CHAT_ID/versions/latest"
        response = client.access_secret_version(request={"name": name})
        os.environ['TELEGRAM_CHAT_ID'] = response.payload.data.decode('UTF-8')

        print("🔐 Loaded credentials from GCP Secret Manager")

    except Exception as e:
        print(f"⚠️  Could not load from Secret Manager: {e}")
        print("Using environment variables...")

    asyncio.run(test_enhanced_telegram())
