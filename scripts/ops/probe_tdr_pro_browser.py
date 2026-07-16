"""Probe The DeFi Report Pro members site using the authenticated Brave profile.

No credentials are used. If Brave has an active thedefireport.io session,
this prints the latest members-only page title and links.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.sources.brave_browser import _BRAVE_PROFILE_ROOT, BraveSession  # noqa: E402


async def main() -> int:
    session = BraveSession(profile_dir=_BRAVE_PROFILE_ROOT, headless=True, port=9224)
    async with session:
        await session.navigate("https://thedefireport.io/members", wait_load=True)
        await session.wait(3)
        url = await session.evaluate("window.location.href")
        title = await session.evaluate("document.title")
        text = await session.get_text()

        print(
            json.dumps(
                {
                    "url": url,
                    "title": title,
                    "members_gated": "/login" in str(url)
                    or "Sign in" in text
                    or "Subscribe" in text,
                    "page_sample": text[:400].replace("\n", " ").strip(),
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
