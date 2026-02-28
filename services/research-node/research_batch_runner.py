#!/usr/bin/env python3
"""
Sapphire Batch Research Runner

Collects safe, public research signals on a schedule for offline review.
Outputs JSON snapshots and markdown briefings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def http_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> Any:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_text(url: str, headers: dict[str, str] | None = None, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.read().decode("utf-8")


def collect_github_repos(limit: int = 20) -> list[dict[str, Any]]:
    since = (dt.date.today() - dt.timedelta(days=14)).isoformat()
    query = f"pushed:>={since} stars:>25"
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": str(limit),
        }
    )
    url = f"https://api.github.com/search/repositories?{params}"
    data = http_get_json(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "sapphire-research-node"})
    items = data.get("items", [])
    results: list[dict[str, Any]] = []
    for item in items:
        results.append(
            {
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "description": item.get("description"),
                "language": item.get("language"),
                "stars": item.get("stargazers_count"),
                "updated_at": item.get("updated_at"),
            }
        )
    return results


def collect_hf_models(limit: int = 20) -> list[dict[str, Any]]:
    url = f"https://huggingface.co/api/models?sort=downloads&direction=-1&limit={limit}"
    data = http_get_json(url, headers={"User-Agent": "sapphire-research-node"})
    results: list[dict[str, Any]] = []
    for item in data:
        results.append(
            {
                "model_id": item.get("modelId"),
                "downloads": item.get("downloads"),
                "likes": item.get("likes"),
                "pipeline_tag": item.get("pipeline_tag"),
                "last_modified": item.get("lastModified"),
                "url": f"https://huggingface.co/{item.get('modelId')}",
            }
        )
    return results


def collect_arxiv(max_results: int = 15) -> list[dict[str, Any]]:
    query = "cat:cs.AI OR cat:cs.LG"
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": str(max_results),
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    xml_data = http_get_text(url)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_data)
    results: list[dict[str, Any]] = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
        link = ""
        for ln in entry.findall("a:link", ns):
            if ln.attrib.get("rel") == "alternate":
                link = ln.attrib.get("href", "")
                break
        results.append(
            {
                "title": title,
                "url": link,
                "published": entry.findtext("a:published", default="", namespaces=ns),
                "updated": entry.findtext("a:updated", default="", namespaces=ns),
            }
        )
    return results


def score_candidates(gh: list[dict[str, Any]], hf: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for repo in gh[:10]:
        stars = int(repo.get("stars") or 0)
        lang = (repo.get("language") or "").lower()
        if stars >= 300 and lang in {"python", "typescript", "javascript", "rust", "go"}:
            out.append(
                {
                    "type": "github_repo",
                    "name": repo.get("name"),
                    "reason": f"high signal repo ({stars} stars, {lang})",
                    "url": repo.get("url"),
                }
            )
    for model in hf[:10]:
        dls = int(model.get("downloads") or 0)
        if dls >= 10000:
            out.append(
                {
                    "type": "hf_model",
                    "name": model.get("model_id"),
                    "reason": f"high adoption model ({dls} downloads)",
                    "url": model.get("url"),
                }
            )
    return out[:12]


def write_snapshot(output_dir: pathlib.Path, profile: str, payload: dict[str, Any]) -> tuple[pathlib.Path, pathlib.Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_now().strftime("%Y%m%d_%H%M%S")
    snapshot = output_dir / f"research_snapshot_{profile}_{ts}.json"
    latest = output_dir / f"latest_{profile}.json"
    snapshot.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return snapshot, latest


def write_markdown(output_dir: pathlib.Path, profile: str, payload: dict[str, Any]) -> pathlib.Path:
    ts = payload["timestamp_utc"]
    path = output_dir / f"research_brief_{profile}_{utc_now().strftime('%Y%m%d_%H%M%S')}.md"
    lines: list[str] = []
    lines.append(f"# Sapphire Research Brief ({profile})")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{ts}`")
    lines.append(f"- Node: `{payload.get('node')}`")
    lines.append("")
    lines.append("## GitHub Signals")
    for repo in payload.get("github_repos", [])[:10]:
        lines.append(
            f"- `{repo.get('name')}` ({repo.get('stars')}⭐, {repo.get('language')}) - {repo.get('url')}"
        )
    lines.append("")
    lines.append("## Hugging Face Signals")
    for model in payload.get("huggingface_models", [])[:10]:
        lines.append(
            f"- `{model.get('model_id')}` ({model.get('downloads')} downloads) - {model.get('url')}"
        )
    lines.append("")
    lines.append("## arXiv Fresh Papers")
    for paper in payload.get("arxiv_papers", [])[:10]:
        lines.append(f"- {paper.get('title')} - {paper.get('url')}")
    lines.append("")
    lines.append("## Candidate Queue")
    for item in payload.get("candidates", []):
        lines.append(f"- [{item.get('type')}] `{item.get('name')}`: {item.get('reason')} ({item.get('url')})")
    lines.append("")
    lines.append("## Safety Gate")
    lines.append("- Do not auto-execute code from discovered sources.")
    lines.append("- Require manual review for new repos/models before integration.")
    lines.append("- Prefer sandbox tests first.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def build_payload(profile: str) -> dict[str, Any]:
    github_repos = collect_github_repos(limit=30 if profile == "daily" else 15)
    huggingface_models = collect_hf_models(limit=30 if profile == "daily" else 15)
    arxiv_papers = collect_arxiv(max_results=25 if profile == "daily" else 12)
    return {
        "timestamp_utc": utc_now().isoformat(),
        "node": os.uname().nodename,
        "profile": profile,
        "github_repos": github_repos,
        "huggingface_models": huggingface_models,
        "arxiv_papers": arxiv_papers,
        "candidates": score_candidates(github_repos, huggingface_models),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sapphire batch research runner")
    parser.add_argument("--profile", choices=["hourly", "daily"], default="hourly")
    parser.add_argument("--output-dir", default="/home/rari/research-node/output")
    args = parser.parse_args()

    output_dir = pathlib.Path(args.output_dir)
    try:
        payload = build_payload(args.profile)
        snap, latest = write_snapshot(output_dir, args.profile, payload)
        brief = write_markdown(output_dir, args.profile, payload)
        print(
            json.dumps(
                {
                    "ok": True,
                    "profile": args.profile,
                    "snapshot": str(snap),
                    "latest": str(latest),
                    "brief": str(brief),
                    "counts": {
                        "github_repos": len(payload["github_repos"]),
                        "huggingface_models": len(payload["huggingface_models"]),
                        "arxiv_papers": len(payload["arxiv_papers"]),
                        "candidates": len(payload["candidates"]),
                    },
                },
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
