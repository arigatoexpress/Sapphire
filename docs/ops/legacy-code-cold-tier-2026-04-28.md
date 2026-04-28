# Legacy Code Cold-Tier Migration

Date: 2026-04-28

`legacy_code/` was a frozen archive for the old `bot-lighter` service. It was
not part of any active LaunchAgent, service entrypoint, or local CI gate, and it
kept archived service material in the Sapphire git tree after the repository
structure policy moved cold artifacts out of T1.

## Cold Copy Evidence

Command:

```bash
python3 scripts/ops/storage_tier_sync.py --apply --i-mean-it
```

Relevant manifest entry:

| Source | Destination | SHA-256 tree hash |
|---|---|---|
| `/Users/aribs/Code/Sapphire/legacy_code` | `/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/cold-tier/sapphire/legacy_code` | `8fddcbb47ac29218db160fdd6af5f04ed9530d6c00627a67c0fda11f6e4c57db` |

The same apply run also copied `results/` and `data/benchmarks/` to cold-tier
destinations, but this PR removes only `legacy_code/` from git.

## Rollback

Restore from Proton Drive cold tier:

```bash
cp -R "/Users/aribs/Library/CloudStorage/ProtonDrive-aribspector@proton.me-folder/Sapphire-OS/cold-tier/sapphire/legacy_code" ./legacy_code
```

Then run:

```bash
python3 scripts/ops/check_repo_structure.py
python3 scripts/ops/local_ci_verify.py --verbose
```
