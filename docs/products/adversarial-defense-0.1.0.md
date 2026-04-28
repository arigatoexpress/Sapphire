# Adversarial Defense 0.1.0

## What This Is

Adversarial Defense 0.1.0 is a local, defensive intelligence layer for Sapphire.
It detects hostile or low-integrity inputs before they contaminate analytics,
operator summaries, source-quality scores, or LLM context.

The first release ships five pure detectors:

- `WashTradeDetector`
- `BotPumpedChannelDetector`
- `OracleAnomalyDetector`
- `PromptInjectionDetector`
- `FalseFlagThreatIntelDetector`

It also ships `adversarial.detection` telemetry helpers and a small CLI service
wrapper at `services/adversarial/run.py`.

## Non-Goals

- No live trading.
- No order drafting.
- No Telegram sends.
- No credential reads.
- No upstream signal mutation by default.
- No plugin tool or registry entry in 0.1.0.

## CLI

```bash
python services/adversarial/run.py status
python services/adversarial/run.py scan-file --kind trades --input trades.jsonl
python services/adversarial/run.py scan-file --kind messages --input messages.jsonl
python services/adversarial/run.py scan-file --kind oracle --input oracle.json
python services/adversarial/run.py scan-file --kind prompt --input prompt.json
python services/adversarial/run.py scan-file --kind threat-intel --input reports.json
```

The CLI exits `0` when the scanned file is clean and `2` when findings are
present. By default it only prints JSON.

Optional telemetry:

```bash
python services/adversarial/run.py scan-file --kind prompt --input prompt.json --emit
```

Optional quarantine report copy:

```bash
SAPPHIRE_ADVERSARIAL_QUARANTINE=1 \
  python services/adversarial/run.py scan-file --kind messages --input messages.jsonl
```

Quarantine is not a move/delete operation. It writes a report copy containing
the input path, input SHA-256, detector findings, and `upstream_mutated=false`.

## Detector Contracts

### WashTradeDetector

Input fields are flexible aliases:

- Buyer: `buyer`, `buyer_account`, `buy_account`, `taker`, `taker_account`
- Seller: `seller`, `seller_account`, `sell_account`, `maker`, `maker_account`
- Symbol: `symbol`, `asset`, `market`, `pair`
- Quantity: `quantity`, `qty`, `amount`, `size`, `base_amount`
- Price: `price`, `trade_price`, `fill_price`
- Time: `timestamp`, `ts`, `time`, `created_at`

Rules:

- `self_trade_same_account`
- `reciprocal_round_trip_cluster`

### BotPumpedChannelDetector

Input fields:

- Text: `text`, `message`, `content`, `body`, `summary`
- Channel: `channel_id`, `channel`, `source`, `room`
- Author: `author`, `author_id`, `sender`, `user`
- Time: `timestamp`, `published_at`, `ts`, `time`, `created_at`

Rules:

- `pump_language_with_bot_or_profit_claim`
- `coordinated_pump_burst`

### OracleAnomalyDetector

Input fields:

- Asset: `asset`, `symbol`, `market`, `pair`
- Source: `source`, `venue`, `oracle`, `provider`
- Price: `price`, `oracle_price`, `value`, `mark_price`
- Reference: `reference_price`, `median_price`, `twap_price`, `index_price`
- Time: `timestamp`, `ts`, `time`, `observed_at`

Rules:

- `reference_price_divergence`
- `cross_source_oracle_outlier`

### PromptInjectionDetector

Input fields:

- Text: `text`, `message`, `content`, `body`, `prompt`, `summary`
- ID: `id`, `message_id`, `document_id`, `source_id`

Rules cover instruction override, jailbreak persona, secret exfiltration
requests, tool hijack attempts, hidden HTML instructions, zero-width smuggling,
and encoded instruction blobs.

### FalseFlagThreatIntelDetector

Input fields:

- Text: `title`, `summary`, `body`, `description`, `analysis`, `claim`
- Claimed actor: `claimed_actor`, `public_claim_actor`, `actor_claim`, `claim_actor`
- Assessed actor: `assessed_actor`, `likely_actor`, `ttp_match_actor`, `cluster_actor`
- Confidence: `confidence`, `attribution_confidence`

Rules:

- `claimed_actor_conflicts_with_ttp_assessment`
- `false_flag_or_persona_marker`
- `hard_attribution_on_low_confidence_report`

## Telemetry

Telemetry event type: `adversarial.detection`

The telemetry module emits paste-safe metadata only:

```json
{
  "schema_version": 1,
  "event_type": "adversarial.detection",
  "severity": "high",
  "detector": "oracle_anomaly",
  "rule_id": "cross_source_oracle_outlier",
  "subject": "mngo:oracle_c",
  "confidence": 0.91,
  "score": 0.88,
  "quarantine_eligible": true,
  "tags": ["project:sapphire", "type:security", "service:adversarial-defense"]
}
```

Secret-shaped and token-shaped text is redacted before publishing.

## Validation

Focused tests:

```bash
pytest tests/unit/test_adversarial_detectors.py \
  tests/unit/test_adversarial_telemetry.py \
  tests/unit/test_adversarial_service.py -q
```

Touched-file lint:

```bash
ruff check lib/security/adversarial_detectors.py \
  lib/security/adversarial_telemetry.py \
  services/adversarial/run.py \
  tests/unit/test_adversarial_detectors.py \
  tests/unit/test_adversarial_telemetry.py \
  tests/unit/test_adversarial_service.py
```

## Source-Backed Design Inputs

- Wash trading and artificial volume: SEC 2024-166 and DOJ Gotbit 2025.
- Oracle manipulation: CFTC Mango Markets enforcement action and Cream Finance
  exploit writeups.
- Telegram pumps and bots: CFTC messaging-app advisory and Xu/Livshits Telegram
  pump-and-dump study.
- False-flag threat intel: Mandiant attribution and GRU persona/disruption
  reporting.
- Prompt injection: OWASP LLM01:2025.
