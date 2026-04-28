"""Service wrapper around lib.correlator.

The daemon at :mod:`services.correlator.run` polls every configured
source every ``poll_interval_seconds`` (default 60s), runs the engine,
publishes ``signal.correlated`` events, and writes a daily JSONL with
a sibling provenance envelope.
"""
