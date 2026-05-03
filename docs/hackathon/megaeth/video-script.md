# Sapphire Sentinel · Multi-Chain — 60s Pitch Video Script

**Target:** 60s hard cap, aim for 55s.
**Recording:** 1080p, browser zoom 110%, no music, narrator voice (Ari).
**Submission targets:**
- MegaETH `awesome-megaeth-ai` — DeFi + Agents + Developer Tools categories
- Mega Mafia 2.0 application (Sapphire as agent operator + chain-health primitive)
- Cross-pollination into Arbitrum London Buildathon (chains 42161 + 10 share the gate)

The 60s cut is the listing-trailer cut. README has the long-form doc.

---

## [0:00] · Hook (5s)

**Voice:**
> "Most cross-chain alpha is approved before the chain it depends on
> is even checked. We thought that was insane."

**On screen:**
- Quick montage of three exchange screens with red flashing "DEPEG" / "RESERVE
  FROZEN" / "FUNDING +800%" text overlays.
- Pull-quote: **"Approve the trade only if the chain agrees."**

---

## [0:05] · The mechanism (15s)

**Voice:**
> "Sapphire Sentinel reads Aave V3 reserve health and GMX V2 funding-rate
> skew on Arbitrum One *before* approving any alpha-paid signal that
> references those protocols. Funding above five hundred percent annualized?
> BLOCK. Reserve frozen? BLOCK. Both work — chain disagrees with the alpha?
> We side with the chain."

**On screen:**

```python
$ python3 -c "from lib.hackathon.chain_health_gate import \
    evaluate_chain_health; \
    print(evaluate_chain_health('arbitrum', 'btc'))"

{
  "severity": "BLOCK",
  "reasons": [
    "gmx_funding_excessive: BTC funding 612% annualized",
    "aave_reserve_paused: USDC reserve flagged"
  ],
  "verdict": "REJECT_ORDER"
}
```

---

## [0:20] · The breadth (15s)

**Voice:**
> "Three chains. Sixty markets. Eleven priced live. GMX V2 reader on Arbitrum,
> Aave V3 read layer on Arbitrum and Optimism, Chainlink fallback for the
> markets Aave doesn't cover — BTC, SOL, AVAX, DOGE."

**On screen — three quick cuts (~5s each):**

1. **`perps_overview()`** terminal output — table of 60 GMX markets with
   funding rates color-coded.
2. **`reserve_health()`** terminal output — Aave V3 reserves with health
   factor + freeze flags.
3. **Chainlink price feed** — `eth_getCode` against the BTC/USD aggregator
   on Arbitrum (`0x6ce185860a4963106506C203335A2910413708e9`) — returns
   real bytecode.

---

## [0:35] · The footgun we caught (10s)

**Voice:**
> "GMX prices return at ten-to-the-thirty scale, not ten-to-the-eight like
> Chainlink. Most agent stacks get this wrong by 22 zeros. We have a unit
> test that fails if anyone tries to. Footgun, caught."

**On screen:**
- Code snippet from `lib/chains/arbitrum/contracts/gmx_price_adapter.py`:
  ```python
  # GMX V2 returns Price.Props with tokenAmount * 1e30 scale,
  # NOT 1e8 like Chainlink. This adapter normalizes to USD floats.
  GMX_PRICE_DECIMALS = 30
  ```
- Cut to test pass output:
  ```
  tests/unit/test_gmx_price_adapter.py::test_gmx_30_decimal_scale PASSED
  ```

---

## [0:45] · The wedge (10s)

**Voice:**
> "Agent operators don't need a faster chain. They need a chain they can
> trust to tell them when to *not* trade. Sentinel is the first chain-health
> primitive that ports across MegaETH, Arbitrum, and Optimism with one
> codebase."

**On screen:**
- Three-chain diagram: MegaETH (4326) ↔ Arbitrum (42161) ↔ Optimism (10),
  all feeding `evaluate_chain_health()` → BLOCK / WARN / OK verdict.
- Three PR badges: #546 (MegaETH), #557 (Arbitrum), #569 (Optimism).

---

## [0:55] · End card (5s)

**Voice:**
> "Sapphire Sentinel — multi-chain agent safety primitive."

**On screen (static end card, hold 5s):**

```
github.com/arigatoexpress/Sapphire
hack.sapphirealpha.xyz

GMX V2 Reader (Arbitrum One)
Aave V3 Pool (Arbitrum One)
Chainlink BTC/USD (Arbitrum One)

#MegaETH #Arbitrum #ChainHealth
```

---

## Director's notes

- **Lead with the meta-claim, not the architecture.** Most cross-chain
  alpha is auto-approved; we built the gate that says no. That's the hook.
- **The 1e30 footgun beat is the credibility moment.** Judges who've shipped
  on GMX V2 will catch it instantly. Judges who haven't will trust us more
  because we caught it.
- **Three-chain coverage is the moat.** Anyone can wrap one protocol in a
  weekend. Three chains, two protocol categories, one primitive — that's
  the year-of-engineering signal.
- **Cut to fit 60s.** If running long, drop the breadth section from 15s
  to 10s by skipping cut #3 (Chainlink fallback). The mechanism + footgun
  + wedge are non-negotiable.

---

## Recording sequence

1. Pre-flight: run `python3 -c "from lib.chains.arbitrum.contracts.gmx_v2 \
   import GMXReader; r = GMXReader(); print(r.perps_overview())"` to
   confirm RPC reachability and that `perps_overview()` returns 11 priced
   markets.
2. Pre-warm browser tabs for Arbiscan addresses so they render instantly.
3. Record take 1 of all 6 segments back to back.
4. Watch take 1. If 1e30 footgun beat fluffs, re-record that segment.
5. Record take 2 of full 60s as backup.
6. Edit, splice, add overlays.
7. Final cut ≤60s. Upload to YouTube unlisted. Capture URL → README +
   awesome-megaeth-ai PR description.
