#!/usr/bin/env python3
"""Sapphire Lead Engine — AI-powered outbound lead generation.

Inspired by Money Printer / AI SDR platforms. Give it a URL or business
description, it finds matching companies and generates personalized outreach.

Uses Regional Intel Workbench data (permits, news, businesses) for local
lead discovery, plus web search for broader reach.

Actions:
    analyze  — Analyze a website/URL to extract ICP (ideal customer profile)
    discover — Find matching businesses from Regional Intel data
    outreach — Generate personalized outreach messages for discovered leads
    pipeline — Full pipeline: analyze → discover → outreach

Usage:
    echo '{"action":"pipeline","url":"https://texashomeoutlet.com"}' | python3 lead_engine.py
    echo '{"action":"discover","industry":"real estate","region":"houston_tx"}' | python3 lead_engine.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
LEADS_DIR = SAPPHIRE_DIR / "data" / "leads"
LEADS_DIR.mkdir(parents=True, exist_ok=True)
REGIONAL_INTEL_API = "http://127.0.0.1:8787"


def _fetch_json(url: str, timeout: int = 10) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _infer_with_ollama(prompt: str, model: str = "hermes3:8b") -> str:
    """Quick inference via the proxy for lead analysis."""
    try:
        payload = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 500},
            }
        ).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:11435/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return f"Inference unavailable: {e}"


def action_analyze(url: str = None, description: str = None) -> dict:
    """Analyze a business URL or description to extract ICP."""
    if url:
        # Try to fetch the website
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Sapphire/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8", errors="ignore")[:5000]
        except Exception:
            html = f"Could not fetch {url}"

        prompt = f"""Analyze this business website and extract their Ideal Customer Profile (ICP).
Website: {url}
Content excerpt: {html[:2000]}

Return a JSON object with:
- business_name: string
- industry: string
- services: list of services offered
- target_customers: who they sell to
- geography: where they operate
- keywords: 5-10 search terms to find similar businesses or customers
- outreach_angle: how to approach potential partners/customers"""
    else:
        prompt = f"""Create an Ideal Customer Profile for this business:
{description}

Return a JSON object with: business_name, industry, services, target_customers, geography, keywords, outreach_angle"""

    result = _infer_with_ollama(prompt)

    # Try to parse JSON from response
    try:
        # Find JSON in response
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            icp = json.loads(result[start:end])
        else:
            icp = {"raw_analysis": result}
    except json.JSONDecodeError:
        icp = {"raw_analysis": result}

    return {"success": True, "icp": icp, "source": url or "description"}


def action_discover(
    industry: str = None, region: str = "houston_tx", keywords: list = None, limit: int = 20
) -> dict:
    """Find matching businesses from Regional Intel data."""
    leads = []

    # 1. Pull from Regional Intel
    data = _fetch_json(f"{REGIONAL_INTEL_API}/api/intel/snapshot?region={region}")
    if data:
        businesses = data.get("businesses", [])
        permits = data.get("permits", [])
        data.get("news", [])
        contacts = data.get("contacts", [])
        orgs = data.get("organizations", [])

        # Filter businesses by industry/keywords
        for biz in businesses[:100]:
            name = biz.get("name", "")
            category = biz.get("category", "")
            searchable = f"{name} {category} {biz.get('description', '')}".lower()

            match = False
            if industry and industry.lower() in searchable:
                match = True
            if keywords:
                for kw in keywords:
                    if kw.lower() in searchable:
                        match = True
                        break

            # No filter = return all; with filter = only matches
            if match or (not industry and not keywords):
                leads.append(
                    {
                        "type": "business",
                        "name": name,
                        "category": category or biz.get("categories", ""),
                        "address": biz.get("address", ""),
                        "source": "regional-intel",
                        "region": region,
                    }
                )

        # Check permits — search ALL text fields against ALL keywords
        all_terms = [t.lower() for t in (keywords or [])]
        if industry:
            all_terms.extend(industry.lower().split())
        # Add common related terms
        all_terms = list(set(all_terms))

        for permit in permits:
            searchable = " ".join(str(v) for v in permit.values()).lower()
            if not all_terms or any(t in searchable for t in all_terms):
                leads.append(
                    {
                        "type": "permit",
                        "name": permit.get(
                            "applicant", permit.get("contractor", permit.get("address", "Unknown"))
                        ),
                        "category": permit.get(
                            "permit_type", permit.get("work_type", "construction")
                        ),
                        "description": permit.get("description", permit.get("address", ""))[:120],
                        "source": "permits",
                        "region": region,
                    }
                )

        # Organizations — search broadly
        for org in orgs:
            searchable = " ".join(
                filter(
                    None,
                    [
                        org.get("name", ""),
                        str(org.get("categories", "")),
                        org.get("description", ""),
                        org.get("address", ""),
                    ],
                )
            ).lower()
            if not all_terms or any(t in searchable for t in all_terms):
                leads.append(
                    {
                        "type": "organization",
                        "name": org.get("name", "Unknown"),
                        "category": str(org.get("categories", ""))[:50],
                        "source": "regional-intel",
                        "region": region,
                    }
                )

        # Contacts (potential decision makers)
        for contact in contacts:
            searchable = " ".join(str(v) for v in contact.values()).lower()
            if not all_terms or any(t in searchable for t in all_terms):
                leads.append(
                    {
                        "type": "contact",
                        "name": contact.get("name", "Unknown"),
                        "category": contact.get("title", contact.get("organization", "")),
                        "source": "regional-intel",
                        "region": region,
                    }
                )

    return {
        "success": True,
        "total_leads": len(leads[:limit]),
        "region": region,
        "filters": {"industry": industry, "keywords": keywords},
        "leads": leads[:limit],
    }


def action_outreach(leads: list, business_context: str = "") -> dict:
    """Generate personalized outreach messages for discovered leads."""
    if not leads:
        return {"error": "No leads provided"}

    messages = []
    for lead in leads[:5]:  # Limit to 5 at a time
        name = lead.get("name", "Unknown")
        category = lead.get("category", "")

        prompt = f"""Write a short, personalized cold outreach email (3-4 sentences) for:
Prospect: {name} ({category})
Our business: {business_context or "Kadima Digital Strategies - AI operations, trading systems, business intelligence"}
Goal: Introduce our services and schedule a brief call.
Tone: Professional, warm, concise. No fluff. Reference something specific about them."""

        msg = _infer_with_ollama(prompt, model="hermes3:8b")  # Reliable model for outreach drafts
        messages.append(
            {
                "lead": name,
                "category": category,
                "message": msg.strip(),
            }
        )

    return {"success": True, "messages": messages}


def action_pipeline(
    url: str = None, description: str = None, region: str = "houston_tx", limit: int = 10
) -> dict:
    """Full pipeline: analyze → discover → outreach."""
    # Step 1: Analyze
    analysis = action_analyze(url=url, description=description)
    icp = analysis.get("icp", {})

    # Step 2: Discover
    industry = icp.get("industry", "")
    keywords = icp.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [keywords]

    discovery = action_discover(
        industry=industry, region=region, keywords=keywords[:5], limit=limit
    )

    # Step 3: Outreach (top 3 leads only)
    top_leads = discovery.get("leads", [])[:3]
    business_desc = f"{icp.get('business_name', '')} - {', '.join(icp.get('services', []))}"
    outreach = action_outreach(top_leads, business_context=business_desc)

    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    result = {
        "timestamp": ts,
        "icp": icp,
        "leads_found": discovery.get("total_leads", 0),
        "leads": discovery.get("leads", []),
        "outreach": outreach.get("messages", []),
    }
    (LEADS_DIR / f"pipeline_{ts}.json").write_text(json.dumps(result, indent=2, default=str))

    return {
        "success": True,
        "icp": icp,
        "leads_found": discovery.get("total_leads", 0),
        "outreach_drafted": len(outreach.get("messages", [])),
        "saved_to": str(LEADS_DIR / f"pipeline_{ts}.json"),
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "discover", "region": "houston_tx"}
    action = params.get("action", "discover")

    if action == "analyze":
        result = action_analyze(url=params.get("url"), description=params.get("description"))
    elif action == "discover":
        result = action_discover(
            industry=params.get("industry"),
            region=params.get("region", "houston_tx"),
            keywords=params.get("keywords"),
            limit=params.get("limit", 20),
        )
    elif action == "outreach":
        result = action_outreach(params.get("leads", []), params.get("business_context", ""))
    elif action == "pipeline":
        result = action_pipeline(
            url=params.get("url"),
            description=params.get("description"),
            region=params.get("region", "houston_tx"),
            limit=params.get("limit", 10),
        )
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
