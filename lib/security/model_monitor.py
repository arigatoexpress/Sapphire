"""Model integrity monitor — SHA-256 verification + Jinja2 backdoor detection.

Verifies Ollama model blobs against their manifest digests and scans Jinja2
model templates for suspicious patterns (prompt injection, data exfiltration,
hidden instructions).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc  # noqa: UP017 — compat alias for Python <3.11

log = logging.getLogger("sapphire.security.models")

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class BlobVerification:
    """Result of verifying a single blob file."""

    digest: str
    path: str = ""
    expected_size: int = 0
    actual_size: int = 0
    sha256_match: bool = True
    size_match: bool = True
    error: str = ""


@dataclass
class ModelVerification:
    """Integrity check result for one Ollama model."""

    name: str
    tag: str = "latest"
    manifest_found: bool = True
    blob_count: int = 0
    blobs_verified: int = 0
    blobs_failed: int = 0
    blobs: list[BlobVerification] = field(default_factory=list)
    status: str = "ok"  # ok / warning / corrupt / missing


@dataclass
class TemplateAlert:
    """A suspicious pattern found in a Jinja2 template."""

    model: str
    pattern_name: str
    severity: str  # critical / high / medium / low
    matched_text: str
    line_number: int = 0
    description: str = ""


@dataclass
class ModelScanResult:
    """Aggregate result of a full model integrity scan."""

    timestamp: str = ""
    total_models: int = 0
    verified_count: int = 0
    failed_count: int = 0
    template_alerts: list[TemplateAlert] = field(default_factory=list)
    models: list[ModelVerification] = field(default_factory=list)
    score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Backdoor detection patterns
# ---------------------------------------------------------------------------

BACKDOOR_PATTERNS: list[dict[str, str]] = [
    {
        "name": "hidden_system_prompt",
        "pattern": r"(?i)(ignore\s+(all\s+)?previous|disregard\s+(all\s+)?instructions|"
        r"you\s+are\s+now\s+(?:DAN|jailbroken|unrestricted))",
        "severity": "critical",
        "description": "Prompt injection / jailbreak instruction in template",
    },
    {
        "name": "data_exfiltration",
        "pattern": r"(?i)(curl\s+https?://|wget\s+|fetch\(|"
        r"requests?\.(get|post)|urllib\.request|"
        r"<script[^>]*src\s*=)",
        "severity": "critical",
        "description": "Potential data exfiltration via network call in template",
    },
    {
        "name": "shell_execution",
        "pattern": r"(?i)(subprocess\.|os\.system\(|os\.popen\(|exec\(|eval\(|"
        r"__import__|`[^`]*`)",
        "severity": "critical",
        "description": "Shell/code execution in template",
    },
    {
        "name": "credential_harvest",
        "pattern": r"(?i)(password|api[_-]?key|secret[_-]?key|token|credential|"
        r"private[_-]?key|ssh[_-]?key).*(?:send|post|upload|exfil|forward)",
        "severity": "high",
        "description": "Possible credential harvesting instruction",
    },
    {
        "name": "hidden_persona",
        "pattern": r"(?i)(you\s+must\s+always|never\s+reveal|"
        r"hidden\s+instruction|secret\s+system\s+prompt|"
        r"do\s+not\s+tell\s+the\s+user)",
        "severity": "high",
        "description": "Hidden persona / concealed instructions",
    },
    {
        "name": "base64_blob",
        "pattern": r"[A-Za-z0-9+/]{80,}={0,2}",
        "severity": "medium",
        "description": "Large base64 blob — may hide encoded payload",
    },
    {
        "name": "url_in_template",
        "pattern": r"https?://(?!ollama\.com|github\.com|huggingface\.co)[^\s\"'<>]+",
        "severity": "low",
        "description": "External URL in template (review manually)",
    },
]


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class ModelMonitor:
    """Verifies Ollama model integrity and scans templates for backdoors."""

    # Default Ollama blob storage paths
    DEFAULT_OLLAMA_DIRS = [
        Path.home() / ".ollama",
        Path("/usr/share/ollama/.ollama"),
    ]

    def __init__(
        self,
        ollama_dir: Path | None = None,
        *,
        verify_sha256: bool = True,
        scan_templates: bool = True,
        ollama_hosts: list[str] | None = None,
    ):
        self.ollama_dir = ollama_dir or self._find_ollama_dir()
        self.verify_sha256 = verify_sha256
        self.scan_templates = scan_templates
        self.ollama_hosts = ollama_hosts or ["127.0.0.1:11434"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self) -> ModelScanResult:
        """Run a full model integrity scan."""
        result = ModelScanResult(timestamp=datetime.now(UTC).isoformat())

        models = self._list_models()
        result.total_models = len(models)

        for model_name, tag in models:
            verification = self._verify_model(model_name, tag)
            result.models.append(verification)

            if verification.status == "ok":
                result.verified_count += 1
            else:
                result.failed_count += 1

        if self.scan_templates:
            result.template_alerts = self._scan_all_templates()

        result.score = self._compute_score(result)
        return result

    # ------------------------------------------------------------------
    # Model enumeration
    # ------------------------------------------------------------------

    def _find_ollama_dir(self) -> Path:
        """Locate the Ollama models directory."""
        for d in self.DEFAULT_OLLAMA_DIRS:
            if d.exists():
                return d
        return self.DEFAULT_OLLAMA_DIRS[0]  # fallback

    def _list_models(self) -> list[tuple[str, str]]:
        """List installed models from manifests directory."""
        models: list[tuple[str, str]] = []
        manifests_dir = self.ollama_dir / "models" / "manifests"
        if not manifests_dir.exists():
            # Try via Ollama API
            return self._list_models_api()
        for registry_dir in manifests_dir.iterdir():
            if not registry_dir.is_dir():
                continue
            for namespace_dir in registry_dir.iterdir():
                if not namespace_dir.is_dir():
                    continue
                for model_dir in namespace_dir.iterdir():
                    if not model_dir.is_dir():
                        continue
                    for tag_file in model_dir.iterdir():
                        if tag_file.is_file():
                            model_name = f"{namespace_dir.name}/{model_dir.name}"
                            if namespace_dir.name == "library":
                                model_name = model_dir.name
                            models.append((model_name, tag_file.name))
        return models

    def _list_models_api(self) -> list[tuple[str, str]]:
        """List models via Ollama HTTP API."""
        for host in self.ollama_hosts:
            url = f"http://{host}/api/tags"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    data = json.loads(resp.read())
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if ":" in name:
                        model, tag = name.rsplit(":", 1)
                    else:
                        model, tag = name, "latest"
                    models.append((model, tag))
                return models
            except Exception as exc:
                log.debug("Ollama API list failed on %s: %s", host, exc)
        return []

    # ------------------------------------------------------------------
    # Blob verification
    # ------------------------------------------------------------------

    def _verify_model(self, model_name: str, tag: str) -> ModelVerification:
        """Verify all blobs for a single model against its manifest."""
        result = ModelVerification(name=model_name, tag=tag)

        manifest = self._load_manifest(model_name, tag)
        if manifest is None:
            result.manifest_found = False
            result.status = "missing"
            return result

        layers = manifest.get("layers", [])
        result.blob_count = len(layers)

        for layer in layers:
            digest = layer.get("digest", "")
            expected_size = layer.get("size", 0)
            blob_result = self._verify_blob(digest, expected_size)
            result.blobs.append(blob_result)

            if blob_result.sha256_match and blob_result.size_match and not blob_result.error:
                result.blobs_verified += 1
            else:
                result.blobs_failed += 1

        if result.blobs_failed > 0:
            result.status = "corrupt"
        elif result.blob_count == 0:
            result.status = "warning"

        return result

    def _load_manifest(self, model_name: str, tag: str) -> dict | None:
        """Load a model's manifest JSON."""
        # Normalize model name to path
        if "/" in model_name:
            namespace, name = model_name.split("/", 1)
        else:
            namespace, name = "library", model_name

        manifest_path = (
            self.ollama_dir / "models" / "manifests" / "registry.ollama.ai" / namespace / name / tag
        )
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to read manifest %s: %s", manifest_path, exc)
            return None

    def _verify_blob(self, digest: str, expected_size: int) -> BlobVerification:
        """Verify a single blob's SHA-256 and size."""
        result = BlobVerification(digest=digest, expected_size=expected_size)

        # Digest format: "sha256:abc123..."
        if not digest.startswith("sha256:"):
            result.error = f"Unsupported digest format: {digest[:20]}"
            result.sha256_match = False
            return result

        expected_hash = digest.split(":", 1)[1]
        blob_path = self.ollama_dir / "models" / "blobs" / digest.replace(":", "-")
        result.path = str(blob_path)

        if not blob_path.exists():
            result.error = "Blob file missing"
            result.sha256_match = False
            result.size_match = False
            return result

        # Size check (fast)
        actual_size = blob_path.stat().st_size
        result.actual_size = actual_size
        result.size_match = actual_size == expected_size

        # SHA-256 check (can be slow for large models)
        if self.verify_sha256:
            sha = hashlib.sha256()
            try:
                with open(blob_path, "rb") as f:
                    while chunk := f.read(1 << 20):  # 1 MB chunks
                        sha.update(chunk)
                actual_hash = sha.hexdigest()
                result.sha256_match = actual_hash == expected_hash
                if not result.sha256_match:
                    result.error = f"SHA-256 mismatch: expected {expected_hash[:12]}..., got {actual_hash[:12]}..."
            except OSError as exc:
                result.error = f"Read error: {exc}"
                result.sha256_match = False

        return result

    # ------------------------------------------------------------------
    # Template scanning
    # ------------------------------------------------------------------

    def _scan_all_templates(self) -> list[TemplateAlert]:
        """Scan all Jinja2 / Modelfile templates for backdoor patterns."""
        alerts: list[TemplateAlert] = []
        blobs_dir = self.ollama_dir / "models" / "blobs"
        if not blobs_dir.exists():
            return alerts

        for blob_file in blobs_dir.iterdir():
            if not blob_file.is_file():
                continue
            # Only scan small files (templates are typically < 50 KB)
            try:
                size = blob_file.stat().st_size
            except OSError:
                continue
            if size > 100_000 or size < 10:
                continue

            try:
                content = blob_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            # Heuristic: if it looks like a template (has Jinja2 markers or
            # Modelfile syntax), scan it
            if not self._looks_like_template(content):
                continue

            model_name = blob_file.name  # digest-based name
            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern_def in BACKDOOR_PATTERNS:
                    if re.search(pattern_def["pattern"], line):
                        alerts.append(
                            TemplateAlert(
                                model=model_name,
                                pattern_name=pattern_def["name"],
                                severity=pattern_def["severity"],
                                matched_text=line.strip()[:120],
                                line_number=line_num,
                                description=pattern_def["description"],
                            )
                        )
        return alerts

    @staticmethod
    def _looks_like_template(content: str) -> bool:
        """Heuristic check if content is a Jinja2 template or Modelfile."""
        markers = [
            "{{",
            "{%",
            "TEMPLATE",
            "SYSTEM",
            "FROM",
            "PARAMETER",
            "<<SYS>>",
            "[INST]",
            "<|im_start|>",
            "<|system|>",
        ]
        return any(m in content for m in markers)

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_score(result: ModelScanResult) -> float:
        """Compute a 0-100 model integrity score."""
        if result.total_models == 0:
            return 100.0
        score = 100.0
        # Failed integrity checks
        if result.total_models > 0:
            integrity_pct = result.failed_count / result.total_models
            score -= integrity_pct * 50
        # Template alerts
        critical_alerts = sum(1 for a in result.template_alerts if a.severity == "critical")
        high_alerts = sum(1 for a in result.template_alerts if a.severity == "high")
        score -= min(30, critical_alerts * 15)
        score -= min(15, high_alerts * 5)
        score -= min(5, len(result.template_alerts) * 0.5)
        return round(max(0.0, score), 1)
