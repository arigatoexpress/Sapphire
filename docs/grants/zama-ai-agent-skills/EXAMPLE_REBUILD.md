# Example: rebuilding `SapphireSentinelBasket.sol` with the SKILL

> Illustrative transcript — not a verbatim Claude Code session. Written to show what an LLM does at each decision point when the `write-fhevm-contracts` skill is loaded. Ari to replace with a real transcript before submitting.

**Setup:** the user has installed `write-fhevm-contracts` into `~/.claude/skills/`. They're working on Sapphire Sentinel and ask the LLM to build a contract that aggregates encrypted basket weights.

---

**user:**
> I need a Solidity contract called `SapphireSentinelBasket` for fhEVM. Users deposit encrypted portfolio weights (basis points, sum should equal 10000). Only the basket owner can read the running total. Sepolia is fine.

**LLM** *(skill triggers on "fhEVM" + "encrypted")*:

> I'll use the `write-fhevm-contracts` skill. Let me sketch a first draft, then run the self-check.
>
> First, type choice. The skill's section 1 table says basis points (0–10 000) fit in `euint16`. I was about to reach for `euint256` out of habit — `euint16` is 8× cheaper per FHE op.
>
> Here's a draft:
>
> ```solidity
> pragma solidity ^0.8.24;
> import { FHE, euint16, euint32 } from "@fhevm/solidity/lib/FHE.sol";
>
> contract SapphireSentinelBasket {
>     address public owner;
>     euint32 private _aggregate;
>
>     constructor() { owner = msg.sender; }
>
>     function depositWeight(euint16 weight) external {
>         _aggregate = FHE.add(_aggregate, weight);
>     }
>
>     function getAggregate() external view returns (euint32) {
>         return _aggregate;
>     }
> }
> ```

---

**LLM** *(self-check pass)*:

> Running the 10-item self-check:
>
> - Item 1 — inherits `ZamaEthereumConfig`? **NO.** I only imported `FHE`. Footgun 5 says this silently misroutes. Fix.
> - Item 2 — `(externalEuintXX, bytes inputProof)` for user inputs? **NO.** I took raw `euint16`. Footgun 3 says an attacker can replay another user's ciphertext. Fix.
> - Item 3 — `FHE.fromExternal(...)` before any FHE op? **NO** (consequence of 2). Fix.
> - Item 4 — `FHE.allow(handle, msg.sender)` for caller-readable handles? **NO.** Owner can't decrypt the aggregate. Fix.
> - Item 5 — `FHE.allowThis(handle)` for handles re-used across calls? **NO.** `_aggregate` is read by `FHE.add` next call — it needs `allowThis`. Fix.
> - Item 6 — no synchronous `FHE.decrypt`? **OK** (none used).
> - Item 7 — gateway-callback verifies `msg.sender == FHE.gateway()`? **N/A** (no callback yet — but the user asked for the owner to read the total, so I should add a reveal flow).
> - Item 8 — smallest type that fits range? **OK** (euint16 / euint32 chosen for the right reasons).
> - Item 9 — `FHE.select` branches both valid? **N/A** (no select used).
> - Item 10 — tests assert plaintext under expected reader? **N/A here** — but I'll write one alongside.
>
> Five items failed. Revising:

---

**LLM** *(revised draft)*:

```solidity
pragma solidity ^0.8.24;

import { FHE, euint16, euint32, externalEuint16 } from "@fhevm/solidity/lib/FHE.sol";
import { ZamaEthereumConfig } from "@fhevm/solidity/config/ZamaEthereumConfig.sol";

contract SapphireSentinelBasket is ZamaEthereumConfig {
    address public owner;
    euint32 private _aggregate;

    mapping(uint256 => address) private _revealRequester;

    constructor() {
        owner = msg.sender;
        _aggregate = FHE.asEuint32(0);
        FHE.allowThis(_aggregate);
    }

    function depositWeight(externalEuint16 weightInput, bytes calldata inputProof) external {
        euint16 weight = FHE.fromExternal(weightInput, inputProof);
        _aggregate = FHE.add(_aggregate, weight);
        FHE.allowThis(_aggregate);
        FHE.allow(_aggregate, owner);
    }

    function requestAggregateReveal() external returns (uint256 requestId) {
        require(msg.sender == owner, "only owner");
        requestId = FHE.requestDecryption(_aggregate, this.onAggregateRevealed.selector);
        _revealRequester[requestId] = msg.sender;
    }

    function onAggregateRevealed(uint256 requestId, uint32 plaintext) external {
        require(msg.sender == FHE.gateway(), "only gateway");
        address requester = _revealRequester[requestId];
        delete _revealRequester[requestId];
        emit AggregateRevealed(requester, plaintext);
    }

    event AggregateRevealed(address indexed owner, uint32 totalBasisPoints);
}
```

---

**LLM** *(re-running self-check)*:

> - Item 1 — `ZamaEthereumConfig` inherited. **OK.**
> - Item 2 — `(externalEuint16, bytes)` accepted, raw `euint16` rejected. **OK.**
> - Item 3 — `FHE.fromExternal(weightInput, inputProof)` before `FHE.add`. **OK.**
> - Item 4 — `FHE.allow(_aggregate, owner)` after every mutation. **OK.**
> - Item 5 — `FHE.allowThis(_aggregate)` in constructor + after every mutation. **OK.**
> - Item 6 — no synchronous decrypt. **OK.**
> - Item 7 — `onAggregateRevealed` requires `msg.sender == FHE.gateway()`. **OK.**
> - Item 8 — `euint16` for weights, `euint32` for the running sum (max 50 deposits × 10 000 = 500 000 > uint16). **OK.**
> - Item 9 — no select used. **OK.**
> - Item 10 — needs a test. Writing one:
>
> ```ts
> it("aggregates two encrypted weights to 10000", async () => {
>   const c = await ethers.deployContract("SapphireSentinelBasket");
>
>   for (const w of [4000, 6000]) {
>     const enc = await fhevm.createEncryptedInput(await c.getAddress(), owner.address);
>     enc.add16(w);
>     const { handles, inputProof } = await enc.encrypt();
>     await c.depositWeight(handles[0], inputProof);
>   }
>
>   const reqTx = await c.requestAggregateReveal();
>   const ev = await waitForEvent(c, "AggregateRevealed");
>   expect(ev.args.totalBasisPoints).to.equal(10000n);
> });
> ```
>
> Self-check passes. Returning to user.

---

**user:**
> Great. One more thing — what if I want to enforce that the aggregate stays under 10 000 bp on every deposit?

**LLM** *(skill section 2 footgun 1 fires)*:

> That requires `FHE.le` (encrypted ≤) and `FHE.select`. Quick warning from the skill:
>
> > Footgun 1: `FHE.select` does not revert on bad conditions. It silently returns the wrong branch's value.
>
> So I can't use `FHE.select` to "abort" — there's no such thing in FHE land. The honest options are:
>
> 1. **Plaintext sentinel + revert.** Track a *plaintext* `uint32 _committedTotalBp` alongside `_aggregate`, increment it from the *known plaintext bound* of `weight` (e.g. require the user to also submit `maxWeight` plaintext and pre-commit to it via signature), and revert in plaintext if it would exceed 10 000.
> 2. **Two-phase commit.** Accept all deposits, then on `requestAggregateReveal` the gateway-callback checks `plaintext <= 10000` and emits a "valid" or "invalid" event. The on-chain *invariant* is enforced after-the-fact, not at deposit time.
> 3. **`FHE.select` clamp.** Use `FHE.select(FHE.le(newSum, ten000), newSum, oldSum)` to silently clamp at the cap. Cheapest, but the user gets no signal that their deposit was rejected — fail-silent. Skill explicitly warns against this pattern.
>
> Option 1 is the right answer for an auditable basket. Want me to wire it in?

---

**Takeaway:** without the SKILL, the LLM's first draft missed 5 of the 10 footgun checks and would have shipped a contract that:
- silently misrouted FHE ops (no config inheritance)
- accepted replayable ciphertexts (no input proof)
- left the owner unable to decrypt the aggregate (no ACL)
- had no reveal path at all (would have prompted a follow-up to add a synchronous decrypt that doesn't exist)

The SKILL caught all five before the user saw the first draft, plus headed off the `FHE.select` silent-clamp footgun on the follow-up question.
