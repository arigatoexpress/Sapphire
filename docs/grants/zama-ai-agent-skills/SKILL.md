---
name: write-fhevm-contracts
description: Use when writing or reviewing Solidity contracts that use Zama's fhEVM (Fully Homomorphic Encryption Virtual Machine) for confidential on-chain computation. Triggers when the user mentions FHE, fhEVM, encrypted state, confidential transactions, or imports from `@fhevm/solidity` or `@zama-fhe/relayer-sdk`.
---

# Write fhEVM Contracts

This skill teaches you to write Solidity contracts on Zama's fhEVM correctly the first time. fhEVM lets you compute on encrypted data on-chain — values like balances, votes, bids, or basket weights stay ciphertext throughout the computation and only the parties an explicit ACL grants are able to decrypt the result.

The model that loads this skill should follow the patterns and footgun checks below before emitting any fhEVM Solidity. The self-check at the bottom is the final gate.

> Status: scaffold (Sapphire OS — Zama AI Agent Skills bounty submission). Authoritative library guidance: <https://docs.zama.ai/protocol>. Ari to polish before submission.

---

## 1. Encrypted types primer

fhEVM exposes encrypted analogues of Solidity's primitive types. Every encrypted type is a handle (32-byte ciphertext reference) — not the value itself — and operations on encrypted handles dispatch into the FHE coprocessor.

| Type        | Plaintext analogue | Typical use                                | Notes |
|-------------|-------------------|--------------------------------------------|-------|
| `ebool`     | `bool`            | conditional flags, vote tallies            | Cheapest. Prefer over `euint8` when 0/1 suffices. |
| `euint8`    | `uint8`           | small counters, percentages                | Smallest integer ct. Use for bounded ranges (≤255). |
| `euint16`   | `uint16`          | basket weights in basis points (0–10 000)  | Sweet spot for most DeFi-style weights. |
| `euint32`   | `uint32`          | timestamps, mid-size balances              | |
| `euint64`   | `uint64`          | token balances (most ERC-20 supplies fit)  | Default for confidential transfers. |
| `euint128`  | `uint128`         | large fixed-point math                     | More gas per op. |
| `euint256`  | `uint256`         | wei amounts, big aggregates                | Most expensive. Avoid unless required. |
| `eaddress`  | `address`         | encrypted recipient / counterparty         | Useful for sealed-bid markets. |

**Storage cost rule of thumb:** every encrypted handle stored in state costs roughly the same as a `uint256` slot, but every *operation* on it costs FHE-coprocessor gas (10×–100× a plaintext op depending on type and op). Pick the smallest type that fits your range. For the Sapphire Sentinel basket case, `euint16` weights in basis points (0–10000) is correct; `euint256` would be wasteful.

---

## 2. The 5 footguns to avoid

### Footgun 1 — `FHE.select` does not revert on bad conditions

```solidity
// WRONG: assumes select reverts if `cond` is malformed
ebool cond = FHE.gt(encryptedBalance, encryptedThreshold);
euint64 payout = FHE.select(cond, encryptedAmount, encryptedZero);
```

`FHE.select(cond, a, b)` is the encrypted ternary. If `cond` was constructed from inputs that were never decrypted to the expected values, you get the *wrong branch's value back silently* — there is no revert. The bug only surfaces when the recipient decrypts and sees zero (or worse, the wrong number).

**Fix:** treat every `FHE.select` as load-bearing. Make sure both branches are valid encrypted values (not just one), grant ACL on both with `FHE.allow`, and add a plaintext sanity check on the inputs that built `cond` (e.g. require `msg.value > 0` before even looking at the encrypted side).

### Footgun 2 — ACL discipline (every encrypted output needs `FHE.allow`)

```solidity
// WRONG: result is never readable by anyone
function compute() external returns (euint64) {
    euint64 result = FHE.add(_a, _b);
    return result; // recipient cannot decrypt
}
```

By default, only the contract that produced an encrypted handle can use it. To let *anyone else* (the user, another contract, a relayer) ever decrypt or operate on the value, you must explicitly grant via `FHE.allow(handle, address)` or `FHE.allowThis(handle)` for the contract itself.

**Fix:** after every meaningful computation, list every party that needs read access and call `FHE.allow` for each. Do this in the same transaction that produced the handle — granting later requires another tx and is easy to forget.

```solidity
function compute() external returns (euint64) {
    euint64 result = FHE.add(_a, _b);
    FHE.allowThis(result);          // contract can re-use it later
    FHE.allow(result, msg.sender);  // caller can decrypt it
    return result;
}
```

### Footgun 3 — Encrypted inputs require proof bytes

User-supplied encrypted inputs come as `(externalEuintXX handle, bytes inputProof)` — the proof attests that the ciphertext was produced by the relayer for *this contract* and *this caller*. Without verifying the proof, an attacker can replay another user's ciphertext.

```solidity
function deposit(externalEuint64 amountInput, bytes calldata inputProof) external {
    euint64 amount = FHE.fromExternal(amountInput, inputProof); // verifies + binds
    // ... use amount
}
```

**Fix:** never accept a raw `euintXX` from a user. Always take `(externalEuintXX, bytes)` and immediately funnel through `FHE.fromExternal(...)`. Reject any function that accepts `euintXX` directly from a user as the rule of thumb.

### Footgun 4 — Decryption is asynchronous

```solidity
// WRONG: this does not exist on fhEVM
uint64 plain = FHE.decrypt(encryptedValue);
```

There is no synchronous decrypt. To get a plaintext value to the EVM, you call `FHE.requestDecryption(handle, callbackSelector)` which returns a `requestId`. The Zama gateway/relayer runs the decrypt off-chain and calls back into your contract with the plaintext at the selector you specified.

**Fix:** structure any "now reveal it" code path as two functions:

```solidity
function reveal(euint64 handle) external returns (uint256 requestId) {
    requestId = FHE.requestDecryption(handle, this.onReveal.selector);
    // store requestId → user mapping so callback knows who to credit
}

function onReveal(uint256 requestId, uint64 plaintext) external {
    require(msg.sender == FHE.gateway(), "only gateway");
    // ... handle the now-plaintext value
}
```

### Footgun 5 — `ZamaEthereumConfig` inheritance is mandatory

Every contract that uses fhEVM must inherit the chain-specific config contract — not just import `@fhevm/solidity/lib/FHE.sol`. Without inheritance, `FHE.allow`, `FHE.fromExternal`, and the gateway call all silently misroute (or revert at runtime with confusing errors).

```solidity
import { FHE, euint64, externalEuint64 } from "@fhevm/solidity/lib/FHE.sol";
import { ZamaEthereumConfig } from "@fhevm/solidity/config/ZamaEthereumConfig.sol";

contract MyConfidentialThing is ZamaEthereumConfig {
    // ...
}
```

For Sepolia testnet use `ZamaEthereumConfig`; for other deployments check the docs for the correct config base.

---

## 3. Canonical contract patterns

> TODO (Ari to polish): expand each pattern below with full compilable Solidity. The skeletons here are enough to anchor the LLM; final submission should ship copy-pasteable contracts.

### 3a. Encrypted basket weights → encrypted aggregate

Use case: portfolio basket where individual weights are private but the aggregate (e.g. total weight = 100%) must be on-chain provable.

```solidity
// TODO: depositWeight(externalEuint16, bytes) accumulates into an euint32 sum
// TODO: getAggregate() returns euint32 with FHE.allow for the basket owner
```

### 3b. Encrypted bid → conditional reveal

Use case: sealed-bid auction. Bids stay encrypted until the auction closes, then the winning bid's amount is revealed via async decryption to the auctioneer only.

```solidity
// TODO: bid(externalEuint64, bytes) — store ciphertext per bidder
// TODO: closeAuction() — FHE.max over all bids, requestDecryption only on the winner
```

### 3c. Encrypted balance → confidential transfer

Use case: ERC-20-shaped token where balances and transfer amounts are encrypted (cf. Zama's `ConfidentialERC20` reference).

```solidity
// TODO: transfer(address to, externalEuint64, bytes)
// TODO: subtract from sender encrypted balance, add to recipient, FHE.allow for each
```

---

## 4. When to use FHE vs alternatives

> TODO (Ari to polish): turn this into a proper decision tree.

- **Use FHE** when the *computation itself* needs to happen on encrypted data and the result needs to be used on-chain (matched on-chain, paid against, etc.). Example: portfolio aggregate weights matter to a public risk policy but the per-asset weights must stay private.
- **Use ZK** when the inputs are plaintext to the prover but you need to prove a property to a verifier without revealing the inputs. Example: proving you have ≥ X of an asset without disclosing the balance.
- **Use a TEE** when the data is too large for FHE coprocessor gas or too latency-sensitive (FHE ops can be 100× slower). Example: ML inference on a multi-MB model.
- **Use a trusted relayer** when none of the above is justified by threat model. Example: a hosted price oracle where the customer just trusts the operator.

Composability beats purity. Real production systems combine FHE for the small confidential aggregate, ZK for proofs of provenance, and a TEE for heavy inference, with the on-chain contract anchoring commitments from all three.

---

## 5. Testing patterns

### Hardhat with mock keys

The fhEVM Hardhat plugin ships a mock coprocessor that runs entirely in-process — no Sepolia, no relayer roundtrip. This is what your CI should use.

```ts
// hardhat.config.ts
import "@fhevm/hardhat-plugin";

// test/MyConfidential.t.ts
import { ethers, fhevm } from "hardhat";

it("aggregates encrypted weights", async () => {
  const c = await ethers.deployContract("MyConfidential");
  const enc = await fhevm.createEncryptedInput(await c.getAddress(), signer.address);
  enc.add16(4000); // 40.00%
  const { handles, inputProof } = await enc.encrypt();

  await c.depositWeight(handles[0], inputProof);

  const aggregateHandle = await c.getAggregate();
  const plain = await fhevm.userDecryptEuint(aggregateHandle, c, signer);
  expect(plain).to.equal(4000n);
});
```

### Sepolia with the relayer

For end-to-end testing with the real coprocessor:
1. Deploy contract to Sepolia.
2. From the client (TS), use `@zama-fhe/relayer-sdk` to encrypt inputs against the contract address + signer.
3. Submit tx; the relayer attests and the gateway runs the FHE op.
4. For decryption, call `FHE.requestDecryption` and wait for the callback (≈30s on Sepolia at time of writing).

### Common assertions for encrypted equality

You can't `expect(handleA).to.equal(handleB)` — handles are different ciphertexts even for the same plaintext. Decrypt both sides under the test signer and compare plaintexts.

```ts
const plainA = await fhevm.userDecryptEuint(handleA, contract, signer);
const plainB = await fhevm.userDecryptEuint(handleB, contract, signer);
expect(plainA).to.equal(plainB);
```

---

## 6. Self-check checklist

Before declaring an fhEVM contract done, the LLM should verify all 10 of these:

1. The contract inherits `ZamaEthereumConfig` (or the right config for the target chain), not just imports `FHE`.
2. Every public/external function that takes encrypted inputs takes `(externalEuintXX, bytes inputProof)` — never raw `euintXX` from users.
3. Every input is funneled through `FHE.fromExternal(handle, inputProof)` before any FHE op.
4. Every encrypted handle that needs to be readable by the caller has `FHE.allow(handle, msg.sender)`.
5. Every encrypted handle that the contract will re-use across calls has `FHE.allowThis(handle)`.
6. There is no `FHE.decrypt(...)` synchronous call anywhere — all decryption goes through `FHE.requestDecryption` + callback.
7. Every `requestDecryption` callback verifies `msg.sender == FHE.gateway()`.
8. Encrypted type widths are the smallest that fit the range (e.g. basis points → `euint16`, balances → `euint64`, full uint → `euint256` only if needed).
9. `FHE.select` branches are both valid encrypted values, with ACL granted on both.
10. Tests exist that decrypt the final state under the expected reader and assert the plaintext — not just that the tx didn't revert.

If any check fails, fix before returning.
