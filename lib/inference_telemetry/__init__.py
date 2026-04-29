"""Inference Mesh Telemetry — per-tier latency, throughput, error, and cost analysis.

Pure-data library that reads append-only call logs (JSONL) from the inference proxy
and the cache directory, then computes per-tier metrics, cost models, and honest
recommendations. Provenance-stamped where it emits artifacts.

Modules:
- ``aggregator``: pure JSONL → ``TelemetryReport``.
- ``cost_model``: per-tier cost model (electricity proxy + Moonshot pricing).
- ``recommender``: surfaces switch-tier recommendations honestly.

Source-of-truth for input shape: the inference proxy writes call records to
``~/.cache/sapphire/inference_proxy/calls.jsonl`` (one JSON object per line):

    {
      "ts": "2026-04-29T12:34:56.789012Z",   # ISO 8601 UTC
      "tier": "T1_windows_gpu",              # T1_windows_gpu / T2_pi_rari1 /
                                              # T2_pi_rari2 / T3_mac_local /
                                              # T4_kimi_cloud
      "model": "hermes3:8b",
      "latency_ms": 412,
      "ok": true,
      "tokens_in": 312,
      "tokens_out": 198,
      "error_class": null                    # populated when ok=false
    }

This format is intentionally a sanitized subset of the inference proxy's
request path: it records tier, model, latency, outcome, token counts, and error
class without storing prompts, completions, API keys, or tenant secrets. Tests
cover both the documented shape and a handful of permissive edge cases (missing
keys, malformed lines).
"""

from __future__ import annotations

VERSION = "0.1.0"
SCHEMA_VERSION = 1

# Canonical tier identifiers used by aggregator + cost_model + recommender.
TIER_T1_GPU = "T1_windows_gpu"
TIER_T2_PI_1 = "T2_pi_rari1"
TIER_T2_PI_2 = "T2_pi_rari2"
TIER_T3_MAC = "T3_mac_local"
TIER_T4_KIMI = "T4_kimi_cloud"

KNOWN_TIERS: tuple[str, ...] = (
    TIER_T1_GPU,
    TIER_T2_PI_1,
    TIER_T2_PI_2,
    TIER_T3_MAC,
    TIER_T4_KIMI,
)

__all__ = [
    "VERSION",
    "SCHEMA_VERSION",
    "TIER_T1_GPU",
    "TIER_T2_PI_1",
    "TIER_T2_PI_2",
    "TIER_T3_MAC",
    "TIER_T4_KIMI",
    "KNOWN_TIERS",
]
