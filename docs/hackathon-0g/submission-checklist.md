# Hackathon submission checklist

The hackathon requires submission through HackQuest. **I cannot submit on your behalf** — HackQuest auth, X posting, video recording, and any mainnet transaction with your funds all need you. Everything else is built and ready.

## Status as of the last commit on `feat/0g-integration`

| Deliverable | Status | Where it lives |
|---|---|---|
| Engineering — `lib/og/`, plugin tools, deploy script, signal_logger hook | ✅ done | `lib/og/`, `plugins/claw-sapphire/tools/og_*.py`, `scripts/deploy_og_chain.py` |
| Tests (56 new, all passing) | ✅ done | `tests/unit/og_integration/` |
| Tool registry entries | ✅ done | `infra/tool-registry.yaml` |
| Design doc | ✅ done | `docs/hackathon-0g/design.md` |
| Hackathon README | ✅ done | `docs/hackathon-0g/README.md` |
| Demo script | ✅ done | `docs/hackathon-0g/demo-script.md` |
| X post draft | ✅ done | `docs/hackathon-0g/x-post.md` |
| **Branch pushed to GitHub** | ⬜ needs you | `git push -u origin feat/0g-integration` |
| **PR opened + merged to main on the public repo** | ⬜ needs you | https://github.com/arigatoexpress/Sapphire |
| **Node deps installed for the storage bridge** | ⬜ needs you | `cd lib/og/_ts && npm install` |
| **Testnet wallet created + funded from 0G faucet** | ⬜ needs you | save private key to `~/.config/sapphire-secrets/og_deploy_key` (mode 0600) |
| **Contracts deployed to 0G testnet** | ⬜ needs you | `python3 scripts/deploy_og_chain.py --network testnet` |
| **Smoke-test publish + verify** | ⬜ needs you | run the og_publish + og_verify commands from `docs/hackathon-0g/README.md` quick-start |
| **Mainnet wallet funded** | ⬜ needs you | acquire 0G on mainnet for ~0.05 0G of gas |
| **Contracts deployed to 0G mainnet** | ⬜ needs you | `python3 scripts/deploy_og_chain.py --network mainnet` |
| **One real signal published on mainnet** | ⬜ needs you | shows the project has *actual on-chain activity*, which judges grade on |
| **Mainnet addresses pasted into README** | ⬜ needs you | replace `0x...` placeholders in `docs/hackathon-0g/README.md` |
| **Demo video recorded** | ⬜ needs you | follow `docs/hackathon-0g/demo-script.md`, upload to YouTube |
| **X post published with required tags** | ⬜ needs you | use draft from `docs/hackathon-0g/x-post.md` |
| **HackQuest form submitted** | ⬜ needs you | https://www.hackquest.io |

## Submission form fields (for HackQuest)

Have these ready when you open the submission form:

| Field | Value (fill in actuals before submitting) |
|---|---|
| Project name | `Sapphire × 0G — Verifiable Autonomous Trading` |
| One-sentence description (≤30 words) | A production trading agent that publishes every signal to 0G Storage and anchors it on 0G Chain, giving traders, auditors, and counterparties on-chain proof of every prediction. |
| Track | Track 2 — Agentic Trading Arena (Verifiable Finance) |
| Code repository (public) | `https://github.com/arigatoexpress/Sapphire` |
| 0G mainnet contract address | `<SapphireSignalVerifier address>` |
| 0G Explorer link (proof of activity) | `https://chainscan.0g.ai/address/<addr>` |
| 0G components used | 0G Storage, 0G Compute (Sealed Inference / TEE), 0G Chain |
| Demo video link | `<YouTube URL>` |
| Public X post link | `<x.com URL>` |
| Hackathon README | `https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon-0g/README.md` |

## Order of operations the day you submit

1. Final commit + push the branch.
2. `npm install` inside `lib/og/_ts/`.
3. Generate testnet wallet, fund from faucet, deploy to testnet, smoke test.
4. Generate mainnet wallet (or reuse testnet wallet — depends on your wallet hygiene), fund a small amount, deploy to mainnet.
5. Publish ONE real signal on mainnet so the explorer shows an event log.
6. Update `docs/hackathon-0g/README.md` with the live mainnet addresses.
7. Record the demo following `docs/hackathon-0g/demo-script.md`. Upload unlisted to YouTube.
8. Post on X using the draft. Save the post URL.
9. Open the HackQuest submission form and paste in everything from the table above.
10. Hit submit.

## Why I can't do steps 8–10 for you

- **HackQuest** requires an authenticated session bound to your account.
- **X posting** requires your X account credentials. Posting on someone else's account violates X ToS and the hackathon's authorship requirement.
- **Mainnet deploys** spend your gas + sign with your private key. You should never share that key with any agent.
- **The demo video** requires you on screen / on mic narrating, plus a recording of *your* actual session for credibility.

If you want to script the deploy + verify steps so they run with one command on demo day, ask and I'll write `scripts/hackathon_smoke.sh` that does steps 3–6 unattended given a pre-funded wallet.
