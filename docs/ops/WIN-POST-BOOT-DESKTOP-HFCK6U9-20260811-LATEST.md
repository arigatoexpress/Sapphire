# Windows P0 post-boot receipt — DESKTOP-HFCK6U9

Observed: `2026-08-11T14:11:39Z`
Coordinator: Codex thread `019ff0f8-5e15-7480-a90f-3ec61eefc667`
Evaluated source: `78783f9e37373d338bb9f6a8e96ece692d10ef2c`
Runtime checkout: `E:\Sapphire\Code\Sapphire` at `86848a81eb9a83b3d659ca4a5ef6e2b26ab3493f`

## Outcome

Windows P0 is **not green** and L2 remains disarmed. Four of seven P0 checks
have current evidence; SSH BatchMode, callable inference-proxy aliases, and
Mac↔Windows policy/killswitch parity remain failed. No service, Scheduled Task,
credential, production, messaging, or money-path state was changed during this
audit.

| P0 check | Result | Evidence |
|---|---|---|
| Post-boot recovery | PASS | Current boot began 2026-08-10 15:54 MDT after a planned shutdown; crash history and dump availability are recorded below. |
| Tailscale | PASS | Service running/automatic; backend Running; self online; zero health issues. |
| SSH BatchMode | FAIL | `sshd` and TCP/22 are listening, but the non-interactive self-probe failed public-key authentication. |
| Inference-proxy aliases | FAIL | Ollama inventory is healthy with 29 models and all 8 target tags installed, but no request traversed each running proxy alias. Inventory is not alias-call evidence. |
| No sleep/lock | PASS | Ultimate Performance; AC sleep `0`; AC hibernate `0`; screen saver disabled. |
| Free-reign/dens/killswitch parity | FAIL | Active Windows policy mirrors hash-identical; Mac is online but SSH is unreachable, so exact commander parity is unproven. Public execution is gated and the ledger is unknown. |
| Scheduled Tasks inventoried | PASS | Inventory captured read-only; `rh-executor` absent and `sapphire-auto-arm-when-ready` disabled. |

## Boot and crash hypothesis

- Uptime at observation was about 16.2 hours. The current boot followed a
  planned shutdown and has no newer Kernel-Power 41 event.
- 2026-08-08 recorded Kernel-Power 41 with bugcheck code `0`, no sleep in
  progress, and no matching minidump. This supports an abrupt power-loss/reset
  hypothesis; the physical or software trigger is unproven.
- 2026-08-05 recorded Kernel-Power 41 with bugcheck code `307` (`0x133`) and no
  contemporaneous minidump. A watchdog-class failure is plausible, but no
  driver or component can be attributed from the available evidence.
- The only enumerated minidump is dated 2026-05-05. It was not opened or copied.

## GPU and inference

- NVIDIA GeForce RTX 5070 Ti, driver `610.88`, 16,303 MiB total VRAM.
- At observation: 1,420 MiB VRAM used, 0% GPU utilization, 25°C.
- Ollama `/api/tags`: HTTP 200, 29 models, current target-model inventory 8/8.
- The Mac inference-proxy health surface on port 11435 was unreachable from
  Windows during the authorized read-only re-probe. No alias call was attempted,
  so `ollama_aliases` remains false.
- The runbook model table was stale and is corrected in this lane to match the
  tested `WINDOWS_REQUIRED_MODELS` contract.

## P1 signals observed but not promoted

- Research-worker endpoint is safe but stale; latest manifest is from
  2026-05-14.
- The read-only TV agent responds, but TradingView CDP is unreachable and no
  tabs are visible.
- Genome seed data contains two lessons. This does not override failed P0.

## Exact remaining gate

To make P0 green, an existing attended access path must permit a successful
non-interactive SSH probe, exact hash readback of the Mac commander
policy/killswitch state, and read-only calls through every required running
inference-proxy alias. Every individual P0 observation must also be fresh, carry
the current Windows boot identity, and postdate that boot. Updating or enabling
services/tasks, copying keys, or arming execution is outside this receipt's
authority.
