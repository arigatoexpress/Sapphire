#!/usr/bin/env python3
"""Test script to debug Telegram notifications."""

import asyncio
import os
from cloud_trader.config import get_settings
from cloud_trader.enhanced_telegram import create_enhanced_telegram_service, TradeNotification, NotificationPriority

async def test_telegram_notifications():
    """Test telegram notifications."""
    print("🔍 Testing Telegram notifications...")

    # Get settings
    settings = get_settings()

    print(f"📋 Telegram bot token configured: {bool(settings.telegram_bot_token)}")
    print(f"📋 Telegram chat ID configured: {bool(settings.telegram_chat_id)}")

    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        print("❌ Telegram credentials not configured!")
        return

    # Create telegram service
    print("🤖 Creating Telegram service...")
    telegram_service = await create_enhanced_telegram_service(settings)

    if not telegram_service:
        print("❌ Failed to create Telegram service!")
        return

    print("✅ Telegram service created successfully")

    # Test startup notification
    print("📤 Sending startup notification...")
    try:
        await telegram_service.send_startup_notification()
        print("✅ Startup notification sent!")
    except Exception as e:
        print(f"❌ Failed to send startup notification: {e}")
        return

    # Test trade notification
    print("📤 Sending test trade notification...")
    test_trade = TradeNotification(
        symbol="BTCUSDT",
        side="BUY",
        price=45000.0,
        quantity=0.001,
        notional=45.0,
        take_profit=46000.0,
        stop_loss=44000.0,
        confidence=0.85,
        ai_analysis="Test trade notification from Sapphire Trading AI"
    )

    try:
        await telegram_service.send_trade_notification(test_trade, NotificationPriority.HIGH)
        print("✅ Test trade notification sent!")
    except Exception as e:
        print(f"❌ Failed to send trade notification: {e}")

    print("🎉 Telegram notification test completed!")

if __name__ == "__main__":
    asyncio.run(test_telegram_notifications())
