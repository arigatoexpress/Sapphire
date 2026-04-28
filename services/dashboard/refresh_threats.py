#!/usr/bin/env python3
"""Refresh threat intelligence data for the SOC dashboard.

Runs cyber-threat-bot and writes output to data/intelligence/YYYY-MM-DD/threats.json
so the /api/soc/threats endpoint can consume it. Runs every 4 hours via LaunchAgent.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DEFAULT_THREAT_BOT_BIN = Path.home() / "Code" / "cyber-threat-bot" / ".venv" / "bin" / "threat-bot"
DEFAULT_DATA_DIR = Path.home() / "Code" / "Sapphire" / "data" / "intelligence"
USER_AGENT = "sapphire-threat-refresh/0.1 (+https://github.com/arigatoexpress/Sapphire)"
NVD_CVE_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
DARK_READING_RSS_URL = "https://www.darkreading.com/rss.xml"


def _data_dir() -> Path:
    return Path(os.environ.get("SAPPHIRE_THREATS_DATA_DIR") or DEFAULT_DATA_DIR).expanduser()


def _threat_bot_bin() -> str | None:
    raw = os.environ.get("SAPPHIRE_THREATS_BOT_BIN") or str(DEFAULT_THREAT_BOT_BIN)
    if raw == "native":
        return raw
    expanded = Path(raw).expanduser()
    if expanded.is_absolute() or expanded.parent != Path("."):
        return str(expanded) if expanded.exists() else None
    return shutil.which(raw)


def main() -> int:
    threat_bot = _threat_bot_bin()
    if threat_bot is None:
        configured = os.environ.get("SAPPHIRE_THREATS_BOT_BIN") or str(DEFAULT_THREAT_BOT_BIN)
        print(f"threat-bot not found: {configured}", file=sys.stderr)
        return 1

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    data_dir = _data_dir()
    out_dir = data_dir / today
    out_dir.mkdir(parents=True, exist_ok=True)

    if threat_bot == "native":
        try:
            threats = _collect_native_public_threats(days=3, per_source=5)
        except Exception as e:
            print(f"native threat refresh failed: {e}", file=sys.stderr)
            return 1
    else:
        result = subprocess.run(
            [threat_bot, "latest", "--days", "3", "--per-source", "5", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"threat-bot failed: {result.stderr}", file=sys.stderr)
            return result.returncode

        try:
            threats = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON from threat-bot: {e}", file=sys.stderr)
            return 1

    refreshed_at = datetime.now(UTC)
    run_stamp = refreshed_at.strftime("%Y%m%dT%H%M%SZ")
    out_file = out_dir / "threats.json"
    payload = {
        "refreshed_at": refreshed_at.isoformat(),
        "source_count": len(threats),
        "threats": threats,
    }
    out_file.write_text(json.dumps(payload, indent=2))

    run_file = data_dir / "runs" / run_stamp / "threats.json"
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_file.write_text(json.dumps(payload, indent=2))

    latest = data_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(today)
    except Exception as e:
        print(f"Symlink update failed: {e}", file=sys.stderr)

    print(f"Wrote {len(threats)} threats to {out_file}")
    print(f"Wrote run snapshot to {run_file}")
    return 0


def _collect_native_public_threats(*, days: int, per_source: int) -> list[dict]:
    """Public-source fallback for remote shadow runs without private repo access."""
    records: list[dict] = []
    cisa_records = _fetch_cisa_kev(days=max(days * 4, 30), limit=per_source)
    records.extend(cisa_records)
    for record in cisa_records:
        try:
            records.append(_fetch_nvd_cve(record["canonical_id"]))
        except Exception:
            continue
    records.extend(_fetch_nvd_recent(days=days, limit=per_source))
    records.extend(_fetch_darkreading(limit=per_source))
    return _merge_records(records)


def _headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
    }


def _request_json(url: str, *, params: dict | None = None) -> dict:
    query = urlencode(params or {})
    request_url = f"{url}?{query}" if query else url
    request = Request(request_url, headers=_headers())
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_text(url: str) -> str:
    request = Request(url, headers=_headers())
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _fetch_cisa_kev(*, days: int, limit: int) -> list[dict]:
    payload = _request_json(CISA_KEV_URL)
    cutoff = datetime.now(UTC) - timedelta(days=days)
    records: list[dict] = []
    for item in payload.get("vulnerabilities", []):
        added = _parse_datetime(item.get("dateAdded"))
        if added is None or added < cutoff:
            continue
        cve_id = _clean_text(item.get("cveID"))
        vendor = _clean_text(item.get("vendorProject"))
        product = _clean_text(item.get("product"))
        title = f"{vendor} {product}: {_clean_text(item.get('vulnerabilityName'))}".strip(": ")
        summary = _clean_text(item.get("shortDescription"))
        due_date = _clean_text(item.get("dueDate"))
        ransomware = _clean_text(item.get("knownRansomwareCampaignUse"))
        if due_date:
            summary = f"{summary} CISA remediation due date: {due_date}.".strip()
        if ransomware:
            summary = f"{summary} Known ransomware campaign use: {ransomware}.".strip()
        records.append(
            {
                "source": "cisa-kev",
                "source_type": "cve",
                "canonical_id": cve_id,
                "title": title or cve_id,
                "url": f"https://www.cisa.gov/known-exploited-vulnerabilities-catalog?search_api_fulltext={cve_id}",
                "published_at": _isoformat(added),
                "summary": summary,
                "score": None,
                "exploited": True,
                "tags": [
                    tag
                    for tag in ["kev", vendor.lower(), product.lower(), *_keyword_tags(summary)]
                    if tag
                ],
                "evidence": [
                    {
                        "label": "CISA Known Exploited Vulnerabilities",
                        "url": CISA_KEV_URL,
                        "published_at": _isoformat(added),
                        "note": f"{cve_id} catalog entry",
                    }
                ],
                "metadata": {
                    "vendor_project": vendor,
                    "product": product,
                    "required_action": _clean_text(item.get("requiredAction")),
                    "due_date": due_date,
                    "known_ransomware_campaign_use": ransomware,
                },
            }
        )
        if len(records) >= limit:
            break
    return records


def _fetch_nvd_recent(*, days: int, limit: int) -> list[dict]:
    now = datetime.now(UTC)
    start = now - timedelta(days=days)
    payload = _request_json(
        NVD_CVE_API,
        params={
            "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": now.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "resultsPerPage": max(limit * 5, 50),
            "noRejected": "",
        },
    )
    records = _parse_nvd(payload, limit=max(limit * 4, 25))
    records.sort(key=_record_priority, reverse=True)
    return records[:limit]


def _fetch_nvd_cve(cve_id: str) -> dict:
    records = _parse_nvd(_request_json(NVD_CVE_API, params={"cveId": cve_id}), limit=1)
    if not records:
        raise ValueError(f"No NVD record found for {cve_id}")
    record = records[0]
    record.setdefault("metadata", {})["cve_org_url"] = f"https://www.cve.org/CVERecord?id={cve_id}"
    return record


def _parse_nvd(payload: dict, *, limit: int) -> list[dict]:
    records: list[dict] = []
    for entry in payload.get("vulnerabilities", []):
        cve = entry.get("cve", {})
        cve_id = _clean_text(cve.get("id"))
        published_at = _parse_datetime(cve.get("published"))
        summary = _english_description(cve.get("descriptions", []))
        score, vector = _extract_cvss(cve.get("metrics", {}))
        cwes = _extract_cwes(cve)
        refs = _extract_references(cve)
        records.append(
            {
                "source": "nvd",
                "source_type": "cve",
                "canonical_id": cve_id,
                "title": f"{cve_id}: {summary[:110]}".rstrip(),
                "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                "published_at": _isoformat(published_at),
                "summary": summary,
                "score": score,
                "exploited": False,
                "tags": [*cwes, *_keyword_tags(summary)],
                "evidence": [
                    {
                        "label": "NVD CVE API 2.0",
                        "url": f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                        "published_at": _isoformat(published_at),
                    }
                ],
                "metadata": {
                    "cvss_vector": vector,
                    "weaknesses": cwes,
                    "references": refs,
                    "source_identifier": _clean_text(cve.get("sourceIdentifier")),
                    "vuln_status": _clean_text(cve.get("vulnStatus")),
                },
            }
        )
        if len(records) >= limit:
            break
    return records


def _fetch_darkreading(*, limit: int) -> list[dict]:
    root = ET.fromstring(_request_text(DARK_READING_RSS_URL))
    channel = root.find("channel")
    if channel is None:
        return []
    records: list[dict] = []
    for item in channel.findall("item")[:limit]:
        title = _clean_text(item.findtext("title"))
        link = _clean_text(item.findtext("link"))
        description = _clean_text(item.findtext("description"))
        published_at = _parse_rfc822_datetime(item.findtext("pubDate"))
        categories = [
            _clean_text(category.text)
            for category in item.findall("category")
            if _clean_text(category.text)
        ]
        slug = link.rstrip("/").rsplit("/", 1)[-1]
        records.append(
            {
                "source": "darkreading",
                "source_type": "news",
                "canonical_id": f"darkreading:{slug}",
                "title": title,
                "url": link,
                "published_at": _isoformat(published_at),
                "summary": description,
                "score": None,
                "exploited": False,
                "tags": [*categories, *_keyword_tags(f"{title} {description}")],
                "evidence": [
                    {
                        "label": "Dark Reading RSS",
                        "url": link,
                        "published_at": _isoformat(published_at),
                    }
                ],
                "metadata": {"categories": categories},
            }
        )
    return records


def _merge_records(records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for record in records:
        key = str(record.get("canonical_id", "")).lower()
        if not key:
            continue
        if key not in merged:
            clone = json.loads(json.dumps(record))
            clone.setdefault("metadata", {})["source_set"] = [record.get("source")]
            merged[key] = clone
            continue
        current = merged[key]
        source_set = list(current.setdefault("metadata", {}).get("source_set", []))
        if record.get("source") not in source_set:
            source_set.append(record.get("source"))
        current["metadata"]["source_set"] = source_set
        current["source"] = "+".join(str(source) for source in source_set if source)
        current["exploited"] = bool(current.get("exploited") or record.get("exploited"))
        current["score"] = _max_score(current.get("score"), record.get("score"))
        if _published_sort_key(record) > _published_sort_key(current):
            current["published_at"] = record.get("published_at")
        if _prefer_title(record, current):
            current["title"] = record.get("title")
        if len(str(record.get("summary") or "")) > len(str(current.get("summary") or "")):
            current["summary"] = record.get("summary")
        for tag in record.get("tags") or []:
            if tag not in current.setdefault("tags", []):
                current["tags"].append(tag)
        for item in record.get("evidence") or []:
            if all(
                existing.get("url") != item.get("url")
                for existing in current.setdefault("evidence", [])
            ):
                current["evidence"].append(item)
        for key_name, value in (record.get("metadata") or {}).items():
            current["metadata"].setdefault(key_name, value)
    return sorted(merged.values(), key=_record_priority, reverse=True)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(unescape(value).split())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_rfc822_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return parsedate_to_datetime(value).astimezone(UTC)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _english_description(values: list[dict]) -> str:
    for item in values:
        if item.get("lang") == "en":
            return _clean_text(item.get("value"))
    return _clean_text(values[0].get("value")) if values else ""


def _extract_cvss(metrics: dict) -> tuple[float | None, str | None]:
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        candidates = metrics.get(key) or []
        if candidates:
            data = candidates[0].get("cvssData", {})
            return data.get("baseScore"), data.get("vectorString")
    return None, None


def _extract_cwes(cve: dict) -> list[str]:
    values: list[str] = []
    for weakness in cve.get("weaknesses", []):
        for desc in weakness.get("description", []):
            text = _clean_text(desc.get("value"))
            if text and text not in values:
                values.append(text)
    return values


def _extract_references(cve: dict, limit: int = 5) -> list[str]:
    refs: list[str] = []
    for entry in cve.get("references", []):
        url = entry.get("url")
        if url and url not in refs:
            refs.append(url)
        if len(refs) >= limit:
            break
    return refs


def _keyword_tags(text: str) -> list[str]:
    lowered = text.lower()
    lookup = {
        "memory-corruption": (
            "overflow",
            "memory corruption",
            "use-after-free",
            "heap",
            "out-of-bounds",
        ),
        "injection": ("injection", "sql", "command", "prompt", "template"),
        "auth": ("authentication", "authorization", "bypass", "session", "token"),
        "path-traversal": ("path traversal", "../", "directory traversal"),
        "deserialization": ("deserialization", "serialize", "pickle", "marshal"),
        "rce": (
            "remote code execution",
            "arbitrary code",
            "execute arbitrary",
            "command execution",
        ),
        "xss": ("cross-site scripting", "xss", "script injection"),
        "supply-chain": ("dependency", "package", "supply chain", "artifact", "plugin"),
        "ai": ("llm", "ai ", "model", "prompt injection", "agent"),
    }
    return [
        label for label, needles in lookup.items() if any(needle in lowered for needle in needles)
    ]


def _record_priority(record: dict) -> float:
    score = 0.0
    if record.get("exploited"):
        score += 5.0
    if record.get("score") is not None:
        score += min(float(record["score"]), 10.0) / 2.0
    published = _parse_datetime(record.get("published_at"))
    if published is not None:
        age_days = max((datetime.now(UTC) - published).total_seconds() / 86400, 0.0)
        score += max(0.0, 3.0 - min(age_days, 9.0) / 3.0)
    if "rce" in (record.get("tags") or []):
        score += 1.5
    return round(score, 2)


def _max_score(left: object, right: object) -> float | None:
    scores = [float(value) for value in (left, right) if value is not None]
    return max(scores) if scores else None


def _published_sort_key(record: dict) -> datetime:
    return _parse_datetime(record.get("published_at")) or datetime.min.replace(tzinfo=UTC)


def _prefer_title(incoming: dict, current: dict) -> bool:
    incoming_title = str(incoming.get("title") or "")
    current_title = str(current.get("title") or "")
    current_id = str(current.get("canonical_id") or "").upper()
    current_generic = current_title.upper().startswith(current_id)
    incoming_generic = incoming_title.upper().startswith(current_id)
    if current_generic and not incoming_generic:
        return True
    return len(incoming_title) > len(current_title) and not (
        not current_generic and incoming_generic
    )


if __name__ == "__main__":
    sys.exit(main())
