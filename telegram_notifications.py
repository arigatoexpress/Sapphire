import requests
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Telegram notification system for trading alerts"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token and self.chat_id and 
                          not self.bot_token.startswith('PLACEHOLDER') and
                          not self.chat_id.startswith('PLACEHOLDER'))
        
        if self.enabled:
            logger.info("✅ Telegram notifications enabled")
        else:
            logger.warning("⚠️  Telegram notifications disabled - using placeholder credentials")
    
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message to Telegram"""
        if not self.enabled:
            logger.info(f"📱 [DISABLED] Would send: {text[:100]}...")
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if result.get("ok"):
                    logger.info("✅ Telegram message sent successfully")
                    return True
                else:
                    logger.error(f"❌ Telegram API error: {result.get('description', 'Unknown error')}")
            else:
                logger.error(f"❌ HTTP error: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Failed to send Telegram message: {e}")
        
        return False
    
    def send_trade_notification(self, trade_data: Dict[str, Any]) -> bool:
        """Send trade execution notification"""
        symbol = trade_data.get('symbol', 'UNKNOWN')
        side = trade_data.get('signal_type', 'UNKNOWN')
        price = trade_data.get('entry_price', 0)
        quantity = trade_data.get('quantity', 0)
        agent = trade_data.get('agent_id', 'unknown')
        
        message = f"""
🚀 *TRADE EXECUTED*

📊 *Symbol:* {symbol}
🎯 *Side:* {side}
💰 *Price:* \${price:.2f}
📦 *Quantity:* {quantity}
🤖 *Agent:* {agent}
⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
        """.strip()
        
        return self.send_message(message)
    
    def send_signal_notification(self, signal_data: Dict[str, Any]) -> bool:
        """Send trading signal notification"""
        symbol = signal_data.get('symbol', 'UNKNOWN')
        signal = signal_data.get('signal_type', 'UNKNOWN')
        confidence = signal_data.get('confidence', 0)
        price = signal_data.get('entry_price', 0)
        agent = signal_data.get('agent_id', 'unknown')
        
        emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "🟡"
        
        message = f"""
🎯 *TRADING SIGNAL*

{emoji} *Signal:* {signal}
📊 *Symbol:* {symbol}
🎚️ *Confidence:* {confidence:.1%}
💰 *Price:* \${price:.2f}
🤖 *Agent:* {agent}
⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
        """.strip()
        
        return self.send_message(message)
    
    def send_system_status(self, status_data: Dict[str, Any]) -> bool:
        """Send system status notification"""
        system_status = status_data.get('status', 'unknown')
        active_agents = status_data.get('active_agents', 0)
        total_capital = status_data.get('total_capital', 0)
        
        emoji = "🟢" if system_status == "operational" else "🔴"
        
        message = f"""
⚙️ *SYSTEM STATUS*

{emoji} *Status:* {system_status.upper()}
🤖 *Active Agents:* {active_agents}/6
💰 *Total Capital:* \${total_capital:,.0f}
⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
        """.strip()
        
        return self.send_message(message)
    
    def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """Send daily trading summary"""
        total_trades = summary_data.get('total_trades', 0)
        total_pnl = summary_data.get('total_pnl', 0)
        win_rate = summary_data.get('win_rate', 0)
        
        emoji = "📈" if total_pnl > 0 else "📉"
        
        message = f"""
📊 *DAILY TRADING SUMMARY*

{emoji} *Total P&L:* \${total_pnl:.2f}
📈 *Win Rate:* {win_rate:.1%}
🔄 *Total Trades:* {total_trades}
⏰ *Date:* {datetime.now().strftime('%Y-%m-%d')}
        """.strip()
        
        return self.send_message(message)

# Global notifier instance
telegram_notifier = None

def initialize_telegram_notifications(bot_token: str = None, chat_id: str = None):
    """Initialize Telegram notifications"""
    global telegram_notifier
    
    # Try to get from environment if not provided
    if not bot_token:
        import os
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not chat_id:
        import os
        chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    telegram_notifier = TelegramNotifier(bot_token, chat_id)
    return telegram_notifier

def send_trade_alert(trade_data: Dict[str, Any]) -> bool:
    """Send trade alert"""
    if telegram_notifier:
        return telegram_notifier.send_trade_notification(trade_data)
    return False

def send_signal_alert(signal_data: Dict[str, Any]) -> bool:
    """Send signal alert"""
    if telegram_notifier:
        return telegram_notifier.send_signal_notification(signal_data)
    return False

def send_system_alert(status_data: Dict[str, Any]) -> bool:
    """Send system alert"""
    if telegram_notifier:
        return telegram_notifier.send_system_status(status_data)
    return False

# Initialize on import
initialize_telegram_notifications()

print("✅ Telegram notification system initialized")
EOF && echo "✅ Telegram notification system created" && echo "" && echo "🔄 DEPLOYING TELEGRAM NOTIFICATIONS:" && kubectl cp telegram_notifications.py trading/sapphire-cloud-trader:/app/ -c sapphire-cloud-trader && echo "✅ Telegram notifications deployed" && echo "" && echo "🧪 TESTING TELEGRAM SYSTEM:" && kubectl exec -n trading deployment/sapphire-cloud-trader -- python -c "
# Test Telegram integration
import sys
sys.path.append('/app')

try:
    from telegram_notifications import telegram_notifier, send_signal_alert
    
    print('🧪 TESTING TELEGRAM NOTIFICATION SYSTEM...')
    
    # Check if notifications are enabled
    if telegram_notifier and telegram_notifier.enabled:
        print('✅ Telegram notifications: ENABLED')
        
        # Test sending a signal alert
        test_signal = {
            'agent_id': 'trend-momentum-agent',
            'symbol': 'BTC/USDT',
            'signal_type': 'BUY',
            'confidence': 0.78,
            'entry_price': 98500.00
        }
        
        result = send_signal_alert(test_signal)
        if result:
            print('✅ Test notification sent successfully!')
        else:
            print('❌ Test notification failed')
            
    else:
        print('⚠️  Telegram notifications: DISABLED (placeholder credentials)')
        print('📝 To enable: Update TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets')
        
        # Show current status
        import os
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'NOT_SET')
        chat_id = os.getenv('TELEGRAM_CHAT_ID', 'NOT_SET')
        
        print(f'Current Bot Token: {bot_token[:10]}...' if bot_token != 'NOT_SET' else 'Bot Token: NOT_SET')
        print(f'Current Chat ID: {chat_id[:10]}...' if chat_id != 'NOT_SET' else 'Chat ID: NOT_SET')
    
except Exception as e:
    print(f'❌ Telegram test failed: {e}')
" 2>/dev/null && echo "" && echo "📋 TELEGRAM SETUP INSTRUCTIONS:" && echo "=================================" && echo "" && echo "To enable Telegram notifications, you need to:" && echo "" && echo "1. Create a Telegram Bot:" && echo "   • Message @BotFather on Telegram" && echo "   • Send /newbot and follow instructions" && echo "   • Copy the bot token" && echo "" && echo "2. Get your Chat ID:" && echo "   • Message your bot with any text" && echo "   • Visit: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates" && echo "   • Copy the 'chat.id' value" && echo "" && echo "3. Update the secrets:" && echo "   kubectl create secret generic telegram-secret \\" && echo "     --from-literal=TELEGRAM_BOT_TOKEN='your_bot_token' \\" && echo "     --from-literal=TELEGRAM_CHAT_ID='your_chat_id' -n trading" && echo "" && echo "4. Restart the deployment" && echo "" && echo "Then you'll receive notifications for:" && echo "• ✅ Trade executions" && echo "• 🎯 Trading signals" && echo "• ⚙️ System status updates" && echo "• 📊 Daily summaries"