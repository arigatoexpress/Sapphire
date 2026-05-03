# Sapphire OS Dashboard — UX Overhaul Spec

**File:** `/Users/aribs/Code/Sapphire-brain/docs/UX_OVERHAUL_SPEC_2026-05-03.md`
**Target site:** https://sapphirealpha.xyz/
**Date:** 2026-05-03
**Constraints:** vanilla JS + inline SVG only (no React, no chart libs, no build pipeline). Inter + JetBrains Mono are loaded. Dark theme baseline (`--bg-0=#07090e` → `--text-1=#e8eef7`). Every panel must fail-safe to a non-broken empty state.

---

## TL;DR — Top 5 priority changes (80% of the perceived improvement)

| # | Change | Why it matters | Effort |
|---|--------|---------------|--------|
| **1** | **Sticky 3-row header** with sidebar-collapse and `Cmd-K` command palette as a true global jump (silos, KPIs, services, anchors, doc links) | The current header is one bland row + a regime banner. A keyboard-first shell makes the dashboard feel like a tool, not a status page. Linear/Vercel/Stripe all converge on this. | M |
| **2** | **Hero "Brain" panel rebuild** — the gauge becomes a *radial dial with three nested rings* (silo health · trading pulse · threat severity), narrative text is replaced with a *living ticker* of the top-3 priority actions as **clickable chips**, and the empty state ships a 3-line "this is what I'll synthesize once data arrives" preview | Right now the hero is mostly an empty arc + greyed text. Empty state is the marketing — it must teach what the brain *is*, not just say "synthesizing…". | M |
| **3** | **Silo grid → silo strip with live mini-sparklines + last-event line** (each card grows from a status pill into a "card spec": title, color bar, 24-bar 32px sparkline, last-event timestamp, hover-reveal of 3 deeper KPIs) | Cards are currently glanceable but information-thin. Stripe/Datadog pattern: every card = number + sparkline + trend. Adds density without sacrificing clarity. | S |
| **4** | **Density toggle + section anchors in a left rail** (Compact / Standard / Spacious; rail jumps to KPIs · Charts · VPIN · DSR · Threats · Services · Intel) | Current page is a 3,000 px scroll with no map. Bloomberg-style nav rail compresses the experience and makes the giant scroll readable. | S |
| **5** | **First-run "what is this?" pattern** — five inline `?` chips (one per section header) that drop a 60-word tooltip; one-time tour with three pinned hot-spots driven by `localStorage.sapphire_tour_v1` (no library, ~120 LOC of vanilla JS) | New visitors (investors, hackathon judges, your mom) bounce off the jargon. A `?` chip per section beats a modal walkthrough — it's progressive disclosure. | S |

---

## Current-state inventory (what was observed at https://sapphirealpha.xyz/)

Pulled raw from the live site (1 May 2026, ~2,058 lines, 76 KB single-page app, no build step). Verified structure:

- **Header** (`header.top`): brand mark + name + uppercase subtitle, status pill `health-strip`, time-range `<select>` (1h/24h/7d/30d/90d), `?` help button.
- **Banner** (`#regime-stale-banner`): yellow staleness warning, hidden by default.
- **Silo grid** (`.silo-grid`, 6 cards): THO / Threat / Wildfire / Intel / Regional / Hackathon. Each card = 3-px left accent bar + title + status pill + one-line description + "Open ↗" link. Hover lifts and recolors border.
- **Brain hero** (`section.brain-hero`): semicircle SVG gauge (`viewBox=0 0 200 120`), narrative paragraph, degraded list, action chips, "Persist + Run" + "Correlate" buttons.
- **KPI strip** (`#kpis`): 6 metric cards, JS-rendered, with sparklines.
- **Charts row** (`.cols-2`): 24h inference / 30d threat severity (both inline SVG).
- **VPIN panel**: scalar + tox label + sparkline.
- **Strategy quality** (DSR): chart + summary table.
- **Threat feed** (`#threats-feed`): list, loading-empty default.
- **Service health table** (`#services`): heartbeats + p50/p95.
- **Inference proxy table**: per-tier breakdown.
- **Intelligence pair**: market regime + Kronos predictions tables.
- **Footer**: api/healthz links, last-refresh timestamp, `?` keyboard hint.
- **Help modal**: `?`-triggered.

**What's working:** color-discriminated cards (one hue per silo), real BigQuery data, health gauge concept, footer endpoint exposure, `?` modal, fail-safe empty payloads.
**What's bland:** flat 1-column scroll, header is sparse and reactive (no jump links, no command palette), brain hero is more skeleton than content even at idle, silo cards have no live data (just pills), no density mode, six tables look identical, no left rail / minimap, regime banner is the only "alert" affordance.

---

## Design system decisions (locked)

### Palette (additive — keep all existing tokens)
```css
:root {
  /* — existing (do not change) — */
  --bg-0: #07090e;  --bg-1: #0b0e16;  --bg-2: #11151f;  --bg-3: #1a2030;
  --border: #1d2331;  --border-bright: #2c3548;
  --text-1: #e8eef7;  --text-2: #a8b3c7;  --text-3: #6c7891;  --text-4: #424d65;
  --accent: #4ea8ff;  --accent-2: #62ff40;
  --green: #3fb950;  --red: #f85149;  --yellow: #d29922;  --purple: #a371f7;  --orange: #ff7a00;

  /* — new additive tokens — */
  --bg-elevated: #141a26;          /* hover/focus surface, between bg-2 and bg-3 */
  --accent-soft: rgba(78,168,255,0.12);
  --accent-edge: rgba(78,168,255,0.32);
  --green-soft: rgba(63,185,80,0.10);
  --red-soft:   rgba(248,81,73,0.10);
  --yellow-soft:rgba(210,153,34,0.10);
  --grid-line:  rgba(168,179,199,0.06);   /* hairline grid for charts */
  --focus-ring: 0 0 0 2px rgba(78,168,255,0.55);
  --r-pill:     999px;
  --t-med:      200ms cubic-bezier(0.4, 0, 0.2, 1);
  --t-slow:     320ms cubic-bezier(0.4, 0, 0.2, 1);
  --shadow-3:   0 12px 32px rgba(0,0,0,0.5);
  --kbd-bg:     #1a2030;
}
```

Semantic rule (from datarocks.co.nz "Ultimate Dashboard Palette"): **never reuse a brand color as a status color**. We're already compliant — `--accent` (blue) is the brand, `--green/--red/--yellow` are status only. Keep that wall.

### Typography (Inter + JetBrains Mono, already loaded)
```
Brand title (Sapphire OS):     Inter 600, 17px, -0.015em
H1 (page title in palette):    Inter 600, 24px, -0.02em
Section header:                Inter 600, 12px UPPERCASE, 0.08em
Panel title (h2 in panels):    Inter 600, 13.5px, -0.005em
Body / table cell:             Inter 400, 13px, line-height 1.5
KPI value (big number):        Inter 600 tabular-nums, 28-32px, -0.02em
KPI label:                     Inter 500, 11px UPPERCASE, 0.07em, var(--text-3)
Mono (timestamps, ids, hex):   JetBrains Mono 400/500, 12px, ss feature "zero"
Kbd (inline shortcut):         JetBrains Mono 500, 11px, kbd-bg surface
```
Add `font-variant-numeric: tabular-nums;` on every `.mono` and KPI value class so digits don't jitter on refresh — a Stripe-dashboard staple.

### Spacing & radii
- Base 4-px grid. Card padding 18-20px. Section gap 28px.
- Radii: `--r-sm 6px` (pills, inputs), `--r 10px` (buttons, banners), `--r-lg 14px` (panels, cards).
- Sticky header height: 56 px.

---

## Section-by-section spec

Each subsection: **(a) current quote** · **(b) recommended change** · **(c) copy-pastable HTML/CSS/JS** · **(d) pattern citation**.

---

### 1. Header → "Operations shell"

**Current:** brand block + health pill + `<select>` + Help button on a single flex row, sits in normal flow (`padding: 8px 0 28px`).

**Recommended change:**
1. Make the header sticky (`position: sticky; top: 0; z-index: 50; backdrop-filter: blur(18px) saturate(160%);`).
2. Add a **command palette trigger** (Cmd-K / Ctrl-K) to the right of Help; show the literal `⌘K` shortcut on the chip. (Linear + Vercel + Notion + Figma all use Cmd-K — see [Mobbin: Command Palette](https://mobbin.com/glossary/command-palette).)
3. Add a **silo-status mini-strip** in the second header row — six 6-px dots colored per silo health, one per silo, hoverable for last-seen.
4. Keep the regime banner but slot it *inside the sticky header* so it doesn't shove content on toggle.

**Code:**

```html
<header class="top sticky">
  <div class="top-row1">
    <div class="brand"> <!-- existing brand block --> </div>
    <div class="header-right">
      <button class="cmdk-trigger" id="cmdk-trigger" type="button" aria-label="Open command palette">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
        <span>Jump to…</span>
        <kbd>⌘K</kbd>
      </button>
      <div class="health-strip" id="header-health">…</div>
      <select id="time-range-select" class="icon-btn">…</select>
      <button class="icon-btn" id="help-btn">Help</button>
    </div>
  </div>
  <div class="top-row2" id="silo-status-strip" aria-label="Silo health snapshot">
    <!-- JS injects 6 mini dots; data-silo="tho|threat|wildfire|intel|regional|hackathon" -->
  </div>
</header>
```

```css
header.top.sticky {
  position: sticky; top: 0; z-index: 50;
  background: rgba(7,9,14,0.78);
  backdrop-filter: blur(18px) saturate(160%);
  -webkit-backdrop-filter: blur(18px) saturate(160%);
  border-bottom: 1px solid var(--border);
  margin: 0 -32px 24px;  /* bleed beyond .wrap padding */
  padding: 12px 32px;
}
.top-row1 { display:flex; align-items:center; justify-content:space-between; gap:20px; flex-wrap:wrap; }
.top-row2 {
  display:flex; gap:8px; padding-top:10px; margin-top:10px;
  border-top: 1px dashed var(--border);
  font-size: 11px; color: var(--text-3);
  align-items: center;
}
.cmdk-trigger {
  display:inline-flex; align-items:center; gap:8px;
  padding: 7px 12px 7px 10px;
  background: var(--bg-1); color: var(--text-2);
  border: 1px solid var(--border); border-radius: var(--r-pill);
  font: 500 12px/1 'Inter', sans-serif; cursor:pointer;
  transition: border-color var(--t-fast), color var(--t-fast);
}
.cmdk-trigger:hover { border-color: var(--accent-edge); color: var(--text-1); }
.cmdk-trigger kbd {
  font: 500 10px/1 'JetBrains Mono', monospace;
  background: var(--kbd-bg); color: var(--text-2);
  padding: 3px 6px; border-radius: 4px;
  border: 1px solid var(--border-bright);
}
.silo-mini-dot {
  width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:6px;
  box-shadow: 0 0 0 2px var(--bg-0);  /* pop against blurred bg */
}
.silo-mini-pair { display:inline-flex; align-items:center; gap:4px; color: var(--text-3); font: 500 11px/1 'Inter'; padding: 0 8px; border-right: 1px solid var(--border); }
.silo-mini-pair:last-child { border-right:none; }
```

**Cmd-K palette (vanilla, ~140 LOC):** see [§ 9 Onboarding & shortcuts](#9-onboarding--shortcuts) below.

**Pattern citation:**
- Linear's command bar — [linear.app/method](https://linear.app/method) describes the keyboard-first philosophy.
- Vercel new dashboard sidebar+collapse — [Vercel changelog: "New dashboard redesign"](https://vercel.com/changelog/dashboard-navigation-redesign-rollout).
- Bloomberg's tabbed/customizable header model — [Bloomberg: "Innovating a modern icon"](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/).

---

### 2. Hero "Brain" panel → radial nested-ring + ticker

**Current quote (HTML):**
```html
<div class="brain-narrative empty" id="brain-narrative">Synthesizing cross-silo state…</div>
…
<div class="brain-actions-empty mono">No priority actions queued.</div>
```
A bare semicircle, gray text, no teaching of *what the brain does*.

**Recommended change:** Replace the single semicircle with **three concentric ring arcs** in a 200×200 SVG (silo-health · trading-pulse · threat-severity), put the composite score in the center, and put a *living ticker* (CSS `@keyframes` translateX) of priority-action chips below the gauge. The empty state becomes its own teach-moment: "Sapphire Brain combines THO uptime, signal toxicity, and threat severity into one health score. Once data flows, this panel will narrate degradations and propose actions."

**Code:**

```html
<section class="brain-hero v2" id="brain-hero">
  <div class="brain-hero-head">
    <div class="brain-hero-title">
      <svg class="brain-icon">…brain svg…</svg>
      <span>Sapphire Brain · cross-silo synthesis</span>
      <button class="info-chip" data-help="brain"><span>?</span></button>
    </div>
    <div class="brain-hero-actions">
      <span class="brain-meta mono" id="brain-meta">—</span>
      <button class="brain-btn primary" id="brain-persist-btn">▶ Persist + Run</button>
      <button class="brain-btn" id="brain-correlate-btn">⇄ Correlate</button>
    </div>
  </div>

  <div class="brain-hero-body">
    <!-- Triple-ring gauge -->
    <div class="brain-rings">
      <svg viewBox="0 0 200 200" class="brain-rings-svg" aria-hidden="true">
        <!-- track rings -->
        <circle cx="100" cy="100" r="86" fill="none" stroke="var(--border)" stroke-width="6"/>
        <circle cx="100" cy="100" r="70" fill="none" stroke="var(--border)" stroke-width="6"/>
        <circle cx="100" cy="100" r="54" fill="none" stroke="var(--border)" stroke-width="6"/>
        <!-- value rings (transform=-90deg so 12 o'clock is 0%) -->
        <circle id="ring-silo"   cx="100" cy="100" r="86" fill="none" stroke="var(--accent)"   stroke-width="6" stroke-linecap="round" pathLength="100" stroke-dasharray="0 100" transform="rotate(-90 100 100)"/>
        <circle id="ring-trade"  cx="100" cy="100" r="70" fill="none" stroke="var(--accent-2)" stroke-width="6" stroke-linecap="round" pathLength="100" stroke-dasharray="0 100" transform="rotate(-90 100 100)"/>
        <circle id="ring-threat" cx="100" cy="100" r="54" fill="none" stroke="var(--red)"      stroke-width="6" stroke-linecap="round" pathLength="100" stroke-dasharray="0 100" transform="rotate(-90 100 100)"/>
      </svg>
      <div class="brain-rings-center">
        <div class="brain-score mono" id="brain-score">—</div>
        <div class="brain-score-lbl">composite</div>
      </div>
      <ul class="brain-rings-legend">
        <li><span class="dot" style="background:var(--accent)"></span>Silo health <em id="brain-pct-silo">—</em></li>
        <li><span class="dot" style="background:var(--accent-2)"></span>Trading pulse <em id="brain-pct-trade">—</em></li>
        <li><span class="dot" style="background:var(--red)"></span>Threat (inverted) <em id="brain-pct-threat">—</em></li>
      </ul>
    </div>

    <!-- Right: narrative + actions ticker -->
    <div class="brain-content">
      <div class="brain-narrative" id="brain-narrative">
        <span class="empty-icon">◌</span>
        <strong>Synthesizing cross-silo state…</strong>
        <p class="empty-teach">When data arrives, this panel will narrate the lowest health score, list degraded services, and propose three priority actions you can launch in one click.</p>
      </div>
      <div class="ticker-wrap" id="brain-ticker">
        <div class="ticker-track">
          <span class="ticker-chip empty">No priority actions yet.</span>
        </div>
      </div>
    </div>
  </div>
</section>
```

```css
.brain-hero.v2 .brain-hero-body { display:grid; grid-template-columns: 240px 1fr; gap: 28px; align-items:center; }
.brain-rings { position: relative; width: 240px; height: 240px; }
.brain-rings-svg { width: 200px; height: 200px; display:block; margin: 0 auto; }
.brain-rings-svg circle { transition: stroke-dasharray var(--t-slow); }
.brain-rings-center {
  position: absolute; inset: 0; display:grid; place-items:center; pointer-events:none;
}
.brain-score { font: 600 36px/1 'Inter'; letter-spacing: -0.02em; color: var(--text-1); }
.brain-score-lbl { font: 500 10px/1 'Inter'; text-transform:uppercase; letter-spacing:0.08em; color: var(--text-3); margin-top:4px; }
.brain-rings-legend { list-style:none; margin: 12px 0 0; padding: 0; display:flex; gap:14px; justify-content:center; flex-wrap:wrap; font-size: 11px; color: var(--text-2); }
.brain-rings-legend .dot { width:8px;height:8px;border-radius:50%; display:inline-block; margin-right:5px; vertical-align: 1px; }
.brain-rings-legend em { font-style:normal; color: var(--text-1); margin-left:4px; font-variant-numeric: tabular-nums; }

.brain-narrative { background: var(--bg-1); border: 1px solid var(--border); border-radius: var(--r); padding: 14px 16px; }
.brain-narrative .empty-icon { color: var(--text-3); margin-right: 8px; animation: pulse 1.6s ease-in-out infinite; }
.brain-narrative .empty-teach { margin: 8px 0 0; color: var(--text-3); font-size: 12px; }
@keyframes pulse { 0%,100%{opacity:0.4} 50%{opacity:1} }

.ticker-wrap { margin-top: 14px; overflow: hidden; mask-image: linear-gradient(90deg, transparent, #000 10%, #000 90%, transparent); }
.ticker-track { display:inline-flex; gap: 10px; animation: ticker 38s linear infinite; padding-right: 40px; }
.ticker-track:hover { animation-play-state: paused; }
.ticker-chip {
  display:inline-flex; align-items:center; gap:8px;
  padding: 8px 14px; background: var(--bg-2); border: 1px solid var(--border);
  border-radius: var(--r-pill); font-size: 12px; color: var(--text-2);
  white-space: nowrap; cursor: pointer; transition: all var(--t-fast);
}
.ticker-chip:hover { border-color: var(--accent); color: var(--text-1); transform: translateY(-1px); }
.ticker-chip.urgent { border-color: rgba(248,81,73,0.4); color: var(--red); }
.ticker-chip.empty { color: var(--text-3); }
@keyframes ticker { from{transform:translateX(0)} to{transform:translateX(-50%)} }
```

```js
// Render ring values (clamped 0-100). 'threat' is inverted because higher severity = worse.
function setBrainRings({silo, trade, threat}) {
  const set = (id, pct) => {
    const el = document.getElementById(id);
    if (!el) return;
    const v = Math.max(0, Math.min(100, pct ?? 0));
    el.setAttribute('stroke-dasharray', `${v} ${100 - v}`);
  };
  set('ring-silo',   silo);
  set('ring-trade',  trade);
  set('ring-threat', 100 - (threat ?? 0));   // invert: full ring = no threats
  document.getElementById('brain-pct-silo')   .textContent = silo   == null ? '—' : `${silo|0}%`;
  document.getElementById('brain-pct-trade')  .textContent = trade  == null ? '—' : `${trade|0}%`;
  document.getElementById('brain-pct-threat') .textContent = threat == null ? '—' : `${threat|0}%`;
  if (silo != null && trade != null && threat != null) {
    const composite = Math.round((silo*0.4 + trade*0.4 + (100-threat)*0.2));
    document.getElementById('brain-score').textContent = composite;
  }
}
```

**Pattern citation:**
- Stripe-style three-ring composite — Stripe's [dashboard basics](https://docs.stripe.com/dashboard/basics) uses concentric KPI cards (revenue / charges / payouts) where each ring conveys progress vs. target.
- Empty state as teaching surface — see [Carbon Design System: Empty states](https://carbondesignsystem.com/patterns/empty-states-pattern/) and Userpilot's "[Empty State in SaaS Applications](https://userpilot.com/blog/empty-state-saas/)" — "informational empty states explain why a screen is empty; action-oriented empty states guide users toward the next step."
- Ticker pattern — Bloomberg Terminal scrolling sparklines/headlines, see [Bloomberg: "How Bloomberg Terminal UX designers conceal complexity"](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/).

---

### 3. Silo grid → "Live silo strip"

**Current quote:**
```html
<a class="silo-card tho" …>
  <span class="accent-bar"></span>
  <div class="silo-head"><div class="silo-title">THO Operations</div><span class="silo-status unknown">…</span></div>
  <div class="silo-desc">Texas Home Outlet — CRM, document center, customer ops</div>
  <span class="silo-link">Open production console →</span>
</a>
```
Six near-identical cards with no live data — color-bar + title + pill + description.

**Recommended change:** every card grows a **mini sparkline** (24-bar, 32 px tall, color-matched to silo accent) and a **last-event line** in monospace (e.g., `2m ago · doc.created · cust 4912`). On hover, expand to reveal three deeper KPIs (e.g., for THO: customers / docs generated 24h / errors).

```html
<a class="silo-card tho v2" id="silo-tho" href="#" target="_blank" rel="noopener">
  <span class="accent-bar"></span>
  <div class="silo-head">
    <div class="silo-title">THO Operations</div>
    <span class="silo-status unknown" id="silo-tho-status">…</span>
  </div>
  <div class="silo-desc">Texas Home Outlet — CRM · documents · customer ops</div>
  <div class="silo-spark"><svg id="silo-tho-spark" viewBox="0 0 100 32" preserveAspectRatio="none" aria-hidden="true"></svg></div>
  <div class="silo-last mono" id="silo-tho-last">awaiting first heartbeat…</div>
  <div class="silo-deep" aria-hidden="true">
    <div><div class="kpi-label">Customers</div><div class="kpi-value mono" id="silo-tho-k1">—</div></div>
    <div><div class="kpi-label">Docs 24h</div><div class="kpi-value mono" id="silo-tho-k2">—</div></div>
    <div><div class="kpi-label">Errors</div><div class="kpi-value mono" id="silo-tho-k3">—</div></div>
  </div>
  <span class="silo-link">Open production console →</span>
</a>
```

```css
.silo-card.v2 { padding-bottom: 14px; }
.silo-spark { height: 32px; margin: 4px 0 2px; }
.silo-spark svg { width: 100%; height: 100%; display:block; }
.silo-last { font-size: 11px; color: var(--text-3); }
.silo-last.has-event { color: var(--text-2); }

.silo-deep {
  max-height: 0; overflow: hidden;
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
  transition: max-height var(--t-med), margin-top var(--t-med);
  margin-top: 0;
}
.silo-card.v2:hover .silo-deep,
.silo-card.v2:focus-visible .silo-deep { max-height: 80px; margin-top: 8px; }

.silo-deep .kpi-value { font-size: 16px; }
.silo-deep .kpi-label { font-size: 9px; }
```

```js
// 24-bar sparkline as bars (color-bar style, mirrors silo accent).
// data: array of numbers (length 1..N); color: CSS color string.
function renderSiloSpark(svgEl, data, color) {
  if (!svgEl || !Array.isArray(data) || !data.length) {
    svgEl.innerHTML = '<rect x="0" y="14" width="100" height="4" rx="2" fill="var(--border)"/>';
    return;
  }
  const max = Math.max(1, ...data);
  const w = 100 / data.length, gap = w * 0.18;
  const bars = data.map((v, i) => {
    const h = (v / max) * 28;
    const x = i * w + gap/2;
    return `<rect x="${x.toFixed(2)}" y="${(32 - h).toFixed(2)}" width="${(w - gap).toFixed(2)}" height="${h.toFixed(2)}" rx="0.5" fill="${color}" opacity="${0.4 + 0.6 * (v/max)}"/>`;
  }).join('');
  svgEl.innerHTML = bars;
}
// usage:
// renderSiloSpark(document.getElementById('silo-tho-spark'), siloData.tho.events_24h, 'var(--accent)');
```

**Pattern citation:**
- Card + sparkline + trend trio — Stripe pattern, "[Stripe MRR & Subscriptions Overview Dashboard](https://databox.com/dashboard-examples/stripe-mrr-subscription-overview)" and [Art of Styleframe: Dashboard Design Patterns 2026](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/) — "each card has a number, a trend indicator, and a sparkline."
- Hover-reveal advanced KPIs — progressive disclosure pattern, see [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/).

---

### 4. Section anchor rail (left side, sticky)

**Current state:** No left rail. Long scroll has no map.

**Recommended:** narrow 56-px sticky rail on `min-width: 1180px`, collapses on smaller. Vertical icon+label list with active-section highlighting (IntersectionObserver). On `< 1180 px`, becomes horizontal pill row directly below header.

```html
<aside class="section-rail" id="section-rail" aria-label="Page sections">
  <a href="#brain-hero" class="rail-item active"><span class="rail-icon">◉</span><span class="rail-lbl">Brain</span></a>
  <a href="#kpis"        class="rail-item"><span class="rail-icon">▤</span><span class="rail-lbl">KPIs</span></a>
  <a href="#charts"      class="rail-item"><span class="rail-icon">∿</span><span class="rail-lbl">Charts</span></a>
  <a href="#vpin"        class="rail-item"><span class="rail-icon">⚖</span><span class="rail-lbl">VPIN</span></a>
  <a href="#strategy-quality" class="rail-item"><span class="rail-icon">σ</span><span class="rail-lbl">DSR</span></a>
  <a href="#threats"     class="rail-item"><span class="rail-icon">!</span><span class="rail-lbl">Threats</span></a>
  <a href="#services"    class="rail-item"><span class="rail-icon">▥</span><span class="rail-lbl">Services</span></a>
  <a href="#predictions" class="rail-item"><span class="rail-icon">⌬</span><span class="rail-lbl">Intel</span></a>
</aside>
```

```css
.section-rail {
  position: fixed; left: 16px; top: 96px;
  display: flex; flex-direction: column; gap: 4px;
  padding: 6px; background: var(--bg-1);
  border: 1px solid var(--border); border-radius: var(--r);
  z-index: 30;
}
.rail-item {
  display:flex; flex-direction:column; align-items:center; gap:2px;
  padding: 8px 6px; min-width: 44px;
  text-decoration:none; color: var(--text-3);
  border-radius: var(--r-sm); font-size: 9px;
  letter-spacing: 0.06em; text-transform: uppercase;
  transition: all var(--t-fast);
}
.rail-item .rail-icon { font: 600 14px/1 'JetBrains Mono'; color: var(--text-3); }
.rail-item:hover { background: var(--bg-2); color: var(--text-1); }
.rail-item:hover .rail-icon { color: var(--accent); }
.rail-item.active { background: var(--accent-soft); color: var(--accent); }
.rail-item.active .rail-icon { color: var(--accent); }
@media (max-width: 1180px) { .section-rail { display:none; } }
```

```js
// Active-section highlighting via IntersectionObserver.
(function () {
  const rail = document.getElementById('section-rail');
  if (!rail) return;
  const links = Array.from(rail.querySelectorAll('.rail-item'));
  const targets = links.map(a => document.querySelector(a.getAttribute('href'))).filter(Boolean);
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (!e.isIntersecting) return;
      const id = '#' + e.target.id;
      links.forEach(a => a.classList.toggle('active', a.getAttribute('href') === id));
    });
  }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });
  targets.forEach(t => io.observe(t));
})();
```

**Pattern citation:**
- Sidebar + section-rail anchor — [Vercel new dashboard sidebar](https://vercel.com/changelog/dashboard-navigation-redesign-rollout); [Art of Styleframe](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/) — "sidebar navigation 240-280 px ... scales from 5 features to 50."
- F-shaped scan — [Palantir Foundry app design best practices](https://www.palantir.com/docs/foundry/workshop/application-design-best-practices) — "horizontal scanning from the top and left corner and vertical scanning down the left side."

---

### 5. KPI strip — denser cards with semantic deltas

**Current:** `<div class="kpi-grid" id="kpis"></div>` (6 cards rendered by JS).

**Recommended:** single template, but tighten:
- 28px tabular-nums big-number.
- Trend arrow + percent in semantic color (green up, red down, gray neutral). Tufte rule: no second visual.
- Sparkline 32 px tall using same `renderSiloSpark` function.
- Click-to-expand row that lifts a 90-day mini-line.

```html
<!-- Template injected by JS -->
<a class="kpi-card" href="#kpi-detail-inference">
  <div class="kpi-row">
    <span class="kpi-label">Inference calls 24h</span>
    <span class="kpi-delta up mono" aria-label="up 12.4 percent">▲ 12.4%</span>
  </div>
  <div class="kpi-value mono">14,221</div>
  <div class="kpi-spark"><svg viewBox="0 0 100 32" preserveAspectRatio="none"></svg></div>
</a>
```

```css
.kpi-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 28px; }
.kpi-card {
  display:block; padding: 14px 16px;
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: var(--r); text-decoration:none; color: inherit;
  transition: border-color var(--t-fast), background var(--t-fast);
}
.kpi-card:hover { border-color: var(--border-bright); background: var(--bg-2); }
.kpi-row { display:flex; justify-content:space-between; align-items:center; margin-bottom: 4px; }
.kpi-label { font: 500 10.5px/1 'Inter'; text-transform:uppercase; letter-spacing:0.08em; color: var(--text-3); }
.kpi-delta { font-size: 11px; font-variant-numeric: tabular-nums; }
.kpi-delta.up   { color: var(--green); }
.kpi-delta.down { color: var(--red); }
.kpi-delta.flat { color: var(--text-3); }
.kpi-value { font: 600 28px/1.1 'Inter', sans-serif; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; color: var(--text-1); margin-bottom: 6px; }
.kpi-spark { height: 32px; }
```

**Pattern citation:**
- Stripe metric-card composition (number + trend + one chart, never all three) — [docs.stripe.com/dashboard/basics](https://docs.stripe.com/dashboard/basics).
- Tufte data-ink ratio — [Art of Styleframe 2026](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/) — "every number shown should inform a decision or trigger an action."

---

### 6. Charts row — line chart + heatmap (not stacked-bar)

**Current:** two side-by-side panels (`#chart-inference` for 24h, `#chart-threats` for 30d), both inline SVG.

**Recommended:**
- Keep **line chart** for `inference proxy calls — last 24h` (bucketed continuous time-series — the canonical line-chart use case per Atlassian: heatmap guide).
- Switch threat severity from a generic chart to a **30-day × 4-level heatmap** (rows: critical/high/medium/low; cols: 30 days; cell intensity = count). Heatmaps remain readable when stacked bars get noisy ([Towards Data Science: Chart Wars](https://towardsdatascience.com/chart-wars-stacked-bar-chart-vs-heatmap-959423de6fee/)).
- Add **hairline grid** + Y-axis tick labels at 0/50/100% of max + hover crosshair.

```html
<div class="cols-2" id="charts">
  <div class="panel">
    <h2><span>Inference proxy calls — last 24h</span><button class="info-chip" data-help="inference">?</button></h2>
    <div class="chart-wrap"><svg id="chart-inference" viewBox="0 0 600 220" preserveAspectRatio="none"></svg></div>
    <div class="legend" id="chart-inference-legend"></div>
  </div>
  <div class="panel">
    <h2><span>Threat severity — last 30d</span><button class="info-chip" data-help="threats">?</button></h2>
    <div class="chart-wrap"><svg id="chart-threats-heatmap" viewBox="0 0 600 220"></svg></div>
    <div class="legend" id="chart-threats-legend"></div>
  </div>
</div>
```

```js
// Heatmap renderer for threat severity (rows = severities, cols = days)
// data: { critical:[...30], high:[...30], medium:[...30], low:[...30] }
function renderHeatmap(svgEl, data, opts = {}) {
  const W = 600, H = 220, padL = 80, padT = 18, padB = 28, padR = 12;
  const rows = ['critical', 'high', 'medium', 'low'];
  const cols = (data[rows[0]] || []).length;
  if (!cols) {
    svgEl.innerHTML = `<text x="${W/2}" y="${H/2}" text-anchor="middle" fill="var(--text-3)" font-family="Inter" font-size="12">no threat data yet</text>`;
    return;
  }
  const cellW = (W - padL - padR) / cols;
  const cellH = (H - padT - padB) / rows.length;
  const all = rows.flatMap(r => data[r] || []);
  const max = Math.max(1, ...all);
  const rowColor = { critical:'var(--red)', high:'#ff8a4c', medium:'var(--yellow)', low:'var(--accent)' };
  let html = '';
  rows.forEach((r, ri) => {
    html += `<text x="${padL - 8}" y="${padT + ri*cellH + cellH/2 + 4}" text-anchor="end" fill="var(--text-3)" font-family="Inter" font-size="10">${r}</text>`;
    (data[r] || []).forEach((v, ci) => {
      const intensity = Math.min(1, v / max);
      html += `<rect x="${padL + ci*cellW}" y="${padT + ri*cellH}" width="${cellW - 1}" height="${cellH - 1}" rx="1" fill="${rowColor[r]}" fill-opacity="${0.05 + intensity * 0.85}"><title>${r} · day ${ci+1}: ${v}</title></rect>`;
    });
  });
  // x-axis ticks every 5 days
  for (let d = 0; d <= cols; d += 5) {
    const x = padL + d * cellW;
    html += `<text x="${x}" y="${H - padB + 14}" text-anchor="middle" fill="var(--text-3)" font-family="JetBrains Mono" font-size="9">${cols - d}d</text>`;
  }
  svgEl.innerHTML = html;
}
```

**Pattern citation:**
- Line vs stacked-bar vs heatmap decision — [Towards Data Science: Chart Wars](https://towardsdatascience.com/chart-wars-stacked-bar-chart-vs-heatmap-959423de6fee/) and [Atlassian: Heatmap complete guide](https://www.atlassian.com/data/charts/heatmap-complete-guide).
- Grafana time-series + heatmap pairing — [Grafana docs: Heatmap visualization](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/heatmap/).

---

### 7. Threat feed — group by severity, collapse old

**Current quote:** `<div id="threats-feed"><div class="empty">loading live feed…</div></div>` — flat list once loaded.

**Recommended:** group rows into three sticky-headed sections (CRITICAL · HIGH · MEDIUM), collapse anything older than 7 days into a `Show 12 older →` accordion. Each row shows: severity pill · CVE ID (mono) · title · time-ago · source-link. Empty state names the three sources so the user learns where data comes from.

```html
<div class="panel" id="threats-panel">
  <h2>
    <span>Recent CISA KEV / NVD / MITRE records</span>
    <a href="…">JSON feed ↗</a>
  </h2>
  <div id="threats-feed">
    <div class="empty rich">
      <div class="empty-headline">No threats in window.</div>
      <div class="empty-body">Sapphire pulls from <strong>CISA KEV</strong>, <strong>NVD</strong>, and <strong>MITRE ATT&amp;CK</strong> every 4 hours. New entries will appear here grouped by severity.</div>
      <a class="empty-cta" href="…">Open raw feed ↗</a>
    </div>
  </div>
</div>
```

```css
.empty.rich { padding: 32px 24px; text-align:center; background: var(--bg-1); border-radius: var(--r); border: 1px dashed var(--border-bright); }
.empty-headline { font: 600 14px/1.4 'Inter'; color: var(--text-1); margin-bottom: 6px; }
.empty-body     { font-size: 12.5px; color: var(--text-3); max-width: 520px; margin: 0 auto 12px; }
.empty-cta { display: inline-block; padding: 6px 14px; background: var(--accent-soft); color: var(--accent); border-radius: var(--r-pill); text-decoration: none; font: 500 12px/1 'Inter'; border: 1px solid var(--accent-edge); }

.threat-group-h { display:flex; align-items:center; gap:10px; padding: 10px 0 6px; position: sticky; top: 56px; background: linear-gradient(var(--bg-1), var(--bg-1) 80%, transparent); }
.threat-row { display:grid; grid-template-columns: 80px 110px 1fr 80px 60px; gap: 12px; padding: 8px 4px; border-top: 1px solid var(--border); align-items:center; font-size: 12.5px; }
.threat-row:hover { background: var(--bg-2); }
```

**Pattern citation:**
- Empty-state-as-onboarding — [SaaSUI: Onboarding flows that convert 2026](https://www.saasui.design/blog/saas-onboarding-flows-that-actually-convert-2026) — "every empty state and first interaction has been designed to guide without announcing itself."
- Useronboard.com gallery: [empty states](https://www.useronboard.com/onboarding-ux-patterns/empty-states/).

---

### 8. Service health table — semantic row backgrounds

**Current:** plain HTML table with severity in a status column.

**Recommended:** add a semantic left-edge color stripe per row (3-px) and a tinted-background for rows where p95 > 1000 ms or status ≠ ok. This matches the "soft companion token" pattern in 2026 token systems (Adminator-style):

```css
#services tbody tr { position: relative; }
#services tbody tr td:first-child { border-left: 3px solid transparent; padding-left: 12px; }
#services tbody tr.s-ok       td:first-child { border-left-color: var(--green); }
#services tbody tr.s-degraded td:first-child { border-left-color: var(--yellow); }
#services tbody tr.s-degraded { background: var(--yellow-soft); }
#services tbody tr.s-down     td:first-child { border-left-color: var(--red); }
#services tbody tr.s-down     { background: var(--red-soft); }

td.num { font-variant-numeric: tabular-nums; }
td.p95-warn { color: var(--yellow); font-weight: 600; }
td.p95-bad  { color: var(--red); font-weight: 600; }
```

```js
function classifyService(row, latencyP95) {
  if (latencyP95 == null) return;
  const td = row.querySelector('td.p95-cell');
  if (latencyP95 > 2000)      td.classList.add('p95-bad');
  else if (latencyP95 > 1000) td.classList.add('p95-warn');
}
```

**Pattern citation:**
- Tinted row backgrounds for status — [datarocks.co.nz: Ultimate Dashboard Palette](https://www.datarocks.co.nz/post/design-matters-7-the-ultimate-dashboard-colour-palette-in-practice).

---

### 9. Onboarding & shortcuts

Three layered onboarding affordances — tour is **not** a modal walkthrough.

#### 9a. `?` info-chips next to every section title (always-on, ~20 LOC)

```html
<button class="info-chip" data-help="kpis" aria-label="What does production telemetry mean?">?</button>
```

```css
.info-chip {
  display: inline-grid; place-items:center;
  width: 18px; height: 18px;
  margin-left: 6px; padding: 0;
  background: var(--bg-2); color: var(--text-3);
  border: 1px solid var(--border); border-radius: 50%;
  font: 600 10px/1 'Inter'; cursor: pointer;
  transition: all var(--t-fast);
}
.info-chip:hover { background: var(--accent-soft); color: var(--accent); border-color: var(--accent-edge); }
```

```js
const HELP_TEXT = {
  brain: "Sapphire Brain combines silo health, trading pulse, and threat severity into one composite score. Ring 1 = silo uptime, Ring 2 = order-flow quality, Ring 3 = inverse threat severity.",
  kpis:  "Real BigQuery counts. Each KPI shows 24h delta and a 24-bar sparkline.",
  inference: "Hourly call volume to the local inference proxy. Stacked by tier (fast/balanced/deep).",
  threats: "30-day heatmap by severity. Source: CISA KEV + NVD + MITRE ATT&CK, refreshed every 4h.",
  vpin: "Volume-Synchronized Probability of Informed Trading (Easley, López de Prado, O'Hara 2012). >0.4 typically signals toxic flow.",
  dsr:  "Deflated Sharpe Ratio (Bailey & López de Prado 2014). Adjusts Sharpe for the number of trials and skew/kurtosis. >0.95 prob = robust.",
  services: "Heartbeats from each Sapphire service. p50/p95 are over the last 60 minutes.",
};
document.addEventListener('click', e => {
  const chip = e.target.closest('.info-chip');
  if (!chip) return;
  e.preventDefault();
  const key = chip.dataset.help;
  showPopover(chip, HELP_TEXT[key] || 'No help available.');
});

function showPopover(anchor, text) {
  document.querySelectorAll('.info-popover').forEach(p => p.remove());
  const r = anchor.getBoundingClientRect();
  const pop = document.createElement('div');
  pop.className = 'info-popover';
  pop.textContent = text;
  pop.style.left = `${Math.min(window.innerWidth - 320, r.left)}px`;
  pop.style.top  = `${r.bottom + window.scrollY + 8}px`;
  document.body.appendChild(pop);
  setTimeout(() => document.addEventListener('click', () => pop.remove(), { once:true }), 0);
}
```

```css
.info-popover {
  position: absolute; z-index: 100; max-width: 300px;
  padding: 10px 12px; background: var(--bg-3);
  border: 1px solid var(--border-bright); border-radius: var(--r-sm);
  box-shadow: var(--shadow-2); color: var(--text-2);
  font-size: 12px; line-height: 1.5;
}
```

#### 9b. First-run tour (3 stops, no library, ~80 LOC)

```js
const TOUR_KEY = 'sapphire_tour_v1';
const TOUR_STEPS = [
  { sel: '#brain-hero', title: 'Sapphire Brain', body: "Composite health score across all 6 silos. Press the ? next to any section for a 60-word primer." },
  { sel: '#cmdk-trigger', title: 'Cmd-K to jump anywhere', body: "Open the command palette to jump to any silo, KPI, or section in one keystroke." },
  { sel: '#section-rail .rail-item.active', title: 'Section rail', body: "The rail tracks where you are. Click any item to scroll to that section." },
];
function runTour() {
  if (localStorage.getItem(TOUR_KEY)) return;
  let i = 0;
  const overlay = document.createElement('div'); overlay.className = 'tour-overlay';
  const tip = document.createElement('div'); tip.className = 'tour-tip';
  document.body.append(overlay, tip);
  const render = () => {
    const step = TOUR_STEPS[i];
    const el = document.querySelector(step.sel);
    if (!el) { return next(); }
    const r = el.getBoundingClientRect();
    overlay.style.setProperty('--cx', `${r.left + r.width/2}px`);
    overlay.style.setProperty('--cy', `${r.top  + r.height/2 + window.scrollY}px`);
    overlay.style.setProperty('--rad', `${Math.max(r.width, r.height)/2 + 12}px`);
    tip.innerHTML = `<h4>${step.title}</h4><p>${step.body}</p>
      <div class="tour-foot">
        <span class="tour-prog">${i+1} / ${TOUR_STEPS.length}</span>
        <button class="tour-skip" type="button">Skip</button>
        <button class="tour-next" type="button">${i === TOUR_STEPS.length - 1 ? 'Done' : 'Next →'}</button>
      </div>`;
    tip.style.left = `${Math.min(window.innerWidth - 340, r.left)}px`;
    tip.style.top  = `${r.bottom + window.scrollY + 12}px`;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  const next = () => { i++; if (i >= TOUR_STEPS.length) end(); else render(); };
  const end = () => { localStorage.setItem(TOUR_KEY, '1'); overlay.remove(); tip.remove(); };
  tip.addEventListener('click', e => {
    if (e.target.classList.contains('tour-next')) next();
    if (e.target.classList.contains('tour-skip')) end();
  });
  render();
}
window.addEventListener('load', () => setTimeout(runTour, 800));
```

```css
.tour-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: radial-gradient(circle var(--rad, 80px) at var(--cx, 50%) calc(var(--cy, 50%) - var(--scrollY, 0px)), transparent 0, transparent 99%, rgba(7,9,14,0.78) 100%);
  pointer-events: none;
  transition: background var(--t-slow);
}
.tour-tip {
  position: absolute; z-index: 201; max-width: 320px;
  padding: 16px 18px; background: var(--bg-2);
  border: 1px solid var(--accent-edge); border-radius: var(--r);
  box-shadow: var(--shadow-3);
}
.tour-tip h4 { margin:0 0 6px; font: 600 13px/1.3 'Inter'; color: var(--text-1); }
.tour-tip p  { margin:0 0 12px; font: 400 12.5px/1.55 'Inter'; color: var(--text-2); }
.tour-foot { display:flex; align-items:center; gap:10px; }
.tour-prog { font: 500 11px/1 'JetBrains Mono'; color: var(--text-3); margin-right:auto; }
.tour-skip, .tour-next { padding: 6px 12px; border-radius: var(--r-sm); font: 500 12px/1 'Inter'; cursor:pointer; border: 1px solid var(--border-bright); }
.tour-skip { background: transparent; color: var(--text-3); }
.tour-next { background: var(--accent); color: #07090e; border-color: var(--accent); }
```

#### 9c. Cmd-K palette (vanilla, ~140 LOC)

```html
<div class="cmdk-backdrop" id="cmdk-backdrop" hidden>
  <div class="cmdk-modal" role="dialog" aria-label="Command palette">
    <div class="cmdk-input-row">
      <input class="cmdk-input" id="cmdk-input" type="text" placeholder="Jump to section, silo, or doc…" autocomplete="off"/>
      <kbd>Esc</kbd>
    </div>
    <div class="cmdk-list" id="cmdk-list" role="listbox"></div>
    <div class="cmdk-footer mono">
      <span><kbd>↑↓</kbd> navigate</span><span><kbd>↵</kbd> open</span><span><kbd>Esc</kbd> close</span>
    </div>
  </div>
</div>
```

```js
const CMDK_ITEMS = [
  { kind:'sec', label:'Sapphire Brain',    href:'#brain-hero',  hint:'Hero composite score' },
  { kind:'sec', label:'Production telemetry', href:'#kpis',     hint:'KPI strip' },
  { kind:'sec', label:'Charts (24h / 30d)',href:'#charts',     hint:'Inference + threats' },
  { kind:'sec', label:'VPIN — toxicity',    href:'#vpin',       hint:'Order-flow quality' },
  { kind:'sec', label:'Strategy DSR',       href:'#strategy-quality', hint:'Deflated Sharpe' },
  { kind:'sec', label:'Threat feed',        href:'#threats',    hint:'CISA / NVD / MITRE' },
  { kind:'sec', label:'Service health',     href:'#services',   hint:'Heartbeats + p95' },
  { kind:'sec', label:'Intelligence',       href:'#predictions',hint:'Regime + Kronos' },
  { kind:'silo',label:'Open THO',           href:'#silo-tho',   hint:'CRM + docs' },
  { kind:'silo',label:'Open Threat Intel',  href:'/api/threats/live', hint:'Live feed' },
  { kind:'silo',label:'Open Wildfire',      href:'https://wildfire.sapphirealpha.xyz/' },
  { kind:'silo',label:'Open Regional Intel',href:'https://regional.sapphirealpha.xyz/admin' },
  { kind:'silo',label:'Open Hackathon Lanes',href:'https://hack.sapphirealpha.xyz/' },
  { kind:'doc', label:'/healthz/',          href:'/healthz/' },
  { kind:'doc', label:'/api/silos/health',  href:'/api/silos/health' },
  { kind:'doc', label:'/api/timeseries/inference', href:'/api/timeseries/inference' },
];
let cmdkIdx = 0, cmdkFiltered = CMDK_ITEMS;

function openCmdk() {
  const bd = document.getElementById('cmdk-backdrop');
  bd.hidden = false;
  const i = document.getElementById('cmdk-input');
  i.value = ''; cmdkFiltered = CMDK_ITEMS; cmdkIdx = 0; renderCmdk();
  setTimeout(() => i.focus(), 0);
}
function closeCmdk() { document.getElementById('cmdk-backdrop').hidden = true; }
function renderCmdk() {
  const list = document.getElementById('cmdk-list');
  list.innerHTML = cmdkFiltered.map((item, idx) => `
    <div class="cmdk-item ${idx === cmdkIdx ? 'active' : ''}" role="option" data-idx="${idx}">
      <span class="cmdk-kind cmdk-kind-${item.kind}">${item.kind}</span>
      <span class="cmdk-label">${item.label}</span>
      <span class="cmdk-hint">${item.hint || ''}</span>
    </div>`).join('') || '<div class="cmdk-empty">No matches.</div>';
}
function activate(item) {
  if (!item) return;
  if (item.href.startsWith('#')) {
    document.querySelector(item.href)?.scrollIntoView({ behavior:'smooth', block:'start' });
  } else {
    window.open(item.href, '_blank', 'noopener');
  }
  closeCmdk();
}
document.addEventListener('keydown', e => {
  const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
  if (isCmdK) { e.preventDefault(); openCmdk(); return; }
  if (document.getElementById('cmdk-backdrop').hidden) return;
  if (e.key === 'Escape') closeCmdk();
  if (e.key === 'ArrowDown') { e.preventDefault(); cmdkIdx = Math.min(cmdkFiltered.length - 1, cmdkIdx + 1); renderCmdk(); }
  if (e.key === 'ArrowUp')   { e.preventDefault(); cmdkIdx = Math.max(0, cmdkIdx - 1); renderCmdk(); }
  if (e.key === 'Enter')     { e.preventDefault(); activate(cmdkFiltered[cmdkIdx]); }
});
document.getElementById('cmdk-input').addEventListener('input', e => {
  const q = e.target.value.toLowerCase().trim();
  cmdkFiltered = !q ? CMDK_ITEMS :
    CMDK_ITEMS.filter(it => (it.label + ' ' + (it.hint||'')).toLowerCase().includes(q));
  cmdkIdx = 0; renderCmdk();
});
document.getElementById('cmdk-trigger').addEventListener('click', openCmdk);
document.getElementById('cmdk-backdrop').addEventListener('click', e => {
  if (e.target === e.currentTarget) closeCmdk();
});
```

```css
.cmdk-backdrop { position: fixed; inset: 0; z-index: 300; background: rgba(7,9,14,0.6); backdrop-filter: blur(6px); display:grid; place-items:start center; padding-top: 14vh; }
.cmdk-modal { width: min(640px, 92vw); background: var(--bg-2); border: 1px solid var(--border-bright); border-radius: var(--r); box-shadow: var(--shadow-3); overflow:hidden; }
.cmdk-input-row { display:flex; align-items:center; gap:10px; padding: 14px 16px; border-bottom: 1px solid var(--border); }
.cmdk-input { flex:1; background:transparent; border:0; outline:none; color: var(--text-1); font: 500 15px/1 'Inter'; }
.cmdk-input::placeholder { color: var(--text-3); }
.cmdk-list { max-height: 50vh; overflow-y: auto; }
.cmdk-item { display: grid; grid-template-columns: 60px 1fr auto; gap: 12px; padding: 10px 16px; cursor:pointer; align-items:center; }
.cmdk-item.active { background: var(--accent-soft); }
.cmdk-kind { font: 500 9px/1 'JetBrains Mono'; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-3); padding: 3px 6px; background: var(--bg-3); border-radius: 3px; text-align: center; }
.cmdk-kind-silo { color: var(--accent-2); }
.cmdk-kind-doc  { color: var(--purple); }
.cmdk-label { font: 500 13px/1.4 'Inter'; color: var(--text-1); }
.cmdk-hint  { font: 400 11.5px/1 'JetBrains Mono'; color: var(--text-3); }
.cmdk-empty { padding: 24px; text-align: center; color: var(--text-3); font-size: 12px; }
.cmdk-footer { padding: 10px 16px; border-top: 1px solid var(--border); display:flex; gap: 16px; font-size: 11px; color: var(--text-3); }
.cmdk-footer kbd { background: var(--kbd-bg); padding: 2px 6px; border-radius: 3px; border: 1px solid var(--border-bright); margin-right: 4px; }
```

**Pattern citation:**
- Cmd-K palette in dashboards — [Mobbin: Command Palette](https://mobbin.com/glossary/command-palette); [Maggie Appleton: Command K Bars](https://maggieappleton.com/command-bar); [Superhuman: How to build a remarkable command palette](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/).
- 3-stop tour preferred over 8+ — [LogRocket: 7 best product tour JS libraries](https://blog.logrocket.com/best-product-tour-js-libraries-frontend-apps/); [UserOnboard onboarding patterns](https://www.useronboard.com/onboarding-ux-patterns/empty-states/).
- `?` info chip + popover (progressive disclosure) — [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/); [IxDF Progressive Disclosure 2026](https://ixdf.org/literature/topics/progressive-disclosure).

---

### 10. Footer — replace with quiet "system bar"

**Current quote:**
```html
<div class="footer">
  <div><span class="mono">tho-ai-agent.sapphire</span> · refreshed <span id="ts" class="mono">—</span> · press <kbd>?</kbd> for help</div>
  <div><a href="/healthz/">/healthz/</a> …</div>
</div>
```

**Recommended:** keep the same content, but render as a **fixed bottom bar** like Vercel's status row — 32 px tall, blurred, monospace.

```css
.footer.fixed {
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 40;
  height: 32px; padding: 0 32px;
  background: rgba(11,14,22,0.86); backdrop-filter: blur(12px);
  border-top: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  font: 500 11px/1 'JetBrains Mono'; color: var(--text-3);
}
.footer.fixed a { color: var(--text-3); margin-left: 14px; text-decoration: none; }
.footer.fixed a:hover { color: var(--accent); }
.wrap { padding-bottom: 64px; } /* clear footer */
```

---

### 11. Density toggle (top-right header dropdown, 1 line of state)

```html
<div class="density-toggle" id="density-toggle" role="radiogroup" aria-label="Layout density">
  <button class="dt-btn" data-density="compact" aria-checked="false">⊟</button>
  <button class="dt-btn active" data-density="standard" aria-checked="true">▦</button>
  <button class="dt-btn" data-density="spacious" aria-checked="false">⊞</button>
</div>
```

```css
.density-toggle { display:inline-flex; background: var(--bg-1); border: 1px solid var(--border); border-radius: var(--r-pill); overflow: hidden; }
.dt-btn { background:transparent; color:var(--text-3); border:0; padding: 6px 10px; cursor:pointer; font-size: 13px; }
.dt-btn.active { background: var(--accent-soft); color: var(--accent); }
:root[data-density="compact"]  { --kpi-pad: 10px 12px; --panel-pad: 14px; --section-gap: 18px; }
:root[data-density="standard"] { --kpi-pad: 14px 16px; --panel-pad: 18px; --section-gap: 28px; }
:root[data-density="spacious"] { --kpi-pad: 18px 20px; --panel-pad: 24px; --section-gap: 40px; }
.kpi-card { padding: var(--kpi-pad); }
.panel    { padding: var(--panel-pad); }
.section-h { margin: var(--section-gap) 0 12px; }
```

```js
document.querySelectorAll('.dt-btn').forEach(b => b.addEventListener('click', () => {
  document.documentElement.setAttribute('data-density', b.dataset.density);
  document.querySelectorAll('.dt-btn').forEach(x => x.classList.toggle('active', x === b));
  localStorage.setItem('sapphire_density', b.dataset.density);
}));
const stored = localStorage.getItem('sapphire_density');
if (stored) document.querySelector(`[data-density="${stored}"]`)?.click();
```

**Pattern citation:**
- Bloomberg-style density toggle — [Matt Ström-Awn: UI Density](https://mattstromawn.com/writing/ui-density/) — "concealing complexity is the secret to dealing with increasing complexity."

---

## Patterns we considered and rejected

- **Full sidebar (Vercel-style 240-px)** — too heavy for a single-tenant operations dashboard and competes with the section rail. We're keeping the rail narrow.
- **Heavy chart library (Chart.js / ECharts)** — violates the no-build-pipeline constraint. Our SVG renderers are ~30 LOC each.
- **Multi-page navigation** — a single scroll + Cmd-K + section rail is faster for the operator profile and matches Linear's keyboard-first ethos.
- **Confetti / motion-rich onboarding** — adds noise. Empty-state-as-marketing wins on long-term LTV.
- **Light theme** — out of scope; would invalidate every soft-color token. Dark stays.

---

## Implementation order (4 PRs, ~2 days each)

1. **PR-A — Shell:** sticky header + Cmd-K palette + section rail + density toggle + fixed footer. (6-8 hrs)
2. **PR-B — Hero rebuild:** triple-ring brain gauge + ticker + new empty state. (4-6 hrs)
3. **PR-C — Silo strip + KPI tightening:** mini-sparklines, hover-reveal, semantic delta arrows. (6 hrs)
4. **PR-D — Charts + heatmap + threat feed grouping + service-row tints + info-chips + tour:** the polish layer. (8 hrs)

Each PR ships with the existing fail-safe empty-payload contract (footer note: "the dashboard never 500s") preserved.

---

## Sources & citations (consolidated)

- Linear design — [LogRocket: Linear design trend](https://blog.logrocket.com/ux-design/linear-design/), [Tela Blog: Elegant Design of Linear.app](https://telablog.com/the-elegant-design-of-linear-app/), [Linear Method](https://linear.app/method)
- Vercel dashboard — [Vercel changelog: dashboard navigation redesign](https://vercel.com/changelog/dashboard-navigation-redesign-rollout), [Vercel new dashboard page](https://vercel.com/try/new-dashboard)
- Stripe dashboard — [Stripe dashboard basics docs](https://docs.stripe.com/dashboard/basics), [Databox: Stripe MRR overview](https://databox.com/dashboard-examples/stripe-mrr-subscription-overview)
- Datadog & Grafana — [Grafana docs: Heatmap visualization](https://grafana.com/docs/grafana/latest/visualizations/panels-visualizations/visualizations/heatmap/), [SigNoz: Datadog vs Grafana 2026](https://signoz.io/blog/datadog-vs-grafana/)
- Palantir Foundry — [Workshop application design best practices](https://www.palantir.com/docs/foundry/workshop/application-design-best-practices), [Foundry platform overview](https://www.palantir.com/docs/foundry/platform-overview/overview)
- Bloomberg Terminal — [Bloomberg: How Bloomberg Terminal UX designers conceal complexity](https://www.bloomberg.com/company/stories/how-bloomberg-terminal-ux-designers-conceal-complexity/), [Bloomberg: Innovating a modern icon](https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/), [Matt Ström-Awn: UI Density](https://mattstromawn.com/writing/ui-density/)
- Notion / Coda — [Zapier: Coda vs Notion 2026](https://zapier.com/blog/coda-vs-notion/)
- 2026 dashboard patterns — [Art of Styleframe: Dashboard Design Patterns 2026](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/)
- Empty states & onboarding — [SaaSUI: Onboarding flows that convert 2026](https://www.saasui.design/blog/saas-onboarding-flows-that-actually-convert-2026), [Carbon: Empty states pattern](https://carbondesignsystem.com/patterns/empty-states-pattern/), [Userpilot: Empty states in SaaS](https://userpilot.com/blog/empty-state-saas/), [UserOnboard: Empty states gallery](https://www.useronboard.com/onboarding-ux-patterns/empty-states/)
- Tour libraries — [LogRocket: 7 best product tour JS libraries](https://blog.logrocket.com/best-product-tour-js-libraries-frontend-apps/), [UserOrbit: Best open-source product tour libraries 2026](https://userorbit.com/blog/best-open-source-product-tour-libraries)
- Progressive disclosure — [NN/g: Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/), [IxDF: Progressive Disclosure 2026](https://ixdf.org/literature/topics/progressive-disclosure), [Lollypop: Power of Progressive Disclosure in SaaS UX](https://lollypop.design/blog/2025/may/progressive-disclosure/)
- Command palette — [Mobbin: Command Palette](https://mobbin.com/glossary/command-palette), [Maggie Appleton: Command K Bars](https://maggieappleton.com/command-bar), [Superhuman: How to build a remarkable command palette](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/)
- Sparklines (vanilla JS) — [GitHub: fnando/sparkline](https://github.com/fnando/sparkline), [GitHub: mitjafelicijan/sparklines](https://github.com/mitjafelicijan/sparklines), [chrisburnell.com: svg-sparkline](https://chrisburnell.com/svg-sparkline/)
- Charts / heatmaps — [Towards Data Science: Chart Wars (Stacked vs Heatmap)](https://towardsdatascience.com/chart-wars-stacked-bar-chart-vs-heatmap-959423de6fee/), [Atlassian: Heatmap complete guide](https://www.atlassian.com/data/charts/heatmap-complete-guide)
- Color & semantic tokens — [datarocks.co.nz: Ultimate Dashboard Palette](https://www.datarocks.co.nz/post/design-matters-7-the-ultimate-dashboard-colour-palette-in-practice), [Colorlib: Best dark admin templates 2026](https://colorlib.com/wp/dark-admin-dashboard-templates/)
- Typography pairing — [fontalternatives.com: Inter + JetBrains Mono pairing](https://fontalternatives.com/pairings/inter-and-jetbrains-mono/)

---

*End of spec — implementable as four sequential PRs against `apps/dashboard/` (or wherever `sapphirealpha.xyz` is served from). All code blocks are copy-pastable; no external dependencies introduced.*
