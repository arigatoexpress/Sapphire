"""Source Quality Measurement 0.1.0.

Pure, deterministic measurement of per-source intelligence quality:

- :mod:`snr` — per-source historical signal-to-noise. Match each
  source's directional intent against the eventual outcome (price move,
  realised PnL, regime label, etc.) and return precision / recall / F1.
- :mod:`correlation` — pairwise cross-source correlation. Surfaces
  near-duplicate sources whose timing+direction align ≥ 87 % of the
  time so the operator can downweight one of them.
- :mod:`decay` — rolling-window quality versus historical baseline.
  Detects sources whose F1 has degraded materially over a short window
  (was-good-now-spammy).

Conventions
-----------
- All inputs are dataclasses or plain dicts — no implicit I/O. The
  daemon (:mod:`services.source_quality.run`) is the one place that
  reads from disk.
- All scores live in ``[0.0, 1.0]`` (precision/recall/F1) or have a
  documented sign (correlation in ``[-1.0, +1.0]`` Spearman, decay as a
  signed delta from baseline F1).
- Determinism: same input dict → same output bytes. Sorted JSON keys
  in every emitted artefact; provenance envelope on every report.

This package is read-only with respect to the rest of the repo. It does
NOT modify any correlator, narrative, or feed module.
"""

from lib.source_quality.correlation import (
    NEAR_DUPLICATE_THRESHOLD,
    CorrelationPair,
    CorrelationReport,
    compute_pairwise_correlation,
    flag_near_duplicates,
)
from lib.source_quality.decay import (
    DEFAULT_DECAY_THRESHOLD,
    DecayAlert,
    DecayReport,
    detect_decay,
)
from lib.source_quality.registry import (
    BUILTIN_SOURCES,
    SourceQualityEntry,
    default_registry,
    records_for_sources,
    register_source,
    registered_sources,
    source_signal_to_record,
)
from lib.source_quality.snr import (
    DEFAULT_OUTCOME_WINDOW_HOURS,
    Outcome,
    SignalRecord,
    SourceSNR,
    compute_source_snr,
    score_signal_against_outcome,
)

__all__ = [
    "BUILTIN_SOURCES",
    "CorrelationPair",
    "CorrelationReport",
    "DEFAULT_DECAY_THRESHOLD",
    "DEFAULT_OUTCOME_WINDOW_HOURS",
    "DecayAlert",
    "DecayReport",
    "NEAR_DUPLICATE_THRESHOLD",
    "Outcome",
    "SignalRecord",
    "SourceQualityEntry",
    "SourceSNR",
    "compute_pairwise_correlation",
    "compute_source_snr",
    "default_registry",
    "detect_decay",
    "flag_near_duplicates",
    "records_for_sources",
    "register_source",
    "registered_sources",
    "score_signal_against_outcome",
    "source_signal_to_record",
]
