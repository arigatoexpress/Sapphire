"""Reusable health-context helper.

Centralizes the live-system snapshot logic that was previously inlined across
the deprecated ``services/telegram-bot/app.py`` (PR #383),
``plugins/claw-sapphire/tools/internal/dev_pulse.py``,
``plugins/claw-sapphire/tools/internal/morning_digest.py``, and the
observability dashboard (Lane 2).

The helper is **pure**: no I/O, no globals, no module-load side effects. Callers
inject the raw JSON payloads from ``health_check.py``, ``status.py``, etc.;
``build_health_context`` shapes them into a typed snapshot suited for the
target surface.

Why a helper? PR #383 added a Telegram-side "live system prompt" that prevents
stale facts (e.g. quoting a 1,200-customer figure that has since grown). The
exact same dance — call ``health_check.py``, call ``status.py``, render bullets
— needed to repeat for the morning digest, dev_pulse, and the observability
endpoint. A shared helper keeps every surface honest with one definition of
"compact health summary".

Scopes:
    - ``"telegram"``  — compact prompt block for Telegram operator surfaces.
    - ``"morning"``   — structured snapshot (dict-friendly) for the morning digest.
    - ``"ops"``       — full snapshot for ops dashboards / observability API.
    - ``"minimal"``   — bare overall + summary, for very short surfaces.

Clock injection: tests pin ``now=lambda: datetime(2026, 4, 28, ...)`` to keep
date-derived strings deterministic. See ``tests/unit/test_health_context_helper.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Public scope literal — keep in sync with build_health_context()
# ---------------------------------------------------------------------------

Scope = Literal["telegram", "morning", "ops", "minimal"]
_VALID_SCOPES: tuple[str, ...] = ("telegram", "morning", "ops", "minimal")


# ---------------------------------------------------------------------------
# Status icon table (kept identical to the historical Telegram render)
# ---------------------------------------------------------------------------

_STATUS_ICON: dict[str, str] = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
_DEFAULT_ICON = "⚪"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """A single named health check (service / data-freshness / inference / etc.)."""

    name: str
    status: str  # "green" | "yellow" | "red" | "unknown"
    detail: str = ""
    icon: str = _DEFAULT_ICON


@dataclass(frozen=True, slots=True)
class InferenceSnapshot:
    """Inference-tier snapshot derived from status.py JSON."""

    proxy_health: dict[str, str] = field(default_factory=dict)
    local_models: tuple[str, ...] = ()
    gpu_models: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.proxy_health or self.local_models or self.gpu_models)


@dataclass(frozen=True, slots=True)
class HealthContext:
    """Structured snapshot returned by ``build_health_context``.

    The shape is stable across scopes — narrower scopes simply leave optional
    fields empty (``checks=()``, ``inference.is_empty``). The ``rendered_lines``
    field is the surface-specific text representation, identical to what each
    caller previously emitted inline.
    """

    scope: Scope
    overall: str  # "GREEN" | "YELLOW" | "RED" | "UNKNOWN"
    summary: str
    collected_at: str  # ISO-8601 UTC; pinned via injected clock in tests
    checks: tuple[HealthCheck, ...] = ()
    inference: InferenceSnapshot = field(default_factory=InferenceSnapshot)
    errors: tuple[str, ...] = ()
    rendered_lines: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Stable JSON-friendly serialization (used by the ops dashboard endpoint)."""
        payload = asdict(self)
        # asdict converts the tuple into a list, which is fine for JSON; we
        # also flatten the nested dataclasses so callers don't need to know
        # about the helper's internal types.
        payload["inference"] = {
            "proxy_health": dict(self.inference.proxy_health),
            "local_models": list(self.inference.local_models),
            "gpu_models": list(self.inference.gpu_models),
        }
        payload["checks"] = [asdict(c) for c in self.checks]
        payload["errors"] = list(self.errors)
        payload["rendered_lines"] = list(self.rendered_lines)
        return payload


# ---------------------------------------------------------------------------
# Internal extraction helpers — pure, scope-agnostic
# ---------------------------------------------------------------------------


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _checks_from_health(data: dict[str, Any], *, include_repos: bool) -> tuple[HealthCheck, ...]:
    sections = ["services", "data_freshness", "inference"]
    if include_repos:
        sections.insert(1, "repos")
    out: list[HealthCheck] = []
    for section in sections:
        items = _coerce_dict(data.get(section))
        for name, info in items.items():
            info_dict = _coerce_dict(info)
            status = str(info_dict.get("status", "unknown"))
            detail = str(info_dict.get("detail", ""))[:70]
            out.append(
                HealthCheck(
                    name=str(name),
                    status=status,
                    detail=detail,
                    icon=_STATUS_ICON.get(status, _DEFAULT_ICON),
                )
            )
    return tuple(out)


def _inference_from_status(data: dict[str, Any]) -> InferenceSnapshot:
    inference = _coerce_dict(data.get("inference"))
    proxy = _coerce_dict(inference.get("proxy_health"))
    local_models = inference.get("local_models", []) or []
    gpu_models = inference.get("gpu_models", []) or []
    if not isinstance(local_models, list):
        local_models = []
    if not isinstance(gpu_models, list):
        gpu_models = []
    return InferenceSnapshot(
        proxy_health={str(k): str(v) for k, v in proxy.items()},
        local_models=tuple(str(m) for m in local_models),
        gpu_models=tuple(str(m) for m in gpu_models),
    )


def _now(clock: Callable[[], datetime] | None) -> datetime:
    if clock is None:
        return datetime.now(UTC)
    value = clock()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


# ---------------------------------------------------------------------------
# Per-scope renderers — produce the exact text the inline code used to emit
# ---------------------------------------------------------------------------


_TELEGRAM_PREAMBLE: tuple[str, ...] = (
    "You are Sapphire, the AI assistant for Kadima Digital Strategies.",
    "You are sharp, concise, technically deep but accessible. You are a trusted advisor, not a chatbot.",
    "Use the live context below as the only current operational truth. If a field is missing, stale, red, or unavailable, say that directly instead of filling gaps from memory.",
    "Never quote historical test counts, customer counts, model counts, win rates, or repo totals unless they appear in this live context or in a slash-command result from this request.",
    "For precise data queries, suggest the relevant slash command such as /health, /status, /price, /threats, or /events.",
    "Keep responses under 300 words unless the topic warrants depth.",
)


def _render_health_lines(
    ctx_overall: str, ctx_summary: str, checks: tuple[HealthCheck, ...]
) -> list[str]:
    """Match the historical ``_health_lines`` output verbatim."""
    lines = [f"*{ctx_overall}* — {ctx_summary}"]
    for c in checks:
        lines.append(f"{c.icon} `{c.name}`: {c.detail}")
    return lines


def _render_status_lines(inference: InferenceSnapshot) -> list[str]:
    """Match the historical ``_status_lines`` output verbatim."""
    lines: list[str] = []
    if inference.proxy_health:
        tier_bits = [f"{name}={state}" for name, state in sorted(inference.proxy_health.items())]
        lines.append("Inference proxy: " + ", ".join(tier_bits))
    if inference.local_models:
        lines.append(
            f"Mac Ollama models: {len(inference.local_models)} ({', '.join(inference.local_models[:5])})"
        )
    if inference.gpu_models:
        lines.append(
            f"GPU Ollama models: {len(inference.gpu_models)} ({', '.join(inference.gpu_models[:5])})"
        )
    if not lines:
        lines.append("Inference proxy/model inventory unavailable from live status.py.")
    return lines


def _render_telegram(
    *,
    overall: str,
    summary: str,
    checks: tuple[HealthCheck, ...],
    inference: InferenceSnapshot,
    health_available: bool,
    collected_at: str,
) -> tuple[str, ...]:
    """Reproduce ``build_live_system_prompt`` exactly.

    The output is a single big string when ``"\\n".join(...)`` is applied, but
    the helper returns it as a tuple so callers can keep individual lines.
    """
    lines: list[str] = list(_TELEGRAM_PREAMBLE)
    lines.append("")
    lines.append(f"Live context collected at {collected_at}:")
    if health_available:
        lines.append("Health snapshot:")
        lines.extend(f"- {line}" for line in _render_health_lines(overall, summary, checks))
    else:
        lines.append("Health snapshot: unavailable from health_check.py.")
    lines.append("Status snapshot:")
    lines.extend(f"- {line}" for line in _render_status_lines(inference))
    return tuple(lines)


def _render_morning(
    *,
    overall: str,
    summary: str,
    checks: tuple[HealthCheck, ...],
    inference: InferenceSnapshot,
    collected_at: str,
) -> tuple[str, ...]:
    """Compact bullet list for the morning digest. Mirrors the dev_pulse digest tone."""
    lines: list[str] = [
        f"*Health* — {overall}: {summary}",
        f"_Collected at {collected_at}_",
    ]
    if checks:
        attention = [c for c in checks if c.status in {"yellow", "red"}]
        if attention:
            lines.append(f"- Attention: {len(attention)}/{len(checks)} checks not green")
            for c in attention[:8]:
                lines.append(f"  {c.icon} {c.name}: {c.detail}")
        else:
            lines.append(f"- All {len(checks)} checks green")
    if not inference.is_empty:
        if inference.proxy_health:
            tier_bits = [f"{n}={s}" for n, s in sorted(inference.proxy_health.items())]
            lines.append("- Inference proxy: " + ", ".join(tier_bits))
        if inference.local_models:
            lines.append(f"- Mac Ollama: {len(inference.local_models)} models")
        if inference.gpu_models:
            lines.append(f"- GPU Ollama: {len(inference.gpu_models)} models")
    return tuple(lines)


def _render_ops(
    *,
    overall: str,
    summary: str,
    checks: tuple[HealthCheck, ...],
    inference: InferenceSnapshot,
    errors: tuple[str, ...],
    collected_at: str,
) -> tuple[str, ...]:
    """Comprehensive snapshot rendering — every check listed."""
    lines: list[str] = [
        f"OVERALL: {overall} — {summary}",
        f"COLLECTED_AT: {collected_at}",
    ]
    if checks:
        lines.append(f"CHECKS ({len(checks)}):")
        for c in checks:
            lines.append(f"  {c.icon} [{c.status}] {c.name}: {c.detail}")
    if not inference.is_empty:
        lines.append("INFERENCE:")
        if inference.proxy_health:
            for name, state in sorted(inference.proxy_health.items()):
                lines.append(f"  proxy {name}: {state}")
        if inference.local_models:
            lines.append(
                f"  mac models ({len(inference.local_models)}): {', '.join(inference.local_models)}"
            )
        if inference.gpu_models:
            lines.append(
                f"  gpu models ({len(inference.gpu_models)}): {', '.join(inference.gpu_models)}"
            )
    if errors:
        lines.append(f"ERRORS ({len(errors)}):")
        for err in errors:
            lines.append(f"  - {err[:200]}")
    return tuple(lines)


def _render_minimal(*, overall: str, summary: str, collected_at: str) -> tuple[str, ...]:
    return (f"{overall} — {summary}", f"@ {collected_at}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_health_context(
    scope: Scope,
    *,
    health_payload: dict[str, Any] | None = None,
    status_payload: dict[str, Any] | None = None,
    extra_errors: list[str] | tuple[str, ...] | None = None,
    now: Callable[[], datetime] | None = None,
) -> HealthContext:
    """Build a typed health snapshot from raw tool JSON payloads.

    Args:
        scope: One of ``"telegram"``, ``"morning"``, ``"ops"``, ``"minimal"``.
            Determines which fields are populated and how ``rendered_lines``
            looks. Narrower scopes still return a complete dataclass — they
            simply leave optional fields empty.
        health_payload: The parsed JSON from ``health_check.py``. ``None`` (or
            an empty dict) means "health snapshot unavailable" and the helper
            renders the corresponding fallback line.
        status_payload: The parsed JSON from ``status.py``. ``None``/empty
            means "no inference data".
        extra_errors: Out-of-band collector errors (e.g. dev_pulse threadpool
            exceptions) to surface in the ``ops`` rendering.
        now: Optional clock callable returning a ``datetime`` for the
            ``collected_at`` field. Defaults to ``datetime.now(UTC)``. Tests
            inject this to pin output.

    Returns:
        A frozen ``HealthContext``. Use ``rendered_lines`` for the textual
        surface (Telegram bot system prompt, morning digest health block, etc.)
        or ``to_dict()`` for the JSON shape consumed by the observability
        dashboard.

    Raises:
        ValueError: If ``scope`` is not one of the four supported literals.
    """
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {_VALID_SCOPES}")

    health_payload = health_payload or {}
    status_payload = status_payload or {}
    extra_errors_tuple: tuple[str, ...] = (
        tuple(str(e) for e in extra_errors) if extra_errors else ()
    )

    health_available = bool(health_payload)
    overall = str(health_payload.get("overall", "UNKNOWN")) if health_available else "UNKNOWN"
    summary = str(health_payload.get("summary", "no summary")) if health_available else "no summary"

    include_repos = scope in {"morning", "ops"}
    checks = _checks_from_health(health_payload, include_repos=include_repos)
    inference = _inference_from_status(status_payload)

    collected_at = _now(now).isoformat()

    if scope == "telegram":
        rendered = _render_telegram(
            overall=overall,
            summary=summary,
            checks=checks,
            inference=inference,
            health_available=health_available,
            collected_at=collected_at,
        )
    elif scope == "morning":
        rendered = _render_morning(
            overall=overall,
            summary=summary,
            checks=checks,
            inference=inference,
            collected_at=collected_at,
        )
    elif scope == "ops":
        rendered = _render_ops(
            overall=overall,
            summary=summary,
            checks=checks,
            inference=inference,
            errors=extra_errors_tuple,
            collected_at=collected_at,
        )
    else:  # minimal
        rendered = _render_minimal(
            overall=overall,
            summary=summary,
            collected_at=collected_at,
        )

    return HealthContext(
        scope=scope,
        overall=overall,
        summary=summary,
        collected_at=collected_at,
        checks=checks if scope != "minimal" else (),
        inference=inference if scope != "minimal" else InferenceSnapshot(),
        errors=extra_errors_tuple,
        rendered_lines=rendered,
    )


__all__ = [
    "HealthCheck",
    "HealthContext",
    "InferenceSnapshot",
    "Scope",
    "build_health_context",
]
