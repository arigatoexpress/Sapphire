#!/usr/bin/env python3
"""Sapphire Starred Repos Synergy Finder.

Fetches your GitHub starred repos, analyzes each for synergies with the
Sapphire ecosystem, and generates actionable integration recommendations.

Actions:
    sync     — Fetch all starred repos, save metadata, detect new stars
    analyze  — Find synergies between starred repos and our codebase
    report   — Generate a full synergy report with recommendations

Usage (stdin JSON):
    echo '{"action":"sync"}' | python3 starred_repos.py
    echo '{"action":"analyze"}' | python3 starred_repos.py
    echo '{"action":"report"}' | python3 starred_repos.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
DATA_DIR = SAPPHIRE_DIR / "data" / "starred_repos"
DATA_DIR.mkdir(parents=True, exist_ok=True)
STARS_FILE = DATA_DIR / "starred.json"
SYNERGY_FILE = DATA_DIR / "synergies.json"
REPORT_FILE = DATA_DIR / "synergy_report.md"

# Our ecosystem repos and their domains
OUR_REPOS = {
    "Sapphire": {
        "path": "~/Code/Sapphire",
        "domains": [
            "trading",
            "ai-agents",
            "automation",
            "telegram",
            "monitoring",
            "pine-script",
            "technical-analysis",
        ],
        "languages": ["python", "typescript", "swift", "rust"],
        "needs": [
            "execution-engine",
            "backtesting",
            "portfolio-management",
            "risk-management",
            "ml-models",
        ],
    },
    "Project-Go-Forward": {
        "path": "~/Code/Project-Go-Forward",
        "domains": [
            "real-estate",
            "document-generation",
            "crm",
            "pdf",
            "ai-chat",
            "customer-management",
        ],
        "languages": ["python", "javascript", "react"],
        "needs": ["ocr", "document-ai", "email-automation", "sms", "scheduling"],
    },
    "cyber-threat-bot": {
        "path": "~/Code/cyber-threat-bot",
        "domains": [
            "cybersecurity",
            "threat-intelligence",
            "cve",
            "mitre-attack",
            "revenue-synthesis",
        ],
        "languages": ["python"],
        "needs": ["osint", "vulnerability-scanning", "network-monitoring", "siem-integration"],
    },
    "regional-intel-workbench": {
        "path": "~/Code/regional-intel-workbench",
        "domains": [
            "business-intelligence",
            "geospatial",
            "permits",
            "news-aggregation",
            "lead-generation",
        ],
        "languages": ["python", "javascript"],
        "needs": ["mapping", "data-enrichment", "nlp", "entity-resolution"],
    },
    "Cointracker": {
        "path": "~/Code/Cointracker",
        "domains": ["crypto", "tax", "defi", "portfolio", "pnl-tracking"],
        "languages": ["python", "typescript"],
        "needs": ["blockchain-indexing", "price-feeds", "tax-lot-matching"],
    },
    "claw-code": {
        "path": "~/Code/claw-code",
        "domains": ["agent-runtime", "rust", "plugins", "tool-execution"],
        "languages": ["rust", "python"],
        "needs": ["sandboxing", "wasm", "plugin-marketplace"],
    },
}

# Keyword → domain mapping for classification
DOMAIN_KEYWORDS = {
    "trading": [
        "trading",
        "trade",
        "exchange",
        "market",
        "finance",
        "quant",
        "backtest",
        "strategy",
        "freqtrade",
        "tensortrade",
    ],
    "ai-agents": [
        "agent",
        "llm",
        "gpt",
        "claude",
        "eliza",
        "flowise",
        "langchain",
        "autogen",
        "crew",
        "swarm",
    ],
    "crypto": ["crypto", "blockchain", "defi", "sui", "solana", "ethereum", "web3", "nft", "token"],
    "cybersecurity": [
        "security",
        "vulnerability",
        "cve",
        "osint",
        "pentest",
        "scanner",
        "sherlock",
        "exploit",
    ],
    "ml-research": [
        "ml",
        "machine-learning",
        "deep-learning",
        "papers",
        "research",
        "model",
        "training",
    ],
    "infrastructure": ["infra", "devops", "docker", "kubernetes", "ci-cd", "monitoring", "ipfs"],
    "data": ["data", "analytics", "scraping", "etl", "pipeline", "database"],
    "real-estate": ["real-estate", "property", "home", "housing", "mortgage"],
}


def gh_api(endpoint: str) -> list | dict:
    """Call GitHub API via gh CLI."""
    result = subprocess.run(
        ["gh", "api", endpoint, "--paginate"], capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh api failed: {result.stderr}")
    return json.loads(result.stdout)


def sync_stars() -> dict:
    """Fetch all starred repos and save metadata."""
    raw = subprocess.run(
        [
            "gh",
            "api",
            "user/starred",
            "--paginate",
            "--jq",
            "[.[] | {full_name, description, language, topics, html_url, stargazers_count, updated_at, archived}]",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if raw.returncode != 0:
        return {"error": f"gh api failed: {raw.stderr}"}

    repos = json.loads(raw.stdout)

    # Load previous stars to detect new ones
    prev_stars = set()
    if STARS_FILE.exists():
        prev = json.loads(STARS_FILE.read_text())
        prev_stars = {r["full_name"] for r in prev}

    new_stars = [r for r in repos if r["full_name"] not in prev_stars]

    # Save current stars
    STARS_FILE.write_text(json.dumps(repos, indent=2))

    return {
        "success": True,
        "total": len(repos),
        "new_since_last_sync": len(new_stars),
        "new_repos": [r["full_name"] for r in new_stars],
        "saved_to": str(STARS_FILE),
    }


def classify_repo(repo: dict) -> list[str]:
    """Classify a repo into domains based on name, description, topics, and language."""
    searchable = " ".join(
        [
            (repo.get("full_name") or "").lower(),
            (repo.get("description") or "").lower(),
            " ".join(repo.get("topics") or []),
            (repo.get("language") or "").lower(),
        ]
    )

    domains = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(kw in searchable for kw in keywords):
            domains.append(domain)

    return domains or ["general"]


def find_synergies() -> dict:
    """Analyze starred repos for synergies with our ecosystem."""
    if not STARS_FILE.exists():
        return {"error": "No starred repos data. Run sync first."}

    repos = json.loads(STARS_FILE.read_text())
    synergies = []

    for repo in repos:
        if repo.get("archived"):
            continue

        domains = classify_repo(repo)
        matches = []

        for our_name, our_info in OUR_REPOS.items():
            # Check domain overlap
            domain_overlap = set(domains) & set(our_info["domains"])
            # Check if it addresses a need
            needs_match = []
            searchable = " ".join(
                [
                    (repo.get("full_name") or "").lower(),
                    (repo.get("description") or "").lower(),
                    " ".join(repo.get("topics") or []),
                ]
            )
            for need in our_info["needs"]:
                if need.replace("-", " ") in searchable or need.replace("-", "") in searchable:
                    needs_match.append(need)

            # Check language compatibility
            lang = (repo.get("language") or "").lower()
            lang_match = lang in our_info["languages"] if lang else False

            if domain_overlap or needs_match:
                score = len(domain_overlap) * 2 + len(needs_match) * 3 + (1 if lang_match else 0)
                matches.append(
                    {
                        "our_repo": our_name,
                        "domain_overlap": list(domain_overlap),
                        "needs_addressed": needs_match,
                        "language_compatible": lang_match,
                        "score": score,
                    }
                )

        if matches:
            matches.sort(key=lambda m: m["score"], reverse=True)
            synergies.append(
                {
                    "repo": repo["full_name"],
                    "description": repo.get("description", ""),
                    "language": repo.get("language"),
                    "url": repo.get("html_url"),
                    "domains": domains,
                    "matches": matches,
                    "top_score": matches[0]["score"],
                }
            )

    synergies.sort(key=lambda s: s["top_score"], reverse=True)
    SYNERGY_FILE.write_text(json.dumps(synergies, indent=2))

    return {
        "success": True,
        "total_starred": len(repos),
        "repos_with_synergies": len(synergies),
        "top_synergies": [
            {"repo": s["repo"], "score": s["top_score"], "best_match": s["matches"][0]["our_repo"]}
            for s in synergies[:10]
        ],
        "saved_to": str(SYNERGY_FILE),
    }


def generate_report() -> dict:
    """Generate a markdown synergy report with recommendations."""
    if not SYNERGY_FILE.exists():
        return {"error": "No synergy data. Run analyze first."}

    synergies = json.loads(SYNERGY_FILE.read_text())
    stars = json.loads(STARS_FILE.read_text()) if STARS_FILE.exists() else []

    lines = [
        "# Starred Repos Synergy Report",
        "",
        f"Generated: {datetime.now().isoformat()}",
        f"Total starred: {len(stars)} | With synergies: {len(synergies)}",
        "",
        "## High-Value Synergies",
        "",
    ]

    for i, s in enumerate(synergies[:15], 1):
        best = s["matches"][0]
        lines.append(f"### {i}. [{s['repo']}]({s['url']})")
        lines.append(f"- **Language**: {s['language'] or 'N/A'} | **Score**: {s['top_score']}")
        lines.append(f"- **Description**: {s['description'][:200]}")
        lines.append(f"- **Best match**: {best['our_repo']}")
        if best.get("domain_overlap"):
            lines.append(f"- **Domain overlap**: {', '.join(best['domain_overlap'])}")
        if best.get("needs_addressed"):
            lines.append(f"- **Addresses needs**: {', '.join(best['needs_addressed'])}")
        lines.append(
            f"- **Integration idea**: Investigate how {s['repo'].split('/')[-1]} can enhance {best['our_repo']}"
        )
        lines.append("")

    # Unmatched repos
    matched_names = {s["repo"] for s in synergies}
    unmatched = [r for r in stars if r["full_name"] not in matched_names and not r.get("archived")]
    if unmatched:
        lines.append("## Unmatched Stars (no clear synergy)")
        lines.append("")
        for r in unmatched:
            lines.append(
                f"- **{r['full_name']}** ({r.get('language', 'N/A')}): {(r.get('description') or 'No description')[:100]}"
            )
        lines.append("")

    report = "\n".join(lines)
    REPORT_FILE.write_text(report)

    return {
        "success": True,
        "synergies_found": len(synergies),
        "report_path": str(REPORT_FILE),
        "top_3": [
            f"{s['repo']} → {s['matches'][0]['our_repo']} (score {s['top_score']})"
            for s in synergies[:3]
        ],
    }


def discover_trending() -> dict:
    """Fetch trending GitHub repos and find synergies with our ecosystem."""
    TRENDING_FILE = DATA_DIR / "trending.json"

    # Use gh search to find recently popular repos in our key domains
    domains_to_search = [
        "trading bot",
        "ai agent framework",
        "cybersecurity tool",
        "real estate tech",
        "crypto defi",
        "rust agent",
        "llm tool",
    ]

    all_trending = []
    seen = set()

    for query in domains_to_search:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "repos",
                    query,
                    "--sort",
                    "stars",
                    "--limit",
                    "5",
                    "--json",
                    "fullName,description,language,url,stargazersCount,updatedAt",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                repos = json.loads(result.stdout)
                for r in repos:
                    name = r.get("fullName", "")
                    if name and name not in seen:
                        seen.add(name)
                        all_trending.append(
                            {
                                "full_name": name,
                                "description": r.get("description", ""),
                                "language": r.get("language", ""),
                                "html_url": r.get("url", ""),
                                "stargazers_count": r.get("stargazersCount", 0),
                                "updated_at": r.get("updatedAt", ""),
                                "search_query": query,
                                "topics": [],
                            }
                        )
        except Exception:
            continue

    # Analyze synergies with our ecosystem
    synergies = []
    for repo in all_trending:
        domains = classify_repo(repo)
        matches = []
        for our_name, our_info in OUR_REPOS.items():
            domain_overlap = set(domains) & set(our_info["domains"])
            needs_match = []
            searchable = " ".join(
                [
                    (repo.get("full_name") or "").lower(),
                    (repo.get("description") or "").lower(),
                ]
            )
            for need in our_info["needs"]:
                if need.replace("-", " ") in searchable or need.replace("-", "") in searchable:
                    needs_match.append(need)
            if domain_overlap or needs_match:
                score = (
                    len(domain_overlap) * 2
                    + len(needs_match) * 3
                    + (1 if (repo.get("language") or "").lower() in our_info["languages"] else 0)
                )
                matches.append(
                    {
                        "our_repo": our_name,
                        "domain_overlap": list(domain_overlap),
                        "needs_addressed": needs_match,
                        "score": score,
                    }
                )
        if matches:
            matches.sort(key=lambda m: m["score"], reverse=True)
            synergies.append(
                {
                    "repo": repo["full_name"],
                    "description": repo.get("description", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language"),
                    "url": repo.get("html_url"),
                    "search_query": repo.get("search_query"),
                    "matches": matches,
                    "top_score": matches[0]["score"],
                }
            )

    synergies.sort(key=lambda s: s["top_score"] * 1000 + s.get("stars", 0), reverse=True)
    TRENDING_FILE.write_text(json.dumps(synergies, indent=2))

    # Also save a trending report
    trend_report_path = DATA_DIR / f"trending_report_{datetime.now().strftime('%Y%m%d')}.md"
    lines = [
        "# Trending GitHub Repos — Synergy Analysis",
        "",
        f"Generated: {datetime.now().isoformat()}",
        f"Searched {len(domains_to_search)} domains, found {len(all_trending)} repos, {len(synergies)} with synergies",
        "",
    ]
    for i, s in enumerate(synergies[:15], 1):
        best = s["matches"][0]
        lines.append(f"### {i}. [{s['repo']}]({s['url']}) ⭐ {s['stars']:,}")
        lines.append(f"- {s['description'][:200]}")
        lines.append(f"- **Synergy with**: {best['our_repo']} (score {best['score']})")
        if best.get("domain_overlap"):
            lines.append(f"- **Domains**: {', '.join(best['domain_overlap'])}")
        if best.get("needs_addressed"):
            lines.append(f"- **Fills need**: {', '.join(best['needs_addressed'])}")
        lines.append("")

    trend_report_path.write_text("\n".join(lines))

    return {
        "success": True,
        "total_searched": len(all_trending),
        "synergies_found": len(synergies),
        "report_path": str(trend_report_path),
        "top_5": [
            {
                "repo": s["repo"],
                "stars": s.get("stars", 0),
                "match": s["matches"][0]["our_repo"],
                "score": s["top_score"],
            }
            for s in synergies[:5]
        ],
    }


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        raw = '{"action": "sync"}'

    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        return

    action = params.get("action", "sync")

    if action == "sync":
        result = sync_stars()
    elif action == "analyze":
        result = find_synergies()
    elif action == "trending":
        result = discover_trending()
    elif action == "full":
        # Starred + trending combined
        sync_result = sync_stars()
        analyze_result = find_synergies() if "error" not in sync_result else sync_result
        report_result = generate_report() if "error" not in analyze_result else analyze_result
        trending_result = discover_trending()
        result = {
            "success": True,
            "starred": sync_result,
            "synergies": analyze_result,
            "report": report_result,
            "trending": trending_result,
        }
    elif action == "report":
        # Run full pipeline
        sync_result = sync_stars()
        if "error" in sync_result:
            result = sync_result
        else:
            analyze_result = find_synergies()
            if "error" in analyze_result:
                result = analyze_result
            else:
                result = generate_report()
                result["sync"] = sync_result
                result["analysis"] = analyze_result
    else:
        result = {"error": f"Unknown action: {action}. Use: sync, analyze, report"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
