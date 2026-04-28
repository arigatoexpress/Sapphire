# Gemini OODA Synthesizer Runbook

The Gemini OODA synthesizer is a Sapphire plugin tool that turns a paste-safe
topic + optional context into a structured OODA packet (Observe / Orient /
Decide / Act). It is the bounded entry point for using the Google AI / Vertex
subscription as a *complement* to the local 4-tier inference mesh, not a
replacement.

## Default posture: dry-run

The tool ships in dry-run mode. It returns a deterministic mock OODA packet
that names the operator's next safe steps and never contacts Google. Anything
called the tool from a CI run, a scheduled task, or `claude.ai/code` will
produce useful output without spending a single token.

```bash
echo '{"action":"synthesize","topic":"BTC regime shift","context":"OI up 3%"}' \
  | python3 plugins/claw-sapphire/tools/gemini_ooda.py
```

## Live mode (manual gate)

Live calls only happen when **all** of the following are true:

1. `SAPPHIRE_GEMINI_LIVE=1` is set in the calling environment.
2. The input passes Sapphire's sensitivity classifier (no API keys, customer
   PINs, internal mesh IPs, position sizes, etc.).
3. A `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is present in
   `~/.sapphire/secrets.env` or the environment.
4. The hourly call cap (`MAX_CALLS_PER_HOUR = 8`) has not been hit.
5. The monthly token cap (`MAX_TOKENS_PER_MONTH = 500_000`) would not be
   exceeded by the projected call.

If any of these fails, the tool falls back to the dry-run mock with
`mode_actual` set to one of:

| `mode_actual`               | Meaning                                            |
|-----------------------------|----------------------------------------------------|
| `dry-run`                   | Default no-spend output.                           |
| `dry-run-blocked-by-env`    | Caller asked for live but `SAPPHIRE_GEMINI_LIVE` ≠ `1`. |
| `dry-run-safety`            | Sensitivity classifier flagged the input.          |
| `dry-run-no-key`            | No `GEMINI_API_KEY` available.                     |
| `dry-run-rate-limited`      | Hourly or monthly cap hit.                         |
| `dry-run-live-error`        | SDK raised an exception; fallback mock returned.   |
| `live`                      | Real Gemini call; payload was returned.            |

### Run a live synthesis

```bash
SAPPHIRE_GEMINI_LIVE=1 echo '{
  "action": "synthesize",
  "topic": "Crypto regime shift",
  "context": "BTC price up 4% over 24h, OI rising, funding flat",
  "mode": "live",
  "model": "gemini-2.5-flash",
  "max_output_tokens": 512,
  "ttl_seconds": 86400
}' | python3 plugins/claw-sapphire/tools/gemini_ooda.py
```

The tool will:

- Route the request through the sensitivity classifier.
- Check the cache at `~/.cache/sapphire/gemini_ooda/<hash>.json`.
- Enforce per-hour and per-month caps via
  `~/.cache/sapphire/gemini_ooda/counters.json`.
- Call Gemini with a strict OODA-only prompt (`temperature=0.2`).
- Cache the parsed JSON result for the requested TTL (default 24 hours).

## Operator commands

```bash
# Show counters, cache size, env state without contacting Google.
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/gemini_ooda.py

# Show the model registry the tool understands.
echo '{"action":"models"}' | python3 plugins/claw-sapphire/tools/gemini_ooda.py
```

## Caps and where they live

| Cap                        | Default     | Where to change                             |
|----------------------------|-------------|---------------------------------------------|
| Per-call output tokens     | 4096 hard   | `MAX_OUTPUT_TOKENS_HARD` (constant)         |
| Per-call input chars       | 12_000 hard | `MAX_INPUT_CHARS_HARD` (constant)           |
| Calls per hour             | 8           | `MAX_CALLS_PER_HOUR` (constant)             |
| Tokens per month           | 500_000     | `MAX_TOKENS_PER_MONTH` (constant)           |
| Cache TTL                  | 86_400 s    | `ttl_seconds` field in the request payload  |

The constants live in
`plugins/claw-sapphire/tools/internal/gemini_ooda.py`. Bumping them in source
keeps the cap enforceable at module import; runtime overrides are intentionally
not supported.

## Where the data lives

- Cache files: `~/.cache/sapphire/gemini_ooda/<32-char hash>.json`
- Counters:   `~/.cache/sapphire/gemini_ooda/counters.json`
- Secrets:    read from `~/.sapphire/secrets.env` (mode 0600), never echoed back

Operators can wipe state safely with:

```bash
rm -rf ~/.cache/sapphire/gemini_ooda/
```

## Acceptance tests

```bash
uv run --python 3.11 --no-project --with-requirements requirements-test.txt \
  pytest plugins/claw-sapphire/tests/test_gemini_ooda.py -q
```

13 tests cover dry-run output, the env gate, the safety gate, the live SDK
seam + cache, the rate cap, the cost cap, model validation, status, models,
the stdin/stdout main entry point, and bad-payload handling.

## Why this exists

Sapphire's local mesh (Nemotron / Kimi / Hermes / Pi cluster) handles the
overwhelming majority of inference. Gemini is reserved for the small set of
prompts where:

- The local mesh produces underwhelming structured output.
- The user explicitly wants an external sanity check.
- A specific Gemini capability (very long context, very fast Flash latency)
  is needed.

This tool is the audited, capped door to that capability — small enough that
the entire spend story fits in a single source file.
