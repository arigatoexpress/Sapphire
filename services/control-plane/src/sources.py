from __future__ import annotations

from app.models import NewsSource


REPUTABLE_NEWS_SOURCES = [
    NewsSource(
        key="wsj-markets",
        name="WSJ (Markets)",
        rss_url="https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        reliability=0.95,
        category="equity",
    ),
    NewsSource(
        key="cnbc-markets",
        name="CNBC (Markets)",
        rss_url="https://www.cnbc.com/id/100003114/device/rss/rss.html",
        reliability=0.91,
        category="equity",
    ),
    NewsSource(
        key="federal-reserve",
        name="Federal Reserve (Press Releases)",
        rss_url="https://www.federalreserve.gov/feeds/press_all.xml",
        reliability=0.99,
        category="macro",
    ),
    NewsSource(
        key="sec-press-releases",
        name="SEC (Press Releases)",
        rss_url="https://www.sec.gov/news/pressreleases.rss",
        reliability=0.99,
        category="macro",
    ),
    NewsSource(
        key="us-treasury-press-releases",
        name="U.S. Treasury (Press Releases)",
        rss_url="https://home.treasury.gov/news/press-releases?format=atom",
        reliability=0.98,
        category="macro",
    ),
    NewsSource(
        key="cftc-press-releases",
        name="CFTC (Press Releases)",
        rss_url="https://www.cftc.gov/PressRoom/PressReleases/rss",
        reliability=0.98,
        category="macro",
    ),
    NewsSource(
        key="coindesk",
        name="CoinDesk",
        rss_url="https://www.coindesk.com/arc/outboundfeeds/rss",
        reliability=0.86,
        category="crypto",
    ),
    NewsSource(
        key="decrypt",
        name="Decrypt",
        rss_url="https://decrypt.co/feed",
        reliability=0.82,
        category="crypto",
    ),
]
