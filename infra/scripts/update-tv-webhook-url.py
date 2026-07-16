#!/usr/bin/env python3
"""Sync Cloud Run TV_WEBHOOK_URL with the current Cloudflare Quick Tunnel origin.

Safe to run every few minutes: it only calls gcloud when the URL has changed.
This script is meant to be run by a LaunchAgent or cron job; it requires gcloud
and the Cloud Run update permission.

Usage:
    python3 infra/scripts/update-tv-webhook-url.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("update-tv-webhook-url")

ROOT = Path(__file__).resolve().parents[2]
TUNNEL_URL_FILE = ROOT / "data" / "webhook" / "tunnel_url.txt"
LAST_DEPLOYED_FILE = ROOT / "data" / "webhook" / "last_deployed_tv_url.txt"

SERVICE = "sapphire-alpha-dashboard"
REGION = "us-central1"
PROJECT = "sapphire-479610"


def _current_tunnel_url() -> str | None:
    if not TUNNEL_URL_FILE.exists():
        return None
    url = TUNNEL_URL_FILE.read_text().strip()
    if not url:
        return None
    return url


def _last_deployed_url() -> str | None:
    if not LAST_DEPLOYED_FILE.exists():
        return None
    return LAST_DEPLOYED_FILE.read_text().strip() or None


def _set_last_deployed(url: str) -> None:
    LAST_DEPLOYED_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_DEPLOYED_FILE.write_text(url, encoding="utf-8")


def _update_cloud_run(url: str, dry_run: bool) -> bool:
    cmd = [
        "gcloud",
        "run",
        "services",
        "update",
        SERVICE,
        "--region",
        REGION,
        "--project",
        PROJECT,
        "--update-env-vars",
        f"TV_WEBHOOK_URL={url}",
    ]
    if dry_run:
        log.info("[dry-run] would run: %s", " ".join(cmd))
        return True
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
        log.info("Updated Cloud Run TV_WEBHOOK_URL to %s", url)
        log.debug(result.stdout)
        return True
    except subprocess.CalledProcessError as exc:
        log.error("gcloud update failed: %s", exc.stderr)
        return False
    except Exception as exc:
        log.error("gcloud update error: %s", exc)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Log what would change without calling gcloud")
    args = parser.parse_args()

    current = _current_tunnel_url()
    if not current:
        log.warning("No tunnel URL found at %s", TUNNEL_URL_FILE)
        return 0

    last = _last_deployed_url()
    if current == last:
        log.debug("URL unchanged: %s", current)
        return 0

    log.info("Tunnel URL changed: %s -> %s", last, current)
    if _update_cloud_run(current, args.dry_run):
        if not args.dry_run:
            _set_last_deployed(current)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
