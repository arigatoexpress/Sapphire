# Plant wire — free-reign → `lib.grok.policy` (Claude checklist)

Paper-safe monorepo contract. **Do not place live orders from this doc.**

## Goal

Before any sole-writer path submits an order on designated rails, call:

```python
from lib.grok.policy import OrderProposal, evaluate_proposal

decision = evaluate_proposal(
    OrderProposal(
        symbol=sym,
        side=side,              # buy|sell
        rail=rail,              # rh_agentic|rh_l2|moss|paper
        asset_class=asset,      # equity|option|l2_token
        notional_usd=notional,
        open_positions_on_rail=n_open,
        contract_address=addr_or_none,
        moss_grant_hours_left=hours_or_none,
        is_defined_risk_option=is_long_premium_option,
    )
)
if not decision.allow:
    log_denial(decision.code, decision.reason)
    return  # NO_TRADE arm
# else continue existing confirmation_firewall / sole writer
```

## Scale-out (AXTI)

```python
from lib.grok.policy import evaluate_scale_out
d = evaluate_scale_out(entry_premium=entry, mark_premium=mark, remaining_qty=qty)
# AXTI_SCALE_OUT → close half / trail; AXTI_SL → close all
```

## Genome on close

```python
from lib.grok.genome import LessonBook, lesson_from_closed_trade
book = LessonBook.load(path)  # plant path for live lessons
book.append(lesson_from_closed_trade(
    trade_id=oid, symbol=sym, rail=rail,
    realized_pnl_usd=pnl, source="broker", tags=["live"],
))
book.save(path)
```

## Verify monorepo side anytime

```bash
make grok-streamline   # or:
python3 scripts/ops/grok_system_streamline.py --write --export --check
```

## Fences

Designated rails only · dens permanent · dust no re-buy · MOSS grant-gated · models propose only.
