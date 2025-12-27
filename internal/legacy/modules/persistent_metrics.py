"""
Persistent Metrics Storage for Sapphire Trading System.

Uses Google Cloud Storage for persistence across deployments.
Local /tmp cache for fast reads, async sync to GCS for durability.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# GCS bucket name for persistent metrics
BUCKET_NAME = "sapphire-trading-performance"

# Local cache paths
CACHE_DIR = "/tmp/sapphire_metrics"
AGENT_PERFORMANCE_FILE = "agent_performance.json"
ANALYTICS_METRICS_FILE = "analytics_metrics.json"
TRADE_HISTORY_FILE = "trade_history.json"


class PersistentMetricsStore:
    """
    Google Cloud Storage-backed metrics persistence.

    Features:
    - Write-through cache: Fast local writes, async GCS sync
    - Startup sync: Downloads latest from GCS on container start
    - Daily snapshots: Automatic backups to GCS
    - Graceful fallback: Continues with local-only if GCS unavailable
    """

    def __init__(self, bucket_name: str = BUCKET_NAME):
        self.bucket_name = bucket_name
        self.cache_dir = CACHE_DIR
        self._gcs_client = None
        self._gcs_available = False
        self._last_sync_time: Dict[str, float] = {}
        self._sync_interval = 60  # Sync to GCS every 60 seconds

        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)

        # Initialize GCS client
        self._init_gcs()

    def _init_gcs(self):
        """Initialize Google Cloud Storage client."""
        try:
            from google.cloud import storage

            self._gcs_client = storage.Client()

            # Check if bucket exists, create if not
            try:
                bucket = self._gcs_client.bucket(self.bucket_name)
                if not bucket.exists():
                    # Create bucket in same region as Cloud Run
                    bucket = self._gcs_client.create_bucket(
                        self.bucket_name, location="northamerica-northeast1"
                    )
                    logger.info(f"✅ Created GCS bucket: {self.bucket_name}")
                else:
                    logger.info(f"✅ GCS bucket connected: {self.bucket_name}")

                self._gcs_available = True
            except Exception as bucket_err:
                logger.warning(f"⚠️ GCS bucket access failed: {bucket_err}")
                self._gcs_available = False

        except ImportError:
            logger.warning("⚠️ google-cloud-storage not installed, using local-only mode")
            self._gcs_available = False
        except Exception as e:
            logger.warning(f"⚠️ GCS initialization failed: {e}, using local-only mode")
            self._gcs_available = False

    def _get_cache_path(self, filename: str) -> str:
        """Get local cache file path."""
        return os.path.join(self.cache_dir, filename)

    def _get_gcs_path(self, filename: str) -> str:
        """Get GCS blob path."""
        return f"metrics/{filename}"

    async def load(self, filename: str) -> Dict[str, Any]:
        """
        Load metrics from storage.

        Priority:
        1. Local cache (if exists and fresh)
        2. GCS (if available)
        3. Empty dict (new installation)
        """
        cache_path = self._get_cache_path(filename)

        # Try local cache first (fast path)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                logger.debug(f"📁 Loaded {filename} from local cache")
                return data
            except Exception as e:
                logger.warning(f"⚠️ Failed to read cache {filename}: {e}")

        # Try GCS (cold start / new container)
        if self._gcs_available:
            try:
                data = await self._load_from_gcs(filename)
                if data:
                    # Update local cache
                    self._write_cache(filename, data)
                    logger.info(f"☁️ Loaded {filename} from GCS, updated local cache")
                    return data
            except Exception as e:
                logger.warning(f"⚠️ Failed to load {filename} from GCS: {e}")

        # Return empty dict for new installation
        logger.info(f"📋 No existing data for {filename}, starting fresh")
        return {}

    async def save(self, filename: str, data: Dict[str, Any]):
        """
        Save metrics to storage.

        Strategy:
        1. Write to local cache immediately (sync)
        2. Sync to GCS periodically (async, batched)
        """
        # Add metadata
        data["_metadata"] = {
            "last_updated": datetime.utcnow().isoformat(),
            "version": data.get("_metadata", {}).get("version", 0) + 1,
        }

        # Write to local cache (fast, synchronous)
        self._write_cache(filename, data)

        # Schedule GCS sync (async, batched)
        current_time = time.time()
        last_sync = self._last_sync_time.get(filename, 0)

        if current_time - last_sync >= self._sync_interval:
            # Time to sync to GCS
            asyncio.create_task(self._sync_to_gcs(filename, data))
            self._last_sync_time[filename] = current_time

    def _write_cache(self, filename: str, data: Dict[str, Any]):
        """Write data to local cache file."""
        cache_path = self._get_cache_path(filename)
        try:
            with open(cache_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"❌ Failed to write cache {filename}: {e}")

    async def _load_from_gcs(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load data from Google Cloud Storage."""
        if not self._gcs_available:
            return None

        try:
            bucket = self._gcs_client.bucket(self.bucket_name)
            blob = bucket.blob(self._get_gcs_path(filename))

            if blob.exists():
                content = blob.download_as_text()
                return json.loads(content)
            return None
        except Exception as e:
            logger.error(f"❌ GCS load failed for {filename}: {e}")
            return None

    async def _sync_to_gcs(self, filename: str, data: Dict[str, Any]):
        """Upload data to Google Cloud Storage."""
        if not self._gcs_available:
            return

        try:
            bucket = self._gcs_client.bucket(self.bucket_name)
            blob = bucket.blob(self._get_gcs_path(filename))

            content = json.dumps(data, indent=2, default=str)
            blob.upload_from_string(content, content_type="application/json")

            logger.info(f"☁️ Synced {filename} to GCS")

            # Create daily snapshot
            await self._create_daily_snapshot(filename, data)

        except Exception as e:
            logger.error(f"❌ GCS sync failed for {filename}: {e}")

    async def _create_daily_snapshot(self, filename: str, data: Dict[str, Any]):
        """Create a daily backup snapshot in GCS."""
        if not self._gcs_available:
            return

        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")
            snapshot_path = f"snapshots/{today}/{filename}"

            bucket = self._gcs_client.bucket(self.bucket_name)
            blob = bucket.blob(snapshot_path)

            # Only create if doesn't exist (once per day)
            if not blob.exists():
                content = json.dumps(data, indent=2, default=str)
                blob.upload_from_string(content, content_type="application/json")
                logger.info(f"📸 Created daily snapshot: {snapshot_path}")

        except Exception as e:
            logger.debug(f"Snapshot creation failed: {e}")

    async def force_sync(self):
        """Force immediate sync of all cached files to GCS."""
        if not self._gcs_available:
            logger.warning("⚠️ GCS not available, skipping force sync")
            return

        for filename in [AGENT_PERFORMANCE_FILE, ANALYTICS_METRICS_FILE, TRADE_HISTORY_FILE]:
            cache_path = self._get_cache_path(filename)
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r") as f:
                        data = json.load(f)
                    await self._sync_to_gcs(filename, data)
                except Exception as e:
                    logger.error(f"❌ Force sync failed for {filename}: {e}")

        logger.info("✅ Force sync complete")

    def get_status(self) -> Dict[str, Any]:
        """Get storage status for health checks."""
        return {
            "gcs_available": self._gcs_available,
            "bucket_name": self.bucket_name,
            "cache_dir": self.cache_dir,
            "last_sync_times": self._last_sync_time,
        }


# Global instance
_store: Optional[PersistentMetricsStore] = None


def get_metrics_store() -> PersistentMetricsStore:
    """Get or create the global persistent metrics store."""
    global _store
    if _store is None:
        _store = PersistentMetricsStore()
    return _store


# Convenience functions for common operations
async def load_agent_performance() -> Dict[str, Any]:
    """Load agent performance data."""
    return await get_metrics_store().load(AGENT_PERFORMANCE_FILE)


async def save_agent_performance(data: Dict[str, Any]):
    """Save agent performance data."""
    await get_metrics_store().save(AGENT_PERFORMANCE_FILE, data)


async def load_analytics_metrics() -> Dict[str, Any]:
    """Load analytics metrics data."""
    return await get_metrics_store().load(ANALYTICS_METRICS_FILE)


async def save_analytics_metrics(data: Dict[str, Any]):
    """Save analytics metrics data."""
    await get_metrics_store().save(ANALYTICS_METRICS_FILE, data)


async def load_trade_history() -> Dict[str, Any]:
    """Load trade history data."""
    return await get_metrics_store().load(TRADE_HISTORY_FILE)


async def save_trade_history(data: Dict[str, Any]):
    """Save trade history data."""
    await get_metrics_store().save(TRADE_HISTORY_FILE, data)
