# Workflow Runner Guard Check - 2026-04-28

Scope: Agent B overnight no-spend CI guard check for Sapphire workflows.

## Command

```bash
rg -n "ubuntu-latest|runs-on" .github/workflows
```

## Result

No unguarded `ubuntu-latest` runners were found in `.github/workflows`.

Observed `runs-on` values:

| Workflow | Runner expression |
|---|---|
| `.github/workflows/content-engine.yml` | `${{ fromJSON(vars.SAPPHIRE_RUNNER) }}` |
| `.github/workflows/weekly-backtest.yml` | `${{ fromJSON(vars.SAPPHIRE_RUNNER) }}` |
| `.github/workflows/ci.yml` | `${{ fromJSON(vars.SAPPHIRE_RUNNER) }}` |
| `.github/workflows/security.yml` | `${{ fromJSON(vars.SAPPHIRE_RUNNER) }}` |
| `.github/workflows/threat-refresh.yml` | `${{ fromJSON(vars.SAPPHIRE_RUNNER) }}` |

## Follow-Up

No workflow edit was needed in this lane.
