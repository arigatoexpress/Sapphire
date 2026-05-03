"""Sapphire OS — public hackathon submissions frontend.

Stateless Flask app served at https://hack.sapphirealpha.xyz/. Hackathon judges
land here to find each submission's pitch, GitHub PR, demo video, contract
addresses, and live status. No auth, no state, no JS frameworks.

Source-of-truth for content lives in `SUBMISSIONS` below — each entry pulls
from PR descriptions and `docs/hackathon*/` markdown that already shipped with
the underlying code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, render_template

app = Flask(__name__, static_folder="static", template_folder="templates")

REPO_URL = "https://github.com/arigatoexpress/Sapphire"


# ---------------------------------------------------------------------------
# Submission catalog. Each entry maps to one card on the page.
#   pr_links        : list of (number, label) pulled from merged PRs
#   contract_addr   : (label, address, explorer_url) for the testnet anchor
#   live_metric     : a humanized "live status" string (test count, block, etc.)
#   demo_url        : direct link to the demo video (or None -> falls back to repo)
#   sponsor_track   : track / sponsor name shown as a pill
# ---------------------------------------------------------------------------

SUBMISSIONS = [
    {
        "slug": "0g",
        "title": "Sapphire × 0G",
        "subtitle": "Verifiable Autonomous Trading",
        "status": "submitted",
        "sponsor": "0G APAC Hackathon",
        "track": "Track 2 · Agentic Trading Arena (Verifiable Finance)",
        "pitch": (
            "Every Sapphire trading signal is sealed by a TEE-attested 0G Compute "
            "inference, content-addressed on 0G Storage, and anchored on 0G Chain "
            "mainnet (16661) before market impact. Anyone can re-derive the "
            "audit trail with one CLI tool — `og_verify`."
        ),
        "bullets": [
            "TEE-sealed inference via 0G Compute (`broker.inference.processResponse`)",
            "Content-addressed signal envelope on 0G Storage (merkle rootHash)",
            "On-chain anchor via `SapphireSignalVerifier.publishSignal(...)` on chainId 16661",
            "Fire-and-forget hook into the trading critical path — opt-in via `SAPPHIRE_OG_ENABLED=1`",
        ],
        "prs": [
            ("525", "feat(0g): verifiable trading layer"),
            ("547", "hackathon smoke script"),
            ("572", "demo recording scripts"),
        ],
        "contracts": [
            (
                "SapphireSignalVerifier",
                "0G Chain mainnet · 16661",
                "https://chainscan.0g.ai",
            ),
        ],
        "live_status": "56 unit tests · 6,567 collected repo-wide · merged",
        "code_paths": [
            "lib/og/{config,storage,chain,compute,envelope,hooks}.py",
            "plugins/claw-sapphire/tools/og_publish.py",
            "plugins/claw-sapphire/tools/og_verify.py",
            "contracts/SapphireSignalVerifier.sol",
            "scripts/deploy_og_chain.py",
            "docs/hackathon-0g/",
        ],
        "demo_url": f"{REPO_URL}/blob/main/docs/hackathon-0g/demo-script-v2.md",
        "demo_label": "3-min demo script",
    },
    {
        "slug": "megaeth",
        "title": "Sapphire Sentinel · Multi-Chain Health Gate",
        "subtitle": "Aave V3 + GMX V2 + Chainlink fallback",
        "status": "live",
        "sponsor": "MegaETH / Arbitrum",
        "track": "Cross-chain alpha verification (Wave A + Wave B)",
        "pitch": (
            "Before any alpha-paid signal is approved, Sentinel reads "
            "Aave V3 reserve health and GMX V2 funding / open-interest skew "
            "on Arbitrum One — escalating to BLOCK on `|funding| > 500%` or "
            "WARNING on lopsided OI. Chainlink fallback prices the BTC / SOL / "
            "AVAX / DOGE markets that Aave does not."
        ),
        "bullets": [
            "60 GMX V2 markets indexed; 11 priced live (4 via Aave + 7 via Chainlink)",
            "GMX `Price.Props` 1e30-scale encoder/decoder (footgun: NOT 1e8)",
            "Sentinel chain-health gate: `severity = max(lend, perps)` with soft-fail on RPC error",
            "All 6 Arbitrum One Chainlink feeds verified live via `eth_getCode`",
        ],
        "prs": [
            ("557", "Arbitrum Aave V3 read layer"),
            ("565", "GMX V2 perps reader + chain-health gate"),
            ("570", "Chainlink oracle fallback (BTC/SOL/AVAX/DOGE)"),
        ],
        "contracts": [
            (
                "GMX V2 Reader",
                "Arbitrum One",
                "https://arbiscan.io/address/0xf60beCBBA17B3a7B1E70c38D43f0a9Bf1d139",
            ),
            (
                "Aave V3 Pool",
                "Arbitrum One",
                "https://arbiscan.io/address/0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            ),
        ],
        "live_status": "134 unit + 2 live integration tests · merged",
        "code_paths": [
            "lib/chains/arbitrum/contracts/{aave_v3,gmx_v2,chainlink_oracle,gmx_price_adapter}.py",
            "lib/chains/megaeth/",
            "lib/hackathon/{sentinel,arbitrum_chain_health,chain_health_gate}.py",
            "config/arbitrum_protocols.yaml",
        ],
        "demo_url": f"{REPO_URL}/pull/570",
        "demo_label": "Live perps_overview() snapshot",
    },
    {
        "slug": "robinhood",
        "title": "Sapphire Sentinel · Robinhood London",
        "subtitle": "Policy + privacy + payment gate for autonomous agents",
        "status": "submitted",
        "sponsor": "Arbitrum / Robinhood London Buildathon",
        "track": "Best Agentic Project · Robinhood Chain reserved slot",
        "pitch": (
            "An AI agent tries to pay for private RWA intelligence on Robinhood "
            "Chain testnet (46630). Sentinel screens the request against a human "
            "mandate (spend cap, allowed domains, prompt-injection screen, "
            "secret-egress screen) and anchors the decision — even rejected "
            "attacks — on `SapphireSentinelRegistry`."
        ),
        "bullets": [
            "Robinhood Chain testnet (chainId 46630) — `recordPaymentEvaluation` lands a real tx for every decision",
            "Prompt-injection + secret-egress screens stack on screen with the BLOCKED stamp",
            "Zama / fhEVM mock surfaces deterministic `resultHash` + `riskHash` from hidden basket weights",
            "Multi-chain: Sentinel queries MegaETH protocol-access layer for USDM peg + Aave reserves before approval",
        ],
        "prs": [
            ("547", "hackathon smoke script (0G)"),
            ("556", "smoke `--target robinhood|both`"),
            ("555", "Sentinel chain-health demo toggle"),
            ("568", "prompt-injection demo toggle"),
        ],
        "contracts": [
            (
                "SapphireSentinelRegistry",
                "Robinhood Chain testnet · 46630",
                "https://explorer.testnet.chain.robinhood.com",
            ),
            (
                "SapphirePaymentGate",
                "Robinhood Chain testnet · 46630",
                "https://explorer.testnet.chain.robinhood.com",
            ),
        ],
        "live_status": "9 smoke-script tests passing · dry-run + live paths verified",
        "code_paths": [
            "contracts/SapphireSentinelRegistry.sol",
            "contracts/SapphirePaymentGate.sol",
            "lib/chains/robinhood_chain.py",
            "lib/hackathon/sentinel.py",
            "lib/hackathon/privacy_mock.py",
            "scripts/hackathon_smoke.sh",
            "scripts/deploy_robinhood_chain.py",
            "docs/hackathon/sapphire-sentinel-london-2026.md",
        ],
        "demo_url": f"{REPO_URL}/blob/main/docs/hackathon/london-demo-script.md",
        "demo_label": "90-second demo script",
    },
    {
        "slug": "zama",
        "title": "write-fhevm-contracts",
        "subtitle": "Anthropic-format skill for fhEVM",
        "status": "draft",
        "sponsor": "Zama Bounty",
        "track": "AI Agent Skills · 1,500 cUSDT first prize",
        "pitch": (
            "A Claude / Cursor / Windsurf skill that teaches LLMs to write "
            "Zama fhEVM contracts correctly the first time. Covers the five "
            "silent-failure footguns (FHE.select, ACL, input proofs, async "
            "decryption, ZamaEthereumConfig inheritance) and ships a 10-point "
            "self-check the model runs before returning."
        ),
        "bullets": [
            "Anthropic skill format — terse YAML frontmatter for trigger discovery",
            "Sapphire ships **14 hermes skills** + 109-tool plugin registry — we eat this format daily",
            "Demo rebuilds `SapphireSentinelBasket.sol` from scratch — illustrative LLM transcript catches all 5 footguns",
            "Bounty deadline 2026-05-10 23:59 AOE",
        ],
        "prs": [
            ("564", "Zama AI Agent Skills bounty scaffold"),
            ("559", "privacy mock + Zama relayer SDK note"),
        ],
        "contracts": [],
        "live_status": "scaffold landed · Ari to dogfood + finalize before 2026-05-10",
        "code_paths": [
            "docs/grants/zama-ai-agent-skills/SKILL.md",
            "docs/grants/zama-ai-agent-skills/SUBMISSION.md",
            "docs/grants/zama-ai-agent-skills/EXAMPLE_REBUILD.md",
            "lib/hackathon/privacy_mock.py",
        ],
        "demo_url": f"{REPO_URL}/blob/main/docs/grants/zama-ai-agent-skills/SKILL.md",
        "demo_label": "Read SKILL.md",
    },
]


@app.route("/")
def index():
    return render_template(
        "index.html",
        submissions=SUBMISSIONS,
        repo_url=REPO_URL,
    )


@app.route("/healthz")
def healthz():
    return {"ok": True, "submissions": len(SUBMISSIONS)}, 200


@app.route("/api/submissions")
def api_submissions():
    """Stable JSON snapshot for any tooling that wants it."""
    return {"submissions": SUBMISSIONS, "repo_url": REPO_URL}, 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
