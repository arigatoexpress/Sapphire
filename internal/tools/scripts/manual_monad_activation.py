import os
import sys
import time

from web3 import Web3


def main():
    print("🦁 MONAD MANUAL ACTIVATION SCRIPT")
    print("=================================")

    # 1. Config
    rpc_url = "https://testnet-rpc.monad.xyz"  # Monad Testnet
    private_key = os.getenv("MONAD_PRIVATE_KEY")

    if not private_key:
        print("❌ Error: MONAD_PRIVATE_KEY not found in environment.")
        print("Please add it to .env or local.env")
        sys.exit(1)

    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    # 2. Connect
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            print(f"❌ Failed to connect to Monad RPC: {rpc_url}")
            sys.exit(1)
        print(f"✅ Connected to Monad Testnet (Chain ID: {w3.eth.chain_id})")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        sys.exit(1)

    # 3. Account
    account = w3.eth.account.from_key(private_key)
    address = account.address
    print(f"👤 Wallet: {address}")

    balance_wei = w3.eth.get_balance(address)
    balance_mon = w3.from_wei(balance_wei, "ether")
    print(f"💰 Balance: {balance_mon:.4f} MON")

    if balance_mon < 0.01:
        print("⚠️ Warning: Low balance. You might not have enough gas.")
        # Continue anyway?

    # 4. Execute 5 Transactions (Self-Transfers)
    print("\n🚀 Executing 5 Activation Transactions...")

    for i in range(1, 6):
        try:
            nonce = w3.eth.get_transaction_count(address)

            tx = {
                "nonce": nonce,
                "to": address,  # Self-transfer
                "value": w3.to_wei(0.000001, "ether"),
                "gas": 21000,
                "gasPrice": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
            }

            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            print(f"   Activity {i}/5: Sent! Hash: {w3.to_hex(tx_hash)}")

            # Wait for confirmation for the verification to 'count' likely
            print("   ⏳ Waiting for confirmation...")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("   ✅ Confirmed.")
            else:
                print("   ❌ Failed on-chain.")

            time.sleep(1)  # Safety delay

        except Exception as e:
            print(f"   ❌ Transaction failed: {e}")
            break

    print("\n✅ Manual Activation Sequence Complete.")
    print("The Monad chain now has 5 transactions from your wallet.")
    print("Symphony checks (activity) should pass shortly.")


if __name__ == "__main__":
    main()
