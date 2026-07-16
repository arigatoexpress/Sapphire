# Ralph Task: Improve error messages in the Sapphire stack

Scan the Python services in /Users/aribs/Code/Sapphire/services and lib/ for error messages that are confusing or leak internal details. Improve them to be:
1. Actionable for the operator.
2. Privacy-preserving (no tokens, addresses, or PII).
3. Consistent in format.

When complete, run `python3 -m pytest tests/unit -q` and ensure no regressions.

Output DONE when all changes are committed to a feature branch and tests pass.
