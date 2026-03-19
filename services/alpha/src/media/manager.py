import os
import asyncio
import time
from collections import deque
from typing import Dict, Any, List, Optional, Deque
from loguru import logger
from .twitter import TwitterClient
from .substack import SubstackClient
from .linkedin import LinkedInClient

class MediaManager:
    """
    Orchestrates social media publishing across multiple channels (X/Twitter, Substack, LinkedIn).
    Handles draft approval workflows, queue management, and background publishing.
    """

    def __init__(self, telegram_bot: Any = None):
        self.telegram = telegram_bot
        self.twitter = TwitterClient()
        self.substack = SubstackClient()
        self.linkedin = LinkedInClient()

        # Configuration
        self.mode = self._normalize_mode(os.getenv("SAPPHIRE_MEDIA_MODE", "owner_approval"))
        self.max_attempts = max(1, int(os.getenv("SAPPHIRE_MEDIA_MAX_ATTEMPTS", "4")))
        self.retry_base_seconds = max(10, int(os.getenv("SAPPHIRE_MEDIA_RETRY_BASE_SECONDS", "120")))
        self.poll_seconds = max(5, int(os.getenv("SAPPHIRE_MEDIA_POLL_SECONDS", "20")))

        # State
        self.queue: Deque[Dict[str, Any]] = deque(maxlen=200)
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self.recent_results: Deque[Dict[str, Any]] = deque(maxlen=50)
        self.last_publish: Dict[str, Any] = {}
        self.publish_sequence = 0
        self.running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def stop(self):
        """Stop the background media loop."""
        self.running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("🛑 MediaManager stopped.")

    async def start(self):
        """Initialize channels and start background loop."""
        logger.info("📢 Starting MediaManager...")
        await self.twitter.start()
        await self.substack.start()
        await self.linkedin.start()
        
        self.running = True
        self._loop_task = asyncio.create_task(self._publish_loop())
        logger.info(f"📢 MediaManager started. Mode: {self.mode}")

    async def _publish_loop(self):
        """Background loop to process queued items."""
        while self.running:
            try:
                await asyncio.sleep(self.poll_seconds)
                await self._process_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Media loop error: {e}")

    async def _process_queue(self):
        if not self.queue:
            return

        now = int(time.time())
        # Process snapshot of queue to avoid infinite retries in same tick
        count = len(self.queue)
        for _ in range(count):
            item = self.queue.popleft()
            if item.get("next_attempt_at", 0) > now:
                self.queue.append(item)
                continue
            
            await self._execute_publish(item)

    async def _execute_publish(self, item: Dict[str, Any]):
        """Execute publish for a single item."""
        item["attempts"] = item.get("attempts", 0) + 1
        item["updated_at"] = int(time.time())
        targets = item.get("targets", [])
        
        results = {}
        failed_targets = []
        retryable = False

        # 1. Twitter
        if "twitter" in targets:
            try:
                if self.twitter.ready:
                    # Construct text: Title + Body
                    text = item.get("title", "")
                    if item.get("body"):
                        text += f"\n\n{item['body']}"
                    
                    post_id = await self.twitter.post(text)
                    results["twitter"] = {"ok": True, "id": post_id}
                else:
                    results["twitter"] = {"ok": False, "reason": "not_ready", "retryable": True}
                    retryable = True
                    failed_targets.append("twitter")
            except Exception as e:
                logger.error(f"Twitter publish error: {e}")
                results["twitter"] = {"ok": False, "reason": str(e), "retryable": True}
                retryable = True
                failed_targets.append("twitter")

        # 2. Substack
        if "substack" in targets:
            try:
                # Substack logic: Title is subject/headline, Body is content
                if self.substack.ready:
                    post_id = await self.substack.post(item.get("title", ""), item.get("body", ""))
                    results["substack"] = {"ok": True, "id": post_id}
                else:
                    results["substack"] = {"ok": False, "reason": "not_ready", "retryable": True}
                    retryable = True
                    failed_targets.append("substack")
            except Exception as e:
                logger.error(f"Substack publish error: {e}")
                results["substack"] = {"ok": False, "reason": str(e), "retryable": True}
                retryable = True
                failed_targets.append("substack")

        # 3. LinkedIn
        if "linkedin" in targets:
            try:
                if self.linkedin.ready:
                    # LinkedIn text: usually body or title+body
                    text = item.get("title", "")
                    if item.get("body"):
                        text += f"\n\n{item['body']}"

                    post_id = await self.linkedin.post(text)
                    results["linkedin"] = {"ok": True, "id": post_id}
                else:
                    results["linkedin"] = {"ok": False, "reason": "not_ready", "retryable": True}
                    retryable = True
                    failed_targets.append("linkedin")
            except Exception as e:
                logger.error(f"LinkedIn publish error: {e}")
                results["linkedin"] = {"ok": False, "reason": str(e), "retryable": True}
                retryable = True
                failed_targets.append("linkedin")

        # Outcome handling
        success_targets = [k for k, v in results.items() if v.get("ok")]
        
        if not failed_targets:
            # Success
            self._record_result(item, "success", results)
            if self.telegram:
                await self.telegram.send_message(
                    f"✅ Media publish completed.\nRequest: `{item['request_id']}`\nTargets: `{', '.join(success_targets)}`",
                    priority="high"
                )
        else:
            # Failure or Partial
            if retryable and item["attempts"] < self.max_attempts:
                # Retry
                delay = self.retry_base_seconds * item["attempts"]
                item["next_attempt_at"] = int(time.time()) + delay
                item["status"] = "queued"
                self.queue.append(item)
                if self.telegram:
                     await self.telegram.send_message(
                        f"⚠️ Media retry scheduled.\nRequest: `{item['request_id']}`\nFailed: `{', '.join(failed_targets)}`\nRetry in {delay}s",
                        priority="medium"
                    )
            else:
                # Final Failure
                self._record_result(item, "failed", results)
                if self.telegram:
                    await self.telegram.send_message(
                        f"❌ Media publish failed.\nRequest: `{item['request_id']}`\nFailed: `{', '.join(failed_targets)}`",
                        priority="high"
                    )

    def request_publish(self, topic: str, title: str, body: str, targets: List[str], source: str = "manual") -> Dict[str, Any]:
        """Enqueue a new publish request."""
        request_id = self._next_id()
        item = {
            "request_id": request_id,
            "topic": topic,
            "title": title,
            "body": body,
            "targets": self._normalize_targets(targets),
            "source": source,
            "status": "pending_approval" if self.mode == "owner_approval" else "queued",
            "created_at": int(time.time()),
            "attempts": 0,
            "next_attempt_at": 0
        }

        if self.mode == "draft_only":
            item["status"] = "draft"
            return item

        if self.mode == "owner_approval":
            self.pending_approvals[request_id] = item
        else:
            self.queue.append(item)
            
        return item

    def approve_request(self, request_id: str) -> bool:
        """Approve a pending request."""
        request_id = self._resolve_id(request_id)
        if request_id in self.pending_approvals:
            item = self.pending_approvals.pop(request_id)
            item["status"] = "queued"
            self.queue.append(item)
            return True
        return False

    def reject_request(self, request_id: str) -> bool:
        """Reject a pending request."""
        request_id = self._resolve_id(request_id)
        if request_id in self.pending_approvals:
            del self.pending_approvals[request_id]
            return True
        return False
        
    def set_mode(self, mode: str) -> str:
        self.mode = self._normalize_mode(mode)
        return self.mode

    def get_status_snapshot(self) -> Dict[str, Any]:
        """Return structured status for snapshotting."""
        return {
            "mode": self.mode,
            "twitter_ready": self.twitter.ready,
            "substack_ready": self.substack.ready,
            "linkedin_ready": self.linkedin.ready,
            "queue_depth": len(self.queue),
            "pending_approvals": len(self.pending_approvals),
            "running": self.running
        }

    def get_status_report(self) -> str:
        """Generate markdown status report."""
        lines = [
            "📰 **SAPPHIRE MEDIA STATUS**",
            f"Mode: `{self.mode}`",
            f"X/Twitter: `{'READY' if self.twitter.ready else 'NOT_READY'}`",
            f"Substack: `{'READY' if self.substack.ready else 'NOT_READY'}`",
            f"LinkedIn: `{'READY' if self.linkedin.ready else 'NOT_READY'}`",
            f"Queue: pending `{len(self.pending_approvals)}` | queued `{len(self.queue)}`",
            "",
            "Commands: `/media mode`, `/media publish`, `/media approve`"
        ]
        return "\n".join(lines)

    def _next_id(self) -> str:
        self.publish_sequence += 1
        return f"media:{int(time.time())}:{self.publish_sequence:04d}"

    def _resolve_id(self, req_id: str) -> str:
        if req_id == "latest":
            # logic to find latest pending
            if self.pending_approvals:
                return sorted(self.pending_approvals.keys())[-1]
        return req_id

    def _record_result(self, item, status, results):
        self.last_publish = {
            "req_id": item["request_id"],
            "status": status,
            "timestamp": int(time.time())
        }
        self.recent_results.append(self.last_publish)

    def _normalize_mode(self, mode: str) -> str:
        mode = mode.lower()
        if "auto" in mode: return "auto_post"
        if "draft" in mode: return "draft_only"
        return "owner_approval"
        
    def _normalize_targets(self, targets: List[str]) -> List[str]:
        # Simplified normalization
        clean = []
        for t in targets:
            t = t.lower()
            if t in ["x", "twitter"]: clean.append("twitter")
            if t in ["substack"]: clean.append("substack")
            if t in ["linkedin", "li"]: clean.append("linkedin")
        if not clean: clean = ["twitter"]
        return list(set(clean))
