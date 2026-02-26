#!/usr/bin/env python3
"""
Telegram Bot that forwards messages to Kimi-Claw agent
"""

import os
import sys
import asyncio
import subprocess
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    ContextTypes, filters
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",") if os.getenv("ALLOWED_USERS") else []
KIMI_CONFIG = os.path.expanduser("~/.kimi/kimi-claw.toml")

# Validate token
if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
    logger.error("BOT_TOKEN not configured")
    sys.exit(1)


def extract_kimi_response(stdout: str) -> str:
    """
    Extract the actual response from Kimi CLI output.
    Kimi outputs in this format:
    ╭──────────────╮
    │ User prompt  │
    ╰──────────────╯
    • Thinking...
    • Actual response here
      with possible continuation lines
    • More response
    """
    lines = stdout.split('\n')
    
    # Find all bullet points and their line numbers
    bullet_indices = []
    for i, line in enumerate(lines):
        if line.strip().startswith('•'):
            bullet_indices.append(i)
    
    if not bullet_indices:
        # No bullets - return everything after the box
        in_box = False
        result = []
        for line in lines:
            if any(c in line for c in ['╭', '│', '╰']):
                in_box = True
                continue
            if in_box and line.strip():
                result.append(line)
        return '\n'.join(result).strip()[:4000] or "No response"
    
    # Thinking keywords to filter out
    thinking_starts = [
        'the user', 'i should', 'i need to', 'i will', 
        'this is', 'i can', 'let me', 'i need', "i'll",
        'first,', 'next,', 'finally,', 'to do this',
        'looking at', 'i see', 'based on', 'analyzing'
    ]
    
    # Find the best response bullet
    # Start from the end and work backwards to find the actual response
    best_response = ""
    best_line_idx = -1
    
    for bullet_idx in reversed(bullet_indices):
        bullet_line = lines[bullet_idx].strip()
        # Remove bullet marker
        text = re.sub(r'^•\s*', '', bullet_line)
        
        # Skip empty or very short
        if len(text) < 5:
            continue
        
        # Check if this looks like thinking vs response
        is_thinking = any(text.lower().startswith(phrase) for phrase in thinking_starts)
        
        if not is_thinking:
            best_response = text
            best_line_idx = bullet_idx
            break
    
    if best_line_idx == -1:
        # All bullets look like thinking, use the last one
        best_response = re.sub(r'^•\s*', '', lines[bullet_indices[-1]])
        best_line_idx = bullet_indices[-1]
    
    # Now collect continuation lines after this bullet
    # Continuation lines are indented or part of the same paragraph
    result_lines = [best_response]
    
    i = best_line_idx + 1
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Stop if we hit another bullet or box border
        if stripped.startswith('•') or '╭' in line or '╰' in line:
            break
        
        # Skip empty lines at the start
        if not stripped and not result_lines:
            i += 1
            continue
        
        # Add non-empty lines
        if stripped:
            result_lines.append(stripped)
        elif result_lines and result_lines[-1] != "":
            # Single empty line for paragraph break
            result_lines.append("")
        
        i += 1
    
    # Join and clean up
    result = '\n'.join(result_lines).strip()
    
    # Remove any trailing box drawing characters
    result = re.sub(r'[╭╰│─\s]+$', '', result)
    
    return result if result else "🤔 I couldn't generate a proper response. Please try again."


async def check_kimi_status() -> bool:
    """Check if Kimi CLI is working."""
    try:
        result = subprocess.run(
            ["kimi", "info"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Kimi status check failed: {e}")
        return False


async def query_kimi(prompt: str) -> str:
    """Send a query to Kimi and get response."""
    start_time = datetime.now()
    logger.info(f"Query: {prompt[:50]}...")
    
    try:
        cmd = [
            "kimi",
            "--config-file", KIMI_CONFIG,
            "--yes",
            "--prompt", prompt
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Response time: {elapsed:.1f}s")
        
        if result.returncode == 0:
            response = extract_kimi_response(result.stdout)
            logger.info(f"Response length: {len(response)} chars")
            
            # Log the raw and extracted response for debugging
            if len(response) < 50:
                logger.warning(f"Short response extracted. Raw length: {len(result.stdout)}")
                logger.debug(f"Raw output: {result.stdout[:500]}")
            
            return response
        else:
            error = result.stderr.strip()[:500] if result.stderr else "Unknown error"
            logger.error(f"Kimi error: {error}")
            return f"❌ Error: {error}"
            
    except subprocess.TimeoutExpired:
        logger.error("Kimi query timed out")
        return "⏱️ Request timed out. Please try again."
    except Exception as e:
        logger.error(f"Exception: {e}")
        return f"❌ Error: {str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    logger.info(f"User {user.id} started bot")
    
    if ALLOWED_USERS and str(user.id) not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Unauthorized.")
        return
    
    welcome_msg = """🤖 <b>Kimi-Claw Telegram Bot</b>

Hello! I'm connected to your Kimi-Claw unified agent.

<b>Commands:</b>
/status - Check Kimi status
/note - Save a note
/help - Show help

Send me any message to chat with Kimi."""
    
    await update.message.reply_text(welcome_msg, parse_mode="HTML")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check Kimi status."""
    is_ready = await check_kimi_status()
    
    if is_ready:
        await update.message.reply_text("✅ <b>Kimi-Claw is ONLINE</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ <b>Kimi-Claw is OFFLINE</b>", parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    await update.message.reply_text(
        "📚 <b>Help</b>\n\nSend any message to chat with Kimi-Claw.",
        parse_mode="HTML"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    user = update.effective_user
    message_text = update.message.text
    
    logger.info(f"From {user.id}: {message_text[:50]}...")
    
    if ALLOWED_USERS and str(user.id) not in ALLOWED_USERS:
        await update.message.reply_text("🚫 Unauthorized.")
        return
    
    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )
    
    # Check Kimi status
    if not await check_kimi_status():
        await update.message.reply_text("❌ Kimi is not available. Please try later.")
        return
    
    # Send processing message
    processing_msg = await update.message.reply_text("🤔 Thinking...")
    
    try:
        # Query Kimi
        response = await query_kimi(message_text)
        
        # Delete processing message
        await processing_msg.delete()
        
        # Send response, splitting if too long
        if len(response) > 4000:
            chunks = []
            current_chunk = ""
            
            for line in response.split('\n'):
                if len(current_chunk) + len(line) + 1 > 3900:
                    chunks.append(current_chunk)
                    current_chunk = line
                else:
                    current_chunk += '\n' + line if current_chunk else line
            
            if current_chunk:
                chunks.append(current_chunk)
            
            for i, chunk in enumerate(chunks):
                if i > 0:
                    await asyncio.sleep(0.5)
                await update.message.reply_text(chunk.strip())
        else:
            await update.message.reply_text(response)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.delete()
        await update.message.reply_text("❌ An error occurred. Please try again.")


async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save a note."""
    note_text = ' '.join(context.args)
    
    if not note_text:
        await update.message.reply_text("⚠️ Usage: /note Your text here")
        return
    
    try:
        with open("notes.txt", "a") as f:
            f.write(f"[{datetime.now().isoformat()}] {note_text}\n")
        await update.message.reply_text(f"📝 Saved: {note_text[:100]}")
    except Exception as e:
        logger.error(f"Error saving note: {e}")
        await update.message.reply_text("❌ Could not save note.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Error: {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ Error. Please try again.")


def main():
    """Start the bot."""
    logger.info("🚀 Starting Kimi-Claw Telegram Bot...")
    
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("note", note_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    logger.info("✅ Bot is running!")
    application.run_polling()


if __name__ == "__main__":
    main()
