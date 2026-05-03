"""Runbook smoke tests — verify first-3-commands shape across operational runbooks.

Tranche 7-C lift: every runbook below ≥ 3/5 in the 2026-04-29 coverage audit
must have a parseable command sequence at the top so a cold operator can start
triage without reading the whole document. This package parses the runbook
markdown and asserts the first three fenced bash blocks are syntactically valid
bash (via `bash -n`).

The test does NOT execute the commands — that would require a live mesh — but
syntactic validation catches typos, dangling line continuations, mismatched
quotes, and accidental Python pasted into a bash block. Full live drills are
tracked separately in each runbook's "Recovery" / "Common Failures" sections.
"""
