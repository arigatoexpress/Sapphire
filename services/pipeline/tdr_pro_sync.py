"""The DeFi Report Pro sync pipeline.

Polls the public podcast RSS, fetches transcripts, writes markdown clippings
into the ~/Knowledge vault, and persists a machine-readable latest-episode
summary for the morning brief.

Live pulls are gated by ``SAPPHIRE_TDR_PRO_LIVE=1`` so CI stays deterministic.
Run from LaunchAgent ``com.sapphire.tdr-pro-sync`` or manually:

    SAPPHIRE_TDR_PRO_LIVE=1 python -m services.pipeline.tdr_pro_sync
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.sources.tdr_pro import TDRProSource, TDRProEpisode  # noqa: E402

log = logging.getLogger("tdr_pro_sync")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

KNOWLEDGE_INBOX = Path.home() / "Knowledge" / "0-Inbox" / "Clippings"
LATEST_JSON = ROOT / "data" / "intelligence" / "latest" / "tdr_pro_latest.json"
DEFAULT_LOOKBACK_DAYS = 14


def _episode_to_summary(ep: TDRProEpisode) -> dict:
    return {
        "guid": ep.guid,
        "title": ep.title,
        "episode": ep.episode,
        "published": ep.published_date,
        "url": ep.url,
        "transcript_url": ep.transcript_url,
        "audio_url": ep.audio_url,
        "duration_label": ep.duration_label,
        "slug": ep.slug,
    }


def sync(
    *,
    inbox_dir: Path | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 5,
) -> dict:
    """Fetch recent TDR Pro episodes and persist clippings + summary JSON.

    Returns a dict describing what was written.  Safe to run repeatedly:
    existing clippings are overwritten with the same filename, so the latest
    version always wins.
    """
    source = TDRProSource(inbox_dir=(inbox_dir or KNOWLEDGE_INBOX))
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    episodes = source.poll(since=since, limit=limit)
    log.info("found %d TDR Pro episode(s) since %s", len(episodes), since.date().isoformat())

    transcripts = source.fetch_transcripts(episodes)
    written = source.write_clippings(episodes, transcripts=transcripts)

    summary = {
        "synced_at": datetime.now(UTC).isoformat(),
        "lookback_days": lookback_days,
        "episodes_found": len(episodes),
        "clippings_written": [str(p) for p in written],
        "episodes": [_episode_to_summary(ep) for ep in episodes],
    }

    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("latest summary → %s", LATEST_JSON)

    return summary


def main() -> int:
    try:
        summary = sync()
    except Exception as exc:
        log.exception("tdr_pro sync failed")
        return 1

    if summary["episodes_found"]:
        log.info("wrote %d clipping(s)", len(summary["clippings_written"]))
    else:
        log.info("no new episodes in lookback window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
