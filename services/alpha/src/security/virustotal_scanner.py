import asyncio
import hashlib
import io
import json
import os
import re
import time
import zipfile
from collections import deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

import aiohttp
from loguru import logger


class VirusTotalSkillScanner:
    _DEFAULT_API_BASE = "https://www.virustotal.com/api/v3"
    _VALID_POLICY_MODES = {"off", "warn", "block_malicious", "block_suspicious"}
    _SEVERITY_ORDER = {"unknown": 0, "benign": 1, "suspicious": 2, "malicious": 3}
    _SKILL_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")

    def __init__(self):
        self.enabled = self._env_flag("SAPPHIRE_VT_ENABLED", default=True)
        self.api_key = str(os.getenv("VIRUSTOTAL_API_KEY", "")).strip()
        self.api_base = str(os.getenv("SAPPHIRE_VT_API_BASE", self._DEFAULT_API_BASE)).rstrip("/")
        skills_dir = str(os.getenv("SAPPHIRE_SKILLS_DIR", "/app/skills")).strip()
        self.skills_dir = Path(skills_dir).expanduser()
        self.max_requests_per_minute = max(
            1, min(int(os.getenv("SAPPHIRE_VT_MAX_REQUESTS_PER_MINUTE", "4")), 60)
        )
        self.max_requests_per_day = max(
            1, min(int(os.getenv("SAPPHIRE_VT_MAX_REQUESTS_PER_DAY", "500")), 50000)
        )
        self.bundle_timeout_seconds = max(5, min(int(os.getenv("SAPPHIRE_VT_TIMEOUT_SECONDS", "25")), 120))
        self.poll_interval_seconds = max(
            2, min(int(os.getenv("SAPPHIRE_VT_POLL_INTERVAL_SECONDS", "5")), 30)
        )
        self.max_poll_attempts = max(1, min(int(os.getenv("SAPPHIRE_VT_MAX_POLL_ATTEMPTS", "12")), 60))
        self.max_skills_per_scan = max(
            1, min(int(os.getenv("SAPPHIRE_VT_MAX_SKILLS_PER_SCAN", "4")), 200)
        )
        self.upload_if_missing_default = self._env_flag(
            "SAPPHIRE_VT_UPLOAD_IF_MISSING", default=False
        )
        self.enforcement_mode = str(
            os.getenv("SAPPHIRE_VT_ENFORCEMENT_MODE", "warn")
        ).strip().lower()
        if self.enforcement_mode not in self._VALID_POLICY_MODES:
            self.enforcement_mode = "warn"

        self._ignore_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            ".clawdhub",
            "dist",
            "build",
        }
        self._ignore_suffixes = {".pyc", ".pyo", ".swp", ".tmp"}
        self._ignore_names = {".DS_Store"}

        self._last_scan_snapshot: Dict[str, Any] = {}
        self._request_timestamps: Deque[float] = deque()
        self._quota_day = int(time.time() // 86400)
        self._quota_day_count = 0

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _now() -> int:
        return int(time.time())

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "api_key_configured": bool(self.api_key),
            "api_base": self.api_base,
            "skills_dir": str(self.skills_dir),
            "skills_dir_exists": self.skills_dir.exists() and self.skills_dir.is_dir(),
            "upload_if_missing_default": bool(self.upload_if_missing_default),
            "enforcement_mode": self.enforcement_mode,
            "rate_limit_per_minute": int(self.max_requests_per_minute),
            "rate_limit_per_day": int(self.max_requests_per_day),
            "requests_in_last_minute": len(self._request_timestamps),
            "requests_today": int(self._quota_day_count),
            "max_poll_attempts": int(self.max_poll_attempts),
            "poll_interval_seconds": int(self.poll_interval_seconds),
            "last_scan": dict(self._last_scan_snapshot),
            "timestamp": self._now(),
        }

    def _consume_quota(self) -> Optional[str]:
        now = time.time()
        quota_day = int(now // 86400)
        if quota_day != self._quota_day:
            self._quota_day = quota_day
            self._quota_day_count = 0

        while self._request_timestamps and now - self._request_timestamps[0] >= 60:
            self._request_timestamps.popleft()

        if len(self._request_timestamps) >= self.max_requests_per_minute:
            return "rate_limit_per_minute"
        if self._quota_day_count >= self.max_requests_per_day:
            return "rate_limit_per_day"

        self._request_timestamps.append(now)
        self._quota_day_count += 1
        return None

    def _resolve_skill_dir(self, skill_name: str) -> Path:
        candidate = str(skill_name or "").strip()
        if not self._SKILL_NAME_RE.fullmatch(candidate):
            raise ValueError("invalid_skill_name")
        base = self.skills_dir.resolve()
        skill_dir = (self.skills_dir / candidate).resolve()
        if base not in skill_dir.parents and skill_dir != base:
            raise ValueError("invalid_skill_path")
        if not skill_dir.exists() or not skill_dir.is_dir():
            raise FileNotFoundError("skill_not_found")
        if not (skill_dir / "SKILL.md").exists():
            raise FileNotFoundError("skill_manifest_missing")
        return skill_dir

    def list_skills(self) -> List[str]:
        if not self.skills_dir.exists() or not self.skills_dir.is_dir():
            return []
        skills: List[str] = []
        for entry in sorted(self.skills_dir.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir():
                continue
            if not (entry / "SKILL.md").exists():
                continue
            skills.append(entry.name)
        return skills[: self.max_skills_per_scan]

    def _should_skip_path(self, path: Path) -> bool:
        if path.name in self._ignore_names:
            return True
        if path.suffix.lower() in self._ignore_suffixes:
            return True
        return any(part in self._ignore_dirs for part in path.parts)

    def _collect_skill_files(self, skill_dir: Path) -> List[Path]:
        collected: List[Path] = []
        for file_path in skill_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(skill_dir)
            if self._should_skip_path(rel):
                continue
            collected.append(rel)
        collected.sort(key=lambda rel: rel.as_posix())
        return collected

    def _build_deterministic_bundle(self, skill_name: str) -> Dict[str, Any]:
        skill_dir = self._resolve_skill_dir(skill_name)
        files = self._collect_skill_files(skill_dir)

        if not files:
            raise ValueError("skill_bundle_empty")

        has_meta = any(path.as_posix() == "_meta.json" for path in files)
        buffer = io.BytesIO()
        with zipfile.ZipFile(
            buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for rel in files:
                absolute = skill_dir / rel
                data = absolute.read_bytes()
                info = zipfile.ZipInfo(filename=rel.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = 0o755 if os.access(absolute, os.X_OK) else 0o644
                info.external_attr = (mode & 0xFFFF) << 16
                archive.writestr(info, data)

            if not has_meta:
                meta = {
                    "bundle_version": 1,
                    "skill": skill_name,
                    "publisher": "sapphire-alpha",
                    "generated_at": 0,
                    "file_count": len(files),
                    "files": [path.as_posix() for path in files],
                }
                meta_bytes = json.dumps(meta, sort_keys=True, separators=(",", ":")).encode("utf-8")
                info = zipfile.ZipInfo(filename="_meta.json", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, meta_bytes)

        bundle = buffer.getvalue()
        return {
            "bytes": bundle,
            "sha256": hashlib.sha256(bundle).hexdigest(),
            "size_bytes": len(bundle),
            "file_count": len(files),
            "meta_embedded": not has_meta,
        }

    async def _vt_request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        payload: Any = None,
        data: Any = None,
    ) -> Dict[str, Any]:
        if not self.api_key:
            return {"ok": False, "status": 0, "error": "vt_api_key_missing"}
        quota_error = self._consume_quota()
        if quota_error:
            return {"ok": False, "status": 429, "error": quota_error}

        headers = {"x-apikey": self.api_key}
        if payload is not None:
            headers["Content-Type"] = "application/json"

        timeout = aiohttp.ClientTimeout(total=self.bundle_timeout_seconds)
        url = f"{self.api_base}{path}"
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method.upper(),
                    url,
                    params=params,
                    json=payload,
                    data=data,
                    headers=headers,
                ) as response:
                    text = await response.text()
                    parsed: Any = {}
                    if text:
                        try:
                            parsed = json.loads(text)
                        except Exception:
                            parsed = {}
                    return {
                        "ok": 200 <= response.status < 300,
                        "status": int(response.status),
                        "json": parsed if isinstance(parsed, dict) else {},
                        "text": text[:1200],
                    }
        except Exception as exc:
            return {"ok": False, "status": 0, "error": str(exc)}

    @staticmethod
    def _extract_nested(obj: Dict[str, Any], path: List[str], fallback: Any = None) -> Any:
        current: Any = obj
        for key in path:
            if not isinstance(current, dict):
                return fallback
            current = current.get(key)
        return current if current is not None else fallback

    @classmethod
    def _normalize_verdict_label(cls, value: Any) -> str:
        token = str(value or "").strip().lower()
        if not token:
            return "unknown"
        if any(part in token for part in {"malicious", "danger", "trojan", "backdoor"}):
            return "malicious"
        if any(part in token for part in {"suspicious", "warning", "risky"}):
            return "suspicious"
        if any(part in token for part in {"benign", "clean", "safe", "harmless"}):
            return "benign"
        return "unknown"

    @classmethod
    def _merge_verdicts(cls, primary: str, secondary: str) -> str:
        first = cls._normalize_verdict_label(primary)
        second = cls._normalize_verdict_label(secondary)
        if cls._SEVERITY_ORDER.get(second, 0) > cls._SEVERITY_ORDER.get(first, 0):
            return second
        return first

    def _extract_code_insight_verdict(self, payloads: List[Dict[str, Any]]) -> str:
        verdict = "unknown"

        def walk(node: Any, key_hint: str = "") -> None:
            nonlocal verdict
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered_key = str(key or "").strip().lower()
                    if isinstance(value, str):
                        if any(token in lowered_key for token in {"insight", "verdict", "classification", "ai"}):
                            verdict = self._merge_verdicts(verdict, value)
                    walk(value, lowered_key)
                return
            if isinstance(node, list):
                for item in node:
                    walk(item, key_hint)

        for payload in payloads:
            walk(payload)
        return verdict

    def _build_verdict_summary(
        self,
        file_report: Optional[Dict[str, Any]],
        analysis_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        file_stats = self._extract_nested(file_report or {}, ["data", "attributes", "last_analysis_stats"], {})
        analysis_stats = self._extract_nested(analysis_report or {}, ["data", "attributes", "stats"], {})
        stats = file_stats if isinstance(file_stats, dict) and file_stats else analysis_stats
        if not isinstance(stats, dict):
            stats = {}

        malicious = int(stats.get("malicious", 0) or 0)
        suspicious = int(stats.get("suspicious", 0) or 0)
        harmless = int(stats.get("harmless", 0) or 0)
        undetected = int(stats.get("undetected", 0) or 0)

        base_verdict = "unknown"
        if malicious > 0:
            base_verdict = "malicious"
        elif suspicious > 0:
            base_verdict = "suspicious"
        elif harmless > 0 and malicious == 0 and suspicious == 0:
            base_verdict = "benign"

        code_insight_verdict = self._extract_code_insight_verdict(
            [file_report or {}, analysis_report or {}]
        )
        final_verdict = self._merge_verdicts(base_verdict, code_insight_verdict)
        policy = self.evaluate_policy(final_verdict)
        return {
            "verdict": final_verdict,
            "base_verdict": base_verdict,
            "code_insight_verdict": code_insight_verdict,
            "stats": {
                "malicious": malicious,
                "suspicious": suspicious,
                "harmless": harmless,
                "undetected": undetected,
            },
            "policy": policy,
        }

    def evaluate_policy(self, verdict: str) -> Dict[str, Any]:
        normalized = self._normalize_verdict_label(verdict)
        mode = self.enforcement_mode
        blocked = False
        reason = "allowed"

        if mode == "off":
            blocked = False
            reason = "enforcement_disabled"
        elif mode == "warn":
            blocked = False
            reason = "warning_only"
        elif mode == "block_malicious":
            blocked = normalized == "malicious"
            reason = "blocked_malicious" if blocked else "allowed_non_malicious"
        elif mode == "block_suspicious":
            blocked = normalized in {"malicious", "suspicious"}
            reason = "blocked_suspicious_or_malicious" if blocked else "allowed_benign"

        return {
            "mode": mode,
            "blocked": blocked,
            "allowed": not blocked,
            "reason": reason,
        }

    async def _lookup_file(self, sha256: str) -> Dict[str, Any]:
        response = await self._vt_request("GET", f"/files/{sha256}")
        if response.get("status") == 404:
            return {"ok": True, "found": False, "status": 404, "report": {}}
        if not response.get("ok"):
            return {
                "ok": False,
                "found": False,
                "status": int(response.get("status", 0) or 0),
                "error": str(response.get("error") or response.get("text") or "lookup_failed")[:200],
                "report": {},
            }
        return {
            "ok": True,
            "found": True,
            "status": int(response.get("status", 0) or 0),
            "report": response.get("json", {}),
        }

    async def _upload_bundle(self, skill_name: str, bundle: bytes) -> Dict[str, Any]:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            bundle,
            filename=f"{skill_name}.zip",
            content_type="application/zip",
        )
        response = await self._vt_request("POST", "/files", data=form)
        if not response.get("ok"):
            return {
                "ok": False,
                "status": int(response.get("status", 0) or 0),
                "error": str(response.get("error") or response.get("text") or "upload_failed")[:200],
                "analysis_id": "",
            }
        analysis_id = str(
            self._extract_nested(response.get("json", {}), ["data", "id"], "")
        ).strip()
        return {
            "ok": bool(analysis_id),
            "status": int(response.get("status", 0) or 0),
            "analysis_id": analysis_id,
            "error": "" if analysis_id else "analysis_id_missing",
        }

    async def _poll_analysis(self, analysis_id: str) -> Dict[str, Any]:
        if not analysis_id:
            return {"ok": False, "status": "missing_analysis_id", "report": {}}

        latest_report: Dict[str, Any] = {}
        latest_status = ""
        for attempt in range(1, self.max_poll_attempts + 1):
            response = await self._vt_request("GET", f"/analyses/{analysis_id}")
            if response.get("ok"):
                latest_report = response.get("json", {})
                latest_status = str(
                    self._extract_nested(latest_report, ["data", "attributes", "status"], "")
                ).strip()
                if latest_status.lower() in {"completed", "finished"}:
                    return {
                        "ok": True,
                        "status": latest_status,
                        "attempt": attempt,
                        "report": latest_report,
                    }
            if attempt < self.max_poll_attempts:
                await asyncio.sleep(self.poll_interval_seconds)

        return {
            "ok": False,
            "status": latest_status or "timeout",
            "attempt": self.max_poll_attempts,
            "report": latest_report,
        }

    async def scan_skill(self, skill_name: str, upload_if_missing: Optional[bool] = None) -> Dict[str, Any]:
        started = self._now()
        upload_enabled = self.upload_if_missing_default if upload_if_missing is None else bool(upload_if_missing)

        if not self.enabled:
            return {"ok": False, "error": "vt_scanning_disabled", "timestamp": started}
        if not self.api_key:
            return {"ok": False, "error": "vt_api_key_missing", "timestamp": started}

        try:
            bundle = self._build_deterministic_bundle(skill_name)
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc), "timestamp": started}
        except ValueError as exc:
            return {"ok": False, "error": str(exc), "timestamp": started}
        except Exception as exc:
            return {"ok": False, "error": f"bundle_failed:{exc}", "timestamp": started}

        sha256 = str(bundle.get("sha256", ""))
        lookup = await self._lookup_file(sha256)
        if not lookup.get("ok") and int(lookup.get("status", 0) or 0) == 429:
            return {
                "ok": False,
                "error": "vt_rate_limited",
                "detail": str(lookup.get("error", "")),
                "timestamp": started,
            }
        upload_result: Dict[str, Any] = {}
        analysis_result: Dict[str, Any] = {}
        file_report = lookup.get("report", {}) if lookup.get("found") else {}

        if lookup.get("ok") and not lookup.get("found") and upload_enabled:
            upload_result = await self._upload_bundle(skill_name, bundle.get("bytes", b""))
            if int(upload_result.get("status", 0) or 0) == 429:
                return {
                    "ok": False,
                    "error": "vt_rate_limited",
                    "detail": str(upload_result.get("error", "")),
                    "timestamp": started,
                }
            if upload_result.get("ok"):
                analysis_result = await self._poll_analysis(str(upload_result.get("analysis_id", "")))
                refreshed_lookup = await self._lookup_file(sha256)
                if refreshed_lookup.get("found"):
                    file_report = refreshed_lookup.get("report", {})
                    lookup = refreshed_lookup

        verdict = self._build_verdict_summary(
            file_report=file_report if isinstance(file_report, dict) else {},
            analysis_report=analysis_result.get("report", {}) if isinstance(analysis_result, dict) else {},
        )

        report = {
            "ok": True,
            "skill": skill_name,
            "timestamp": started,
            "bundle": {
                "sha256": sha256,
                "size_bytes": int(bundle.get("size_bytes", 0)),
                "file_count": int(bundle.get("file_count", 0)),
                "meta_embedded": bool(bundle.get("meta_embedded", False)),
            },
            "vt": {
                "lookup_ok": bool(lookup.get("ok")),
                "lookup_hit": bool(lookup.get("found")),
                "lookup_status": int(lookup.get("status", 0) or 0),
                "uploaded": bool(upload_result.get("ok")),
                "upload_status": int(upload_result.get("status", 0) or 0),
                "upload_error": str(upload_result.get("error", "")).strip(),
                "analysis_id": str(upload_result.get("analysis_id", "")).strip(),
                "analysis_completed": bool(analysis_result.get("ok")),
                "analysis_status": str(analysis_result.get("status", "")).strip(),
                "analysis_attempts": int(analysis_result.get("attempt", 0) or 0),
                "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
            },
            "security": verdict,
        }

        self._last_scan_snapshot = {
            "type": "single",
            "skill": skill_name,
            "timestamp": started,
            "verdict": verdict.get("verdict", "unknown"),
            "policy": verdict.get("policy", {}),
            "report_url": f"https://www.virustotal.com/gui/file/{sha256}",
        }
        return report

    async def scan_all_skills(self, upload_if_missing: Optional[bool] = None) -> Dict[str, Any]:
        started = self._now()
        if not self.enabled:
            return {"ok": False, "error": "vt_scanning_disabled", "timestamp": started}
        if not self.api_key:
            return {"ok": False, "error": "vt_api_key_missing", "timestamp": started}

        skills = self.list_skills()
        results: List[Dict[str, Any]] = []
        counts = {"benign": 0, "suspicious": 0, "malicious": 0, "unknown": 0}
        blocked = 0
        for skill in skills:
            try:
                scan_result = await self.scan_skill(skill, upload_if_missing=upload_if_missing)
            except Exception as exc:
                scan_result = {"ok": False, "skill": skill, "error": f"scan_failed:{exc}"}
            results.append(scan_result)
            verdict = str(
                self._extract_nested(scan_result, ["security", "verdict"], "unknown")
            ).strip().lower()
            if verdict not in counts:
                verdict = "unknown"
            counts[verdict] += 1
            if bool(self._extract_nested(scan_result, ["security", "policy", "blocked"], False)):
                blocked += 1

        summary = {
            "ok": True,
            "timestamp": started,
            "skills_scanned": len(results),
            "counts": counts,
            "blocked_count": blocked,
            "results": results,
        }
        self._last_scan_snapshot = {
            "type": "all",
            "timestamp": started,
            "skills_scanned": len(results),
            "counts": counts,
            "blocked_count": blocked,
        }
        logger.info(
            "VirusTotal skill scan complete: skills={} benign={} suspicious={} malicious={} blocked={}",
            len(results),
            counts["benign"],
            counts["suspicious"],
            counts["malicious"],
            blocked,
        )
        return summary
