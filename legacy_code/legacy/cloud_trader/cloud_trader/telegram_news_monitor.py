"""
Telegram News Monitor Service for Sapphire V2.3
Listens to news/alpha groups and forwards relevant market information to trading agents
"""

import asyncio
import logging
import os
from typing import Callable, List, Optional, Set
from datetime import datetime
from dataclasses import dataclass

from telethon import TelegramClient, events
from telethon.tl.types import Message, User, Channel

logger = logging.getLogger(__name__)


@dataclass
class NewsMessage:
    """Structured news/alpha message from Telegram"""
    chat_id: int
    chat_name: str
    message_id: int
    text: str
    sender: Optional[str]
    timestamp: datetime
    has_media: bool
    is_forward: bool
    raw_event: events.NewMessage.Event


class TelegramNewsMonitor:
    """
    Telegram User Client for monitoring news/alpha channels

    Features:
    - Connects as user client (not bot) to access all groups
    - Filters messages from configured channels/groups
    - Forwards structured news to registered callbacks
    - Auto-reconnection and resilient error handling
    - Async-first design for integration with trading system
    """

    def __init__(
        self,
        api_id: str,
        api_hash: str,
        session_name: str = "client_session",
        monitored_chats: Optional[List[int]] = None,
    ):
        """
        Initialize Telegram News Monitor

        Args:
            api_id: Telegram API ID from .env
            api_hash: Telegram API Hash from .env
            session_name: Session file name (preserves auth)
            monitored_chats: List of chat IDs to monitor (None = all chats)
        """
        self.api_id = int(api_id)
        self.api_hash = api_hash
        self.session_name = session_name
        self.monitored_chats: Set[int] = set(monitored_chats) if monitored_chats else set()

        self.client: Optional[TelegramClient] = None
        self.callbacks: List[Callable[[NewsMessage], None]] = []
        self.running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(f"🔧 TelegramNewsMonitor initialized (monitoring {len(self.monitored_chats) if self.monitored_chats else 'ALL'} chats)")

    def add_handler(self, callback: Callable[[NewsMessage], None]) -> None:
        """
        Register a callback function to receive news messages

        Args:
            callback: Function that receives NewsMessage objects
        """
        self.callbacks.append(callback)
        logger.info(f"✅ Registered news handler: {callback.__name__}")

    def add_monitored_chat(self, chat_id: int) -> None:
        """Add a chat ID to monitoring list"""
        self.monitored_chats.add(chat_id)
        logger.info(f"📡 Added chat {chat_id} to monitoring")

    def remove_monitored_chat(self, chat_id: int) -> None:
        """Remove a chat ID from monitoring list"""
        self.monitored_chats.discard(chat_id)
        logger.info(f"🚫 Removed chat {chat_id} from monitoring")

    async def start(self) -> None:
        """
        Start the Telegram client and begin monitoring

        This method initializes the connection and sets up event handlers.
        It's designed to run in the background within an asyncio event loop.
        """
        if self.running:
            logger.warning("⚠️ TelegramNewsMonitor already running")
            return

        if not self.api_id or not self.api_hash:
            logger.error("❌ Missing Telegram credentials (API_ID or API_HASH)")
            raise ValueError("Telegram credentials not configured")

        self.running = True
        self._task = asyncio.create_task(self._run_client())
        logger.info("🚀 TelegramNewsMonitor started")

    async def _run_client(self) -> None:
        """Internal method to run the Telegram client loop"""
        retry_delay = 5
        max_retry_delay = 300  # 5 minutes

        while self.running:
            try:
                async with TelegramClient(self.session_name, self.api_id, self.api_hash) as client:
                    self.client = client

                    # Log connection info
                    me = await client.get_me()
                    logger.info(f"✅ Connected to Telegram as: {me.username or me.first_name} (ID: {me.id})")

                    # Log monitored chats
                    if self.monitored_chats:
                        logger.info(f"📡 Monitoring {len(self.monitored_chats)} specific chats")
                        await self._log_monitored_chats()
                    else:
                        logger.info("📡 Monitoring ALL accessible chats")

                    # Register event handler
                    @client.on(events.NewMessage)
                    async def handle_new_message(event: events.NewMessage.Event):
                        await self._process_message(event)

                    # Reset retry delay on successful connection
                    retry_delay = 5

                    # Keep connection alive
                    logger.info("🔄 Listening for news messages...")
                    await client.run_until_disconnected()

            except Exception as e:
                if self.running:
                    logger.error(f"❌ Telegram client error: {e}", exc_info=True)
                    logger.info(f"🔄 Reconnecting in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)

                    # Exponential backoff
                    retry_delay = min(retry_delay * 2, max_retry_delay)
                else:
                    break

        logger.info("🛑 TelegramNewsMonitor stopped")

    async def _log_monitored_chats(self) -> None:
        """Log details about monitored chats"""
        if not self.client:
            return

        for chat_id in self.monitored_chats:
            try:
                entity = await self.client.get_entity(chat_id)
                chat_name = getattr(entity, 'title', None) or getattr(entity, 'username', str(chat_id))
                logger.info(f"  📢 Monitoring: {chat_name} ({chat_id})")
            except Exception as e:
                logger.warning(f"  ⚠️ Could not fetch chat {chat_id}: {e}")

    async def _process_message(self, event: events.NewMessage.Event) -> None:
        """
        Process incoming message and forward to callbacks

        Args:
            event: Telethon NewMessage event
        """
        try:
            message: Message = event.message
            chat = await event.get_chat()

            # Filter by monitored chats if configured
            if self.monitored_chats and chat.id not in self.monitored_chats:
                return

            # Skip empty messages
            if not message.text:
                return

            # Get chat name
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'username', f'Chat_{chat.id}')

            # Get sender info
            sender_name = None
            if message.sender:
                sender = message.sender
                if isinstance(sender, User):
                    sender_name = sender.username or sender.first_name
                elif isinstance(sender, Channel):
                    sender_name = sender.title or sender.username

            # Create structured news message
            news_msg = NewsMessage(
                chat_id=chat.id,
                chat_name=chat_name,
                message_id=message.id,
                text=message.text,
                sender=sender_name,
                timestamp=message.date,
                has_media=bool(message.media),
                is_forward=bool(message.fwd_from),
                raw_event=event,
            )

            # Forward to all registered callbacks
            for callback in self.callbacks:
                try:
                    # Support both sync and async callbacks
                    if asyncio.iscoroutinefunction(callback):
                        await callback(news_msg)
                    else:
                        callback(news_msg)
                except Exception as e:
                    logger.error(f"❌ Error in news handler {callback.__name__}: {e}", exc_info=True)

            # Log the news
            logger.info(
                f"📰 [{chat_name}] {sender_name or 'Unknown'}: "
                f"{message.text[:100]}{'...' if len(message.text) > 100 else ''}"
            )

        except Exception as e:
            logger.error(f"❌ Error processing message: {e}", exc_info=True)

    async def stop(self) -> None:
        """
        Gracefully stop the Telegram client
        """
        logger.info("🛑 Stopping TelegramNewsMonitor...")
        self.running = False

        if self.client and self.client.is_connected():
            await self.client.disconnect()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("✅ TelegramNewsMonitor stopped")

    async def get_monitored_chats_info(self) -> List[dict]:
        """
        Get information about all monitored chats

        Returns:
            List of chat info dictionaries
        """
        if not self.client or not self.client.is_connected():
            logger.warning("⚠️ Client not connected")
            return []

        chats_info = []

        # If no specific chats configured, get recent dialogs
        chats_to_check = self.monitored_chats if self.monitored_chats else []

        for chat_id in chats_to_check:
            try:
                entity = await self.client.get_entity(chat_id)
                info = {
                    'id': chat_id,
                    'name': getattr(entity, 'title', None) or getattr(entity, 'username', str(chat_id)),
                    'type': entity.__class__.__name__,
                    'username': getattr(entity, 'username', None),
                }
                chats_info.append(info)
            except Exception as e:
                logger.error(f"❌ Error fetching chat {chat_id}: {e}")

        return chats_info

    async def list_available_chats(self, limit: int = 50) -> List[dict]:
        """
        List available chats/channels for configuration

        Args:
            limit: Maximum number of chats to return

        Returns:
            List of chat info dictionaries
        """
        if not self.client or not self.client.is_connected():
            logger.warning("⚠️ Client not connected")
            return []

        chats_info = []

        async for dialog in self.client.iter_dialogs(limit=limit):
            info = {
                'id': dialog.id,
                'name': dialog.name,
                'type': dialog.entity.__class__.__name__,
                'is_group': dialog.is_group,
                'is_channel': dialog.is_channel,
                'unread_count': dialog.unread_count,
            }
            chats_info.append(info)

        return chats_info


# Helper function for easy initialization
def create_news_monitor(
    monitored_chat_ids: Optional[List[int]] = None,
    api_id: Optional[str] = None,
    api_hash: Optional[str] = None,
) -> TelegramNewsMonitor:
    """
    Factory function to create TelegramNewsMonitor with environment variables

    Args:
        monitored_chat_ids: List of Telegram chat IDs to monitor
        api_id: Override API_ID from environment
        api_hash: Override API_HASH from environment

    Returns:
        Configured TelegramNewsMonitor instance
    """
    api_id = api_id or os.getenv("TELEGRAM_API_ID") or os.getenv("API_ID")
    api_hash = api_hash or os.getenv("TELEGRAM_API_HASH") or os.getenv("API_HASH")

    if not api_id or not api_hash:
        raise ValueError("Telegram credentials not found in environment variables")

    return TelegramNewsMonitor(
        api_id=api_id,
        api_hash=api_hash,
        monitored_chats=monitored_chat_ids,
    )
