"""Gemini OODA cache provenance coverage."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from lib.core.provenance import verify

ROOT = Path(__file__).resolve().parents[2]
INTERNAL = ROOT / "plugins" / "claw-sapphire" / "tools" / "internal" / "gemini_ooda.py"

_spec = importlib.util.spec_from_file_location("gemini_ooda_internal_for_provenance", INTERNAL)
assert _spec is not None and _spec.loader is not None
gemini_ooda = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gemini_ooda
_spec.loader.exec_module(gemini_ooda)


def test_live_cache_payload_is_provenance_stamped(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "gemini_ooda_cache"
    secrets_file = tmp_path / "secrets.env"
    secrets_file.write_text("GEMINI_API_KEY=test-key\n", encoding="utf-8")
    monkeypatch.setattr(gemini_ooda, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(gemini_ooda, "COUNTER_PATH", cache_dir / "counters.json")
    monkeypatch.setattr(gemini_ooda, "SECRETS_FILE", secrets_file)
    monkeypatch.setenv("SAPPHIRE_GEMINI_LIVE", "1")

    calls: list[dict[str, Any]] = []

    def fake_sdk(prompt: str, *, model: str, max_output_tokens: int, api_key: str) -> dict[str, Any]:
        calls.append({"prompt": prompt, "model": model, "api_key": api_key})
        return {
            "text": json.dumps(
                {
                    "observe": "No spend path is intact.",
                    "orient": "The request used the test SDK seam.",
                    "decide": "Keep live Gemini gated.",
                    "act": ["Inspect the provenance-stamped cache."],
                }
            ),
            "prompt_tokens": 11,
            "output_tokens": 17,
            "total_tokens": 28,
        }

    first = gemini_ooda.synthesize(
        topic="OODA cache provenance",
        context="safe dry-run-adjacent test context",
        mode="live",
        model=gemini_ooda.DEFAULT_MODEL,
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )

    cache_files = [path for path in cache_dir.glob("*.json") if path.name != "counters.json"]
    assert first["metadata"]["mode_actual"] == "live"
    assert len(calls) == 1
    assert len(cache_files) == 1

    cached = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert verify(cached) is True
    assert cached["ooda"]["observe"] == "No spend path is intact."
    assert cached["tokens"]["total_tokens"] == 28
    assert cached["provenance"]["generator"] == "plugins.claw_sapphire.gemini_ooda"
    assert cached["provenance"]["model"] == gemini_ooda.DEFAULT_MODEL
    assert cached["provenance"]["ttl_seconds"] == 600
    assert cached["provenance"]["metadata"] == {"cache": True, "mode": "live"}
    assert cached["provenance"]["prompt_hash"]

    second = gemini_ooda.synthesize(
        topic="OODA cache provenance",
        context="safe dry-run-adjacent test context",
        mode="live",
        model=gemini_ooda.DEFAULT_MODEL,
        max_output_tokens=128,
        ttl_seconds=600,
        sdk_call=fake_sdk,
    )

    assert second["metadata"]["cached"] is True
    assert len(calls) == 1
