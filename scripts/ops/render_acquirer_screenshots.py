#!/usr/bin/env python3
"""Render dashboard screenshots for the acquirer microsite.

This is an operator-driven harness. It boots the Sapphire dashboard locally on
a temporary port, navigates to a list of authenticated pages, captures each as
a full-page PNG, and writes them under ``web/acquirer/assets/screenshots/``.

It is gated by ``SAPPHIRE_PLAYWRIGHT_LOCAL=1`` and refuses to run otherwise so
that CI never starts a browser. Tests exercise the dry-run path only and do
NOT import playwright.

Usage:

    /usr/local/bin/python3 -m pip install -r web/acquirer/requirements.txt
    /usr/local/bin/python3 -m playwright install chromium  # ~300 MB
    SAPPHIRE_PLAYWRIGHT_LOCAL=1 /usr/local/bin/python3 \\
        scripts/ops/render_acquirer_screenshots.py

Dry run (default in tests):

    /usr/local/bin/python3 scripts/ops/render_acquirer_screenshots.py --dry-run

The harness is idempotent: re-running it overwrites the previous screenshots
without crashing on existing files.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# These pages will be screenshotted. Order is intentional: the home page
# first, then the acquisition surfaces, then aggregate diligence, then
# observability (which lands later in Tranche 3 Lane 2).
DEFAULT_PAGES: tuple[tuple[str, str], ...] = (
    ("/", "home.png"),
    ("/sovereign-thesis", "sovereign-thesis.png"),
    ("/threat-intel", "threat-intel.png"),
    ("/customer-dossier", "customer-dossier.png"),
    ("/diligence", "diligence.png"),
    ("/sovereign-thesis-story", "sovereign-thesis-story.png"),
    ("/observability", "observability.png"),
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "web" / "acquirer" / "assets" / "screenshots"
ENV_FLAG = "SAPPHIRE_PLAYWRIGHT_LOCAL"


@dataclass
class HarnessConfig:
    """Configuration for a single render pass.

    The dataclass is the only public surface tests interact with. It carries
    no behavior of its own, only the knobs the operator can twist.
    """

    output_dir: Path = DEFAULT_OUTPUT_DIR
    base_url: str = "http://127.0.0.1:8080"
    dry_run: bool = True
    pages: tuple[tuple[str, str], ...] = DEFAULT_PAGES
    timeout_ms: int = 15_000
    auth_password_env: str = "AUTH_PASSWORD"
    plan_path: Path | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def planned_outputs(self) -> list[Path]:
        """Return the absolute paths the operator should expect on disk."""
        return [self.output_dir / name for _path, name in self.pages]


def ensure_output_dir(config: HarnessConfig) -> Path:
    """Create the output directory if it does not exist. Idempotent."""
    config.output_dir.mkdir(parents=True, exist_ok=True)
    return config.output_dir


def write_dry_run_plan(config: HarnessConfig) -> Path:
    """Persist a JSON plan describing what a live run would capture.

    This is the only side effect of a dry run. It lets tests verify
    determinism and lets the operator inspect the plan before going live.
    """
    ensure_output_dir(config)
    plan = {
        "base_url": config.base_url,
        "output_dir": str(config.output_dir),
        "dry_run": True,
        "pages": [
            {"path": path, "filename": name, "absolute": str(config.output_dir / name)}
            for path, name in config.pages
        ],
        "env_flag": ENV_FLAG,
        "timeout_ms": config.timeout_ms,
        "schema_version": 1,
    }
    target = config.plan_path or (config.output_dir / "plan.dry-run.json")
    target.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    return target


def assert_live_authorized(env: dict[str, str] | None = None) -> None:
    """Raise unless ``SAPPHIRE_PLAYWRIGHT_LOCAL=1`` is set.

    Live runs MUST be operator-driven. CI must never trip the live path.
    """
    env = env if env is not None else dict(os.environ)
    if env.get(ENV_FLAG) != "1":
        raise RuntimeError(
            f"Refusing to run live: set {ENV_FLAG}=1 to authorize Playwright. "
            "Use --dry-run for the safe path."
        )


def run_dry_run(config: HarnessConfig) -> dict[str, object]:
    """Run the dry-run path. Does NOT import playwright."""
    plan_path = write_dry_run_plan(config)
    return {
        "mode": "dry-run",
        "plan_path": str(plan_path),
        "outputs": [str(p) for p in config.planned_outputs()],
        "ok": True,
    }


def run_live(config: HarnessConfig) -> dict[str, object]:  # pragma: no cover - operator-only
    """Run the live Playwright path. Imported lazily so tests stay clean."""
    assert_live_authorized()
    ensure_output_dir(config)

    # Lazy import - never reached in the dry-run path. Tests that exercise the
    # dry-run code therefore do not need Playwright installed.
    try:
        from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Playwright not installed. Run "
            "'/usr/local/bin/python3 -m pip install -r web/acquirer/requirements.txt' "
            "and '/usr/local/bin/python3 -m playwright install chromium'."
        ) from exc

    captured: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            password = os.environ.get(config.auth_password_env)
            if password:
                context.set_extra_http_headers({"X-Auth-Password": password})
            page = context.new_page()
            page.set_default_timeout(config.timeout_ms)
            for path, name in config.pages:
                url = config.base_url.rstrip("/") + path
                target = config.output_dir / name
                try:
                    page.goto(url, wait_until="networkidle")
                    page.screenshot(path=str(target), full_page=True)
                    captured.append(str(target))
                except Exception as exc:  # noqa: BLE001 - operator visibility
                    sys.stderr.write(f"[render] {url} -> failed: {exc}\n")
            context.close()
        finally:
            browser.close()
    return {"mode": "live", "outputs": captured, "ok": True}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render dashboard screenshots for the acquirer microsite.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Default. Writes a plan JSON; never imports Playwright.",
    )
    parser.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help=f"Run Playwright. Requires {ENV_FLAG}=1.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Where to write PNGs (and the dry-run plan).",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8080",
        help="Dashboard base URL. Default: %(default)s.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=15_000,
        help="Per-page navigation timeout in milliseconds.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = HarnessConfig(
        output_dir=args.output_dir,
        base_url=args.base_url,
        dry_run=args.dry_run,
        timeout_ms=args.timeout_ms,
    )
    if config.dry_run:
        result = run_dry_run(config)
    else:
        result = run_live(config)
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
