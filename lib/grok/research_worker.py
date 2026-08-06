"""Validate Windows research-worker manifests (paper_only invariant)."""

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_TRUE = (
    "paper_only",
)
REQUIRED_FALSE = (
    "live_trading_enabled",
    "telegram_sends_enabled",
)
REQUIRED_KEYS = (
    "schema_version",
    "generated_at",
    "host",
    "git_sha",
    "paper_only",
    "live_trading_enabled",
    "telegram_sends_enabled",
)


def validate_research_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return {ok, errors, warnings} for a research-worker manifest dict."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(manifest, Mapping):
        return {"ok": False, "errors": ["manifest_not_object"], "warnings": []}

    for k in REQUIRED_KEYS:
        if k not in manifest:
            errors.append(f"missing_key:{k}")

    for k in REQUIRED_TRUE:
        if k in manifest and manifest[k] is not True:
            errors.append(f"{k}_must_be_true")

    for k in REQUIRED_FALSE:
        if k in manifest and manifest[k] is not False:
            errors.append(f"{k}_must_be_false")

    ver = manifest.get("schema_version")
    if ver is not None and int(ver) < 1:
        errors.append("schema_version_lt_1")

    if not manifest.get("git_sha"):
        warnings.append("empty_git_sha")

    max_age = manifest.get("max_age_seconds", 36 * 3600)
    age = manifest.get("age_seconds")
    if age is not None and max_age is not None:
        try:
            if float(age) > float(max_age):
                warnings.append("stale_manifest")
        except (TypeError, ValueError):
            warnings.append("bad_age_fields")

    return {"ok": not errors, "errors": errors, "warnings": warnings}
