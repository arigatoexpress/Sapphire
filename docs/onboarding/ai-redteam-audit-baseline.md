# AI Red-Team — Baseline Audit

*Written 2026-04-20 by a Claude agent as a pre-engagement baseline for the
researcher joining the Sapphire red-team scope. Not exhaustive. Intended as
a starting map, not a finished one.*

**Goal:** document what the sensitivity classifier and the model-integrity
scanner cover today, what they miss, and where the highest-leverage work
lies. Concrete regex / file / line references throughout.

Read [ai-redteam-scope.md](ai-redteam-scope.md) first for rules of engagement.

---

## 1. Sensitivity classifier (`plugins/claw-sapphire/lib/sensitivity_classifier.py`)

### 1.1 What it is

A four-group regex classifier (credentials · financial · personal ·
system_internals). Runs in microseconds (no LLM). Called by:

- `services/inference-proxy/app.py` — T4 (Kimi Cloud / Moonshot) gate
- `plugins/claw-sapphire/lib/router.py` — cloud task gate

Fail-safe (any match → block). Hits first match, returns reason string.

### 1.2 What it catches correctly

Verified against the built-in self-test at module bottom:
- Direct mentions of credential tokens in plaintext (`api_key`, `password`,
  `token=`, `bearer `)
- Tailscale CGNAT IPs (`100.*.*.*`)
- Env var names (`MOONSHOT_API_KEY`, `TELEGRAM_BOT_TOKEN`, etc.)
- LaunchAgent labels (`com.sapphire.*`)
- Dollar-denominated position sizes (`$12,500`, `$5k`)
- US phone + email regex
- SSN / "social security"

### 1.3 What it misses — ranked by priority

These are **primary research targets for the first-PR engagement**
([ai-redteam-scope.md](ai-redteam-scope.md) § 4.1). The corresponding
corpus in [`tests/fixtures/redteam/`](../../tests/fixtures/redteam/)
contains one probe per category, marked `xfail` so the friend's first PR
can flip them to passing as the classifier is hardened.

| # | Category | Example bypass | Current behavior |
|---|---|---|---|
| 1 | **Unicode homoglyph** | `"my аpi_key is sk-abc"` (Cyrillic `а` U+0430) | **passes** — regex expects Latin `a` |
| 2 | **Zero-width char** | `"api\u200bkey = sk-abc"` | **passes** — zero-width not stripped |
| 3 | **Leetspeak** | `"my p4ssword is hunter2"` | **passes** — no fuzzy match |
| 4 | **Base64-encoded secret** | `"the value is c2stYWJjMTIz"` (=`sk-abc123`) | **passes** — no base64 decode or detection |
| 5 | **Hex-encoded secret** | `"env: 6170695f6b6579=sk-abc"` (hex of `api_key`) | **passes** — no hex detect |
| 6 | **URL-encoded** | `"please use api%5fkey=sk-abc"` | **passes** — no URL-decode |
| 7 | **Semantic, not literal** | `"my OpenAI auth token starts with sk- and is 51 chars"` | **passes** — no keyword match |
| 8 | **String-split across turns** | turn 1: `"remember X = sk-abc"` → turn 2: `"that was my api key"` | turn 2 blocks; turn 1 content already shipped (see 1.4) |
| 9 | **Missing key format: AWS** | `"AKIAIOSFODNN7EXAMPLE"` | **passes** — `AKIA[A-Z0-9]{16}` not in pattern list |
| 10 | **Missing key format: Slack** | `"xoxb-1234-5678-abcdef"` | **passes** |
| 11 | **Missing key format: Stripe** | `"sk_live_abc123…"` | **passes** |
| 12 | **Missing key format: GitHub PAT** | `"ghp_xxxxxxxxxxxxxxxxxxxx"` | **passes** |
| 13 | **Missing key format: Telegram bot token** | `"123456789:AAE…"` (`\d+:[A-Za-z0-9_-]{35}`) | **passes** |
| 14 | **Raw JWT header** | `"eyJhbGciOiJIUzI1NiJ9…"` (no `token=` prefix) | **passes** — current regex requires `token[=:\s\"']` |
| 15 | **Raw PEM in message** | `"-----BEGIN OPENSSH PRIVATE KEY-----"` | catches via `private[_\-\s]?key` — **caught**, no action |

**Recommendation for the first PR:** pick 1–3 from the top of this list
(most exploitable: homoglyph + base64 + semantic). Each is roughly:
- Extend the pattern list with a new rule OR add a normalization pre-pass
- Add a regression test that would have failed before (see fixture below)
- Document the tradeoff in the patch (e.g., base64 detection may cause
  false positives on legitimate binary data in prompts)

### 1.4 Architectural observations (harder to fix in a first PR)

- **No normalization pass before matching.** Adding `unicodedata.normalize("NFKC", text)` + zero-width strip as a pre-pass would close #1, #2, and chunks of #7 at once. That's a more ambitious PR worth proposing.
- **No message-history scanning.** `is_sensitive()` iterates over a message list but each message is independently classified. A cross-turn leak like #8 is in scope but the classifier can't see it alone; the inference-proxy would need to concatenate-and-scan OR pass a rolling window.
- **No entropy-based "looks like a secret" fallback.** A high-entropy string of 20+ chars is probably a token regardless of surrounding context. Shannon-entropy probe over sliding windows is a standard anti-secrets technique worth considering.
- **No allow-list for public strings.** `p&l` in a published strategy post is blocked — the pattern is "fail safe" but fails closed in a way that blocks legitimate content. A published-corpus allow-list is a nice-to-have.

---

## 2. Model integrity monitor (`lib/security/model_monitor.py`)

### 2.1 What it is

Two separate responsibilities:

1. **Blob SHA-256 verification** against Ollama manifest (`_verify_blob`).
2. **Jinja2 / Modelfile backdoor scanner** with 7 pattern groups
   (`BACKDOOR_PATTERNS`, lines 84–134).

### 2.2 What it catches correctly

- Tampered blobs (SHA-256 mismatch vs. manifest)
- Missing blobs (referenced by manifest but not on disk)
- Literal jailbreak strings ("ignore all previous instructions", "you are
  now DAN")
- Shell-exec Jinja2 patterns (`os.system`, backticks, `__import__`)
- Exfil via `curl`, `requests.get`, `urllib.request`

### 2.3 What it misses — ranked by priority

| # | Category | Example | Current behavior |
|---|---|---|---|
| 1 | **Manifest tampering** | attacker replaces both blob and manifest with matching SHAs | **passes** — check asks "does blob match the local manifest?" not "does manifest match the signed upstream?" No sigstore/TUF chain. |
| 2 | **URL allow-list bypass** | `https://github.com.attacker.com/exfil` (subdomain trick) | **passes** — `(?!github\.com)` negative-lookahead fails at the `github.com.` prefix, so the *whole regex* doesn't match at all. The URL slips through unflagged. **Clean vuln; reproducible.** |
| 3 | **Path-traversal via allowed domain** | `https://github.com/attacker/exfil-proxy/raw/main/beacon.sh` | **passes** — legitimate github.com repo URLs aren't flagged; an attacker-owned repo serves as the C2. |
| 4 | **SSTI payload** | `{{ ''.__class__.__mro__[1].__subclasses__() }}` | **passes** — none of the 7 patterns match this classic Jinja2 SSTI. |
| 5 | **Module loading alternatives** | `runpy.run_module`, `importlib.import_module`, `pickle.loads`, `marshal.loads` | **passes** — shell-execution regex only catches `subprocess`, `os.system`, `exec`, `eval`, `__import__`. |
| 6 | **Non-HTTP exfil** | `socket.connect`, `ftplib`, `smtplib.SMTP().sendmail()` | **passes** — exfil regex is HTTP-only. |
| 7 | **URL-safe base64** | `_-` instead of `+/` in the base64 blob regex | **passes** — pattern is `[A-Za-z0-9+/]{80,}={0,2}` only. |
| 8 | **Sub-80-char base64** | 60–79 chars (room for a 40–60 byte payload) | **passes** — threshold is 80+. |
| 9 | **Creative jailbreak phrasings** | "forget your previous rules", "new system prompt:", "system override follows" | **passes** — regex only catches "ignore … previous" / "disregard … instructions" / "you are now DAN/jailbroken/unrestricted". |
| 10 | **Large-blob backdoors** | backdoor in a blob > 100 KB | **passes** — `_scan_all_templates` skips blobs >100 KB for speed. |

### 2.4 Architectural observations

- **No manifest signature chain.** The most impactful finding. Real
  defense is: pin Ollama registry's signing key, verify manifest signatures
  before trusting blobs. `sigstore` / `cosign` integration exists for
  container images; Ollama has a registry model similar enough to apply.
  This is a large PR but the single highest-leverage item in § 2.
- **No drift detection.** `scan()` is a snapshot. A baseline-vs-current
  comparator stored under `data/security/model_monitor_baselines.json`
  (with ctime + blob-digest) would alert on "a known-good model's manifest
  changed." Medium-size PR, big security win.
- **Score function is easy to game.** Capped penalties (`min(30,
  critical_alerts * 15)`) let an attacker tune the number of patterns
  that trigger to stay above a configured threshold. A multiplicative or
  at-least-one-critical-fail-open rule would harden this; a binary
  "template-scan contains *any* critical → model unusable" policy is
  arguably the right stance.
- **No scan of model weights for known malicious patterns.** Large-model
  Trojans (e.g., specific pattern→harmful-behavior triggers) aren't caught
  by any of the 7 patterns and wouldn't be even if the size limit were
  removed. Behavioral probes (run the model against a known-adversarial
  corpus and diff outputs vs. reference) is the real answer — out of scope
  for a regex scanner, in scope for a follow-on effort.

---

## 3. Suggested first-PR paths (stack-ranked)

A fresh researcher should pick **one** of these for a first contribution.
All are laptop-reproducible — no Tailscale or mesh access required.

1. **Jinja2 URL allow-list bypass (§ 2.3, row 2)** — ✨ *fastest win*.
   The fix is a 2-line regex tweak:
   `(?!(?:ollama\.com|github\.com|huggingface\.co)(?:/|$))` (anchor the
   allow-list) plus a regression test. Probably 20 minutes of work end
   to end. Great "first PR landed" momentum.
2. **Classifier homoglyph + zero-width normalization (§ 1.3 rows 1–2)** —
   ~1 day. Adds `unicodedata.normalize("NFKC", ...)` + zero-width strip
   pre-pass. Eliminates 2 bypasses, no regression risk on existing
   positive cases. Fixture already stubbed.
3. **Classifier missing-key-format rules (§ 1.3 rows 9–13)** — ~2 hours.
   Just five new regex lines, five test cases. Extends coverage to AWS /
   Slack / Stripe / GitHub / Telegram token shapes.
4. **Jinja2 SSTI + module-loader patterns (§ 2.3 rows 4–5)** — ~1 day.
   Expand the `shell_execution` pattern to cover `__class__`, `__mro__`,
   `__subclasses__`, `__bases__`, `pickle.loads`, `marshal.loads`,
   `runpy.run_*`. Add an SSTI regression corpus.
5. **Model-monitor manifest signature verification (§ 2.4 first bullet)**
   — ~1 week. Research-heavy. Needs to determine whether Ollama publishes
   signed manifests (likely not, as of today), so may require first
   building a local signing key + cosign-style layer. Ambitious but the
   single most valuable hardening work on the red-team roadmap.

---

## 4. Starter fixture

A corpus of ~20 probes covering categories from § 1.3 and § 2.3 lives at
[`tests/fixtures/redteam/`](../../tests/fixtures/redteam/). The probes are
already wired into `tests/unit/test_redteam_corpus.py` — probes that
currently get through unflagged are marked `xfail`. The researcher's first
PR should be **flipping one `xfail` to passing by hardening the
classifier / scanner**.

Run the corpus locally:

```bash
pytest tests/unit/test_redteam_corpus.py -v
# Expected: mix of passed + xfail + xpassed. Over time, the xfail count
# drops as the hardening ships.
```

---

*Drift watch: this doc was written 2026-04-20 against commit
`65a32ffa` (current HEAD of `claude/trusting-wescoff-0420b2`). If
`sensitivity_classifier.py` or `model_monitor.py` has changed since,
reconfirm every table row against the actual code before relying on the
findings.*
