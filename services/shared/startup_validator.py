"""
Startup configuration validator.

Each service calls validate_config() at boot with its list of required variables.
Missing or empty vars are logged clearly; the process exits so Cloud Run restarts it
immediately with a visible error — far better than silently running with bad config.

Usage::

    from startup_validator import validate_config

    validate_config(
        service="bot-lighter",
        required=["LIGHTER_PUB_KEY", "LIGHTER_PRIV_KEY", "GOOGLE_CLOUD_PROJECT"],
        warn_if_missing=["GEMINI_API_KEY"],
    )
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


def validate_config(
    service: str,
    required: list[str],
    warn_if_missing: list[str] | None = None,
) -> None:
    """
    Validate that all *required* environment variables are non-empty.

    Parameters
    ----------
    service:
        Service name used in log messages.
    required:
        Env var names that MUST be set; missing → exit(1).
    warn_if_missing:
        Env var names that are strongly recommended; missing → warning only.
    """
    missing: list[str] = []
    for var in required:
        if not os.environ.get(var, "").strip():
            missing.append(var)

    if missing:
        logger.critical(
            "❌ [%s] STARTUP FAILED — missing required environment variables:\n%s\n"
            "Set the above variables and redeploy.",
            service,
            "\n".join(f"  • {v}" for v in missing),
        )
        # Also print to stderr so Cloud Run surfacing captures it even before logging is set up.
        print(
            f"FATAL [{service}]: missing required env vars: {', '.join(missing)}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    for var in (warn_if_missing or []):
        if not os.environ.get(var, "").strip():
            logger.warning(
                "⚠️  [%s] Optional env var not set — feature may be degraded: %s",
                service,
                var,
            )

    logger.info(
        "✅ [%s] Config validation passed (%d required vars present)",
        service,
        len(required),
    )
