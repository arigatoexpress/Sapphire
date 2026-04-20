# Sapphire OS — First-Week Checklist

A concrete day-by-day path for a new collaborator. Tuned for someone joining
with an AI / open-source model security focus, but the first three days
apply to any new collaborator.

## Day 1 — Land the environment

- [ ] Clone the repo: `git clone https://github.com/arigatoexpress/Sapphire.git`
- [ ] Python 3.11 venv: `python3.11 -m venv .venv && source .venv/bin/activate`
- [ ] Install: `pip install -e '.[dev]'`
- [ ] Hooks: `make install-hooks`
- [ ] Doctor: `make doctor` — read every line
- [ ] Tests: `make test-all` — must be 1,967 passing (1,932 core + 35 plugin)
- [ ] Read [collaborator-pack.md](collaborator-pack.md) end-to-end
- [ ] Read [CLAUDE.md](../../CLAUDE.md) — the project map

**Done if:** local test suite passes and you can explain the 4-tier inference
proxy in two sentences.

## Day 2 — Read the security-critical code

- [ ] `lib/security/model_monitor.py` — Ollama blob fingerprint + Jinja2
      template scanner (7 patterns). Read the tests too.
- [ ] `plugins/claw-sapphire/lib/sensitivity_classifier.py` — regex gate
      for cloud-tier routing.
- [ ] `services/inference-proxy/app.py` — 4-tier routing + its own
      sensitivity gate.
- [ ] `plugins/claw-sapphire/lib/nemotron.py` — the client all agent tools
      hit.
- [ ] `lib/core/kill_switch.py`, `lib/core/confirmation_firewall.py`,
      `lib/core/heartbeat.py` — runtime safety.

**Done if:** you can draw the path a prompt takes from hermes-agent → proxy
→ model, and label every sensitivity-gate along it.

## Day 3 — Reproduce the inference stack locally

- [ ] Install Ollama: https://ollama.com
- [ ] `ollama pull nemotron-mini`
- [ ] `ollama pull hermes3:8b`
- [ ] Start the proxy locally: `make inference-proxy`
- [ ] Hit it with `curl`:
  ```bash
  curl -s http://127.0.0.1:11435/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -d '{"model":"fast","messages":[{"role":"user","content":"hello"}]}'
  ```
- [ ] Check `/metrics`: `curl http://127.0.0.1:11435/metrics`
- [ ] Read the [ai-redteam-scope.md](ai-redteam-scope.md) end-to-end.

**Done if:** you have a working local mirror of T3 (Mac Ollama) and can
route a prompt through the proxy.

## Day 4 — Pick a target and build a fixture

- [ ] Pick **one** attack surface from `ai-redteam-scope.md` § 4. Default
      recommendation: **§ 4.1 Sensitivity classifier bypass** — highest
      single-laptop impact.
- [ ] Create a test fixture directory: `tests/fixtures/redteam/<your-handle>/`.
- [ ] Write a `pytest` that calls the classifier on your adversarial
      corpus and asserts the expected behavior (pass → classifier caught
      it; fail → it slipped past).
- [ ] Run it: `pytest tests/fixtures/redteam/<your-handle>/ -v`.

**Done if:** you have at least one `xfail`-marked test that documents a
bypass, **or** one passing hardening test that would have failed before
your proposed fix.

## Day 5 — Open the first PR

- [ ] Branch: `git checkout -b <your-handle>/first-finding`
- [ ] Commit — small and atomic. Pre-commit will run ruff + gitleaks +
      bandit; don't bypass.
- [ ] Open the PR. Fill out `.github/pull_request_template.md` — the "Risk
      touch points" checklist matters. Check the `security` box under
      "Type".
- [ ] If the finding is sensitive (§ 5.2 of `ai-redteam-scope.md`), **do
      not open a PR yet.** Telegram-DM Ari first.
- [ ] Watch CI — `.github/workflows/ci.yml` runs ruff, tests, plugin tests,
      registry, gitleaks. Green means you're ready for review.

**Done if:** CI is green and the PR is awaiting review from @arigatoexpress
(per `CODEOWNERS`).

## After the first week

Recurring cadence that works well here:

- **Monday:** read the morning brief (the operator Telegrams it at 7 AM CT)
  to understand what the system is doing.
- **Tuesday–Thursday:** research / PR work.
- **Friday:** catch up on Dependabot PRs; run `make ci` locally before
  pushing.
- **Any day:** `make doctor` if something feels off.

Keep the scope tight — one finding per PR, one concern per issue. The
reviewers can move faster that way and you build a trail of small wins
rather than one sprawling mega-PR.
