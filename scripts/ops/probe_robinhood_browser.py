"""Probe Robinhood login state using the authenticated Brave profile.

No credentials are used. If Brave has an active robinhood.com session, this
prints the account nickname and a session-health summary. If not, it reports
that the user needs to log in via Brave first.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.sources.brave_browser import BraveSession, _BRAVE_PROFILE_ROOT  # noqa: E402


async def main() -> int:
    session = BraveSession(profile_dir=_BRAVE_PROFILE_ROOT, headless=True, port=9223)
    async with session:
        # Authenticated pages redirect to /login when the session is missing.
        await session.navigate("https://robinhood.com/account", wait_load=True)
        await session.wait(2)
        url = await session.evaluate("window.location.href")
        text = await session.get_text()

        cookies = await session.get_cookies(".robinhood.com")
        session_cookie_names = {c.get("name") for c in cookies}

        logged_in = "/login" not in str(url) and ("Portfolio" in text or "Account" in text or "session_id" in session_cookie_names)

        print(json.dumps({
            "url": url,
            "logged_in": logged_in,
            "robinhood_cookie_names": sorted(session_cookie_names),
            "page_sample": text[:300].replace("\n", " ").strip(),
        }, indent=2))
        return 0 if logged_in else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
