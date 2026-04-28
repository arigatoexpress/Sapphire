# Sapphire OS — Brand Guidelines

The Sapphire OS visual identity exists for a single audience: corporate-development
and acquirer reviewers reading the diligence packet end-to-end. The system is
deliberately quiet, technical, and warm. It has more in common with the cover of
a NIST publication or a Bloomberg terminal layout than with a consumer-SaaS landing
page. Use this document when adding a slide, an OG card, a doc cover, or any
artifact that carries the Sapphire mark.

---

## 1. Palette

The palette is anchored in a deep sapphire base and lit by a two-step electric blue.
Every text-on-color combination has been validated against WCAG AA (4.5:1 for body,
3:1 for large display).

| Token         | Hex       | Role                                     | Pairs with                              |
|---------------|-----------|------------------------------------------|-----------------------------------------|
| `--bg`        | `#0b1220` | Primary background (deep sapphire)       | `--fg` (15.1:1), `--accent-2` (10.6:1)  |
| `--bg-elev`   | `#111a2e` | Elevated surface (cards, code blocks)    | `--fg` (13.4:1), `--fg-muted` (7.8:1)   |
| `--bg-card`   | `#14213d` | Card surface (slightly warmer elevation) | `--fg` (11.7:1), `--accent-2` (8.3:1)   |
| `--line`      | `#1f2a47` | Hairlines, dividers, subtle outlines     | Decorative; never carries text          |
| `--fg`        | `#e6ecff` | Primary foreground (off-white)           | All `--bg-*` tokens                     |
| `--fg-muted`  | `#aab4d4` | Secondary foreground (captions, meta)    | `--bg` (7.8:1), `--bg-elev` (7.0:1)     |
| `--accent`    | `#6da5ff` | Primary accent (links, focus, edges)     | `--bg` (7.0:1) at large size            |
| `--accent-2`  | `#8edcff` | High-contrast accent (display, emphasis) | `--bg` (10.6:1), `--bg-elev` (9.4:1)    |

### Reserved-use defaults
If a third party builds an external surface (deck cover, partner email banner) and
cannot consume the operator-rendered palette, fall back to:
- Deep sapphire `#0A2540` background
- Electric blue `#1565C0` accent
- Off-white `#F7F8FA` foreground
- Near-black `#040D14` text on light surfaces

---

## 2. Typography

The type stack is the system font stack — no font files ship with the microsite.
This keeps the site portable across static hosts and free of CDN dependencies.

```css
font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto,
             "Helvetica Neue", Arial, sans-serif;
```

| Tier        | Size  | Weight | Tracking   | Use                                      |
|-------------|-------|--------|------------|------------------------------------------|
| Display     | 56px  | 700    | -0.5px     | OG image headlines                       |
| H1          | 32px  | 600    | -0.16px    | Page hero ("Sapphire is a…")             |
| H2          | 24px  | 600    | -0.08px    | Section headings ("Capabilities")        |
| H3          | 17px  | 600    | 0          | Card titles                              |
| Body        | 16px  | 400    | 0          | Lede + body copy                         |
| Caption     | 13px  | 400    | 0.05em     | Card metric labels (uppercased)          |
| Mono        | inherit | 400  | 0          | Code, file paths, env-var names          |

Mono stack:

```css
font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
```

Numerals: prefer tabular figures where supported. Never letter-space body copy.
Display gestures (the "OS" suffix in the wordmark, OG taglines) accept up to
0.2em tracking when used as a deliberate visual element.

---

## 3. Logo usage

The Sapphire OS logo is a wordmark with a leading octahedral monogram. The
monogram is a stylized sapphire cross-section: an outer rhombus, an inner facet
fill at ~35% opacity, two cross-hairs, and a single center node. This silhouette
echoes the "correlation hub" of the hero illustration — the same shape appears in
both, by design.

**Files**
- `logo.svg` / `logo.png` — for light or neutral backgrounds.
- `logo-dark-bg.svg` / `logo-dark-bg.png` — for the deep-sapphire background.
- `favicon.svg` / `favicon.ico` — monogram only, 32×32.

**Sizing**
- Minimum on screen: 80px wide. Below that, use the favicon (monogram only).
- Default: 256×64 (the file's native viewBox).
- Maximum without redrawing: 512×128. Beyond that, use the SVG.

**Clearspace**
- Maintain at least one monogram-height of clear space on every side.
- Never place the wordmark over busy imagery; if the background varies, use the
  dark-bg logo on a `#0b1220`-tinted backdrop or place a `--bg-elev` block behind it.

**Don't**
- Don't recolor the wordmark outside the palette tokens.
- Don't separate the monogram from the wordmark except in favicon contexts.
- Don't outline the wordmark, drop-shadow it, or rotate the monogram.
- Don't typeset "Sapphire OS" in a different face — always use the SVG asset.

---

## 4. Iconography

Icon style is **stroke-only, monochrome, geometric**. We follow a Tabler-Icons /
Heroicons-outline cadence: 32×32 viewBox, 1.6px stroke, round caps, round joins,
two opacity stops (`1.0` and `0.35`) when a secondary accent is needed.

**Capability icons** live at `branding/capability-icons/` and use `currentColor`
for the stroke. Each card sets the color to `--accent-2` so the icon inherits
the accent treatment without any per-icon configuration.

When designing a new icon:
1. Start from a 24×24 conceptual frame; pad to 32×32 viewBox.
2. Snap every endpoint to a half-pixel grid for crisp rendering.
3. Prefer one strong gesture over decorative detail.
4. Never fill — use stroke + opacity for hierarchy.

---

## 5. OG image template

The Open-Graph card is the highest-leverage visual in the system: it's what
appears when an acquirer pastes the microsite URL into Slack, Notion, or an
email client. The current template (`og-image.png`, 1200×630) follows a fixed
composition:

- Sapphire-bg background with a subtle `--line` grid.
- Sapphire OS logo top-left, 60px from each edge.
- Headline "Sapphire OS / Multi-modal Intelligence Platform" centered-left, in
  display weight, with the second line in `--accent-2`.
- Subhead "Built for acquirers, ready for production diligence." in `--fg-muted`
  body weight directly below.
- Signal-flow accent: five thin curves from the left edge converging on a
  central monogram, echoing the hero illustration.
- Footer band with `ACQUIRER BRIEF` (`--accent-2`) and a versioned
  `PRODUCTION / DILIGENCE-READY / v0.1.0` tag in muted gray.

Future regenerations should keep the headline, subhead, and lockup positions
fixed. Only the version tag and the source labels in the signal-flow accent are
allowed to vary.

---

## 6. Voice and tone

The operator's voice is direct, technical, and warm.

- **Direct.** Lead with the claim, not the build-up. ("Sapphire is a
  production-graded autonomy control plane.") Avoid "we believe", "we think",
  "we're excited to announce".
- **Technical.** Use file paths, PR numbers, and env-flag names inline with body
  copy. Reviewers want to grep their way to the code. Examples:
  `lib/core/risk_kernel`, `SAPPHIRE_VERTEX_LIVE=1`, `PR #331`.
- **Warm.** When a constraint exists, name it and explain why. ("Live mode
  requires `SAPPHIRE_VERTEX_LIVE=1` plus secret-loaded credentials.") Never
  apologize for the safety posture; explain it.

Never use marketing superlatives ("revolutionary", "best-in-class",
"cutting-edge"). Never use exclamation points. Never use emoji in headers,
captions, or asset metadata.

---

## 7. Accessibility floor

Every artifact that carries the Sapphire mark must meet:
- WCAG AA contrast on every text-on-color combination (4.5:1 body, 3:1 large).
- A meaningful `<title>` and `<desc>` on every standalone SVG.
- An `aria-hidden="true"` on every decorative icon embedded in another component.
- A `noindex,nofollow` meta tag on any HTML page that hosts these assets while
  the acquirer review is in progress. (The microsite already enforces this.)

When in doubt, the accessibility floor wins over the visual gesture.
