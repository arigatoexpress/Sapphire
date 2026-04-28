#!/usr/bin/env python3
"""Validate Sapphire top-level layout against STRUCTURE.md."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRUCTURE = ROOT / "STRUCTURE.md"
DIR_START = "<!-- canonical-top-level-dirs:start -->"
DIR_END = "<!-- canonical-top-level-dirs:end -->"
FILE_START = "<!-- canonical-top-level-files:start -->"
FILE_END = "<!-- canonical-top-level-files:end -->"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="Base ref for added-path checks.")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    repo = args.repo_root.resolve()
    structure = repo / "STRUCTURE.md"
    allowed_dirs = parse_section(structure, DIR_START, DIR_END, strip_slash=True)
    allowed_files = parse_section(structure, FILE_START, FILE_END, strip_slash=False)

    errors: list[str] = []
    errors.extend(check_current_top_level(repo, allowed_dirs, allowed_files))
    errors.extend(check_added_top_level(repo, args.base, allowed_dirs, allowed_files))

    if errors:
        print("Repository structure check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Repository structure check passed.")
    return 0


def parse_section(path: Path, start: str, end: str, *, strip_slash: bool) -> set[str]:
    text = path.read_text(encoding="utf-8")
    try:
        body = text.split(start, 1)[1].split(end, 1)[0]
    except IndexError as exc:
        raise SystemExit(f"missing STRUCTURE.md marker: {start} or {end}") from exc

    items: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        token = stripped[2:].split(" ", 1)[0].strip("`")
        if strip_slash:
            token = token.rstrip("/")
        items.add(token)
    return items


def check_current_top_level(
    repo: Path, allowed_dirs: set[str], allowed_files: set[str]
) -> list[str]:
    errors: list[str] = []
    for child in sorted(repo.iterdir(), key=lambda p: p.name):
        if child.name == ".git":
            continue
        if is_git_ignored(repo, child):
            continue
        if child.is_dir() and child.name not in allowed_dirs:
            errors.append(f"top-level directory is undocumented in STRUCTURE.md: {child.name}/")
        if child.is_file() and child.name not in allowed_files:
            errors.append(f"top-level file is undocumented in STRUCTURE.md: {child.name}")
    return errors


def check_added_top_level(
    repo: Path, base: str, allowed_dirs: set[str], allowed_files: set[str]
) -> list[str]:
    merge_base = git(repo, ["merge-base", "HEAD", base]).strip()
    if not merge_base:
        return []
    diff = git(repo, ["diff", "--name-only", "--diff-filter=A", f"{merge_base}...HEAD"])
    errors: list[str] = []
    for raw in diff.splitlines():
        path = Path(raw)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            continue
        top = path.parts[0]
        if len(path.parts) == 1:
            if top not in allowed_files and top not in allowed_dirs:
                errors.append(f"new top-level path is not canonical: {top}")
        elif top not in allowed_dirs:
            errors.append(f"new file is under a non-canonical top-level directory: {raw}")
    return errors


def git(repo: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def is_git_ignored(repo: Path, path: Path) -> bool:
    rel = str(path.relative_to(repo))
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", rel],
        cwd=repo,
        check=False,
    )
    if result.returncode == 0:
        return True
    status = subprocess.run(
        ["git", "status", "--ignored", "--short", "--", rel],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return any(line.startswith("!!") for line in status.stdout.splitlines())


if __name__ == "__main__":
    raise SystemExit(main())
