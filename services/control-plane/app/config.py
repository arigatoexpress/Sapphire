from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _split_csv_int(raw: str) -> list[int]:
    output: list[int] = []
    for item in _split_csv(raw):
        try:
            output.append(int(item))
        except ValueError:
            continue
    return output


def _as_bool(raw: str, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str
    firestore_collection: str
    telegram_bot_token: str
    telegram_webhook_secret: str
    digest_top_k: int
    min_alpha_score: int
    max_news_age_hours: int
    request_timeout_seconds: float
    # Reduce spam + duplicates across frequent scheduler runs.
    min_digest_interval_minutes: int
    heartbeat_interval_minutes: int
    heartbeat_directive_max_chars: int
    timezone: str
    default_aster_assets: list[str]
    default_lighter_assets: list[str]
    default_macro_keywords: list[str]
    use_in_memory_store: bool
    job_shared_token: str
    control_plane_shared_token: str
    startup_register_webhook: bool
    public_base_url: str
    allowed_telegram_user_ids: list[int]
    allowed_telegram_chat_ids: list[int]
    # Article snippet enrichment + de-dupe sizing.
    snippet_cache_ttl_seconds: float
    snippet_fetch_timeout_seconds: float
    snippet_fetch_max_concurrency: int
    sent_item_id_buffer_size: int
    zkpass_enabled: bool = False
    zkpass_mode: str = "advisory"
    zkpass_required_actions: list[str] = field(default_factory=list)
    zkpass_allowed_schema_ids: list[str] = field(default_factory=list)
    zkpass_allowed_recipients: list[str] = field(default_factory=list)
    zkpass_allowed_allocator_addresses: list[str] = field(default_factory=list)
    zkpass_allowed_validator_addresses: list[str] = field(default_factory=list)
    zkpass_max_age_seconds: int = 86400
    zkpass_verify_signatures: bool = False
    zkpass_allocator_message_template: str = (
        "I am allocator and I have allocated task {taskId} with uHash {uHash}"
    )
    zkpass_validator_message_template: str = "I am validator and I have validated task {taskId}"
    zkpass_breakglass_enabled: bool = False
    zkpass_breakglass_token: str = ""
    zkpass_breakglass_allowed_actions: list[str] = field(default_factory=list)
    zkpass_breakglass_allowed_actors: list[str] = field(default_factory=list)
    zkpass_breakglass_require_reason: bool = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    on_cloud_run = bool(os.getenv("K_SERVICE"))
    request_timeout_seconds = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "12"))
    configured_project_id = (os.getenv("GCP_PROJECT_ID") or "").strip()
    platform_project_id = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    # In Cloud Run, prefer platform-provided project ID to avoid stale manual overrides.
    if on_cloud_run and platform_project_id:
        project_id = platform_project_id
    else:
        project_id = configured_project_id or platform_project_id or "sapphire"
    return Settings(
        gcp_project_id=project_id,
        firestore_collection=os.getenv("FIRESTORE_COLLECTION", "telegram_chats"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_webhook_secret=os.getenv("TELEGRAM_WEBHOOK_SECRET", ""),
        digest_top_k=int(os.getenv("DIGEST_TOP_K", "7")),
        min_alpha_score=int(os.getenv("MIN_ALPHA_SCORE", "35")),
        max_news_age_hours=int(os.getenv("MAX_NEWS_AGE_HOURS", "20")),
        request_timeout_seconds=request_timeout_seconds,
        min_digest_interval_minutes=int(os.getenv("MIN_DIGEST_INTERVAL_MINUTES", "60")),
        heartbeat_interval_minutes=int(os.getenv("HEARTBEAT_INTERVAL_MINUTES", "60")),
        heartbeat_directive_max_chars=int(os.getenv("HEARTBEAT_DIRECTIVE_MAX_CHARS", "600")),
        timezone=os.getenv("TIMEZONE", "UTC"),
        # Aster Shield: tokenized equities + commodities perps (USDT-margined).
        default_aster_assets=_split_csv(
            os.getenv("DEFAULT_ASTER_ASSETS", "AAPL,TSLA,NVDA,GOLD,SILVER")
        ),
        # Lighter: crypto perps (WETH/WBTC-style symbols).
        default_lighter_assets=_split_csv(
            os.getenv("DEFAULT_LIGHTER_ASSETS", "WETH,WBTC,SOL,LINK,UNI")
        ),
        default_macro_keywords=_split_csv(
            os.getenv(
                "DEFAULT_MACRO_KEYWORDS",
                "fed,interest rate,cpi,inflation,etf,liquidity,regulation,earnings",
            )
        ),
        # Default to in-memory store for local dev, but use Firestore on Cloud Run.
        use_in_memory_store=_as_bool(os.getenv("USE_IN_MEMORY_STORE"), default=(not on_cloud_run)),
        job_shared_token=os.getenv("JOB_SHARED_TOKEN", ""),
        control_plane_shared_token=os.getenv("CONTROL_PLANE_SHARED_TOKEN", ""),
        startup_register_webhook=_as_bool(
            os.getenv("STARTUP_REGISTER_WEBHOOK", "false"), default=False
        ),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
        allowed_telegram_user_ids=_split_csv_int(os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")),
        allowed_telegram_chat_ids=_split_csv_int(os.getenv("ALLOWED_TELEGRAM_CHAT_IDS", "")),
        snippet_cache_ttl_seconds=float(os.getenv("SNIPPET_CACHE_TTL_SECONDS", str(6 * 3600))),
        snippet_fetch_timeout_seconds=float(
            os.getenv("SNIPPET_FETCH_TIMEOUT_SECONDS", str(request_timeout_seconds))
        ),
        snippet_fetch_max_concurrency=int(os.getenv("SNIPPET_FETCH_MAX_CONCURRENCY", "3")),
        sent_item_id_buffer_size=int(os.getenv("SENT_ITEM_ID_BUFFER_SIZE", "2500")),
        zkpass_enabled=_as_bool(os.getenv("ZKPASS_ENABLED", "false"), default=False),
        zkpass_mode=os.getenv("ZKPASS_MODE", "advisory").strip().lower() or "advisory",
        zkpass_required_actions=_split_csv(
            os.getenv(
                "ZKPASS_REQUIRED_ACTIONS",
                "control.executor_policy.update,org.initialize.apply,control.agents.cleanup",
            )
        ),
        zkpass_allowed_schema_ids=_split_csv(os.getenv("ZKPASS_ALLOWED_SCHEMA_IDS", "")),
        zkpass_allowed_recipients=_split_csv(os.getenv("ZKPASS_ALLOWED_RECIPIENTS", "")),
        zkpass_allowed_allocator_addresses=_split_csv(
            os.getenv("ZKPASS_ALLOWED_ALLOCATOR_ADDRESSES", "")
        ),
        zkpass_allowed_validator_addresses=_split_csv(
            os.getenv("ZKPASS_ALLOWED_VALIDATOR_ADDRESSES", "")
        ),
        zkpass_max_age_seconds=int(os.getenv("ZKPASS_MAX_AGE_SECONDS", "86400")),
        zkpass_verify_signatures=_as_bool(
            os.getenv("ZKPASS_VERIFY_SIGNATURES", "false"), default=False
        ),
        zkpass_allocator_message_template=os.getenv(
            "ZKPASS_ALLOCATOR_MESSAGE_TEMPLATE",
            "I am allocator and I have allocated task {taskId} with uHash {uHash}",
        ),
        zkpass_validator_message_template=os.getenv(
            "ZKPASS_VALIDATOR_MESSAGE_TEMPLATE",
            "I am validator and I have validated task {taskId}",
        ),
        zkpass_breakglass_enabled=_as_bool(
            os.getenv("ZKPASS_BREAKGLASS_ENABLED", "false"), default=False
        ),
        zkpass_breakglass_token=os.getenv("ZKPASS_BREAKGLASS_TOKEN", ""),
        zkpass_breakglass_allowed_actions=_split_csv(
            os.getenv("ZKPASS_BREAKGLASS_ALLOWED_ACTIONS", "")
        ),
        zkpass_breakglass_allowed_actors=_split_csv(
            os.getenv("ZKPASS_BREAKGLASS_ALLOWED_ACTORS", "")
        ),
        zkpass_breakglass_require_reason=_as_bool(
            os.getenv("ZKPASS_BREAKGLASS_REQUIRE_REASON", "true"), default=True
        ),
    )
