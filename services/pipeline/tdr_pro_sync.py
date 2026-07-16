"""The DeFi Report Pro sync pipeline.

Polls the public podcast RSS, fetches transcripts, writes markdown clippings
into the ~/Knowledge vault, maintains a master episode index, and persists a
machine-readable latest-episode summary for the morning brief.

Live pulls are gated by ``SAPPHIRE_TDR_PRO_LIVE=1`` so CI stays deterministic.
Run from LaunchAgent ``com.sapphire.tdr-pro-sync`` or manually:

    SAPPHIRE_TDR_PRO_LIVE=1 python -m services.pipeline.tdr_pro_sync

CLI flags are available for ad-hoc runs:

    SAPPHIRE_TDR_PRO_LIVE=1 python -m services.pipeline.tdr_pro_sync --dry-run --limit 3
    python -m services.pipeline.tdr_pro_sync --index-only
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.sources.tdr_pro import TDR_PRO_RSS_URL, TDRProEpisode, TDRProSource  # noqa: E402

log = logging.getLogger("tdr_pro_sync")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)

KNOWLEDGE_INBOX = Path.home() / "Knowledge" / "0-Inbox" / "Clippings"
KNOWLEDGE_HUB = Path.home() / "Knowledge" / "3-Resources" / "Clippings"
HUB_INDEX = KNOWLEDGE_HUB / "tdr-pro-index.md"
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


def _load_local_episodes(source: TDRProSource) -> list[TDRProEpisode]:
    """Rehydrate episode metadata from clippings already in the vault.

    Scans the curated hub directory first, then the inbox, so manually
    processed clippings take precedence over raw inbox copies.  The index can
    therefore be rebuilt from local clippings without polling RSS.
    """
    episodes: list[TDRProEpisode] = []
    search_dirs = [KNOWLEDGE_HUB, source.inbox_dir]
    seen_episodes: set[str] = set()
    seen_slugs: set[str] = set()
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.md"):
            if path.name == HUB_INDEX.name or path.stem in seen_slugs:
                continue
            text = path.read_text(encoding="utf-8")
            source_field = next(
                (line.split(":", 1)[1].strip().strip('"').lower() for line in text.splitlines() if line.strip().startswith("source:")),
                "",
            )
            if "tdr_pro" not in source_field and "defi report" not in source_field:
                continue
            try:
                fm_end = text.index("\n---", 4)
                fm = text[4:fm_end]
                body = text[fm_end + 4 :]
                fields: dict[str, str] = {}
                for line in fm.splitlines():
                    if ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    value = value.strip().strip('"')
                    fields[key.strip()] = value

                episode = fields.get("episode", "").lstrip("Ee")
                title = fields.get("title", path.stem)
                published = fields.get("published", "")
                pub_dt = datetime.fromisoformat(published).replace(tzinfo=UTC) if published else datetime.now(UTC)
                audio_url = fields.get("audio_url", "")
                transcript_url = fields.get("transcript_url", "")
                url = fields.get("url", "")
                description = ""
                if "## Show notes" in body:
                    description = body.split("## Show notes", 1)[1].split("##", 1)[0].strip()

                # Fallback: old-format clippings kept URLs in body bullets.
                if not audio_url:
                    for line in body.splitlines():
                        if line.strip().startswith("- Audio:"):
                            audio_url = line.split(":", 1)[1].strip()
                            break
                if not transcript_url:
                    for line in body.splitlines():
                        if line.strip().startswith("- Transcript:"):
                            transcript_url = line.split(":", 1)[1].strip()
                            break

                episode_key = episode or path.stem
                if episode_key in seen_episodes:
                    continue
                seen_episodes.add(episode_key)
                seen_slugs.add(path.stem)
                episodes.append(
                    TDRProEpisode(
                        guid=path.stem,
                        title=title,
                        description=description,
                        url=url or audio_url or transcript_url or TDR_PRO_RSS_URL,
                        published_at=pub_dt,
                        episode=episode or None,
                        audio_url=audio_url or None,
                        transcript_url=transcript_url or None,
                        slug_override=path.stem,
                    )
                )
            except Exception:
                log.warning("skipping malformed local clipping %s", path)
                continue
    return episodes


def sync(
    *,
    inbox_dir: Path | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    limit: int = 5,
    dry_run: bool = False,
) -> dict:
    """Fetch recent TDR Pro episodes and persist clippings + index + summary JSON.

    Returns a dict describing what was written.  Safe to run repeatedly:
    existing clippings are overwritten with the same filename, so the latest
    version always wins.
    """
    source = TDRProSource(inbox_dir=(inbox_dir or KNOWLEDGE_INBOX))
    since = datetime.now(UTC) - timedelta(days=lookback_days)

    episodes = source.poll(since=since, limit=limit)
    log.info("found %d TDR Pro episode(s) since %s", len(episodes), since.date().isoformat())

    transcripts = source.fetch_transcripts(episodes)
    written = source.write_clippings(
        episodes,
        transcripts=transcripts,
        dry_run=dry_run,
        index_path=HUB_INDEX.name,
    )
    index_path = source.write_hub_index(
        episodes,
        index_path=HUB_INDEX,
        dry_run=dry_run,
    )

    summary = {
        "synced_at": datetime.now(UTC).isoformat(),
        "lookback_days": lookback_days,
        "episodes_found": len(episodes),
        "clippings_written": [str(p) for p in written],
        "hub_index": str(index_path),
        "episodes": [_episode_to_summary(ep) for ep in episodes],
    }

    if not dry_run:
        LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
        LATEST_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        log.info("latest summary → %s", LATEST_JSON)

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync The DeFi Report Pro podcast into the Knowledge vault.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write any files.")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS, help="Days to look back.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum episodes to fetch.")
    parser.add_argument("--index-only", action="store_true", help="Rebuild the hub index from local clippings without polling RSS.")
    args = parser.parse_args(argv)

    try:
        if args.index_only:
            source = TDRProSource(inbox_dir=KNOWLEDGE_INBOX)
            episodes = _load_local_episodes(source)
            if not episodes:
                log.info("no local TDR Pro clippings found in %s", source.inbox_dir)
                return 0
            index_path = source.write_hub_index(episodes, index_path=HUB_INDEX)
            log.info("rebuilt hub index with %d episode(s) → %s", len(episodes), index_path)
            return 0

        summary = sync(lookback_days=args.lookback_days, limit=args.limit, dry_run=args.dry_run)
    except Exception:
        log.exception("tdr_pro sync failed")
        return 1

    if summary["episodes_found"]:
        log.info("wrote %d clipping(s)", len(summary["clippings_written"]))
        log.info("hub index → %s", summary["hub_index"])
    else:
        log.info("no new episodes in lookback window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
