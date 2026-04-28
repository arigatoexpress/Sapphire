# Codex Overnight Agent A Report - 2026-04-28

## Summary

Agent A restored pytest collection, removed obsolete skipped legacy tests, triaged the cached failure set, refreshed README test counts, and added coverage for provenance and Gemini OODA cache provenance. All Agent A PRs were merged with `[skip ci]`, local gates, and diffs scoped to the approved paths.

Final canonical state:

- Main SHA: `11105290`
- Open PRs: none
- Active Sapphire worktrees: canonical checkout only
- Final readiness sweep: `37 pass / 9 warn / 0 fail / 2 skip`

## Merged PRs

| PR | Summary | Files touched |
| --- | --- | --- |
| [#360](https://github.com/arigatoexpress/Sapphire/pull/360) | Repaired pytest collection under bare macOS Python by pinning optional test deps and adding a mapped optional-dependency collection guard. | `pyproject.toml`, `tests/conftest.py` |
| [#364](https://github.com/arigatoexpress/Sapphire/pull/364) | Deleted obsolete `tests/legacy/` skipped modules after confirming no imports referenced them. | `tests/legacy/**` |
| [#365](https://github.com/arigatoexpress/Sapphire/pull/365) | Resolved active cached failures by making FastAPI/Flask integration deps explicit skips under bare Python and isolating dashboard `app` imports from inference-proxy path leakage. | `tests/integration/test_dashboard_endpoints.py`, `tests/integration/test_signal_pipeline_e2e.py` |
| [#366](https://github.com/arigatoexpress/Sapphire/pull/366) | Refreshed the README unit-test count after suite restoration. | `README.md` |
| [#367](https://github.com/arigatoexpress/Sapphire/pull/367) | Added provenance CLI coverage for dry-run, apply-gate, verify failure, and apply/verify round trip. | `tests/unit/test_provenance_scripts.py` |
| [#368](https://github.com/arigatoexpress/Sapphire/pull/368) | Added Gemini OODA cache-provenance coverage through the SDK seam with temp cache/secrets and no live model call. | `tests/unit/test_gemini_ooda_cache_provenance.py` |
| [#369](https://github.com/arigatoexpress/Sapphire/pull/369) | Refreshed README again after the new provenance/OODA unit coverage landed. | `README.md` |

## Open PRs

None at handoff.

## Test Counts

| Measurement | Before | After |
| --- | ---: | ---: |
| Bare `pytest --collect-only -q tests/` collection errors | 18 actual collection errors | 0 errors |
| Cached last-failed entries | 207 entries | 0 active failures; cache cleared after verifying remaining entries were stale deleted `tests/legacy/...` IDs |
| Bare `pytest --collect-only -q` total | No reliable count while collection errored | 2581 collected |
| Pinned `/usr/local/bin/python3 -m pytest --collect-only -q` total | 3717 collected | 3529 collected |
| Bare `pytest tests/unit/ --tb=short -q` | Blocked by collection/dependency failures before PR #360 | 2509 passed / 7 skipped / 21 xfailed |
| Pinned `/usr/local/bin/python3 -m pytest tests/unit/ --tb=short -q` | Not re-run at initial SHA during this tranche | 3462 passed / 1 skipped / 21 xfailed |

Notes:

- The pinned collect total dropped mainly because `tests/legacy/` was removed. Later coverage PRs added active tests back on top of that smaller suite.
- Bare Python intentionally skips optional FastAPI/Flask/aiohttp/google/loguru/web3-dependent tests when those deps are absent; the pinned `/usr/local/bin/python3` environment remains the full local test runtime.
- Canonical `.pytest_cache/v/cache/lastfailed` was cleared with `pytest --cache-clear --collect-only -q` after `pytest --last-failed` confirmed the only active entries now skip cleanly.

## Coverage Added

- Provenance verifier/backfill CLI: apply requires `--i-mean-it`, verify returns nonzero for missing sidecars, and a backfill/verify happy path succeeds in a temp directory.
- Gemini OODA cache provenance: live-mode cache writes are provenance-stamped, hash-verified, TTL/model/prompt metadata is present, and a second identical request reads from cache without a second SDK call.
- Integration harness reliability: dashboard endpoint tests no longer import the wrong `app` module when another service path pollutes `sys.path`; signal-pipeline/dashboard integration tests now skip cleanly under bare Python when optional service deps are not installed.

## Discoveries Not Fixed

- `pre-commit run --all-files` is unsafe as a default for this repo today: it autoformatted hundreds of unrelated files and still failed existing repo-wide JSON/private-key/Bandit checks. I preserved that accidental formatter churn as `stash@{Mon Apr 27 22:31:36 2026}` and `/tmp/sapphire-agent-a/precommit-all-files-accidental-20260428.patch`; it was not applied or merged.
- Production readiness still has 9 WARNs at handoff: degraded inference tiers now include `pi-rari1`, `pi-rari2`, and `windows-gpu`; confirmation firewall has 4 expired pending confirmations; routine probes are external-disabled; GCP/Gemini live gates remain manual/offline. All are outside Agent A's test-suite allow-list.
- Hosted GitHub checks were intentionally skipped via `[skip ci]`; every merge used local verification instead.
