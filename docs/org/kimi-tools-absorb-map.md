# Kimi Tools Absorb Map

Verified on 2026-04-26. This is a read-only Wave 3 consolidation map for the
local-only `/Users/aribs/Code/kimi-tools` repo. No files in `kimi-tools` were
changed, no Kimi/Moonshot/OpenRouter request was sent, and no secret values were
read or printed.

## Current Shape

`kimi-tools` is a local git repo with one commit and no remote:

| File | Purpose |
|---|---|
| `kimi_client.py` | OpenAI-compatible Moonshot/OpenRouter chat client with result dataclass and health helper. |
| `models.py` | Moonshot/OpenRouter model catalog and tier aliases. |
| `setup-pi-ollama.sh` | Raspberry Pi Ollama bootstrap script for lightweight local fallback models. |
| `SYSTEM_UPGRADE_PLAN.md` | Historical design plan for the inference proxy and Kimi fallback tier. |

The repo has no `AGENTS.md`, no `CLAUDE.md`, no CI, no tests, and no remote.
`python3 -m py_compile kimi_client.py models.py __init__.py` passes, and
`kimi_client.health()` reports unavailable when no relevant API keys are set.

## Caller Inventory

No live Sapphire code imports `kimi-tools` directly. A targeted scan found no
`from kimi_tools`, `import kimi_tools`, `import kimi_client`, or active
`~/Code/kimi-tools` import paths outside historical docs/metadata.

Current overlap already lives in Sapphire:

| Capability | Sapphire owner |
|---|---|
| Moonshot/OpenRouter OpenAI-compatible fallback | `services/inference-proxy/app.py:_call_kimi_cloud` |
| Kimi tier aliases and routing | `services/inference-proxy/app.py:MODEL_TIERS` |
| Plugin-side Kimi HTTP execution | `plugins/claw-sapphire/lib/router.py:_kimi_http` |
| Telegram relay fallback | `lib/telegram/kimi_relay.py` and Hermes `kimi-relay-writer` hook |
| Kimi operator documentation | `~/.hermes/skills/sapphire/kimi-delegate/SKILL.md` |

The standalone repo is therefore no longer a runtime dependency. It is a small
historical/prototype workbench whose durable pieces should move into Sapphire or
be retired after an explicit soak.

## Recommendation

Use a two-step absorb, then archive:

1. **Absorb docs and model catalog into Sapphire**: Sapphire now has
   `tests/unit/test_kimi_cloud_fallback.py`, covering Kimi aliases, provider
   priority, fail-closed missing provider behavior, health-gated provider
   calls, and dry-run Telegram relay flattening. Move any still-useful catalog
   notes into `services/inference-proxy/` or `docs/org/` if future work needs
   them.
2. **Retire local repo after soak**: once Sapphire tests cover the behavior and
   the inference proxy has passed a health soak, mark `kimi-tools` as
   `candidate_archive` review-only with a rollback note pointing to this map.

Do not delete `/Users/aribs/Code/kimi-tools` in the absorb PR. The reversible
cutover is: keep the repo read-only for 14 days after Sapphire coverage lands,
then quarantine or archive only with a dedicated cleanup PR/report.

## Guardrail Coverage

- `tests/unit/test_kimi_cloud_fallback.py` covers Kimi model alias resolution,
  Moonshot before OpenRouter priority, OpenRouter fallback, missing-provider
  fail-closed behavior, health-gated provider calls, and dry-run Telegram relay
  flattening.
- `tests/unit/test_sensitivity_filter.py` covers the sensitivity gate that
  blocks Kimi Cloud routing before external calls for secret-like or private
  content.
- The remaining archive gate is procedural: do not delete or move
  `/Users/aribs/Code/kimi-tools` until a later cleanup PR/report records a soak
  and rollback path.
