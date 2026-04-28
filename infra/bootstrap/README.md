# Fresh-Mac Bootstrap Examples

These files support `scripts/ops/bootstrap_fresh_mac.sh` and the
`make sapphire-on-fresh-mac` entrypoint. They are intentionally demo-safe:
placeholders are inert, live flags are off, and LaunchAgents are installed with
`RunAtLoad=false` so nothing starts just because the files were copied.

Files:

- `demo-services.env`: non-secret demo flags loaded by local shells or wrappers.
- `demo-launchagents.list`: the LaunchAgent labels copied by the fresh-mac
  bootstrap.

Use `SAPPHIRE_BOOTSTRAP_DRY_RUN=1 make sapphire-on-fresh-mac` first on any new
machine to inspect every command before it writes outside the repo.
