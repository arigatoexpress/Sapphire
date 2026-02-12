#!/usr/bin/env python3
"""
CLI tool to configure and test Telegram News Monitor
"""

import asyncio
import os
import sys
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cloud_trader.telegram_news_monitor import create_news_monitor
from cloud_trader.news_intelligence_agent import NewsIntelligenceAgent, NewsInsight
from cloud_trader.telegram_news_monitor import NewsMessage
from dotenv import load_dotenv

load_dotenv()


async def list_chats():
    """List all available chats/channels"""
    print("\n🔍 Fetching your Telegram chats...\n")

    monitor = create_news_monitor()
    await monitor.start()

    # Wait for connection
    await asyncio.sleep(3)

    chats = await monitor.list_available_chats(limit=100)

    print("📋 Available Chats/Channels:\n")
    print(f"{'ID':<15} {'Type':<12} {'Name':<40} {'Unread'}")
    print("-" * 80)

    for chat in chats:
        chat_type = "📢 Channel" if chat['is_channel'] else "👥 Group" if chat['is_group'] else "💬 Chat"
        print(f"{chat['id']:<15} {chat_type:<12} {chat['name']:<40} {chat['unread_count']}")

    await monitor.stop()

    print("\n💡 To monitor specific chats, add their IDs to NEWS_MONITOR_CHAT_IDS in .env")
    print("   Example: NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210")


async def test_monitor(chat_ids: List[int]):
    """Test news monitoring with AI analysis"""
    print(f"\n🚀 Starting News Monitor test for {len(chat_ids)} chats...\n")

    # Initialize intelligence agent
    intelligence = NewsIntelligenceAgent()
    intelligence.initialize_model()

    # Track insights
    insights_received = []

    def on_insight(insight: NewsInsight):
        """Callback for insights"""
        insights_received.append(insight)
        print(f"\n{'='*80}")
        print(f"💡 TRADING INSIGHT #{len(insights_received)}")
        print(f"{'='*80}")
        print(f"Source: {insight.source_chat}")
        print(f"Tokens: {', '.join(insight.affected_tokens)}")
        print(f"Sentiment: {insight.sentiment.upper()} | Action: {insight.suggested_action.upper()}")
        print(f"Urgency: {insight.urgency.upper()} | Confidence: {insight.confidence:.0%}")
        print(f"\nReasoning: {insight.reasoning}")
        print(f"\nKey Points:")
        for i, point in enumerate(insight.key_points, 1):
            print(f"  {i}. {point}")
        print(f"\nOriginal Message: {insight.source_message[:200]}...")
        print(f"{'='*80}\n")

    intelligence.add_insight_callback(on_insight)

    # Create monitor
    monitor = create_news_monitor(monitored_chat_ids=chat_ids)

    async def on_news(news: NewsMessage):
        """Process news through intelligence"""
        print(f"📰 [{news.chat_name}] {news.sender}: {news.text[:80]}...")
        await intelligence.process_news(news)

    monitor.add_handler(on_news)

    # Start monitoring
    await monitor.start()

    print("✅ Monitor started. Listening for news... (Press Ctrl+C to stop)\n")
    print(f"📡 Monitoring chats: {', '.join(map(str, chat_ids))}\n")

    try:
        # Run until interrupted
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping monitor...")

    await monitor.stop()

    print(f"\n📊 Session Summary:")
    print(f"   Total insights generated: {len(insights_received)}")
    print(f"   Stats: {intelligence.get_stats()}")


async def test_all_chats():
    """Test monitoring ALL chats (no filter)"""
    print("\n🚀 Starting News Monitor test for ALL chats...\n")
    print("⚠️  WARNING: This will process messages from ALL your Telegram chats!")
    print("    Consider using specific chat IDs for production.\n")

    # Initialize intelligence agent
    intelligence = NewsIntelligenceAgent()
    intelligence.initialize_model()

    # Track insights
    insights_count = [0]  # Use list for mutable counter in closure

    def on_insight(insight: NewsInsight):
        """Callback for insights"""
        insights_count[0] += 1
        print(f"\n💡 INSIGHT #{insights_count[0]}: {insight.affected_tokens} | {insight.sentiment} | {insight.suggested_action}")
        print(f"   From: {insight.source_chat}")
        print(f"   {insight.reasoning[:150]}...")

    intelligence.add_insight_callback(on_insight)

    # Create monitor with no chat filter
    monitor = create_news_monitor(monitored_chat_ids=None)

    async def on_news(news: NewsMessage):
        """Process news through intelligence"""
        print(f"📰 [{news.chat_name}] {news.text[:60]}...")
        await intelligence.process_news(news)

    monitor.add_handler(on_news)

    # Start monitoring
    await monitor.start()

    print("✅ Monitor started. Listening for ALL chats... (Press Ctrl+C to stop)\n")

    try:
        # Run until interrupted
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping monitor...")

    await monitor.stop()

    print(f"\n📊 Session Summary:")
    print(f"   Total insights generated: {insights_count[0]}")


def main():
    """Main CLI entry point"""
    if len(sys.argv) < 2:
        print("""
╔══════════════════════════════════════════════════════════════╗
║         Sapphire V2.3 - News Monitor Configuration          ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python configure_news_monitor.py <command> [args]

Commands:
    list        List all your Telegram chats/channels with IDs
    test        Test news monitor with specific chat IDs
    test-all    Test news monitor on ALL chats (no filter)

Examples:
    # List all chats to find IDs
    python configure_news_monitor.py list

    # Test monitoring specific chats
    python configure_news_monitor.py test -1001234567890 -1009876543210

    # Test monitoring all chats
    python configure_news_monitor.py test-all

Configuration:
    Set these in your .env file:
    - API_ID=20785477
    - API_HASH=331de234a1c2b2937a054912379b91e1
    - NEWS_MONITOR_CHAT_IDS=-1001234567890,-1009876543210 (optional)

Notes:
    - Session file 'client_session.session' preserves authentication
    - First run may require 2FA code from Telegram
    - Use Ctrl+C to stop monitoring
        """)
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        asyncio.run(list_chats())

    elif command == "test":
        if len(sys.argv) < 3:
            print("❌ Error: Please provide chat IDs to monitor")
            print("   Example: python configure_news_monitor.py test -1001234567890 -1009876543210")
            sys.exit(1)

        try:
            chat_ids = [int(id) for id in sys.argv[2:]]
            asyncio.run(test_monitor(chat_ids))
        except ValueError:
            print("❌ Error: Invalid chat ID format. Must be integers.")
            sys.exit(1)

    elif command == "test-all":
        asyncio.run(test_all_chats())

    else:
        print(f"❌ Unknown command: {command}")
        print("   Valid commands: list, test, test-all")
        sys.exit(1)


if __name__ == "__main__":
    main()
