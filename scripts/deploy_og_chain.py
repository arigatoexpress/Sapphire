"""Deploy Sapphire OS contracts to 0G Chain (testnet or mainnet).

Adapted from scripts/deploy_robinhood_chain.py. Same compile/deploy flow,
parameterized for 0G's two networks, and additionally writes the
SapphireSignalVerifier ABI to data/chain/sapphire_signal_verifier.abi.json so
the runtime client (lib/og/chain.py) can load it without a fresh compile.

Private key lookup order:
  1. $OG_PRIVATE_KEY env var
  2. ~/.config/sapphire-secrets/og_deploy_key  (mode 0600)

Deployed addresses are written to data/chain/deployments.json under
`og_testnet` or `og_mainnet`.

Usage:
    python3 scripts/deploy_og_chain.py --check                # preflight
    python3 scripts/deploy_og_chain.py --abi-only             # write ABI only
    python3 scripts/deploy_og_chain.py --network testnet --dry-run
    python3 scripts/deploy_og_chain.py --network testnet      # full deploy
    python3 scripts/deploy_og_chain.py --network mainnet      # full deploy

Modes:
    --check     Read-only preflight: RPC reachable, chain ID matches,
                deploy key present, deployer balance sufficient.
    --abi-only  Compile and write ABI files only. No deploy. No key needed.
    --dry-run   Compile contracts only. No deploy.
    (default)   Full deploy: compile + broadcast + save deployment record.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.og.config import (  # noqa: E402  (sys.path manipulation above)
    OG_CHAIN_MAINNET,
    OG_CHAIN_TESTNET,
    OG_EXPLORER_MAINNET,
    OG_EXPLORER_TESTNET,
    OG_RPC_MAINNET,
    OG_RPC_TESTNET,
)

log = logging.getLogger("deploy_og_chain")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

SECRETS_FILE = Path.home() / ".config" / "sapphire-secrets" / "og_deploy_key"
DEPLOYMENTS_FILE = ROOT / "data" / "chain" / "deployments.json"
ABI_DIR = ROOT / "data" / "chain"
CONTRACTS_DIR = ROOT / "contracts"

CONTRACTS = [
    "SapphireSignalVerifier",
    "SapphirePaymentGate",
    "SapphireSentinelRegistry",
]

NETWORKS = {
    "testnet": {
        "chain_id": OG_CHAIN_TESTNET,
        "rpc": OG_RPC_TESTNET,
        "explorer": OG_EXPLORER_TESTNET,
        "min_balance_eth": 0.1,
    },
    "mainnet": {
        "chain_id": OG_CHAIN_MAINNET,
        "rpc": OG_RPC_MAINNET,
        "explorer": OG_EXPLORER_MAINNET,
        "min_balance_eth": 0.05,
    },
}


def _load_private_key() -> str:
    key = os.environ.get("OG_PRIVATE_KEY", "").strip()
    if key:
        return key
    if SECRETS_FILE.exists():
        key = SECRETS_FILE.read_text().strip()
        if key:
            return key
    raise RuntimeError(
        f"No deploy key found. Set $OG_PRIVATE_KEY or create {SECRETS_FILE} (chmod 0600)."
    )


def _compile_contracts() -> dict[str, dict]:
    try:
        import solcx  # type: ignore[import]
    except ImportError:
        log.error("py-solc-x not installed. Run: pip install py-solc-x")
        sys.exit(1)

    solcx.install_solc("0.8.20", show_progress=False)
    solcx.set_solc_version("0.8.20")

    compiled: dict[str, dict] = {}
    for name in CONTRACTS:
        sol_file = CONTRACTS_DIR / f"{name}.sol"
        if not sol_file.exists():
            raise FileNotFoundError(f"Contract source not found: {sol_file}")
        log.info("Compiling %s ...", name)
        result = solcx.compile_source(
            sol_file.read_text(),
            output_values=["abi", "bin"],
            solc_version="0.8.20",
            evm_version="cancun",
        )
        contract_key = next(k for k in result if k.endswith(f":{name}"))
        compiled[name] = {
            "abi": result[contract_key]["abi"],
            "bytecode": result[contract_key]["bin"],
        }
        log.info("  compiled %s — %d ABI entries", name, len(compiled[name]["abi"]))
    return compiled


def _write_abis(compiled: dict[str, dict]) -> None:
    ABI_DIR.mkdir(parents=True, exist_ok=True)
    for name, blob in compiled.items():
        target = ABI_DIR / f"{_snake(name)}.abi.json"
        target.write_text(json.dumps(blob["abi"], indent=2))
        log.info("  ABI written → %s", target)


def _snake(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _deploy_contract(w3, compiled: dict, name: str, account, chain_id: int) -> tuple[str, str]:
    abi = compiled[name]["abi"]
    bytecode = compiled[name]["bytecode"]
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price
    tx = contract.constructor().build_transaction(
        {
            "from": account.address,
            "nonce": nonce,
            "gasPrice": gas_price,
            "chainId": chain_id,
        }
    )
    tx["gas"] = w3.eth.estimate_gas(tx)
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log.info("  tx sent: 0x%s", tx_hash.hex())
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt["status"] != 1:
        raise RuntimeError(f"Deployment of {name} failed (status=0)")
    address = receipt["contractAddress"]
    log.info("  deployed %s → %s", name, address)
    return address, tx_hash.hex()


def _save_deployments(network: str, addresses: dict[str, str], tx_hashes: dict[str, str]) -> None:
    cfg = NETWORKS[network]
    DEPLOYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if DEPLOYMENTS_FILE.exists():
        try:
            existing = json.loads(DEPLOYMENTS_FILE.read_text())
        except Exception:
            pass

    existing[f"og_{network}"] = {
        "chain_id": cfg["chain_id"],
        "rpc": cfg["rpc"],
        "deployed_at": int(time.time()),
        "contracts": {
            name: {
                "address": addresses[name],
                "tx_hash": tx_hashes.get(name, ""),
                "explorer": f"{cfg['explorer']}/address/{addresses[name]}",
            }
            for name in addresses
        },
    }
    DEPLOYMENTS_FILE.write_text(json.dumps(existing, indent=2))
    log.info("Deployments saved → %s", DEPLOYMENTS_FILE)


def _preflight(network: str) -> int:
    cfg = NETWORKS[network]
    try:
        from eth_account import Account  # type: ignore[import]
        from web3 import Web3  # type: ignore[import]
    except ImportError:
        log.error("[FAIL] web3 / eth-account not installed")
        log.error("       fix: pip install web3 eth-account py-solc-x")
        return 1

    status = 0
    missing_sources = [n for n in CONTRACTS if not (CONTRACTS_DIR / f"{n}.sol").exists()]
    if missing_sources:
        log.error("[FAIL] contract sources missing: %s", missing_sources)
        return 1
    log.info("[ OK ] contract sources present: %s", ", ".join(CONTRACTS))

    w3 = Web3(Web3.HTTPProvider(cfg["rpc"], request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        log.error("[FAIL] RPC unreachable: %s", cfg["rpc"])
        return 1
    chain_id = w3.eth.chain_id
    if chain_id != cfg["chain_id"]:
        log.error("[FAIL] chain_id mismatch: got %s, expected %s", chain_id, cfg["chain_id"])
        status = 1
    else:
        log.info("[ OK ] RPC %s (chain_id %d, block %d)", cfg["rpc"], chain_id, w3.eth.block_number)

    try:
        private_key = _load_private_key()
    except RuntimeError as exc:
        log.error("[FAIL] %s", exc)
        return 1
    try:
        account = Account.from_key(private_key)
    except Exception as exc:
        log.error("[FAIL] deploy key not parseable: %s", exc)
        return 1
    log.info("[ OK ] deploy key loaded: %s", account.address)

    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = float(w3.from_wei(balance_wei, "ether"))
    if balance_eth < cfg["min_balance_eth"]:
        log.error(
            "[FAIL] deployer balance %.6f 0G < %.4f 0G minimum (faucet for testnet, fund for mainnet)",
            balance_eth,
            cfg["min_balance_eth"],
        )
        status = 1
    else:
        log.info("[ OK ] deployer balance: %.6f 0G", balance_eth)

    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", choices=list(NETWORKS), default="testnet")
    parser.add_argument("--check", action="store_true", help="Read-only preflight")
    parser.add_argument("--abi-only", action="store_true", help="Compile + write ABIs; no deploy")
    parser.add_argument("--dry-run", action="store_true", help="Compile only")
    args = parser.parse_args()

    if args.check:
        sys.exit(_preflight(args.network))

    compiled = _compile_contracts()
    _write_abis(compiled)
    if args.abi_only:
        log.info("ABI-only mode — done.")
        return

    if args.dry_run:
        log.info("Dry-run — skipping deployment.")
        for name in compiled:
            log.info("  %s: bytecode %d bytes", name, len(compiled[name]["bytecode"]) // 2)
        return

    cfg = NETWORKS[args.network]
    try:
        from eth_account import Account  # type: ignore[import]
        from web3 import Web3  # type: ignore[import]
    except ImportError:
        log.error("web3 not installed")
        sys.exit(1)

    private_key = _load_private_key()
    account = Account.from_key(private_key)
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
    if not w3.is_connected():
        log.error("Cannot connect to %s", cfg["rpc"])
        sys.exit(1)

    log.info(
        "Deployer: %s  balance: %.6f 0G",
        account.address,
        w3.from_wei(w3.eth.get_balance(account.address), "ether"),
    )

    addresses: dict[str, str] = {}
    tx_hashes: dict[str, str] = {}
    for name in CONTRACTS:
        log.info("Deploying %s ...", name)
        addr, tx_hash = _deploy_contract(w3, compiled, name, account, cfg["chain_id"])
        addresses[name] = addr
        tx_hashes[name] = tx_hash

    _save_deployments(args.network, addresses, tx_hashes)
    log.info("=== Deployment to 0G %s complete ===", args.network)
    for name, addr in addresses.items():
        log.info("  %-30s %s", name, addr)
        log.info("    %s/address/%s", cfg["explorer"], addr)


if __name__ == "__main__":
    main()
