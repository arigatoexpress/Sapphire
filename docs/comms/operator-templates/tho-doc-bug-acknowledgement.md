---
name: THO Document Center bug — partner-reported acknowledgement
audience: Mark / Ben / Celeste — whichever partner reported the bug, plus the others CC'd
when_to_use: When a partner reports a Document Center / XFA fill / docs-package bug. Promises investigation, sets a fix-deploy expectation, does NOT promise a Cloud Run deploy time without operator review.
placeholders: ["{{first_name}}", "{{bug_short_description}}", "{{repro_acknowledgement}}", "{{expected_fix_window}}", "{{retest_customer_name}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# Re: {{bug_short_description}}

Hey {{first_name}},

Got it. {{repro_acknowledgement}}

This looks like a real bug in the doc-fill path, not a configuration thing on your end. I'm investigating now and aiming to have a fix in deploy-ready shape within {{expected_fix_window}}. I won't push the next Cloud Run revision without eyeballing the change first — once it's up, I'll let you know so you can re-test (use {{retest_customer_name}} or any fictional customer; please don't run the test against a real lead until I confirm).

If anyone else has hit the same thing recently, send me the customer name + roughly when, even if no error message — pattern data helps narrow it.

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: acknowledges the bug as real (validates the partner's report), commits to a window without committing to a deploy time, gives a clear "what to do next" (re-test with fictional customer), and asks for additional pattern data without making it homework.
- Common edits:
  - The {{expected_fix_window}} should be a real window — "today by EOD", "by Wednesday". Vague = unhelpful. If genuinely unsure, write "within 24-48 hours, will pin down and confirm by EOD today."
  - {{repro_acknowledgement}} examples: "Celeste reproduced the empty package on her end too — that helps." / "Joe Blo reproed for me locally."
- Tone calibration: warm but technical. The partners aren't engineers, but they're sharp; over-explaining patronizes them. The "please don't run the test against a real lead" line is non-negotiable — if you skip it, someone WILL run a fictional-customer fix against a real customer's docs, and that's a much worse problem than the original bug.
- Never promise the bug is "small" or "easy to fix" before you've found the cause. Common operator failure mode.
