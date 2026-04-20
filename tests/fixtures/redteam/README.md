# Red-team corpus

Adversarial probes against Sapphire's OSS-model hardening. Driven by
[`tests/unit/test_redteam_corpus.py`](../../unit/test_redteam_corpus.py).

## Files

- `sensitivity_classifier_probes.json` — probes against
  `plugins/claw-sapphire/lib/sensitivity_classifier.py`. Each probe
  declares an expected outcome (`sensitive` or `safe`). Probes currently
  misclassified by the live classifier are marked `"xfail": true` —
  they're the **concrete targets for hardening PRs**.
- `model_monitor_probes.json` — adversarial Jinja2 / Modelfile templates
  targeting `lib/security/model_monitor.py`'s `BACKDOOR_PATTERNS`. Same
  `xfail` convention.

## Running

```bash
pytest tests/unit/test_redteam_corpus.py -v
```

Expected shape of the output:

```
tests/unit/test_redteam_corpus.py::test_classifier[001_homoglyph] XFAIL
tests/unit/test_redteam_corpus.py::test_classifier[002_zero_width] XFAIL
tests/unit/test_redteam_corpus.py::test_classifier[010_aws_access_key] XFAIL
tests/unit/test_redteam_corpus.py::test_classifier[020_plaintext_password] PASSED
tests/unit/test_classifier_corpus.py::test_classifier[021_tailscale_ip] PASSED
...
```

- **PASSED** = classifier handled it correctly (known-good probe; regression protection).
- **XFAIL** = classifier currently misses it (expected failure; working as known-broken).
- **XPASSED** = classifier now *does* handle it. **If you see XPASSED, that
  means a probe got fixed — remove the `xfail: true` flag in the JSON to
  lock the fix in as a regression test.**

## Writing a first PR

1. Pick a probe from the ranked list in
   [docs/onboarding/ai-redteam-audit-baseline.md](../../../docs/onboarding/ai-redteam-audit-baseline.md).
2. Run the corpus — confirm the probe is `XFAIL`.
3. Extend the classifier (or scanner) to catch it.
4. Rerun — the probe should be `XPASSED`.
5. Flip `"xfail": true` → `false` in the JSON to convert the expected-fail
   into a locked-in regression test.
6. Open a PR (see [.github/pull_request_template.md](../../../.github/pull_request_template.md)).

## Adding a new probe

Append an object to the appropriate JSON:

```json
{
  "id": "031_my_new_bypass",
  "description": "one-line what this probes",
  "input": "the adversarial string / template",
  "expected": "sensitive" | "safe",
  "xfail": true,
  "category": "homoglyph" | "base64" | "semantic" | ...
}
```

Keep probes minimal — one bypass per probe. Don't bundle two techniques
into one input unless the combination is the interesting thing.

## Responsible use

These probes are intentional adversarial inputs. They stay in the repo
because (a) the classifier is open-source and no attacker gets new
capability from seeing them, and (b) the point of red-team fixtures is
that they're public — so every future hardening PR has a baseline to
protect. Do **not** commit probes that encode real credentials, real PII,
or real keys, even yours. Use obviously-fake values (`sk-abc123`,
`john@example.com`, `AKIA…EXAMPLE`).
