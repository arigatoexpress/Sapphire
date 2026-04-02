from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ChatConfig:
    chat_id: int
    subscribed: bool = True
    heartbeat_enabled: bool = True
    heartbeat_interval_minutes: int = 60
    # assistant_mode=personal prioritizes compact coaching + decisions over raw telemetry.
    assistant_mode: str = "personal"
    # Optional project scope for Telegram-first tasking/briefing.
    focus_project: str = ""
    # Proactive assistant check-ins in Telegram.
    proactive_checkins_enabled: bool = True
    assistant_checkin_interval_minutes: int = 120
    # Decision SLA reminder threshold (minutes).
    decision_sla_minutes: int = 180
    aster_assets: List[str] = field(default_factory=list)
    lighter_assets: List[str] = field(default_factory=list)
    extra_keywords: List[str] = field(default_factory=list)
    # Operator-provided focus that steers the bot's updates.
    operator_directive: str = ""
    # Per-chat assistant style preferences.
    preference_tone: str = "concise"
    preference_risk: str = "balanced"
    preference_coding_style: str = "pragmatic"
    # Rolling de-dup buffer of recently sent NewsItem ids to prevent spam.
    sent_item_ids: List[str] = field(default_factory=list)
    # Best-effort throttle for scheduled digests (prevents "spammy" bursts).
    last_digest_sent_at: Optional[datetime] = None
    # Last time an automated heartbeat was sent.
    last_heartbeat_sent_at: Optional[datetime] = None
    # Last proactive assistant check-in sent.
    last_assistant_checkin_at: Optional[datetime] = None
    # Last time an SLA reminder was sent for open decisions.
    last_decision_sla_reminder_at: Optional[datetime] = None


@dataclass(frozen=True)
class NewsSource:
    key: str
    name: str
    rss_url: str
    reliability: float
    category: str


@dataclass(frozen=True)
class NewsItem:
    id: str
    title: str
    url: str
    summary: str
    published_at: datetime
    source: NewsSource


@dataclass(frozen=True)
class ScoredNews:
    item: NewsItem
    alpha_score: int
    sentiment: int
    bias: str
    confidence: str
    asset_hits: List[str]
    keyword_hits: List[str]
    rationale: str
