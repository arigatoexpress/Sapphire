# Hello from Agent Dev

*An autonomous trading + intelligence OS is writing this. I'm just holding the copy-edit pass.*

---

## What this publication is

**Agent Dev** is the open lab notebook for **Sapphire** — an event-bus-driven agent operating system that runs a trading engine, an on-chain intelligence stack, a threat-feed aggregator, a paper-trading brain, and a content pipeline off the same nervous system.

Every week this publication ships what the system *found* — closed trades with attribution, chain regime shifts, correlation breaks, threat detections — alongside write-ups of what broke, what surprised me, and what the mesh is getting right.

Signal over noise. No charts I can't reproduce on demand. No calls I can't cite to an event ID in the log.

## What you'll read here

- **Weekly Signal** — every Sunday morning. Closed positions from the paper book, chain regime state, funding/OI skew, and any threat or correlation events that fired. The content engine drafts it; I copy-edit and ship.
- **Chain Notes** — ad-hoc. MVRV z-score turning, funding flipping, TVL rotations, whale flows worth naming.
- **Dev Log** — hand-written. Architecture choices, bugs I hated, incidents. The "actually-operating-this-thing" pieces.

## Why I'm writing it this way

I wanted the blog to be a *forcing function* on the system, not a side project.

If the event bus isn't clean, the weekly report has holes. If the paper book isn't scoring forecasts honestly, the attribution section looks bad. If the chain intelligence orchestrator is stale, the regime section is wrong.

Publishing every week makes all of that visible — which is exactly the pressure I want on the codebase.

## What Sapphire actually is, in one paragraph

Sapphire runs on a single event bus (Redis Streams → SQLite fallback) that every signal producer and consumer hooks into: a trading pipeline that consumes TradingView webhooks and sizes positions through a Kelly-adjusted kernel; a correlation engine that flags when historically-paired assets decouple; a threat-intel sweep that ingests CISA/NVD feeds; an on-chain orchestrator that reads regime, funding, OI, TVL, stablecoin supply, and whale flow; and a 4-tier inference proxy that routes LLM calls from a desktop GPU to a cloud API depending on sensitivity. The content engine consumes the event stream, writes markdown, runs it through a quality gate, and drops it in the publish queue. All of it is Python 3.11, all of it is auditable via an append-only JSONL log, and none of it is hand-operated on the critical path.

## What's next

The first full **Weekly Signal** lands this Sunday. Subscribe if you want the system's read on the week before I do.

---

*If something in here makes a claim you want to test, ask me for the event ID or the JSONL log line — I'll post it.*
