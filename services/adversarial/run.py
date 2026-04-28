#!/usr/bin/env python3
"""Run Sapphire's adversarial intelligence defense checks.

Default behavior is read-only: scan inputs, print a JSON report, and do not
emit telemetry or quarantine copies unless explicitly requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.security.adversarial_detectors import (  # noqa: E402
    BotPumpedChannelDetector,
    DetectorReport,
    FalseFlagThreatIntelDetector,
    OracleAnomalyDetector,
    PromptInjectionDetector,
    WashTradeDetector,
)
from lib.security.adversarial_telemetry import emit_report  # noqa: E402

DEFAULT_QUARANTINE_DIR = ROOT / "data" / "security" / "adversarial" / "quarantine"

DETECTOR_FACTORIES = {
    "trades": WashTradeDetector,
    "messages": BotPumpedChannelDetector,
    "oracle": OracleAnomalyDetector,
    "prompt": PromptInjectionDetector,
    "threat-intel": FalseFlagThreatIntelDetector,
}


def _now_key() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def quarantine_enabled() -> bool:
    return os.environ.get("SAPPHIRE_ADVERSARIAL_QUARANTINE", "").strip() == "1"


def load_records(path: str | Path) -> list[dict[str, Any] | str]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any] | str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
        return rows

    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        for key in ("records", "items", "trades", "messages", "observations", "reports", "prompts"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    raise ValueError(f"unsupported input JSON shape: {type(data).__name__}")


def scan_records(kind: str, records: list[dict[str, Any] | str]) -> DetectorReport:
    factory = DETECTOR_FACTORIES.get(kind)
    if factory is None:
        raise ValueError(f"unsupported kind: {kind}")
    detector = factory()
    return detector.analyze(records)  # type: ignore[arg-type]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def maybe_quarantine_report(
    report: DetectorReport,
    *,
    input_path: str | Path,
    quarantine_dir: str | Path | None = None,
) -> dict[str, Any]:
    enabled = quarantine_enabled()
    if not enabled or not report.findings:
        return {"enabled": enabled, "written": False, "path": ""}

    source = Path(input_path)
    out_dir = Path(quarantine_dir or DEFAULT_QUARANTINE_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{_now_key()}-{source.stem}-adversarial-report.json"
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "source_path": str(source),
        "source_sha256": _sha256(source),
        "mode": "report_copy_only",
        "upstream_mutated": False,
        "report": report.to_dict(),
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return {"enabled": True, "written": True, "path": str(out_path)}


def status() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "adversarial-defense",
        "detectors": sorted(DETECTOR_FACTORIES),
        "event_type": "adversarial.detection",
        "quarantine_enabled": quarantine_enabled(),
        "safety": {
            "mutates_upstream_signals_by_default": False,
            "trading_critical_path": False,
            "telegram_sends": False,
            "requires_secrets": False,
        },
    }


def scan_file(args: argparse.Namespace) -> dict[str, Any]:
    records = load_records(args.input)
    report = scan_records(args.kind, records)
    event_ids: list[Any] = []
    if args.emit:
        event_ids = emit_report(report, run_id=args.run_id or "", dry_run=False)
    quarantine = maybe_quarantine_report(
        report,
        input_path=args.input,
        quarantine_dir=args.quarantine_dir,
    )
    return {
        "ok": report.clean,
        "service": "adversarial-defense",
        "kind": args.kind,
        "input": str(args.input),
        "telemetry_emitted": len(event_ids),
        "quarantine": quarantine,
        "report": report.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status")

    scan = sub.add_parser("scan-file")
    scan.add_argument("--kind", required=True, choices=sorted(DETECTOR_FACTORIES))
    scan.add_argument("--input", required=True, type=Path)
    scan.add_argument("--emit", action="store_true", help="Emit adversarial.detection telemetry")
    scan.add_argument("--run-id", default="")
    scan.add_argument("--quarantine-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "status":
        result = status()
    else:
        result = scan_file(args)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
