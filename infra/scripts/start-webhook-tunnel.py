#!/usr/bin/env python3
"""Expose the Mac webhook receiver (localhost:9090) via Cloudflare Quick Tunnel.

Starts cloudflared, extracts the public URL, writes it to
data/webhook/tunnel_url.txt, and stays alive as long as the tunnel is up.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path.home() / "Code" / "Sapphire"
TUNNEL_LOG = ROOT / "data" / "logs" / "webhook-tunnel.log"
URL_FILE = ROOT / "data" / "webhook" / "tunnel_url.txt"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    TUNNEL_LOG.parent.mkdir(parents=True, exist_ok=True)
    URL_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(TUNNEL_LOG, "a") as log:
        log.write("\n--- tunnel start ---\n")
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", "http://localhost:9090"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        url_written = False
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                log.write(line)
                log.flush()
                if not url_written:
                    match = URL_RE.search(line)
                    if match:
                        URL_FILE.write_text(match.group(0) + "\n", encoding="utf-8")
                        log.write(f"tunnel_url={match.group(0)}\n")
                        log.flush()
                        url_written = True
        except Exception as exc:
            log.write(f"tunnel watcher error: {exc}\n")
            proc.terminate()
            return 1

    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
