# Operator decision — free-reign gate scope

**Date:** 2026-08-06  
**From:** Claude plant wire (`43f1cc9`) + Grok monorepo review  
**Status:** **RECOMMENDED DEFAULT = ACCEPT free_reign-only** (change only if Ari disagrees)

## What Claude did

`gate_order` runs in `~/ops-state/telegram-bot/executor.py` only when
`via == "free_reign"` (auto-approvals from free-reign policy).

Human Telegram **Approve** clicks share the same executor / `decisions.jsonl`
queue but are **not** re-gated by monorepo dens/options-first.

## Why free_reign-only is correct

| Lane | Authority | Should monorepo policy re-block? |
|---|---|---|
| Free-reign auto | Agent / sticky mandate | **Yes** — dens, dust, L2 $10, MOSS, options-first |
| Human TG Approve | Ari attended | **No** — human already made the call; OPTIONS_FIRST must not silently veto intentional equity buys |

Universal gate broke 10/46 tests by refusing legitimate human `MSTR:USD`-class approvals — that is a feature, not a bug.

## If Ari wants universal gate later

Second mode: `GATE_ALL_EXECUTOR=1` or policy flag `gate_human_telegram: true` —
**do not flip without explicit operator phrase.** Ship as opt-in only.

## Genome honesty (accept)

`source="auto_estimate"` is correct until broker fill prices are threaded.
Do not relabel as `broker` without real RH/on-chain fill data.

## Still required after accept

1. **Reload rh-executor** so wired `executor.py` is the live process  
   → `docs/handoffs/CLAUDE-EXECUTOR-RELOAD-PROMPT-2026-08-06.md`
2. Win P0 before any L2 ARM  
3. Gemini dashboard deploy  

Money / L2 ARM: still off.
