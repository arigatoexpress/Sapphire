"""Sapphire OS — public hackathon submissions frontend.

Stateless Flask app served at https://hack.sapphirealpha.xyz/. Hackathon judges
land here to find each submission's pitch, GitHub PR, demo video, contract
addresses, live status, and an embedded judge-grade pitch deck.

Source-of-truth for content lives in `SUBMISSIONS` below — each entry pulls
from PR descriptions and `docs/hackathon*/` markdown that already shipped with
the underlying code.

Routes:
  /                            landing page with 4 expandable cards
  /healthz                     liveness probe
  /api/submissions             stable JSON snapshot of all 4 entries
  /api/probe/<slug>            JSON RPC probe — calls eth_getCode against
                               the deployed contract for that submission
                               and returns whether bytecode exists. Used by
                               the live-probe widget on each card.
"""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, render_template, url_for

app = Flask(__name__, static_folder="static", template_folder="templates")

REPO_URL = "https://github.com/arigatoexpress/Sapphire"
DOCS_URL = f"{REPO_URL}/blob/main/docs"


# ---------------------------------------------------------------------------
# Submission catalog. Each entry maps to one expandable card.
# ---------------------------------------------------------------------------

SUBMISSIONS = [
    {
        "slug": "0g",
        "title": "Sapphire × 0G",
        "subtitle": "Verifiable Autonomous Trading",
        "status": "submitted",
        "sponsor": "0G APAC Hackathon",
        "track": "Track 2 · Agentic Trading Arena (Verifiable Finance)",
        "deadline": "2026-05-16 23:59 UTC+8",
        "prize_summary": "$150K pool · 1st $45K · 2nd $35K · 3rd $20K",
        "pitch": (
            "Every Sapphire trading signal is sealed by a TEE-attested 0G Compute "
            "inference, content-addressed on 0G Storage, and anchored on 0G Chain "
            "mainnet (16661) before market impact. Anyone can re-derive the "
            "audit trail with one CLI tool — `og_verify`."
        ),
        "one_line_pitch": (
            "Trading agents must prove their predictions before market impact."
        ),
        "novelty": (
            "Three 0G primitives wired in one round-trip — Compute (TEE inference) → "
            "Storage (merkle rootHash) → Chain (mainnet 16661 anchor). The asset "
            "isn't the contract; it's the round-trip verifier that any holder of "
            "a 0G RPC + our public address can re-derive in one CLI call."
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
            {
                "name": "SapphireSignalVerifier",
                "network": "0G Chain mainnet · chainId 16661",
                "explorer_url": "https://chainscan.0g.ai",
                "rpc_url": "https://evmrpc.0g.ai",
                "address": None,  # filled in from data/chain/deployments.json if present
            },
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
        "video_embed_url": None,  # placeholder — recorded video URL goes here
        "video_script_url": f"{DOCS_URL}/hackathon/0g/video-script.md",
        "deck_url": f"{DOCS_URL}/hackathon/0g/deck.md",
        "criteria": [
            {
                "name": "0G Technical Integration Depth & Innovation",
                "verbatim": "Extent of adoption of 0G components, and innovative solutions to AI / on-chain pain points.",
                "match": "All three primitives wired (Compute + Storage + Chain). Round-trip verifier is the novelty.",
            },
            {
                "name": "Technical Implementation & Completeness",
                "verbatim": "Functional integrity, code quality, and mandatory on-chain deployment.",
                "match": "Mainnet 16661 deploy + 56 unit tests for the integration alone + 6,567 repo-wide.",
            },
            {
                "name": "Product Value & Market Potential",
                "verbatim": "Market fit, problem-solving capability, user value, and growth roadmap.",
                "match": "Trading-agent provability is a $T market gap. Roadmap → Apollo Accelerator → Guild on 0G.",
            },
            {
                "name": "User Experience & Demo Quality",
                "verbatim": "Intuitiveness and user-friendliness of UI/UX; clarity and persuasiveness of pitch and demo.",
                "match": "One-CLI verify (`og_verify.py`). One-page judge view at hack.sapphirealpha.xyz. 60s + 3-min cuts.",
            },
            {
                "name": "Team Capability & Documentation",
                "verbatim": "Team background, quality of open-source code and README.",
                "match": "Solo founder, public repo. 6 supporting docs under `docs/hackathon-0g/`.",
            },
        ],
        "roadmap": [
            "Apollo Accelerator application (post-mainnet activity proof)",
            "Sentinel × 0G — chain-health gate gets a 0G dimension",
            "Publish `og_verify` as a standalone primitive",
            "Hardware-wallet flow for OG_PRIVATE_KEY (Ledger-signed)",
            "Guild on 0G — Sapphire as a verifiable-trading Guild operator",
        ],
    },
    {
        "slug": "megaeth",
        "title": "Sapphire Sentinel · Multi-Chain Health Gate",
        "subtitle": "Aave V3 + GMX V2 + Chainlink fallback",
        "status": "live",
        "sponsor": "MegaETH / Arbitrum",
        "track": "awesome-megaeth-ai listing · Mafia 2.0 · London AI Agentic ($15K)",
        "deadline": "Rolling — Mafia 2.0 + awesome-megaeth-ai PR · London Buildathon 2026-05-25",
        "prize_summary": "Mafia 2.0 syndicate check + reputational + London $15K AI Agentic",
        "pitch": (
            "Before any alpha-paid signal is approved, Sentinel reads "
            "Aave V3 reserve health and GMX V2 funding / open-interest skew "
            "on Arbitrum One — escalating to BLOCK on `|funding| > 500%` or "
            "WARNING on lopsided OI. Chainlink fallback prices the BTC / SOL / "
            "AVAX / DOGE markets that Aave does not."
        ),
        "one_line_pitch": "Approve the trade only if the chain agrees.",
        "novelty": (
            "Three chains, two protocol categories, one primitive. The "
            "chain-health gate composes — `evaluate_chain_health()` returns "
            "the worst-of severity across all chains the alpha references. "
            "The 1e30-scale GMX price footgun has a unit test that fails "
            "if anyone tries to revert it."
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
            ("569", "Optimism Aave V3 (chain 10)"),
            ("546", "MegaETH chain-health gate (chain 4326)"),
        ],
        "contracts": [
            {
                "name": "Aave V3 Pool",
                "network": "Arbitrum One · chainId 42161",
                "explorer_url": "https://arbiscan.io/address/0x794a61358D6845594F94dc1DB02A252b5b4814aD",
                "rpc_url": "https://arbitrum-one-rpc.publicnode.com",
                "address": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            },
            {
                "name": "Chainlink BTC/USD",
                "network": "Arbitrum One · chainId 42161",
                "explorer_url": "https://arbiscan.io/address/0x6ce185860a4963106506C203335A2910413708e9",
                "rpc_url": "https://arbitrum-one-rpc.publicnode.com",
                "address": "0x6ce185860a4963106506C203335A2910413708e9",
            },
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
        "video_embed_url": None,
        "video_script_url": f"{DOCS_URL}/hackathon/megaeth/video-script.md",
        "deck_url": f"{DOCS_URL}/hackathon/megaeth/deck.md",
        "criteria": [
            {
                "name": "awesome-megaeth-ai · active maintenance + docs",
                "verbatim": "Active maintenance + docs.",
                "match": "6,567 tests, daily commits, 4 architecture docs for chain integrations.",
            },
            {
                "name": "awesome-megaeth-ai · clear value to MegaETH developers",
                "verbatim": "Clear value to MegaETH developers (chain ID 4326 / 6343).",
                "match": "First Python wrapper on chain 4326; existing skill packs are TS/Solidity-leaning.",
            },
            {
                "name": "Mafia 2.0 · innovation over generic DeFi",
                "verbatim": "Selection bias against generic DeFi wrappers.",
                "match": "Sentinel is a primitive (chain-health gate), not a wrapper.",
            },
            {
                "name": "London Buildathon AI Agentic ($15K)",
                "verbatim": "Special category for AI agents building on Arbitrum and the Robinhood Chain.",
                "match": "Sentinel runs on Arbitrum One (42161) and Robinhood Chain (46630).",
            },
        ],
        "roadmap": [
            "awesome-megaeth-ai PR opened (DeFi + Agents + Developer Tools)",
            "Mafia 2.0 application filed",
            "Add a 4th chain — Base (8453) — same primitive port pattern",
            "Publish `pip install sapphire-sentinel` for non-Sapphire integrators",
            "ML-driven anomaly layer on top of rule-based gate",
        ],
    },
    {
        "slug": "robinhood",
        "title": "Sapphire Sentinel · Robinhood London",
        "subtitle": "Policy + privacy + payment gate for autonomous agents",
        "status": "submitted",
        "sponsor": "Arbitrum / Robinhood London Buildathon",
        "track": "AI Agentic Category ($15K) + Robinhood Chain Innovation Award ($30K)",
        "deadline": "Buildathon starts 2026-05-25 · Founder House 2026-07-10 → 12",
        "prize_summary": "$70K Open · $15K AI Agentic · $30K Innovation · $30K Grants",
        "pitch": (
            "An AI agent tries to pay for private RWA intelligence on Robinhood "
            "Chain testnet (46630). Sentinel screens the request against a human "
            "mandate (spend cap, allowed domains, prompt-injection screen, "
            "secret-egress screen) and anchors the decision — even rejected "
            "attacks — on `SapphireSentinelRegistry`."
        ),
        "one_line_pitch": "Agent safety on the chain Robinhood operates.",
        "novelty": (
            "Most safety systems silently drop bad requests. We anchor the "
            "*rejected* attack on chain so a year-later auditor can prove the "
            "attack happened *and* was caught. Plus chain-health composition "
            "(USDM peg + Aave reserves) and a Zama fhEVM mock that returns "
            "deterministic resultHash + riskHash without leaking weights."
        ),
        "bullets": [
            "Robinhood Chain testnet (chainId 46630) — `recordPaymentEvaluation` lands a real tx for every decision",
            "Prompt-injection + secret-egress screens stack on screen with the BLOCKED stamp",
            "Zama / fhEVM mock surfaces deterministic `resultHash` + `riskHash` from hidden basket weights",
            "Multi-chain: Sentinel queries MegaETH protocol-access layer for USDM peg + Aave reserves before approval",
        ],
        "prs": [
            ("498", "Sapphire Sentinel hackathon lane"),
            ("544", "Zama / fhEVM mock"),
            ("546", "MegaETH chain-health gate"),
            ("547", "hackathon smoke script (0G)"),
            ("553", "end-to-end integration tests"),
            ("555", "chain-health dashboard panel + DEPEG demo toggle"),
            ("556", "smoke `--target robinhood|both`"),
            ("567", "Forge test suite (18 cases) + Slither CI"),
            ("568", "prompt-injection demo toggle"),
        ],
        "contracts": [
            {
                "name": "SapphireSentinelRegistry",
                "network": "Robinhood Chain testnet · chainId 46630",
                "explorer_url": "https://explorer.testnet.chain.robinhood.com",
                "rpc_url": "https://rpc.testnet.chain.robinhood.com",
                "address": None,
            },
            {
                "name": "SapphirePaymentGate",
                "network": "Robinhood Chain testnet · chainId 46630",
                "explorer_url": "https://explorer.testnet.chain.robinhood.com",
                "rpc_url": "https://rpc.testnet.chain.robinhood.com",
                "address": None,
            },
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
        "video_embed_url": None,
        "video_script_url": f"{DOCS_URL}/hackathon/robinhood/video-script.md",
        "deck_url": f"{DOCS_URL}/hackathon/robinhood/deck.md",
        "criteria": [
            {
                "name": "AI Agentic Category ($15K)",
                "verbatim": "Special category for AI agents building on Arbitrum and the Robinhood Chain, with the top three winners sharing $15K, at least one spot reserved for Robinhood Chain.",
                "match": "Sentinel runs on Robinhood Chain (46630) AND Arbitrum (42161). Multi-chain agent.",
            },
            {
                "name": "Robinhood Chain Innovation Award ($30K)",
                "verbatim": "Reserved for projects building on the Robinhood Chain only and fully sponsored by the Robinhood team.",
                "match": "Sentinel + Payment Gate deployed on chain 46630. Privacy-mock + chain-health twist IS the innovation.",
            },
            {
                "name": "Open Category ($70K)",
                "verbatim": "Top 3 winners ($40K/$20K/$10K). At least one spot reserved for Robinhood Chain.",
                "match": "Robinhood-Chain-anchored project; we qualify for the reserved spot.",
            },
            {
                "name": "Devfolio · technical complexity",
                "verbatim": "Standard Devfolio judging.",
                "match": "4 gates compose into one severity verdict; 18-case Forge suite + Slither CI; multi-chain port in <1 day per chain.",
            },
        ],
        "roadmap": [
            "Mainnet contracts on Robinhood Chain when chain 46630 mainnet launches",
            "Replace Zama mock with real fhEVM (cross-pollinates with Zama submission)",
            "Publish `pip install sapphire-sentinel` for Robinhood Chain integrators",
            "ML-driven anomaly layer on the gate",
            "Sentinel becomes default agent-safety primitive on Robinhood Chain mainnet",
        ],
    },
    {
        "slug": "zama",
        "title": "write-fhevm-contracts",
        "subtitle": "Anthropic-format skill for fhEVM",
        "status": "draft",
        "sponsor": "Zama Bounty",
        "track": "AI Agent Skills · Mainnet Season 2 Bounty Track",
        "deadline": "2026-05-10 23:59",
        "prize_summary": "1st 1,500 cUSDT · 2nd 1,000 · 3rd 500 (3,000 cUSDT total)",
        "pitch": (
            "A Claude / Cursor / Windsurf skill that teaches LLMs to write "
            "Zama fhEVM contracts correctly the first time. Covers the five "
            "silent-failure footguns (FHE.select, ACL, input proofs, async "
            "decryption, ZamaEthereumConfig inheritance) and ships a 10-point "
            "self-check the model runs before returning."
        ),
        "one_line_pitch": (
            "A portable Anthropic-format skill that teaches LLMs to write fhEVM contracts correctly the first time."
        ),
        "novelty": (
            "Five silent-failure footguns. Ten-point pre-write self-check the "
            "model runs against its own draft before returning. We've shipped "
            "14 hermes skills + 17 plugin manifest entries — we eat this "
            "format daily."
        ),
        "bullets": [
            "Anthropic skill format — terse YAML frontmatter for trigger discovery",
            "Sapphire ships 14 hermes skills + 109-tool plugin registry — we eat this format daily",
            "Demo rebuilds `SapphireSentinelBasket.sol` from scratch — illustrative LLM transcript catches all 5 footguns",
            "Bounty deadline 2026-05-10 23:59 AOE",
        ],
        "prs": [
            ("564", "Zama AI Agent Skills bounty scaffold"),
            ("559", "Zama deep dive — programs, winner patterns, Sentinel extensions"),
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
        "video_embed_url": None,
        "video_script_url": f"{DOCS_URL}/hackathon/zama/video-script.md",
        "deck_url": f"{DOCS_URL}/hackathon/zama/deck.md",
        "criteria": [
            {
                "name": "Accuracy",
                "verbatim": "Submissions are judged on accuracy [...]",
                "match": "All 5 footguns covered with positive + negative example. EXAMPLE_REBUILD.md verified compileable.",
            },
            {
                "name": "Completeness",
                "verbatim": "Encrypted types, FHE operations, access control, input proofs, decryption patterns, frontend integration, testing, anti-patterns.",
                "match": "All 8 areas covered in numbered SKILL.md sections.",
            },
            {
                "name": "Agent effectiveness",
                "verbatim": "[...] agent effectiveness [...]",
                "match": "YAML frontmatter triggers on the right phrases; tested in real Claude Code sessions; 60s cut IS a real session.",
            },
            {
                "name": "Code quality",
                "verbatim": "[...] code quality [...]",
                "match": "Source skill is structured Markdown with idempotent activation; positive examples are real working Solidity.",
            },
            {
                "name": "Error prevention",
                "verbatim": "[...] error prevention.",
                "match": "10-point pre-write checklist IS the error-prevention mechanism. Sapphire ships 14 production skills.",
            },
        ],
        "roadmap": [
            "Win → 1,500 cUSDT funds first real-fhEVM port of `lib/hackathon/privacy_mock.py`",
            "Publish to Anthropic skill marketplace + Cursor's skill registry",
            "Add a 6th footgun when one shows up (skill is versioned)",
            "Instrument the skill — telemetry on real-world catches",
            "Publish the meta-skill: how to write portable skills",
        ],
    },
]


# ---------------------------------------------------------------------------
# Hydrate contract addresses from data/chain/deployments.json if present.
# ---------------------------------------------------------------------------

def _hydrate_addresses() -> None:
    """If a deployments.json is present, fill in `address` fields in-place.

    Looks for `data/chain/deployments.json` at the repo root. In the
    Cloud Run container the service is copied to `/app/` (no parent repo
    structure), so we check several candidate paths and silently no-op
    if none exists.
    """
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for n in (1, 2, 3):
        try:
            candidates.append(here.parents[n] / "data" / "chain" / "deployments.json")
        except IndexError:
            break

    deployments_file: Path | None = next((p for p in candidates if p.exists()), None)
    if deployments_file is None:
        return
    try:
        deployments = json.loads(deployments_file.read_text())
    except Exception:
        return

    # Map (slug, contract_name) -> deployments-json key path
    address_map = {
        ("0g", "SapphireSignalVerifier"): ("og_mainnet", "SapphireSignalVerifier"),
        ("robinhood", "SapphireSentinelRegistry"): ("robinhood_chain_testnet", "SapphireSentinelRegistry"),
        ("robinhood", "SapphirePaymentGate"): ("robinhood_chain_testnet", "SapphirePaymentGate"),
    }

    for sub in SUBMISSIONS:
        for c in sub["contracts"]:
            key = (sub["slug"], c["name"])
            if key not in address_map:
                continue
            net_key, contract_key = address_map[key]
            block = deployments.get(net_key, {})
            contracts = block.get("contracts", {})
            entry = contracts.get(contract_key, {})
            addr = entry.get("address")
            if addr and not c.get("address"):
                c["address"] = addr
                # Repoint explorer to the address-specific page
                explorer_base = c["explorer_url"].rstrip("/")
                if "/address/" not in explorer_base:
                    c["explorer_url"] = f"{explorer_base}/address/{addr}"


_hydrate_addresses()


@app.route("/")
def index():
    return render_template(
        "index.html",
        submissions=SUBMISSIONS,
        repo_url=REPO_URL,
        live_demo_url="https://hack.sapphirealpha.xyz",
    )


@app.route("/healthz")
def healthz():
    return {"ok": True, "submissions": len(SUBMISSIONS)}, 200


@app.route("/api/submissions")
def api_submissions():
    """Stable JSON snapshot for any tooling that wants it."""
    return jsonify({"submissions": SUBMISSIONS, "repo_url": REPO_URL}), 200


@app.route("/api/probe/<slug>")
def api_probe(slug: str):
    """Live JSON RPC probe — calls eth_getCode against each deployed contract.

    Returns whether bytecode is present (proof the contract is live), the
    first 64 hex chars of the bytecode for visual confirmation, and the RPC
    URL used. Soft-fails: any RPC error returns ok=False with the error
    string, never raises 500.
    """
    sub = next((s for s in SUBMISSIONS if s["slug"] == slug), None)
    if sub is None:
        return jsonify({"ok": False, "error": f"unknown slug: {slug}"}), 404

    results = []
    for contract in sub.get("contracts", []):
        addr = contract.get("address")
        rpc_url = contract.get("rpc_url")
        entry = {
            "name": contract["name"],
            "network": contract["network"],
            "address": addr,
            "rpc_url": rpc_url,
        }
        if not addr or not rpc_url:
            entry["ok"] = False
            entry["status"] = "deployment_address_pending"
            entry["bytecode_preview"] = None
            entry["bytecode_size"] = 0
            results.append(entry)
            continue

        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "eth_getCode",
                "params": [addr, "latest"],
                "id": 1,
            }
        ).encode()
        req = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                # Some public RPCs (Arbitrum Foundation's primary endpoint)
                # 403 generic Python user-agents. A browser-shaped UA fixes
                # the 403 without requiring an API key.
                "User-Agent": "Mozilla/5.0 (compatible; SapphireHackathonFrontend/1.0)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                body = json.loads(resp.read().decode())
            code = body.get("result", "0x")
            has_code = bool(code) and code != "0x"
            entry["ok"] = has_code
            entry["status"] = "deployed_bytecode_present" if has_code else "no_bytecode"
            # First 64 hex chars after the 0x prefix
            entry["bytecode_preview"] = code[:66] if has_code else None
            entry["bytecode_size"] = (len(code) - 2) // 2 if has_code else 0
        except Exception as exc:
            entry["ok"] = False
            entry["status"] = "rpc_error"
            entry["error"] = str(exc)[:200]
            entry["bytecode_preview"] = None
            entry["bytecode_size"] = 0
        results.append(entry)

    return jsonify({"slug": slug, "contracts": results}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
