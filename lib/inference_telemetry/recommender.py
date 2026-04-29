"""Cost / latency recommender — surfaces "switch X→Y to save $Z/mo" honestly.

Constraints:
- Pure: no I/O, no clock reads beyond what aggregator already captured.
- Honest: every recommendation lists caveats. The recommender NEVER hides the
  fact that switching tiers changes latency, capability, and reliability. It
  surfaces dollar figures alongside the tradeoff.
- Operator-decided: recommendations are illustrative; the operator owns the
  actual decision.

Recommendation shape:

    {
        "kind": "switch_tier",
        "from_tier": "T4_kimi_cloud",
        "to_tier": "T1_windows_gpu",
        "monthly_savings_usd": 24.18,
        "monthly_volume": 740.0,
        "caveats": [
            "T1 is GPU-bound: latency p99 is 412ms vs T4's 2400ms — likely better",
            "T1 cannot serve sensitive prompts that require T4 routing",
            "Saving estimate assumes constant traffic — observed window is 1.2 hours"
        ],
        "confidence": "low",   # low / medium / high
    }
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from . import (
    KNOWN_TIERS,
    SCHEMA_VERSION,
    TIER_T1_GPU,
    TIER_T2_PI_1,
    TIER_T2_PI_2,
    TIER_T3_MAC,
    TIER_T4_KIMI,
    VERSION,
)
from .aggregator import (
    TelemetryReport,
    TierStats,
    project_monthly_calls,
    project_monthly_cost,
)
from .cost_model import DEFAULT_COST_MODEL, CostModel, estimate_tier_unit_cost

# ── Models ──────────────────────────────────────────────────────────────────


@dataclass
class Recommendation:
    kind: str
    from_tier: str | None = None
    to_tier: str | None = None
    monthly_savings_usd: float = 0.0
    monthly_volume: float = 0.0
    caveats: list[str] = field(default_factory=list)
    confidence: str = "low"
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["monthly_savings_usd"] = round(self.monthly_savings_usd, 4)
        d["monthly_volume"] = round(self.monthly_volume, 3)
        return d


@dataclass
class RecommendationBundle:
    schema_version: int = SCHEMA_VERSION
    version: str = VERSION
    generator: str = "lib.inference_telemetry.recommender"
    has_real_data: bool = False
    cost_model_name: str = "default"
    kimi_rates_supplied: bool = False
    recommendations: list[Recommendation] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "generator": self.generator,
            "has_real_data": self.has_real_data,
            "cost_model_name": self.cost_model_name,
            "kimi_rates_supplied": self.kimi_rates_supplied,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "caveats": list(self.caveats),
        }


# ── Helpers ─────────────────────────────────────────────────────────────────


def _by_tier(report: TelemetryReport) -> dict[str, TierStats]:
    return {ts.tier: ts for ts in report.tiers}


def _confidence(report: TelemetryReport, observed: TierStats, monthly_volume: float) -> str:
    """Heuristic: confidence increases with sample size + window coverage.

    - <50 calls or window <1h → "low"
    - 50–500 calls and window ≥1h → "medium"
    - >500 calls and window ≥6h → "high"
    """
    window_seconds = float(report.window_seconds or 0.0)
    if observed.calls < 50 or window_seconds < 3600:
        return "low"
    if observed.calls > 500 and window_seconds >= 6 * 3600:
        return "high"
    return "medium"


def _shared_caveats(report: TelemetryReport, model: CostModel) -> list[str]:
    caveats: list[str] = []
    if not report.has_real_data:
        caveats.append(
            "no real fixture data — recommendations are illustrative; metrics derive from synthetic or empty input"
        )
    if not model.kimi_rates_supplied:
        caveats.append(
            "Kimi (T4) rates default to 0 — supply real rates from "
            f"{model.moonshot_pricing_url} (retrieved {model.moonshot_pricing_retrieved}) "
            "before trusting any T4 dollar figure"
        )
    if report.window_seconds and report.window_seconds < 3600:
        caveats.append(
            f"observed window is {report.window_seconds / 60:.1f} minutes — "
            "monthly extrapolation assumes traffic is stationary, which is rarely true"
        )
    if report.total_calls < 50:
        caveats.append(
            f"only {report.total_calls} calls in window — sample size below 50 "
            "is too small for reliable percentile / cost recommendations"
        )
    return caveats


# ── Core recommender ────────────────────────────────────────────────────────


def _switch_recommendation(
    report: TelemetryReport,
    by_tier: dict[str, TierStats],
    *,
    from_tier: str,
    to_tier: str,
    cost_model: CostModel,
    extra_caveats: tuple[str, ...] = (),
) -> Recommendation | None:
    if from_tier not in by_tier or by_tier[from_tier].calls == 0:
        return None
    observed = by_tier[from_tier]

    # Compute current cost share attributable to this tier alone.
    if report.window_seconds and report.window_seconds > 0:
        tier_share = observed.cost_usd / max(report.total_cost_usd, 1e-12) if report.total_cost_usd else 0.0
    else:
        tier_share = 0.0
    monthly_total_cost = project_monthly_cost(report)
    monthly_volume_calls = project_monthly_calls(report)
    monthly_from_cost = monthly_total_cost * tier_share if monthly_total_cost else 0.0
    # Volume share: number of calls in this tier projected forward.
    if report.total_calls > 0 and monthly_volume_calls > 0:
        monthly_tier_calls = monthly_volume_calls * (observed.calls / report.total_calls)
    else:
        monthly_tier_calls = 0.0

    to_unit = estimate_tier_unit_cost(to_tier, cost_model)
    if to_unit is None:
        # Cannot estimate destination cost (e.g. unsupplied Kimi rates).
        rec = Recommendation(
            kind="switch_tier",
            from_tier=from_tier,
            to_tier=to_tier,
            monthly_savings_usd=0.0,
            monthly_volume=monthly_tier_calls,
            confidence="low",
            rationale=(
                f"cannot estimate monthly savings: per-call cost for {to_tier} is unsupplied "
                "(supply rates and re-run)"
            ),
        )
        rec.caveats.extend(extra_caveats)
        rec.caveats.append(
            f"destination tier {to_tier} cost is unknown under current CostModel "
            f"'{cost_model.name}' — supply rates explicitly"
        )
        return rec

    monthly_to_cost = monthly_tier_calls * to_unit
    savings = monthly_from_cost - monthly_to_cost

    rec = Recommendation(
        kind="switch_tier",
        from_tier=from_tier,
        to_tier=to_tier,
        monthly_savings_usd=savings,
        monthly_volume=monthly_tier_calls,
        confidence=_confidence(report, observed, monthly_tier_calls),
        rationale=(
            f"observed {observed.calls} calls on {from_tier} (cost-share={tier_share:.3f}); "
            f"projecting {monthly_tier_calls:.0f} calls/mo at unit cost ${to_unit:.6f}"
        ),
    )
    rec.caveats.extend(extra_caveats)
    return rec


def _latency_caveat(observed: TierStats, dest: TierStats | None, dest_label: str) -> str | None:
    """Emit a caveat when destination latency p99 is materially worse."""
    if dest is None or dest.calls == 0:
        return f"destination {dest_label} has no observed calls — latency cost unknown"
    obs_p99 = observed.latency_p99_ms or 0.0
    dest_p99 = dest.latency_p99_ms or 0.0
    if dest_p99 > 0 and obs_p99 > 0 and dest_p99 > obs_p99 * 1.5:
        return (
            f"destination latency p99 ({dest_p99:.0f}ms) is {dest_p99 / obs_p99:.1f}× "
            f"observed p99 ({obs_p99:.0f}ms); switching may regress UX"
        )
    return None


def recommend(
    report: TelemetryReport,
    cost_model: CostModel | None = None,
) -> RecommendationBundle:
    """Surface honest tier-switch recommendations.

    Strategy:
    - For each cloud-using tier (T4 Kimi), suggest moving traffic to T1 Windows
      GPU when the GPU has observed capacity and lower latency. Caveat:
      sensitive prompts cannot be cloud-bound, but the inverse is fine.
    - For T3 Mac local heavy use, suggest moving to T1 (faster, similar cost) —
      but warn if Mac is being used as a fallback (high latency suggests CPU
      inference, which is expected when GPU is unhealthy).
    - For T1 Windows GPU when error_rate is high, suggest *not* switching to
      cloud unless latency is also bad — this is a routing-health note, not a
      cost recommendation.

    All recommendations include caveats. The bundle's top-level ``caveats``
    field carries posture-wide warnings (no real data, missing Kimi rates).
    """
    cost_model = cost_model or DEFAULT_COST_MODEL
    bundle = RecommendationBundle(
        has_real_data=report.has_real_data,
        cost_model_name=cost_model.name,
        kimi_rates_supplied=cost_model.kimi_rates_supplied,
    )
    bundle.caveats.extend(_shared_caveats(report, cost_model))

    by_tier = _by_tier(report)

    # Recommendation 1: T4 → T1 (cost saving, capability gated).
    if TIER_T4_KIMI in by_tier and TIER_T1_GPU in by_tier:
        latency_warn = _latency_caveat(by_tier[TIER_T4_KIMI], by_tier[TIER_T1_GPU], "T1_windows_gpu")
        rec = _switch_recommendation(
            report,
            by_tier,
            from_tier=TIER_T4_KIMI,
            to_tier=TIER_T1_GPU,
            cost_model=cost_model,
            extra_caveats=(
                "T4 is reserved for non-sensitive deep research — T1 cannot serve T4-only "
                "queries that require Kimi-class context windows or sensitivity-blocked routing",
                "switching only applies to T4 calls that do NOT require cloud capability",
            ),
        )
        if rec is not None:
            if latency_warn:
                rec.caveats.append(latency_warn)
            bundle.recommendations.append(rec)

    # Recommendation 2: T3 → T1 (latency + cost, gated on T1 health).
    if TIER_T3_MAC in by_tier and TIER_T1_GPU in by_tier:
        latency_warn = _latency_caveat(by_tier[TIER_T3_MAC], by_tier[TIER_T1_GPU], "T1_windows_gpu")
        rec = _switch_recommendation(
            report,
            by_tier,
            from_tier=TIER_T3_MAC,
            to_tier=TIER_T1_GPU,
            cost_model=cost_model,
            extra_caveats=(
                "T3 Mac local is the always-on fallback when GPU is unhealthy",
                "if T3 calls are happening because T1 was down, switching the routing "
                "without addressing T1 reliability does NOT help",
            ),
        )
        if rec is not None:
            if latency_warn:
                rec.caveats.append(latency_warn)
            bundle.recommendations.append(rec)

    # Recommendation 3: heavy T1 use → consider T2 Pi for lightweight models.
    # Only emit when T1 has very high call count and low avg tokens (suggesting
    # quick classification jobs that fit on a Pi).
    if TIER_T1_GPU in by_tier:
        t1 = by_tier[TIER_T1_GPU]
        avg_tokens = (t1.tokens_in + t1.tokens_out) / max(t1.calls, 1)
        if t1.calls >= 100 and avg_tokens > 0 and avg_tokens < 200:
            for pi_tier in (TIER_T2_PI_1, TIER_T2_PI_2):
                rec = _switch_recommendation(
                    report,
                    by_tier,
                    from_tier=TIER_T1_GPU,
                    to_tier=pi_tier,
                    cost_model=cost_model,
                    extra_caveats=(
                        "T2 Pi can only serve small models (≤4B params: nemotron-mini, gemma2:2b, smollm2)",
                        "if T1 is serving hermes3:8b or larger, the Pi cannot replace it",
                        f"observed avg tokens/call on T1 = {avg_tokens:.0f} — Pi is reasonable below ~200",
                    ),
                )
                if rec is not None:
                    rec.confidence = "low"  # Always low — capability gating is uncertain.
                    bundle.recommendations.append(rec)
                    break  # Only one Pi recommendation per report.

    # Recommendation 4: error rate on a tier above 10% → routing health note,
    # not a cost recommendation.
    for tier_name in KNOWN_TIERS:
        ts = by_tier.get(tier_name)
        if ts is None or ts.calls < 20:
            continue
        if ts.error_rate > 0.10:
            note = Recommendation(
                kind="routing_health_warning",
                from_tier=tier_name,
                to_tier=None,
                monthly_savings_usd=0.0,
                monthly_volume=project_monthly_calls(report)
                * (ts.calls / max(report.total_calls, 1)),
                confidence=_confidence(report, ts, 0.0),
                rationale=(
                    f"observed error rate on {tier_name}: {ts.error_rate:.1%} ({ts.failure}/{ts.calls}); "
                    "investigate before recommending any cost-driven re-routing"
                ),
            )
            note.caveats.append(
                "this is a health warning, not a cost recommendation — fixing the tier may "
                "be cheaper than rerouting"
            )
            top_classes = sorted(ts.error_classes.items(), key=lambda x: -x[1])[:3]
            if top_classes:
                note.caveats.append(
                    "top error classes: "
                    + ", ".join(f"{c}={n}" for c, n in top_classes)
                )
            bundle.recommendations.append(note)

    # Stable ordering for tests + provenance.
    bundle.recommendations.sort(
        key=lambda r: (r.kind, r.from_tier or "", r.to_tier or "")
    )
    return bundle


# ── Convenience helpers ─────────────────────────────────────────────────────


def top_n(bundle: RecommendationBundle, n: int = 3) -> list[Recommendation]:
    """Return the top-N recommendations by absolute savings (with health-warnings last)."""
    cost_recs = [r for r in bundle.recommendations if r.kind == "switch_tier"]
    health_recs = [r for r in bundle.recommendations if r.kind != "switch_tier"]
    cost_recs.sort(key=lambda r: -abs(r.monthly_savings_usd))
    out: list[Recommendation] = list(cost_recs[:n])
    out.extend(health_recs[: max(0, n - len(out))])
    return out


__all__ = [
    "Recommendation",
    "RecommendationBundle",
    "recommend",
    "top_n",
]
