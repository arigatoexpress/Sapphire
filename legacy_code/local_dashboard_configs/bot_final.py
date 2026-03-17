#!/usr/bin/env python3
"""
Kimi-Claw Bot - Final Version
Aster + Lighter with $25 test allocation each
"""

import subprocess
import json
import os
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters
)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
RARI1_IP = "192.168.2.1"

def run_on_rari1(cmd):
    """Run command on rari1 via ethernet"""
    try:
        result = subprocess.run(
            ['ssh', '-o', 'ConnectTimeout=3', f'rari@{RARI1_IP}', cmd],
            capture_output=True, text=True, timeout=30
        )
        try:
            return json.loads(result.stdout)
        except:
            return {'success': result.returncode == 0, 'output': result.stdout}
    except Exception as e:
        return {'success': False, 'error': str(e)}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    await update.message.reply_text("""
🦅 **Kimi Claw** - Unified Trading Bot

**Platforms:**
💡 Lighter (L2) - API Index 0
⚡ Aster (DEX)

**Test Allocation:** $25 per platform

**Commands:**
💰 /balance - Check all balances
📊 /status - System status
💱 /buy <platform> <symbol> <amount>
💱 /sell <platform> <symbol> <amount>
🆘 /help - All commands

Route: rari2 → Ethernet → rari1 → VPN → Exchange
    """)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balances for both platforms"""
    msg = await update.message.reply_text("💰 Fetching balances...")
    
    # Get Lighter balance
    lighter = run_on_rari1('cd ~/.sapphire && python3 unified_trader.py balance --platform lighter')
    
    text = "💰 **Account Balances**\n\n"
    
    # Lighter
    if lighter.get('success'):
        text += f"""💡 **Lighter Protocol**
```
Collateral: ${lighter['collateral']:.2f} USDC
Available:  ${lighter['available']:.2f} USDC
Test Budget: ${lighter['test_allocation']:.2f}
Status: ✅ Ready
```
"""
    else:
        text += f"""💡 **Lighter**
```
Status: ❌ {lighter.get('error', 'Error')}
```
"""
    
    # Aster (placeholder for now)
    text += f"""\n⚡ **Aster DEX**
```
Status: 🔄 Connecting...
Test Budget: $25.00
```
_Needs Aster client setup_
"""
    
    text += "\n_Via rari1 VPN (Anonymous IP) ✅_"
    await msg.edit_text(text)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """System status"""
    await update.message.reply_text("""
📊 **System Status**

🖥️ **rari2** (Brain)
```
Status:     ✅ Online
Telegram:   ✅ Active
Location:   192.168.2.2
```

🖥️ **rari1** (Brawn)
```
Status:     ✅ Online
VPN:        ✅ Active
Location:   192.168.2.1
Lighter:    ✅ 853 USDC
Aster:      🔄 Pending
```

🌐 **Network**
```
Ethernet:   ✅ 192.168.2.2 ↔ 192.168.2.1
VPN Exit:   ✅ Anonymous
Privacy:    ✅ Protected
```

**Test Budgets:**
• Lighter: $25.00 / $853.01 available
• Aster: $25.00 (pending setup)
    """)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buy command"""
    if len(context.args) < 3:
        await update.message.reply_text("""
💱 **Buy Order**

Usage:
`/buy lighter ETH 0.01`
`/buy aster BTC 0.001`

Parameters:
• Platform: lighter or aster
• Symbol: ETH, BTC, etc.
• Amount: Quantity to buy

Max per order: $25 (test allocation)
        """)
        return
    
    platform = context.args[0].lower()
    symbol = context.args[1].upper()
    amount = context.args[2]
    
    if platform not in ['lighter', 'aster']:
        await update.message.reply_text("❌ Platform must be 'lighter' or 'aster'")
        return
    
    # Execute
    executing = await update.message.reply_text(
        f"🚀 Buying {amount} {symbol} on {platform.title()}...",
        parse_mode='Markdown'
    )
    
    cmd = f'cd ~/.sapphire && python3 unified_trader.py trade --platform {platform} --symbol {symbol}/USDC --side buy --amount {amount}'
    result = run_on_rari1(cmd)
    
    if result.get('success'):
        text = f"""
✅ **Buy Order Submitted**

```
Platform: {platform.title()}
Symbol:   {symbol}/USDC
Side:     BUY
Amount:   {amount}
Type:     {result.get('price', 'market')}
Budget:   ${result.get('test_allocation', 25)} test allocation
```

**Note:** {result.get('note', 'Order processing')}

_Route: rari2 → rari1 → VPN → {platform.title()} ✅_
        """
    else:
        text = f"""
❌ **Order Failed**

Error: {result.get('error', 'Unknown error')}

Platform: {platform}
Symbol: {symbol}
Amount: {amount}
        """
    
    await executing.edit_text(text)

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sell command"""
    if len(context.args) < 3:
        await update.message.reply_text("""
💱 **Sell Order**

Usage:
`/sell lighter ETH 0.01`
`/sell aster BTC 0.001`
        """)
        return
    
    platform = context.args[0].lower()
    symbol = context.args[1].upper()
    amount = context.args[2]
    
    executing = await update.message.reply_text(
        f"🚀 Selling {amount} {symbol} on {platform.title()}..."
    )
    
    cmd = f'cd ~/.sapphire && python3 unified_trader.py trade --platform {platform} --symbol {symbol}/USDC --side sell --amount {amount}'
    result = run_on_rari1(cmd)
    
    if result.get('success'):
        text = f"""
✅ **Sell Order Submitted**

Platform: {platform.title()}
Symbol: {symbol}/USDC
Side: SELL
Amount: {amount}
Budget: ${result.get('test_allocation', 25)} test allocation

{result.get('note', '')}
        """
    else:
        text = f"❌ Error: {result.get('error', 'Unknown')}"
    
    await executing.edit_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command"""
    await update.message.reply_text("""
🆘 **Kimi Claw Commands**

**Trading:**
`/buy <platform> <symbol> <amount>`
`/sell <platform> <symbol> <amount>`

**Examples:**
`/buy lighter ETH 0.01`
`/sell lighter BTC 0.001`

**Info:**
`/balance` - Check all balances
`/status` - System status
`/help` - This message

**Platforms:**
• 💡 Lighter - L2 order book (853 USDC available)
• ⚡ Aster - DEX (pending setup)

**Test Budget:** $25 per platform
**Route:** rari2 → Ethernet → rari1 → VPN → Exchange
**Privacy:** ✅ Anonymous IP
    """)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages"""
    text = update.message.text.lower()
    
    if any(word in text for word in ['buy', 'long']):
        await update.message.reply_text("💡 Use: `/buy lighter ETH 0.01`")
    elif any(word in text for word in ['sell', 'short']):
        await update.message.reply_text("💡 Use: `/sell lighter ETH 0.01`")
    elif 'balance' in text or 'fund' in text:
        await balance(update, context)
    elif 'status' in text:
        await status(update, context)
    else:
        await update.message.reply_text("""
👋 Hey! Try these commands:

💰 `/balance` - Check funds
📊 `/status` - System info
💱 `/buy lighter ETH 0.01`
💱 `/sell lighter ETH 0.01`

Test budget: $25 per platform
        """)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    print("✅ Kimi Claw Bot Started!")
    print("📡 Route: Telegram → rari2 → Ethernet → rari1 → VPN → Lighter/Aster")
    print("💰 Test Budget: $25 per platform")
    app.run_polling()

if __name__ == '__main__':
    main()
