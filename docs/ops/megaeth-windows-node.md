# MegaETH Windows Node — Operator Runbook

Stand up MegaETH self-hosted verification on the Windows PC (Tailnet `100.x.x.z`) and wire it into Sapphire so the Mac dashboard can hit a private endpoint over Tailscale.

> **TL;DR — node software readiness (2026-04-30).** MegaETH does **not** publish open-source replica or full-node client software. RPC nodes (replica + full) are operated only by the MegaETH team and managed providers (Alchemy, QuickNode, Tatum). The single piece of self-hostable, official software is the [`stateless-validator`](https://github.com/megaeth-labs/stateless-validator) — a Rust client that re-executes every block against a SALT witness fetched from the public RPC. That is what this runbook stands up. **You are not running an RPC node; you are running an independent verifier of the public RPC.** A "self-hosted RPC" still means proxying `https://mainnet.megaeth.com/rpc` from the Windows box.

This runbook is **documentation only**. Do not run install commands from here without operator review.

Sources used (all retrieved 2026-04-30):

- MegaETH Architecture — <https://docs.megaeth.com/architecture>
- Stateless Validation guide — <https://docs.megaeth.com/node/stateless-validation>
- `mega_getBlockWitness` — <https://docs.megaeth.com/node/witness>
- Connect to MegaETH (chain params) — <https://docs.megaeth.com/user/connect>
- `megaeth-labs/stateless-validator` README — <https://github.com/megaeth-labs/stateless-validator>
- `megaeth-labs` org listing — <https://github.com/megaeth-labs>

---

## 1. Node software inventory (`github.com/megaeth-labs`)

Surveyed via `gh repo list megaeth-labs --limit 50` on 2026-04-30. The org has 31 public repos. The candidates relevant to "running a node" are:

| Repo | Purpose | Lang | License | Last commit | README | Runs as a node? |
|---|---|---|---|---|---|---|
| [`stateless-validator`](https://github.com/megaeth-labs/stateless-validator) | Independently re-executes blocks against SALT witnesses fetched from a MegaETH RPC. Workspace = 4 crates + 2 binaries. | Rust (nightly-2026-02-03, edition 2024, MSRV 1.95) | MIT OR Apache-2.0 | 2026-04-29 (v2.0.10) | Detailed quickstart, env-var table, includes mainnet `genesis.json` under `test_data/mainnet/` | **YES — this is the only self-hostable client.** Consumes the public RPC; emits validation reports. |
| [`mega-evm`](https://github.com/megaeth-labs/mega-evm) | The MegaETH EVM (revm fork) + system contracts + `mega-evme` CLI for replay. | Rust | MIT OR Apache-2.0 | 2026-04-28 | Build instructions, `cargo install mega-evme` | No. Library + replay CLI; consumed by stateless-validator. |
| [`salt`](https://github.com/megaeth-labs/salt) | Small Authentication Large Trie — KV store backing the witness format. | Rust | Apache-2.0 | 2026-04-24 | Library docs | No. Library only. |
| [`stateless-validator`'s `debug-trace-server`](https://github.com/megaeth-labs/stateless-validator/tree/main/bin/debug-trace-server) | Companion binary that exposes `debug_traceBlockByNumber`, `debug_traceTransaction` etc. by re-executing on top of stateless-validator's witness fetcher. | Rust | MIT OR Apache-2.0 | 2026-04-29 | Same repo README | Optional — useful if Sapphire ever needs trace methods locally. |
| [`reth`](https://github.com/megaeth-labs/reth) | Fork of paradigmxyz/reth. **Last commit 2026-04-23, no MegaETH-specific runnable binary, no node-launch instructions in README.** | Rust | Apache-2.0 | 2026-04-23 | Upstream Reth README only | **No.** Not a runnable MegaETH node. |
| [`telescope`](https://github.com/megaeth-labs/telescope) | Empty description, 4 stars, internal tooling — not a node. | Rust | none | 2026-04-23 | Sparse | No. |
| [`evmone-compiler`](https://github.com/megaeth-labs/evmone-compiler) | EVM AOT compiler. | C++ | Apache-2.0 | 2026-04-23 | Build doc | No. Library. |
| [`documentation`](https://github.com/megaeth-labs/documentation) | The docs.megaeth.com source. The only `node/` content is `stateless-validation.md` and `witness.md` — there is **no `replica-node.md` or `full-node.md`**. | Markdown | none | 2026-04-29 | n/a | No. |

**Honest assessment.** The MegaETH architecture page describes "replica nodes" and "full nodes" as roles inside the network, but the only client software the team has open-sourced and documented is the **stateless validator**. Nothing in `megaeth-labs` ships a runnable replica or full node binary today. Every blog/doc reference to "running a node" on docs.megaeth.com points back at stateless-validator. So:

- **What you can run today**: stateless-validator (mainnet block-by-block independent re-execution).
- **What you cannot run today**: a self-hosted RPC server that serves `eth_*` from local state. There is no open-source replica/full-node client to do that.
- **What this means for the runbook**: section 5 ("Sapphire integration") proxies the public RPC instead of pointing at a local one. The integrity guarantee comes from the validator confirming each block matches; the data path is still the public endpoint.

---

## 2. Windows-native vs WSL2 vs dual-boot

CI on `stateless-validator` runs only on `ubuntu-24.04` (`.github/workflows/build-and-test.yml` and `release.yaml`). No Windows runner. No prebuilt release binaries (the v2.0.10 release has no asset attachments — source-only distribution per the README). The Rust toolchain is pinned to `nightly-2026-02-03` with `miri` and `rust-src` components.

A Windows-native build is *technically* possible (the deps are mostly alloy + revm, both portable), but Untested by upstream and you'd be the canary. This is not where Ari should be spending operator time.

**Decision: WSL2 + Ubuntu 24.04** is the recommended path:

- Matches upstream CI exactly → highest probability of a clean `cargo build --release`.
- Linux-native filesystem (ext4 inside the WSL VHDX) avoids NTFS perf cliffs for redb databases.
- Tailscale runs on the Windows host already; WSL2 mirrored networking exposes the validator's metrics port over the Windows tailnet IP without extra plumbing.
- NSSM can supervise a WSL command line so reboots restart the validator.
- Reversible — uninstall WSL2 deletes the VHDX and that's it.

**Mirrored networking** (Win11 23H2+) is required so the validator's metrics endpoint binds on the Windows tailnet adapter cleanly. Without mirrored networking, WSL2 uses NAT and you'd need `netsh interface portproxy` rules — workable but fragile.

> **VPN warning.** Ari hit ProtonVPN tunnel collapse on `rari2` that broke internet when the tunnel died. **Do not run any VPN client on this Windows box** while the node is up — Tailscale is the only tunnel that should be active. If a VPN ever gets installed here, set "kill on tunnel down" off, or stop the validator first.

---

## 3. Install + run steps

### 3.1 Pre-flight on Windows host

| Check | Command (PowerShell as Admin) | Expected |
|---|---|---|
| Win11 build | `winver` | 22H2 or later (23H2+ for mirrored networking) |
| Tailscale up | `tailscale status` | Includes `100.x.x.z` |
| Tailnet IP | `tailscale ip -4` | `100.x.x.z` (substitute below as `<TAILNET_IP>`) |
| E: free space | `Get-PSDrive E` | ≥ 200 GB free (chain data + witness cache) |
| Existing services | `Get-ScheduledTask \| ? TaskName -like 'Sapphire*'` | OllamaServe, SapphireWebhook, SapphireDashboard — leave alone |

### 3.2 Install WSL2 + Ubuntu 24.04

PowerShell as Admin:

```powershell
# Enable WSL2 + virtual machine platform (reboot required if first time)
wsl --install --no-distribution
# Fetch latest kernel
wsl --update
# Install Ubuntu 24.04 LTS
wsl --install -d Ubuntu-24.04
# Set version 2 explicitly (default since Win11, but cheap to re-assert)
wsl --set-default-version 2
```

Reboot. On first launch of Ubuntu, set username `sapphire` (no password reuse from Mac keychain — generate fresh).

Enable mirrored networking — create `C:\Users\<user>\.wslconfig`:

```ini
[wsl2]
networkingMode=mirrored
firewall=true
dnsTunneling=true
autoProxy=true

[experimental]
hostAddressLoopback=true
```

`wsl --shutdown` to apply.

### 3.3 Install Rust + build stateless-validator

Inside the Ubuntu shell:

```bash
# Standard Rust install — pinned toolchain auto-downloads on first build
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"

# Build deps (clang for some alloy crates, pkg-config + libssl-dev for reqwest-rustls handles cert bundle, but keep the openssl headers around for safety)
sudo apt-get update
sudo apt-get install -y build-essential clang pkg-config libssl-dev git

# Clone + build (release; first build ~15-25 min on a 16-core box)
mkdir -p /mnt/e/megaeth
sudo chown -R "$USER:$USER" /mnt/e/megaeth
cd /mnt/e/megaeth
git clone https://github.com/megaeth-labs/stateless-validator.git
cd stateless-validator
git checkout v2.0.10        # pin a tag rather than tracking main
cargo build --release --bin stateless-validator
ls -lh target/release/stateless-validator
```

Source: <https://docs.megaeth.com/node/stateless-validation> § "Installation"

### 3.4 Bootstrap data directory

```bash
mkdir -p /mnt/e/megaeth/data /mnt/e/megaeth/data/logs
# Genesis ships in the repo
cp test_data/mainnet/genesis.json /mnt/e/megaeth/data/genesis.json

# Fetch a trusted anchor from the public RPC (finalized header)
ANCHOR_HASH=$(curl -sX POST https://mainnet.megaeth.com/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_getHeaderByNumber","params":["finalized"],"id":1}' \
  | jq -r '.result.hash')
echo "Anchor: $ANCHOR_HASH"
```

> **Cross-check the anchor before trusting it.** The validator anchors all subsequent verification on this hash. Pull the same finalized hash from <https://megaeth.blockscout.com> in a browser and confirm they match before passing it to `--start-block`. Source: <https://docs.megaeth.com/node/stateless-validation> § "First run".

### 3.5 First run (foreground, smoke test)

```bash
TAILNET_IP=100.x.x.z   # output of `tailscale ip -4` on Windows host

cd /mnt/e/megaeth/stateless-validator

./target/release/stateless-validator \
  --data-dir /mnt/e/megaeth/data \
  --rpc-endpoint https://mainnet.megaeth.com/rpc \
  --witness-endpoint https://mainnet.megaeth.com/rpc \
  --genesis-file /mnt/e/megaeth/data/genesis.json \
  --start-block "$ANCHOR_HASH" \
  --log.file-directory /mnt/e/megaeth/data/logs \
  --data-max-concurrent-requests 4 \
  --witness-max-concurrent-requests 4 \
  --metrics-enabled true \
  --metrics-port 9090
```

The README explicitly recommends `4/4` concurrency caps "tuned for the public mainnet RPC at `mainnet.megaeth.com/rpc`: unbounded concurrency may trigger HTTP 429 rate-limiting" (<https://docs.megaeth.com/node/stateless-validation> § "First run"). Do not raise these without a managed RPC plan (Alchemy / QuickNode).

Healthy first-run output (per upstream README) shows `Replay block`, `Successfully validated block`, `Chain advanced` lines marching forward in `/mnt/e/megaeth/data/logs/stateless-validator.log`.

`Ctrl-C` once you see five clean `Successfully validated block` lines — that confirms anchor, genesis, witness fetcher, and storage all work.

### 3.6 Bind metrics on the tailnet IP

The validator's Prometheus metrics port should be reachable from the Mac at `100.x.x.w` over the tailnet, **not** from the public internet. With WSL mirrored networking, binding `9090` inside WSL exposes it on every Windows interface; you must restrict at the firewall layer.

PowerShell as Admin on the Windows host:

```powershell
# Allow inbound 9090 ONLY on the Tailscale virtual adapter
New-NetFirewallRule `
  -DisplayName "Sapphire MegaETH Validator metrics (Tailscale)" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 9090 `
  -InterfaceAlias "Tailscale" `
  -Profile Any

# Explicitly block 9090 on Public + Private profiles (defense in depth)
New-NetFirewallRule `
  -DisplayName "Sapphire MegaETH Validator metrics (DENY public/private)" `
  -Direction Inbound `
  -Action Block `
  -Protocol TCP `
  -LocalPort 9090 `
  -Profile Public,Private
```

Sapphire convention: bind on tailnet, not `0.0.0.0`. Validator currently has no `--metrics-bind-addr` flag (see "Open questions"); the firewall rule is the enforcement.

### 3.7 Disk + bandwidth assumptions

| Resource | Estimate (validator only, no full state) | Source |
|---|---|---|
| `--data-dir` (redb canonical chain + contract cache) | 5-20 GB / month at `--canonical-chain-max-length 1000` | upstream default `1000` retained rows; bounded `ContractCache` |
| Witness fetch bandwidth | 1-3 Mbps sustained per `--witness-max-concurrent-requests 4` | rough order; verify against actual `eth_blockNumber` cadence — block budget at 100k TPS target × small per-block witness |
| Logs (`stateless-validator.log`, daily-rotated, 200 MB max) | ~1-2 GB / month after rotation | `--log.file-max-size 200` default, `tracing-appender` daily rotation |

A *full* node (re-execute from genesis with full state) is what `megaeth-labs` has not shipped. Don't size for it.

---

## 4. Process supervision

### 4.1 Wrapper script

`E:\megaeth\run-validator.cmd`:

```cmd
@echo off
REM Sapphire MegaETH Stateless Validator launcher
REM Resumes from last validated block; subsequent runs omit --start-block + --genesis-file
wsl -d Ubuntu-24.04 -u sapphire -- /mnt/e/megaeth/stateless-validator/target/release/stateless-validator ^
  --data-dir /mnt/e/megaeth/data ^
  --rpc-endpoint https://mainnet.megaeth.com/rpc ^
  --witness-endpoint https://mainnet.megaeth.com/rpc ^
  --log.file-directory /mnt/e/megaeth/data/logs ^
  --data-max-concurrent-requests 4 ^
  --witness-max-concurrent-requests 4 ^
  --metrics-enabled true ^
  --metrics-port 9090
```

### 4.2 NSSM service install

[NSSM](https://nssm.cc/) (Non-Sucking Service Manager) wraps an arbitrary command into a Windows service with restart policy + log rotation. Download v2.24+ from nssm.cc, extract to `C:\Tools\nssm\`, then PowerShell as Admin:

```powershell
$NSSM = "C:\Tools\nssm\win64\nssm.exe"

& $NSSM install SapphireMegaETHValidator "E:\megaeth\run-validator.cmd"
& $NSSM set    SapphireMegaETHValidator AppDirectory "E:\megaeth"
& $NSSM set    SapphireMegaETHValidator DisplayName "Sapphire MegaETH Stateless Validator"
& $NSSM set    SapphireMegaETHValidator Description "Independently re-executes MegaETH mainnet blocks via stateless-validator v2.0.10"
& $NSSM set    SapphireMegaETHValidator Start SERVICE_AUTO_START
& $NSSM set    SapphireMegaETHValidator AppStdout "E:\megaeth\data\logs\nssm-stdout.log"
& $NSSM set    SapphireMegaETHValidator AppStderr "E:\megaeth\data\logs\nssm-stderr.log"
& $NSSM set    SapphireMegaETHValidator AppRotateFiles 1
& $NSSM set    SapphireMegaETHValidator AppRotateBytes 200000000   # 200 MB
& $NSSM set    SapphireMegaETHValidator AppExit Default Restart
& $NSSM set    SapphireMegaETHValidator AppRestartDelay 5000        # 5 s
& $NSSM start  SapphireMegaETHValidator

# Verify
Get-Service SapphireMegaETHValidator
```

Survives reboots. Survives WSL crash (NSSM relaunches the wrapper, which re-`wsl -d`s).

### 4.3 Healthcheck

From the Windows host (or the Mac via tailnet):

```bash
# Liveness — Prometheus metrics endpoint
curl -s --max-time 2 http://100.x.x.z:9090/metrics | head -20

# Block-tip lag — fetch latest from public RPC, compare against validator's own report
LATEST=$(curl -sX POST https://mainnet.megaeth.com/rpc \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  | jq -r '.result' | python3 -c 'import sys; print(int(sys.stdin.read().strip(), 16))')
VALIDATED=$(curl -s http://100.x.x.z:9090/metrics \
  | awk '/^stateless_validator_chain_tip_block_number/{print $2}')
echo "public_tip=$LATEST validator_tip=$VALIDATED lag=$((LATEST - ${VALIDATED%.*}))"
```

(Exact metric name to be confirmed against `stateless_core::pipeline` source on first run — open question for Ari at the bottom.)

---

## 5. Sapphire integration

### 5.1 Env var override (Lane 1 contract)

The Sapphire RPC client in `plugins/claw-sapphire/tools/internal/megaeth.py` (Lane 1, branch `feat/megaeth-rpc-tool` / PR #529) reads `SAPPHIRE_MEGAETH_RPC` from env. To route through the Windows host *as a verification co-signer*, the plugin tool itself does **not** change — it still hits `mainnet.megaeth.com/rpc` unless `SAPPHIRE_MEGAETH_RPC` is set, and in our case the validator does not serve eth_* methods (see § 1).

What actually changes:

| Env var | Old | New | Why |
|---|---|---|---|
| `SAPPHIRE_MEGAETH_RPC` | `https://mainnet.megaeth.com/rpc` | (same — validator is not an RPC server) | No change. Public RPC is still the only `eth_*` source. |
| `SAPPHIRE_MEGAETH_VALIDATOR_METRICS` | unset | `http://100.x.x.z:9090/metrics` | New — surfaces validator health into the Mac dashboard. Add to `.envrc` or LaunchAgent EnvironmentVariables. |
| `SAPPHIRE_MEGAETH_VALIDATOR_TIP_FRESHNESS_SECS` | unset | `30` | Max acceptable lag (validator tip behind public tip) in seconds before health degrades. |

If a future MegaETH release ships a self-hostable RPC, swap `SAPPHIRE_MEGAETH_RPC` to `http://100.x.x.z:8545/rpc` at that point — the env-var seam is already there.

### 5.2 Mac-side healthcheck

```bash
# Public-RPC reachability check (existing, unchanged)
curl -s --max-time 2 https://mainnet.megaeth.com/rpc \
  -X POST -H 'Content-Type: application/json' \
  --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' | jq
# → {"jsonrpc":"2.0","id":1,"result":"0x10e6"}    # 4326 = MegaETH mainnet

# Validator co-signer reachability over Tailscale
curl -s --max-time 2 http://100.x.x.z:9090/metrics \
  | grep -E '^stateless_validator_(chain_tip|advanced_blocks|errors)' | head -5
```

If both pass, Sapphire trusts the public RPC; if the validator metrics call fails or shows a tip lag > `SAPPHIRE_MEGAETH_VALIDATOR_TIP_FRESHNESS_SECS`, the dashboard surfaces a "validator stale" warning — but trading is **not** blocked, because mainnet trading is still gated by the five-step activation in `docs/integrations/megaeth.md`.

### 5.3 docs/integrations/megaeth.md update

PR #528 (`feat/megaeth-docs`, currently open) is the place to add a "self-hosted validator co-signer" subsection pointing back here. Since #528 is not yet merged, I'm leaving a TODO marker in *this* runbook and not editing #528's worktree from here. When #528 merges, follow up with a small docs PR appending:

```markdown
## Self-hosted validator co-signer (Windows PC)

Sapphire optionally runs the official MegaETH `stateless-validator` on the Windows PC (`100.x.x.z`) as an independent verifier of the public RPC. Setup, supervision, and decommission are documented in [docs/ops/megaeth-windows-node.md](../ops/megaeth-windows-node.md). It does **not** replace `SAPPHIRE_MEGAETH_RPC`; it sits alongside it as a verifier and feeds health into the dashboard.
```

---

## 6. Monitoring

`services/heartbeat/heartbeat.py` already monitors named services via the `KeepAlive` pattern. Two integration options, lowest-touch first:

### 6.1 Heartbeat probe (smallest change, recommended first)

Add the validator metrics URL to the heartbeat watch list as a generic HTTP probe. No code change required if the heartbeat service already supports URL probes; otherwise this is a ~10-line addition that GETs the metrics endpoint and asserts 200.

Health emitted to the existing Mac dashboard alongside other services. **Ship this first.**

### 6.2 Dashboard panel (follow-up PR)

`services/analytics_dashboard/app.py` is Flask. Add a `/megaeth-validator` route that scrapes `${SAPPHIRE_MEGAETH_VALIDATOR_METRICS}`, parses the four useful metrics — chain tip, advanced blocks, error counter, witness fetch latency — and renders alongside the other dashboard panels. Strictly read-only; no Sapphire→validator writes.

Both deferred to a separate PR. This runbook leaves a TODO at `services/heartbeat/heartbeat.py` if the operator wants to land 6.1 in the same week.

---

## 7. Risk + reversibility

### 7.1 Decommission (full)

```powershell
# Stop and remove the service
& "C:\Tools\nssm\win64\nssm.exe" stop SapphireMegaETHValidator
& "C:\Tools\nssm\win64\nssm.exe" remove SapphireMegaETHValidator confirm

# Remove firewall rules
Remove-NetFirewallRule -DisplayName "Sapphire MegaETH Validator metrics (Tailscale)"
Remove-NetFirewallRule -DisplayName "Sapphire MegaETH Validator metrics (DENY public/private)"

# Wipe data (irreversible)
Remove-Item -Recurse -Force E:\megaeth

# Optional — uninstall WSL distro
wsl --unregister Ubuntu-24.04
```

WSL itself can stay — it's used for nothing else right now, but is otherwise harmless to leave installed.

### 7.2 Recover from corrupted `--data-dir`

The validator anchor is the only piece of trust. If `redb` shows checksum errors or the pipeline halts repeatedly:

```bash
# Inside WSL
wsl -d Ubuntu-24.04 -u sapphire
cd /mnt/e/megaeth
mv data data.broken-$(date +%Y%m%d-%H%M)
mkdir -p data/logs
cp stateless-validator/test_data/mainnet/genesis.json data/genesis.json
# Re-fetch a fresh anchor (see § 3.4) and re-run § 3.5 with --start-block + --genesis-file
```

Witness data is re-fetchable from the public RPC; nothing in `--data-dir` is irreplaceable.

### 7.3 Keystore / signing

**There is no keystore.** stateless-validator never signs transactions; it has no private keys. This is one of the reasons it is safe to run on the same box as the Sapphire webhook — the blast radius if Windows is compromised does not include any MegaETH funds. (Sapphire's separate `feat/megaeth-executor-scaffold` PR #527 *does* introduce keys; that is **not** what this box runs.)

### 7.4 Bandwidth + ISP cost

The "200 Mbps full node" number from the task brief assumed running an RPC node, which we are **not**. Stateless-validator pulls one block worth of data + one witness per block; estimate 1-3 Mbps sustained at the current public-RPC concurrency cap of 4. Worst case at 100k TPS sequencer throughput on a saturated witness pipe is ~10-20 Mbps — still nothing for a residential gigabit connection.

Estimated monthly egress: ~5-15 GB inbound, negligible outbound. **Verify Ari's ISP has no monthly cap below 1 TB.** If yes, this is invisible.

---

## 8. Open questions for Ari

These are the must-answers before scheduling install:

1. **RAM on the Windows box**: ≥ 32 GB confirmed? (Validator needs ~4-8 GB resident; rest is for existing Sapphire/Ollama load. Full node is moot — no software exists.)
2. **E: drive**: ≥ 200 GB free for `E:\megaeth`? (Far less than the "2 TB" originally scoped, because we're running validator-only.)
3. **ISP bandwidth + monthly cap**: gigabit symmetric assumed; cap < 1 TB/mo would be a non-issue but worth confirming.
4. **Tailscale ACL**: lock `100.x.x.z:9090` to Mac (`100.x.x.w`) and any future Sapphire devices only. Do **not** open it tagwide. Default ACL likely already restrictive — needs an explicit check.
5. **WSL mirrored networking**: confirm Win11 build is 23H2 or later. If 22H2, fall back to NAT + `netsh portproxy` and accept the brittleness.
6. **Validator metric names**: `stateless_validator_chain_tip_*` is inferred from the README; the actual Prometheus metric names need a one-time read of `stateless_core::pipeline` source on first deploy. Healthcheck commands above use placeholder names.
7. **Anchor independence source**: Blockscout is used as the cross-check above. If Ari wants a stronger anchor (e.g. cross-check against a second managed RPC like Alchemy), set up that second endpoint at install time — it's a one-line change to step 3.4.
8. **Dashboard panel scope**: ship § 6.1 (heartbeat probe) immediately, or wait for § 6.2 (dedicated panel) and ship them together?

---

## Appendix A — chain parameters (for reference)

From <https://docs.megaeth.com/user/connect> (mainnet tab) and ChainList ID 4326:

| Parameter | Value |
|---|---|
| Network name | MegaETH |
| Chain ID | `4326` (`0x10e6`) |
| Native token | ETH (18 decimals) |
| Public RPC | `https://mainnet.megaeth.com/rpc` |
| Block explorer | `https://megaeth.blockscout.com` |
| Mini-block cadence | ~10 ms |
| EVM block cadence | ~1 s |
| EIP-1559 base-fee adjustment | effectively disabled |
| Settlement | Ethereum L1 via OP Stack + EigenDA + Kailua ZK fault proofs |

## Appendix B — what we are explicitly **not** running

- Not a sequencer (only Lattice runs that — confirmed by docs.megaeth.com/architecture).
- Not an RPC server (no open-source replica/full-node client exists).
- Not a prover (out of scope; specialized hardware + proof submission infra).
- No keystore; no private keys; no signing path.
