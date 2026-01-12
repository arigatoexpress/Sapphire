"""
Smart Notification Manager

Implements intelligent notification deduplication and batching to prevent
Telegram spam while ensuring critical errors are still reported.
"""

import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional

from error_classifier import ErrorCategory, ErrorSeverity
from loguru import logger


@dataclass
class ErrorOccurrence:
    """Tracks an error occurrence with timestamp and count."""

    timestamp: float
    message: str
    count: int = 1


class SmartNotificationManager:
    """
    Manages notifications with deduplication and batching.

    Features:
    - Deduplicates identical errors within a time window
    - Batches low-severity errors into hourly digests
    - Always allows critical errors through
    """

    def __init__(self, dedup_window: int = 300, digest_interval: int = 3600):
        """
        Initialize smart notification manager.

        Args:
            dedup_window: Seconds to deduplicate identical errors (default: 5 minutes)
            digest_interval: Seconds between digest emails (default: 1 hour)
        """
        # Track recent errors by signature
        self.recent_errors: Dict[str, ErrorOccurrence] = {}

        # Configuration
        self.dedup_window = dedup_window
        self.digest_interval = digest_interval
        self.last_digest = time.time()

        # Errors for digest
        self.digest_errors: List[str] = []

    def should_notify(
        self, error_message: str, error_category: ErrorCategory, error_severity: ErrorSeverity
    ) -> bool:
        """
        Determine if an error should trigger immediate notification.

        Args:
            error_message: The error message
            error_category: Error category from classifier
            error_severity: Error severity from classifier

        Returns:
            True if should notify immediately, False if should batch/suppress
        """
        # Always notify critical errors
        if error_severity == ErrorSeverity.CRITICAL:
            logger.info(f"🚨 Critical error, notifying immediately: {error_message[:100]}")
            return True

        # Never notify INFO-level or resource errors
        if error_severity == ErrorSeverity.INFO or error_category == ErrorCategory.RESOURCE:
            self.digest_errors.append(error_message)
            logger.debug(f"📊 Added to digest: {error_message[:100]}")
            return False

        # For other errors, check deduplication
        signature = self._generate_signature(error_message)
        current_time = time.time()

        # Check if we've seen this error recently
        if signature in self.recent_errors:
            last_occurrence = self.recent_errors[signature]

            # If within dedup window, don't notify again
            time_since_last = current_time - last_occurrence.timestamp
            if time_since_last < self.dedup_window:
                last_occurrence.count += 1
                logger.debug(
                    f"⏭️  Deduplicated error (count: {last_occurrence.count}, "
                    f"last seen {time_since_last:.0f}s ago): {signature[:80]}"
                )
                return False

        # New error or outside dedup window - notify
        self.recent_errors[signature] = ErrorOccurrence(current_time, error_message)
        logger.info(f"🔔 New error notification allowed: {signature[:100]}")
        return True

    def _generate_signature(self, error_message: str) -> str:
        """
        Generate unique signature for error deduplication.

        Removes timestamps, transaction hashes, and specific values to group
        similar errors together.

        Args:
            error_message: Raw error message

        Returns:
            Normalized error signature
        """
        # Remove timestamps
        msg = re.sub(r"\d{4}-\d{2}-\d{2}", "", error_message)
        msg = re.sub(r"\d{2}:\d{2}:\d{2}", "", msg)

        # Remove transaction hashes and addresses
        msg = re.sub(r"0x[a-fA-F0-9]{40,}", "TX_HASH", msg)
        msg = re.sub(r"[a-zA-Z0-9]{40,}", "HASH", msg)

        # Remove numbers (amounts, IDs, prices)
        msg = re.sub(r"\$?\d+\.?\d*", "NUM", msg)

        # Remove extra whitespace
        msg = " ".join(msg.split())

        return msg.strip()

    async def send_hourly_digest(self, telegram_bot):
        """
        Send batched error digest if interval has elapsed.

        Args:
            telegram_bot: Telegram bot instance to send message with
        """
        current_time = time.time()

        # Check if it's time for digest
        if current_time - self.last_digest < self.digest_interval:
            return

        # Check if there are errors to report
        if not self.digest_errors:
            logger.debug("No errors for digest")
            return

        # Group errors by signature and count
        error_counts = defaultdict(int)
        for error in self.digest_errors:
            signature = self._generate_signature(error)
            error_counts[signature] += 1

        # Create digest message (top 10 most frequent errors)
        digest_lines = ["📊 **Hourly Error Digest**\n"]

        for error, count in sorted(error_counts.items(), key=lambda x: -x[1])[:10]:
            # Truncate long messages
            error_preview = error[:60] + "..." if len(error) > 60 else error
            digest_lines.append(f"• {error_preview} ({count}x)")

        digest_lines.append(f"\nTotal errors: {len(self.digest_errors)}")
        digest = "\n".join(digest_lines)

        # Send digest
        logger.info(f"📧 Sending hourly digest with {len(self.digest_errors)} errors")
        await telegram_bot.send_message(digest, priority="low")

        # Reset
        self.digest_errors = []
        self.last_digest = current_time

    def get_stats(self) -> dict:
        """
        Get current statistics.

        Returns:
            Dict with notification stats
        """
        total_deduped = sum(occ.count - 1 for occ in self.recent_errors.values())

        return {
            "unique_errors_tracked": len(self.recent_errors),
            "total_deduplicated": total_deduped,
            "digest_pending": len(self.digest_errors),
            "dedup_window_seconds": self.dedup_window,
        }


# Global instance
notification_manager = SmartNotificationManager()
