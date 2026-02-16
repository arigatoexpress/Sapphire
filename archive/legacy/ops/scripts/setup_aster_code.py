#!/usr/bin/env python3
"""
Aster Code - Agent & Builder Approval Script

Sets up the Aster Code builder system:
1. Generates an agent wallet (or uses existing ASTER_API_KEY/SECRET)
2. Calls /fapi/v3/approveAgent (EIP-712 signed by main wallet)
3. Calls /fapi/v3/approveBuilder (EIP-712 signed by main wallet)

Usage:
    ETH_PRIVATE_KEY=0x... python scripts/setup_aster_code.py

    # Optionally specify agent address and builder:
    ETH_PRIVATE_KEY=0x... \
    ASTER_AGENT_ADDRESS=0x... \
    ASTER_CODE_BUILDER_ADDRESS=0x... \
    ASTER_CODE_FEE_RATE=0 \
    python scripts/setup_aster_code.py

Environment Variables:
    ETH_PRIVATE_KEY              - Main wallet private key (REQUIRED for signing)
    ASTER_BASE_URL               - Aster API base URL (default: https://fapi.asterdex.com)
    ASTER_AGENT_ADDRESS          - Agent/signer address (auto-generated if not set)
    ASTER_AGENT_PRIVATE_KEY      - Agent/signer private key (auto-generated if not set)
    ASTER_CODE_BUILDER_ADDRESS   - Builder address for fee attribution
    ASTER_CODE_FEE_RATE          - Max fee rate (default: "0")
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from eth_account import Account
    from eth_account.messages import encode_typed_data
except ImportError:
    print("ERROR: eth-account not installed. Run: pip install eth-account")
    sys.exit(1)


# Aster Code EIP-712 domain for mainnet
ASTER_DOMAIN = {
    "name": "AsterSignTransaction",
    "version": "1",
    "chainId": 1666,
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}

# Testnet domain (chainId=714)
ASTER_DOMAIN_TESTNET = {
    "name": "AsterSignTransaction",
    "version": "1",
    "chainId": 714,
    "verifyingContract": "0x0000000000000000000000000000000000000000",
}

BASE_URL = os.environ.get("ASTER_BASE_URL", "https://fapi.asterdex.com")
IS_TESTNET = "testnet" in BASE_URL


def get_nonce() -> str:
    """Generate microsecond-precision nonce."""
    return str(int(time.time() * 1_000_000))


def sign_eip712_management(
    private_key: str,
    primary_type: str,
    type_fields: list,
    message: dict,
) -> str:
    """Sign an EIP-712 typed data message for Aster management endpoints.

    Management endpoints (approveAgent, approveBuilder, etc.) use dynamic primaryType.
    Field names are capitalized before signing.
    """
    domain = ASTER_DOMAIN_TESTNET if IS_TESTNET else ASTER_DOMAIN

    full_types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        primary_type: type_fields,
    }

    typed_data = {
        "types": full_types,
        "primaryType": primary_type,
        "domain": domain,
        "message": message,
    }

    encoded = encode_typed_data(full_types=typed_data["types"],
                                 domain_data=typed_data["domain"],
                                 primary_type=typed_data["primaryType"],
                                 message=typed_data["message"])

    account = Account.from_key(private_key)
    signed = account.sign_message(encoded)
    return signed.signature.hex()


async def approve_agent(
    client: httpx.AsyncClient,
    user_address: str,
    eth_private_key: str,
    agent_address: str,
    agent_name: str = "SapphireTrader",
    builder_address: Optional[str] = None,
    max_fee_rate: str = "0",
) -> Dict[str, Any]:
    """Call POST /fapi/v3/approveAgent to authorize an agent/signer."""

    nonce = get_nonce()

    # Parameters for the request
    params = {
        "user": user_address,
        "nonce": nonce,
        "agentName": agent_name,
        "agentAddress": agent_address,
        "ipWhitelist": "",
        "expired": "",
        "canSpotTrade": "true",
        "canPerpTrade": "true",
        "canWithdraw": "false",
    }

    if builder_address:
        params["builder"] = builder_address
        params["maxFeeRate"] = max_fee_rate

    # EIP-712 type for ApproveAgent (capitalize field names for signing)
    type_fields = [
        {"name": "User", "type": "address"},
        {"name": "Nonce", "type": "string"},
        {"name": "AgentName", "type": "string"},
        {"name": "AgentAddress", "type": "address"},
        {"name": "IpWhitelist", "type": "string"},
        {"name": "Expired", "type": "string"},
        {"name": "CanSpotTrade", "type": "string"},
        {"name": "CanPerpTrade", "type": "string"},
        {"name": "CanWithdraw", "type": "string"},
    ]

    # Capitalize field names for the signing message
    message = {
        "User": user_address,
        "Nonce": nonce,
        "AgentName": agent_name,
        "AgentAddress": agent_address,
        "IpWhitelist": "",
        "Expired": "",
        "CanSpotTrade": "true",
        "CanPerpTrade": "true",
        "CanWithdraw": "false",
    }

    if builder_address:
        type_fields.append({"name": "Builder", "type": "address"})
        type_fields.append({"name": "MaxFeeRate", "type": "string"})
        message["Builder"] = builder_address
        message["MaxFeeRate"] = max_fee_rate

    signature = sign_eip712_management(
        eth_private_key, "ApproveAgent", type_fields, message
    )
    params["signature"] = signature

    print(f"  POST {BASE_URL}/fapi/v3/approveAgent")
    print(f"  Agent: {agent_address}")
    print(f"  Builder: {builder_address or 'none'}")

    resp = await client.post(f"{BASE_URL}/fapi/v3/approveAgent", params=params)
    result = resp.json()
    print(f"  Response [{resp.status_code}]: {json.dumps(result, indent=2)}")
    return result


async def approve_builder(
    client: httpx.AsyncClient,
    user_address: str,
    eth_private_key: str,
    builder_address: str,
    max_fee_rate: str = "0",
) -> Dict[str, Any]:
    """Call POST /fapi/v3/approveBuilder to approve builder fee attribution."""

    nonce = get_nonce()

    params = {
        "user": user_address,
        "nonce": nonce,
        "builderAddress": builder_address,
        "maxFeeRate": max_fee_rate,
    }

    type_fields = [
        {"name": "User", "type": "address"},
        {"name": "Nonce", "type": "string"},
        {"name": "BuilderAddress", "type": "address"},
        {"name": "MaxFeeRate", "type": "string"},
    ]

    message = {
        "User": user_address,
        "Nonce": nonce,
        "BuilderAddress": builder_address,
        "MaxFeeRate": max_fee_rate,
    }

    signature = sign_eip712_management(
        eth_private_key, "ApproveBuilder", type_fields, message
    )
    params["signature"] = signature

    print(f"  POST {BASE_URL}/fapi/v3/approveBuilder")
    print(f"  Builder: {builder_address}")
    print(f"  MaxFeeRate: {max_fee_rate}")

    resp = await client.post(f"{BASE_URL}/fapi/v3/approveBuilder", params=params)
    result = resp.json()
    print(f"  Response [{resp.status_code}]: {json.dumps(result, indent=2)}")
    return result


async def check_agents(
    client: httpx.AsyncClient,
    user_address: str,
) -> Dict[str, Any]:
    """GET /fapi/v3/agent - list authorized agents."""
    resp = await client.get(
        f"{BASE_URL}/fapi/v3/agent",
        params={"user": user_address},
    )
    return resp.json()


async def check_builders(
    client: httpx.AsyncClient,
    user_address: str,
) -> Dict[str, Any]:
    """GET /fapi/v3/builder - list approved builders."""
    resp = await client.get(
        f"{BASE_URL}/fapi/v3/builder",
        params={"user": user_address},
    )
    return resp.json()


async def main():
    eth_private_key = os.environ.get("ETH_PRIVATE_KEY")
    if not eth_private_key:
        print("ERROR: ETH_PRIVATE_KEY environment variable required.")
        print()
        print("This is the private key of your main Aster wallet:")
        print("  0xAf72Ae447aD3dcdcDfBAA01bB9c7b3C37a031aAf")
        print()
        print("Usage:")
        print(f"  ETH_PRIVATE_KEY=0x... python {sys.argv[0]}")
        sys.exit(1)

    # Derive user address from private key
    user_account = Account.from_key(eth_private_key)
    user_address = user_account.address

    # Agent address - generate or use existing
    agent_address = os.environ.get("ASTER_AGENT_ADDRESS")
    agent_private_key = os.environ.get("ASTER_AGENT_PRIVATE_KEY")

    if not agent_address:
        # Generate a fresh agent wallet
        agent_account = Account.create()
        agent_address = agent_account.address
        agent_private_key = agent_account.key.hex()
        generated = True
    else:
        generated = False

    builder_address = os.environ.get(
        "ASTER_CODE_BUILDER_ADDRESS",
        user_address,  # Default: builder is the user themselves
    )
    max_fee_rate = os.environ.get("ASTER_CODE_FEE_RATE", "0")

    print("=" * 60)
    print("  Aster Code - Agent & Builder Setup")
    print("=" * 60)
    print(f"  Base URL:          {BASE_URL}")
    print(f"  Network:           {'Testnet' if IS_TESTNET else 'Mainnet'}")
    print(f"  User Address:      {user_address}")
    print(f"  Agent Address:     {agent_address}")
    print(f"  Builder Address:   {builder_address}")
    print(f"  Max Fee Rate:      {max_fee_rate}")
    print()

    if generated:
        print("  NEW AGENT WALLET GENERATED!")
        print(f"  Agent Address:     {agent_address}")
        print(f"  Agent Private Key: {agent_private_key}")
        print()
        print("  SAVE THESE! Add to GCP Secret Manager:")
        print(f"    ASTER_AGENT_ADDRESS     = {agent_address}")
        print(f"    ASTER_AGENT_PRIVATE_KEY = {agent_private_key}")
        print()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Check existing agents
        print("[1/4] Checking existing agents...")
        try:
            agents = await check_agents(client, user_address)
            if agents.get("code") == 200 and agents.get("data"):
                print(f"  Found {len(agents['data'])} existing agent(s):")
                for a in agents["data"]:
                    print(f"    - {a.get('agentAddress')} ({a.get('agentName', 'unnamed')})")
            else:
                print(f"  No existing agents or response: {agents}")
        except Exception as e:
            print(f"  Could not check agents: {e}")

        # Step 2: Check existing builders
        print("\n[2/4] Checking existing builders...")
        try:
            builders = await check_builders(client, user_address)
            if builders.get("code") == 200 and builders.get("data"):
                print(f"  Found {len(builders['data'])} existing builder(s):")
                for b in builders["data"]:
                    print(f"    - {b.get('builderAddress')} (maxFeeRate={b.get('maxFeeRate')})")
            else:
                print(f"  No existing builders or response: {builders}")
        except Exception as e:
            print(f"  Could not check builders: {e}")

        # Step 3: Approve agent
        print("\n[3/4] Approving agent...")
        try:
            result = await approve_agent(
                client=client,
                user_address=user_address,
                eth_private_key=eth_private_key,
                agent_address=agent_address,
                agent_name="SapphireTrader",
                builder_address=builder_address,
                max_fee_rate=max_fee_rate,
            )
            if result.get("code") == 200:
                print("  Agent approved successfully!")
            else:
                print(f"  Agent approval response: {result}")
        except Exception as e:
            print(f"  ERROR approving agent: {e}")

        # Step 4: Approve builder
        print("\n[4/4] Approving builder...")
        try:
            result = await approve_builder(
                client=client,
                user_address=user_address,
                eth_private_key=eth_private_key,
                builder_address=builder_address,
                max_fee_rate=max_fee_rate,
            )
            if result.get("code") == 200:
                print("  Builder approved successfully!")
            else:
                print(f"  Builder approval response: {result}")
        except Exception as e:
            print(f"  ERROR approving builder: {e}")

    print()
    print("=" * 60)
    print("  Setup Complete")
    print("=" * 60)
    print()
    print("  Next steps:")
    print("  1. Save agent credentials to GCP Secret Manager")
    print("  2. Update Cloud Run env vars:")
    print(f"     ASTER_AGENT_ADDRESS={agent_address}")
    print(f"     ASTER_CODE_BUILDER_ADDRESS={builder_address}")
    print(f"     ASTER_CODE_FEE_RATE={max_fee_rate}")
    print("  3. The trading system will now use the agent for order signing")
    print("  4. Builder fees will be attributed automatically on filled orders")
    print()


if __name__ == "__main__":
    asyncio.run(main())
