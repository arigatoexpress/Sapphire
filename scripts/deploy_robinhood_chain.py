"""Deploy Sapphire OS contracts to Robinhood Chain testnet.

Uses web3.py + py-solc-x for compilation; Foundry not required.

Private key lookup order:
  1. $ROBINHOOD_DEPLOY_KEY env var
  2. ~/.config/sapphire-secrets/robinhood_deploy_key  (mode 0600)

Deployed addresses are written to data/chain/deployments.json.

Usage:
    python3 scripts/deploy_robinhood_chain.py [--check | --dry-run | --verify]

Modes:
    --check     Read-only preflight: RPC reachable, chain ID matches,
                deploy key present, deployer balance sufficient. No compile,
                no deploy. Safe to run anywhere.
    --dry-run   Compile contracts only (requires py-solc-x). No deploy.
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

log = logging.getLogger("deploy_robinhood_chain")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

CHAIN_ID = 46630
RPC_URL = "https://rpc.testnet.chain.robinhood.com"
EXPLORER_URL = "https://explorer.testnet.chain.robinhood.com"
SECRETS_FILE = Path.home() / ".config" / "sapphire-secrets" / "robinhood_deploy_key"
DEPLOYMENTS_FILE = ROOT / "data" / "chain" / "deployments.json"
CONTRACTS_DIR = ROOT / "contracts"

CONTRACTS = [
    "SapphireSignalVerifier",
    "SapphirePaymentGate",
]


def _load_private_key() -> str:
    key = os.environ.get("ROBINHOOD_DEPLOY_KEY", "").strip()
    if key:
        return key
    if SECRETS_FILE.exists():
        key = SECRETS_FILE.read_text().strip()
        if key:
            return key
    raise RuntimeError(
        "No deploy key found. Set $ROBINHOOD_DEPLOY_KEY or create "
        f"{SECRETS_FILE} (chmod 0600)."
    )


def _compile_contracts() -> dict[str, dict]:
    """Compile all contracts with solcx, return {name: {'abi': ..., 'bytecode': ...}}."""
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
        )
        # solcx returns keys like "<stdin>:ContractName"
        contract_key = next(k for k in result if k.endswith(f":{name}"))
        compiled[name] = {
            "abi": result[contract_key]["abi"],
            "bytecode": result[contract_key]["bin"],
        }
        log.info("  compiled %s — %d ABI entries", name, len(compiled[name]["abi"]))

    return compiled


def _deploy_contract(w3, compiled: dict, name: str, account) -> str:
    """Deploy a single contract, return its address."""
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
            "chainId": CHAIN_ID,
        }
    )
    tx["gas"] = w3.eth.estimate_gas(tx)

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log.info("  tx sent: 0x%s", tx_hash.hex())

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError(f"Deployment of {name} failed (status=0)")

    address = receipt["contractAddress"]
    log.info("  deployed %s → %s", name, address)
    return address


def _save_deployments(addresses: dict[str, str], tx_hashes: dict[str, str]) -> None:
    DEPLOYMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if DEPLOYMENTS_FILE.exists():
        try:
            existing = json.loads(DEPLOYMENTS_FILE.read_text())
        except Exception:
            pass

    existing["robinhood_testnet"] = {
        "chain_id": CHAIN_ID,
        "rpc": RPC_URL,
        "deployed_at": int(time.time()),
        "contracts": {
            name: {
                "address": addresses[name],
                "tx_hash": tx_hashes.get(name, ""),
                "explorer": f"{EXPLORER_URL}/address/{addresses[name]}",
            }
            for name in addresses
        },
    }
    DEPLOYMENTS_FILE.write_text(json.dumps(existing, indent=2))
    log.info("Deployments saved → %s", DEPLOYMENTS_FILE)


MIN_DEPLOY_BALANCE_ETH = 0.01  # rough floor for two simple deploys + buffer


def _preflight() -> int:
    """Read-only readiness check. Returns 0 on success, non-zero on failure."""
    try:
        from eth_account import Account  # type: ignore[import]
        from web3 import Web3  # type: ignore[import]
    except ImportError:
        log.error("[FAIL] web3 / eth-account not installed")
        log.error("       fix: pip install -r requirements-test.txt")
        return 1

    status = 0

    # 1. Contract sources present
    missing_sources = [n for n in CONTRACTS if not (CONTRACTS_DIR / f"{n}.sol").exists()]
    if missing_sources:
        log.error("[FAIL] contract sources missing: %s", missing_sources)
        status = 1
    else:
        log.info("[ OK ] contract sources present: %s", ", ".join(CONTRACTS))

    # 2. RPC reachable + chain ID
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 10}))
    if not w3.is_connected():
        log.error("[FAIL] RPC unreachable: %s", RPC_URL)
        return 1 if status == 0 else status
    try:
        chain_id = w3.eth.chain_id
    except Exception as exc:
        log.error("[FAIL] RPC reachable but chain_id call failed: %s", exc)
        return 1
    if chain_id != CHAIN_ID:
        log.error("[FAIL] chain_id mismatch: got %s, expected %s", chain_id, CHAIN_ID)
        status = 1
    else:
        log.info("[ OK ] RPC %s (chain_id %d, block %d)", RPC_URL, chain_id, w3.eth.block_number)

    # 3. Deploy key present
    try:
        private_key = _load_private_key()
    except RuntimeError as exc:
        log.error("[FAIL] %s", exc)
        return 1 if status == 0 else status
    account = Account.from_key(private_key)
    log.info("[ OK ] deploy key loaded: %s", account.address)

    # 4. Balance sufficient
    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = float(w3.from_wei(balance_wei, "ether"))
    if balance_eth < MIN_DEPLOY_BALANCE_ETH:
        log.error(
            "[FAIL] deployer balance %.6f ETH < %.4f ETH minimum — fund via testnet faucet",
            balance_eth, MIN_DEPLOY_BALANCE_ETH,
        )
        status = 1
    else:
        log.info("[ OK ] deployer balance: %.6f ETH (min %.4f)", balance_eth, MIN_DEPLOY_BALANCE_ETH)

    # 5. Existing deployment?
    if DEPLOYMENTS_FILE.exists():
        try:
            existing = json.loads(DEPLOYMENTS_FILE.read_text())
            net = existing.get("robinhood_testnet", {}).get("contracts", {})
            if net:
                log.info("[NOTE] prior deployment on record (will be overwritten):")
                for name, info in net.items():
                    log.info("         %s → %s", name, info.get("address"))
        except Exception:
            pass

    return status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only preflight; no compile, no deploy")
    parser.add_argument("--dry-run", action="store_true", help="Compile only, skip deployment")
    parser.add_argument("--verify", action="store_true", help="Attempt block explorer verification")
    args = parser.parse_args()

    if args.check:
        sys.exit(_preflight())

    compiled = _compile_contracts()
    if args.dry_run:
        log.info("Dry-run mode — skipping deployment.")
        for name in compiled:
            log.info("  %s: bytecode %d bytes", name, len(compiled[name]["bytecode"]) // 2)
        return

    try:
        from eth_account import Account  # type: ignore[import]
        from web3 import Web3  # type: ignore[import]
    except ImportError:
        log.error("web3 not installed. Run: pip install web3")
        sys.exit(1)

    private_key = _load_private_key()
    account = Account.from_key(private_key)

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        log.error("Cannot connect to %s", RPC_URL)
        sys.exit(1)

    balance = w3.eth.get_balance(account.address)
    log.info("Deployer: %s  balance: %.6f ETH", account.address, w3.from_wei(balance, "ether"))

    addresses: dict[str, str] = {}
    tx_hashes: dict[str, str] = {}

    for name in CONTRACTS:
        log.info("Deploying %s ...", name)
        addr = _deploy_contract(w3, compiled, name, account)
        addresses[name] = addr
        tx_hashes[name] = ""  # receipt is awaited inside _deploy_contract

    _save_deployments(addresses, tx_hashes)

    log.info("")
    log.info("=== Deployment complete ===")
    for name, addr in addresses.items():
        log.info("  %-30s %s", name, addr)
        log.info("    %s/address/%s", EXPLORER_URL, addr)

    if args.verify:
        log.info("Block explorer verification not yet implemented.")


if __name__ == "__main__":
    main()
