# Forge tests — `tests/forge/`

Solidity test suite for the on-chain contracts in `contracts/`. Currently
covers `SapphireSentinelRegistry.sol` (the non-custodial mandate +
payment-receipt anchor on Robinhood Chain testnet).

## Run locally

Prerequisites: [Foundry](https://book.getfoundry.sh/) (`curl -L
https://foundry.paradigm.xyz | bash && foundryup`).

```bash
# One-time: install forge-std into contracts/lib/ (gitignored)
forge install foundry-rs/forge-std@v1.9.4 --no-commit

# Build + test + gas report
forge build --sizes
forge test --gas-report -vvv

# Single test
forge test --match-test test_RegisterMandate_HappyPath_PersistsAndEmits -vvv

# Just the fuzz harness
forge test --match-test testFuzz -vvv
```

## CI

`.github/workflows/sentinel-contracts.yml` runs on every push/PR that
touches `contracts/`, `tests/forge/`, `foundry.toml`, `slither.config.json`,
or the workflow itself. It produces two downloadable artifacts:

- **`forge-results`** — full test output, gas report, and the compiled
  ABI/bytecode JSON.
- **`slither-results`** — Slither JSON + markdown checklist.

Slither is configured to fail the job on HIGH or MEDIUM severity findings
via `slither.config.json`.

## Adding a new test case

1. Add a function `test_<Subject>_<Behaviour>` to
   `SapphireSentinelRegistry.t.sol` (or a new `<Contract>.t.sol` file).
2. Use the existing `setUp()` / `_registerDefaultMandate()` helpers when you
   need a baseline mandate.
3. For event assertions, copy the event signature into the test contract
   and use `vm.expectEmit(true, true, true, true)` before the call.
4. For fuzz tests, prefix with `testFuzz_` and use `bound(...)` to keep the
   input inside the contract's domain.
5. Run `forge test --match-test <new_name> -vvv` until green, then commit.

## Files

| File | Purpose |
|---|---|
| `SapphireSentinelRegistry.t.sol` | 18 cases: ACL, replay protection, hash binding, spend cap, expiry, two-step operator transfer, view sentinels, fuzz harness. |
