"""Per-tier cost model for inference mesh telemetry.

Tier cost basis (as of 2026-04-29):

- **T1 Windows GPU** (RTX 5070 Ti, ~285 W TBP, ~0.4s/inference): treated as an
  *electricity-only proxy* of $0.001 per inference. Operator can re-tune via
  ``CostModel.t1_per_inference_usd`` after a real wattage + duty-cycle
  measurement; default chosen as the lane's stated proxy and documented as
  illustrative, not metered.
- **T2 Pi (rari1 + rari2)**: negligible (~5W ARM SBCs). Default cost = 0.0.
- **T3 Mac local**: electricity-only proxy. The Mac is "always-on" anyway, so
  marginal inference cost is bounded by extra wattage during inference. Default
  $0.0008 per inference (slightly less than the GPU proxy) as a placeholder.
- **T4 Kimi Cloud (Moonshot)**: per-token cost using Moonshot's published
  pricing. **No live API calls; rates are operator-supplied at instantiation
  time.** The default model uses zero rates and emits a clear note so
  recommender output never silently inflates a cost report. Operators populate
  the rates from Moonshot's published page:
  https://platform.moonshot.cn/docs/pricing/chat (retrieval date 2026-04-29).

Why we don't hard-code Kimi rates:
- Lane spec forbids live API calls.
- Moonshot pricing varies by SKU (kimi-k2, kimi-k1.5, etc.) and changes over
  time; baking a rate in could turn into stale fabrication.
- The recommender labels Kimi cost cells as "rate-supplied=False" when the
  default model is used, so operators see the gap explicitly.

Honest framing: every recommendation surfaces this caveat. Operators decide
what rates to apply; the library never invents them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import (
    TIER_T1_GPU,
    TIER_T2_PI_1,
    TIER_T2_PI_2,
    TIER_T3_MAC,
    TIER_T4_KIMI,
)

if TYPE_CHECKING:
    from .aggregator import CallRecord

MOONSHOT_PRICING_URL = "https://platform.moonshot.cn/docs/pricing/chat"
MOONSHOT_PRICING_RETRIEVED = "2026-04-29"


@dataclass(frozen=True)
class CostModel:
    """Per-tier cost-model parameters.

    Attributes:
        name: short identifier surfaced in reports / provenance.
        t1_per_inference_usd: USD per inference for T1 Windows GPU.
        t2_per_inference_usd: USD per inference for T2 Pi (rari1, rari2).
        t3_per_inference_usd: USD per inference for T3 Mac local.
        t4_input_usd_per_1k_tokens: USD / 1000 input tokens for T4 Kimi Cloud.
        t4_output_usd_per_1k_tokens: USD / 1000 output tokens for T4 Kimi Cloud.
        moonshot_pricing_url: citation URL — required so report viewers can
            verify the rates against Moonshot's source of truth.
        moonshot_pricing_retrieved: retrieval date for ``moonshot_pricing_url``.
        kimi_rates_supplied: True iff operator passed real per-token rates.
            Default ``CostModel`` has zero rates and ``kimi_rates_supplied=False``,
            which is honest — Kimi cost is unknown.
    """

    name: str = "default"
    t1_per_inference_usd: float = 0.001
    t2_per_inference_usd: float = 0.0
    t3_per_inference_usd: float = 0.0008
    t4_input_usd_per_1k_tokens: float = 0.0
    t4_output_usd_per_1k_tokens: float = 0.0
    moonshot_pricing_url: str = MOONSHOT_PRICING_URL
    moonshot_pricing_retrieved: str = MOONSHOT_PRICING_RETRIEVED
    kimi_rates_supplied: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "t1_per_inference_usd": self.t1_per_inference_usd,
            "t2_per_inference_usd": self.t2_per_inference_usd,
            "t3_per_inference_usd": self.t3_per_inference_usd,
            "t4_input_usd_per_1k_tokens": self.t4_input_usd_per_1k_tokens,
            "t4_output_usd_per_1k_tokens": self.t4_output_usd_per_1k_tokens,
            "moonshot_pricing_url": self.moonshot_pricing_url,
            "moonshot_pricing_retrieved": self.moonshot_pricing_retrieved,
            "kimi_rates_supplied": self.kimi_rates_supplied,
            "notes": list(self.notes),
        }


DEFAULT_COST_MODEL = CostModel(
    name="default",
    notes=(
        "T1 + T3 use electricity-only proxies; tune to your wattage measurements.",
        "T4 Kimi Cloud rates default to 0 — supply real rates via with_kimi_rates() "
        f"after consulting {MOONSHOT_PRICING_URL} ({MOONSHOT_PRICING_RETRIEVED}).",
    ),
)


def with_kimi_rates(
    *,
    input_usd_per_1k_tokens: float,
    output_usd_per_1k_tokens: float,
    base: CostModel | None = None,
    name: str = "operator-supplied",
) -> CostModel:
    """Return a new ``CostModel`` with operator-supplied Kimi per-token rates.

    The function never reaches the network; the operator is responsible for
    sourcing the rates from Moonshot's pricing page (cited above).
    """
    base = base or DEFAULT_COST_MODEL
    return CostModel(
        name=name,
        t1_per_inference_usd=base.t1_per_inference_usd,
        t2_per_inference_usd=base.t2_per_inference_usd,
        t3_per_inference_usd=base.t3_per_inference_usd,
        t4_input_usd_per_1k_tokens=float(input_usd_per_1k_tokens),
        t4_output_usd_per_1k_tokens=float(output_usd_per_1k_tokens),
        moonshot_pricing_url=base.moonshot_pricing_url,
        moonshot_pricing_retrieved=base.moonshot_pricing_retrieved,
        kimi_rates_supplied=True,
        notes=base.notes + (f"kimi rates supplied via with_kimi_rates({name})",),
    )


def with_overrides(
    *,
    base: CostModel | None = None,
    t1_per_inference_usd: float | None = None,
    t2_per_inference_usd: float | None = None,
    t3_per_inference_usd: float | None = None,
    name: str | None = None,
) -> CostModel:
    """Return a ``CostModel`` with electricity-proxy overrides for T1/T2/T3."""
    base = base or DEFAULT_COST_MODEL
    return CostModel(
        name=name or f"{base.name}-overrides",
        t1_per_inference_usd=(
            float(t1_per_inference_usd)
            if t1_per_inference_usd is not None
            else base.t1_per_inference_usd
        ),
        t2_per_inference_usd=(
            float(t2_per_inference_usd)
            if t2_per_inference_usd is not None
            else base.t2_per_inference_usd
        ),
        t3_per_inference_usd=(
            float(t3_per_inference_usd)
            if t3_per_inference_usd is not None
            else base.t3_per_inference_usd
        ),
        t4_input_usd_per_1k_tokens=base.t4_input_usd_per_1k_tokens,
        t4_output_usd_per_1k_tokens=base.t4_output_usd_per_1k_tokens,
        moonshot_pricing_url=base.moonshot_pricing_url,
        moonshot_pricing_retrieved=base.moonshot_pricing_retrieved,
        kimi_rates_supplied=base.kimi_rates_supplied,
        notes=base.notes + ("electricity-proxy overrides applied",),
    )


def estimate_cost_record(record: CallRecord, model: CostModel | None = None) -> float:
    """Estimate USD cost for a single ``CallRecord`` under ``model``.

    Failed (non-ok) calls are still counted as cost-bearing for T1/T2/T3 because
    the GPU/CPU still spent cycles. T4 only charges on success — Moonshot
    typically does not bill failed completions, but this is conservative: when
    operators care, they can override via ``with_kimi_rates(name=...)`` and a
    custom recorder.
    """
    model = model or DEFAULT_COST_MODEL
    tier = record.tier
    if tier == TIER_T1_GPU:
        return float(model.t1_per_inference_usd)
    if tier in (TIER_T2_PI_1, TIER_T2_PI_2):
        return float(model.t2_per_inference_usd)
    if tier == TIER_T3_MAC:
        return float(model.t3_per_inference_usd)
    if tier == TIER_T4_KIMI:
        if not record.ok:
            return 0.0
        tokens_in_k = float(record.tokens_in or 0) / 1000.0
        tokens_out_k = float(record.tokens_out or 0) / 1000.0
        return tokens_in_k * float(model.t4_input_usd_per_1k_tokens) + tokens_out_k * float(
            model.t4_output_usd_per_1k_tokens
        )
    # Unknown tier: treat as zero so we never silently invent cost.
    return 0.0


def estimate_tier_unit_cost(tier: str, model: CostModel | None = None) -> float | None:
    """Per-call cost estimate by tier (no token shape)."""
    model = model or DEFAULT_COST_MODEL
    if tier == TIER_T1_GPU:
        return float(model.t1_per_inference_usd)
    if tier in (TIER_T2_PI_1, TIER_T2_PI_2):
        return float(model.t2_per_inference_usd)
    if tier == TIER_T3_MAC:
        return float(model.t3_per_inference_usd)
    if tier == TIER_T4_KIMI:
        if not model.kimi_rates_supplied:
            return None
        # Approximate: assume 500 in / 250 out tokens average.
        return 0.5 * float(model.t4_input_usd_per_1k_tokens) + 0.25 * float(
            model.t4_output_usd_per_1k_tokens
        )
    return None


__all__ = [
    "MOONSHOT_PRICING_URL",
    "MOONSHOT_PRICING_RETRIEVED",
    "CostModel",
    "DEFAULT_COST_MODEL",
    "with_kimi_rates",
    "with_overrides",
    "estimate_cost_record",
    "estimate_tier_unit_cost",
]
