"""
Molthub / ClawdHub Skill Security Auditor for Sapphire Scout.

Scans skill.md files and skill bundles for supply-chain attacks:
  - Credential exfiltration (reading .env, API keys, private keys)
  - Unauthorized network egress (webhook.site, pastebin, etc.)
  - Instruction injection (hidden prompts that override safety)
  - Unsigned / unverified provenance

Produces audit reports with severity ratings and isnad (provenance) chains.

Designed for integration with Molthub community audit system.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger


# ── Threat Categories ─────────────────────────────────────────────

class ThreatSeverity(Enum):
    CRITICAL = "critical"   # Active credential theft / code execution
    HIGH = "high"           # Suspicious data access or egress patterns
    MEDIUM = "medium"       # Missing security controls / unsigned
    LOW = "low"             # Cosmetic or informational
    CLEAN = "clean"         # No threats detected


class ThreatCategory(Enum):
    CREDENTIAL_THEFT = "credential_theft"
    DATA_EXFILTRATION = "data_exfiltration"
    INSTRUCTION_INJECTION = "instruction_injection"
    EXCESSIVE_PERMISSIONS = "excessive_permissions"
    UNSIGNED_PROVENANCE = "unsigned_provenance"
    OBFUSCATED_CODE = "obfuscated_code"
    NETWORK_EGRESS = "network_egress"
    FILESYSTEM_ACCESS = "filesystem_access"


# ── Detection Patterns ────────────────────────────────────────────

# Credential theft: reading secrets, env files, private keys
CREDENTIAL_PATTERNS = [
    # Direct env file access
    (r"\.env\b", "References .env file", ThreatSeverity.HIGH),
    (r"~/\.clawdbot/", "Accesses ClawdBot config directory", ThreatSeverity.CRITICAL),
    (r"~/\.claude/", "Accesses Claude config directory", ThreatSeverity.CRITICAL),
    (r"~/\.config/", "Accesses user config directory", ThreatSeverity.HIGH),
    (r"process\.env", "Reads environment variables", ThreatSeverity.MEDIUM),
    (r"os\.environ", "Reads environment variables (Python)", ThreatSeverity.MEDIUM),
    # API key patterns
    (r"API[_\-]?KEY", "References API keys", ThreatSeverity.MEDIUM),
    (r"SECRET[_\-]?KEY", "References secret keys", ThreatSeverity.HIGH),
    (r"PRIVATE[_\-]?KEY", "References private keys", ThreatSeverity.CRITICAL),
    (r"Bearer\s+[A-Za-z0-9\-_\.]+", "Contains bearer token pattern", ThreatSeverity.HIGH),
    # Direct secret reading
    (r"readFile.*\.env", "Reads .env file contents", ThreatSeverity.CRITICAL),
    (r"cat\s+.*\.env", "Reads .env file via shell", ThreatSeverity.CRITICAL),
    (r"cat\s+.*id_rsa", "Reads SSH private key", ThreatSeverity.CRITICAL),
    (r"cat\s+.*\.ssh/", "Reads SSH directory contents", ThreatSeverity.CRITICAL),
]

# Data exfiltration: sending data to external endpoints
EXFIL_PATTERNS = [
    (r"webhook\.site", "Sends data to webhook.site (known exfil endpoint)", ThreatSeverity.CRITICAL),
    (r"pastebin\.com", "Sends data to pastebin (potential exfil)", ThreatSeverity.HIGH),
    (r"requestbin\.", "Sends data to requestbin (known exfil)", ThreatSeverity.CRITICAL),
    (r"pipedream\.net", "Sends data to pipedream (potential exfil)", ThreatSeverity.HIGH),
    (r"ngrok\.io", "Sends data to ngrok tunnel", ThreatSeverity.HIGH),
    (r"burpcollaborator", "BurpSuite collaborator endpoint", ThreatSeverity.CRITICAL),
    (r"interactsh\.", "Interactsh exfil endpoint", ThreatSeverity.CRITICAL),
    (r"POST\s+https?://", "Sends HTTP POST to external URL", ThreatSeverity.MEDIUM),
    (r"fetch\s*\(.*https?://", "Fetches external URL", ThreatSeverity.MEDIUM),
    (r"curl\s+.*-d\s", "Uses curl with data payload", ThreatSeverity.HIGH),
    (r"wget\s+", "Downloads external resource", ThreatSeverity.MEDIUM),
]

# Instruction injection: hidden prompts trying to override agent behavior
INJECTION_PATTERNS = [
    (r"ignore\s+(previous|all|your)\s+(instructions|rules|constraints)", "Instruction override attempt", ThreatSeverity.CRITICAL),
    (r"you\s+are\s+now\s+", "Role reassignment injection", ThreatSeverity.CRITICAL),
    (r"system\s*:\s*you\s+are", "System prompt injection", ThreatSeverity.CRITICAL),
    (r"pretend\s+(you|to)\s+(are|be)", "Social engineering via pretending", ThreatSeverity.HIGH),
    (r"<\s*hidden\s*>|display:\s*none|visibility:\s*hidden", "Hidden content", ThreatSeverity.HIGH),
    (r"base64\.\s*(encode|decode)", "Base64 encoding (potential obfuscation)", ThreatSeverity.MEDIUM),
    (r"eval\s*\(", "Dynamic code evaluation", ThreatSeverity.HIGH),
    (r"exec\s*\(", "Dynamic code execution", ThreatSeverity.HIGH),
    (r"Function\s*\(", "Dynamic function creation (JS)", ThreatSeverity.HIGH),
]

# Excessive filesystem access
FILESYSTEM_PATTERNS = [
    (r"readdir|listdir|os\.walk", "Enumerates directory contents", ThreatSeverity.MEDIUM),
    (r"glob\s*\(.*\*", "Glob pattern filesystem scan", ThreatSeverity.MEDIUM),
    (r"/etc/passwd", "Reads system user database", ThreatSeverity.CRITICAL),
    (r"/etc/shadow", "Reads system password hashes", ThreatSeverity.CRITICAL),
    (r"~/.aws/", "Accesses AWS credentials", ThreatSeverity.CRITICAL),
    (r"~/.gcloud/|~/.config/gcloud", "Accesses GCloud credentials", ThreatSeverity.CRITICAL),
    (r"~/.kube/config", "Accesses Kubernetes config", ThreatSeverity.CRITICAL),
]


# ── Data Structures ───────────────────────────────────────────────

@dataclass
class ThreatFinding:
    """A single detected threat in a skill."""

    category: ThreatCategory
    severity: ThreatSeverity
    description: str
    evidence: str         # The matched text/line
    line_number: int = 0  # Line where found (0 = unknown)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "description": self.description,
            "evidence": self.evidence[:200],
            "line_number": self.line_number,
        }


@dataclass
class IsnadLink:
    """A link in the provenance (isnad) chain."""

    agent_id: str
    role: str       # author, auditor, voucher
    timestamp: float
    verdict: str    # clean, suspicious, malicious
    confidence: float
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "timestamp": self.timestamp,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "notes": self.notes[:200],
        }


@dataclass
class SkillAuditReport:
    """Complete audit report for a skill."""

    skill_name: str
    skill_hash: str             # SHA256 of content
    findings: List[ThreatFinding] = field(default_factory=list)
    isnad_chain: List[IsnadLink] = field(default_factory=list)
    overall_severity: ThreatSeverity = ThreatSeverity.CLEAN
    permission_manifest: Dict[str, bool] = field(default_factory=dict)
    audited_at: float = 0.0
    auditor_id: str = "SAPPHIRE_SCOUT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "skill_hash": self.skill_hash,
            "overall_severity": self.overall_severity.value,
            "finding_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "isnad_chain": [l.to_dict() for l in self.isnad_chain],
            "permission_manifest": self.permission_manifest,
            "audited_at": self.audited_at,
            "auditor_id": self.auditor_id,
        }

    def get_summary(self) -> str:
        """Human-readable audit summary."""
        severity_emoji = {
            ThreatSeverity.CRITICAL: "🔴",
            ThreatSeverity.HIGH: "🟠",
            ThreatSeverity.MEDIUM: "🟡",
            ThreatSeverity.LOW: "🟢",
            ThreatSeverity.CLEAN: "✅",
        }
        emoji = severity_emoji.get(self.overall_severity, "❓")

        lines = [
            f"{emoji} *Skill Audit: {self.skill_name}*",
            f"  Severity: {self.overall_severity.value.upper()}",
            f"  Hash: `{self.skill_hash[:16]}...`",
            f"  Findings: {len(self.findings)}",
        ]

        # Group findings by category
        categories: Dict[str, int] = {}
        for f in self.findings:
            cat = f.category.value
            categories[cat] = categories.get(cat, 0) + 1
        for cat, count in sorted(categories.items()):
            lines.append(f"    {cat}: {count}")

        # Permission manifest
        if self.permission_manifest:
            requested = [k for k, v in self.permission_manifest.items() if v]
            if requested:
                lines.append(f"  Permissions: {', '.join(requested)}")

        # Isnad chain
        if self.isnad_chain:
            lines.append(f"  Isnad chain: {len(self.isnad_chain)} links")
            for link in self.isnad_chain[-3:]:
                lines.append(
                    f"    {link.role}: {link.agent_id} → {link.verdict} "
                    f"({link.confidence:.0%})"
                )

        return "\n".join(lines)


# ── Skill Auditor ─────────────────────────────────────────────────

class SkillAuditor:
    """
    Scans skill content for supply-chain attack patterns.

    Usage:
        auditor = SkillAuditor()
        report = auditor.audit_skill("weather_skill", skill_content)
        if report.overall_severity in (ThreatSeverity.CRITICAL, ThreatSeverity.HIGH):
            # Block installation, alert community
            ...
    """

    def __init__(self, auditor_id: str = "SAPPHIRE_SCOUT") -> None:
        self.auditor_id = auditor_id
        self._compiled_patterns: List[tuple] = []
        self._compile_all_patterns()
        # Audit history for dedup and stats
        self._audit_history: List[SkillAuditReport] = []
        self._max_history = 200

    def _compile_all_patterns(self) -> None:
        """Pre-compile all detection patterns for performance."""
        all_patterns = [
            (CREDENTIAL_PATTERNS, ThreatCategory.CREDENTIAL_THEFT),
            (EXFIL_PATTERNS, ThreatCategory.DATA_EXFILTRATION),
            (INJECTION_PATTERNS, ThreatCategory.INSTRUCTION_INJECTION),
            (FILESYSTEM_PATTERNS, ThreatCategory.FILESYSTEM_ACCESS),
        ]
        for pattern_list, category in all_patterns:
            for pattern, description, severity in pattern_list:
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                    self._compiled_patterns.append(
                        (compiled, description, severity, category)
                    )
                except re.error as e:
                    logger.warning(f"Bad pattern '{pattern}': {e}")

    def audit_skill(
        self,
        skill_name: str,
        content: str,
        author_id: Optional[str] = None,
        existing_isnad: Optional[List[IsnadLink]] = None,
    ) -> SkillAuditReport:
        """
        Audit a skill's content for security threats.

        Args:
            skill_name: Name/identifier of the skill
            content: Full text content of the skill (skill.md, code, etc.)
            author_id: Optional author identifier for isnad chain
            existing_isnad: Optional existing provenance chain

        Returns:
            SkillAuditReport with all findings and severity assessment
        """
        skill_hash = hashlib.sha256(content.encode()).hexdigest()

        report = SkillAuditReport(
            skill_name=skill_name,
            skill_hash=skill_hash,
            audited_at=time.time(),
            auditor_id=self.auditor_id,
        )

        # Build isnad chain
        if existing_isnad:
            report.isnad_chain.extend(existing_isnad)
        if author_id:
            report.isnad_chain.append(IsnadLink(
                agent_id=author_id,
                role="author",
                timestamp=time.time(),
                verdict="unverified",
                confidence=0.0,
            ))

        # Run pattern matching line by line
        lines = content.split("\n")
        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue  # Skip empty lines and comments

            for compiled, description, severity, category in self._compiled_patterns:
                match = compiled.search(stripped)
                if match:
                    report.findings.append(ThreatFinding(
                        category=category,
                        severity=severity,
                        description=description,
                        evidence=stripped[:200],
                        line_number=line_num,
                    ))

        # Detect permission requirements
        report.permission_manifest = self._extract_permissions(content)

        # Check for obfuscation patterns
        self._check_obfuscation(content, report)

        # Calculate overall severity
        report.overall_severity = self._compute_overall_severity(report.findings)

        # Add auditor's isnad link
        report.isnad_chain.append(IsnadLink(
            agent_id=self.auditor_id,
            role="auditor",
            timestamp=time.time(),
            verdict=report.overall_severity.value,
            confidence=self._compute_confidence(report),
            notes=f"{len(report.findings)} findings across {len(set(f.category for f in report.findings))} categories",
        ))

        # Record in history
        self._audit_history.append(report)
        if len(self._audit_history) > self._max_history:
            self._audit_history = self._audit_history[-self._max_history:]

        logger.info(
            f"🔍 Skill audit: {skill_name} → {report.overall_severity.value} "
            f"({len(report.findings)} findings)"
        )
        return report

    def _extract_permissions(self, content: str) -> Dict[str, bool]:
        """Detect what permissions a skill implicitly requests."""
        lower = content.lower()
        return {
            "filesystem_read": bool(re.search(r"read.*file|open\(|readFile|cat\s", lower)),
            "filesystem_write": bool(re.search(r"write.*file|writeFile|>\s|>>", lower)),
            "network_access": bool(re.search(r"fetch|http|curl|wget|request|socket", lower)),
            "env_access": bool(re.search(r"\.env|process\.env|os\.environ|getenv", lower)),
            "shell_exec": bool(re.search(r"exec\(|system\(|spawn|child_process|subprocess", lower)),
            "crypto_keys": bool(re.search(r"private.key|secret.key|api.key|token", lower)),
        }

    def _check_obfuscation(self, content: str, report: SkillAuditReport) -> None:
        """Detect obfuscation techniques used to hide malicious intent."""
        # Base64 encoded strings longer than 40 chars
        b64_matches = re.findall(r"[A-Za-z0-9+/=]{40,}", content)
        if len(b64_matches) > 2:
            report.findings.append(ThreatFinding(
                category=ThreatCategory.OBFUSCATED_CODE,
                severity=ThreatSeverity.HIGH,
                description=f"Contains {len(b64_matches)} base64-like encoded strings",
                evidence=f"Found {len(b64_matches)} long encoded strings",
            ))

        # Unicode homoglyph attacks (e.g., using Cyrillic 'а' instead of Latin 'a')
        non_ascii = sum(1 for c in content if ord(c) > 127 and not c.isspace())
        if non_ascii > 10:
            report.findings.append(ThreatFinding(
                category=ThreatCategory.OBFUSCATED_CODE,
                severity=ThreatSeverity.MEDIUM,
                description=f"Contains {non_ascii} non-ASCII characters (possible homoglyph attack)",
                evidence=f"{non_ascii} non-ASCII chars detected",
            ))

        # Excessive whitespace or zero-width chars (hidden content)
        zwc = content.count("\u200b") + content.count("\u200c") + content.count("\u200d") + content.count("\ufeff")
        if zwc > 0:
            report.findings.append(ThreatFinding(
                category=ThreatCategory.OBFUSCATED_CODE,
                severity=ThreatSeverity.HIGH,
                description=f"Contains {zwc} zero-width characters (hidden content)",
                evidence=f"{zwc} zero-width chars found",
            ))

    def _compute_overall_severity(self, findings: List[ThreatFinding]) -> ThreatSeverity:
        """Determine overall severity from individual findings."""
        if not findings:
            return ThreatSeverity.CLEAN

        severity_order = [
            ThreatSeverity.CRITICAL,
            ThreatSeverity.HIGH,
            ThreatSeverity.MEDIUM,
            ThreatSeverity.LOW,
        ]
        for sev in severity_order:
            if any(f.severity == sev for f in findings):
                return sev
        return ThreatSeverity.LOW

    def _compute_confidence(self, report: SkillAuditReport) -> float:
        """Compute audit confidence based on findings quality."""
        if not report.findings:
            return 0.9  # High confidence in clean result

        critical_count = sum(1 for f in report.findings if f.severity == ThreatSeverity.CRITICAL)
        high_count = sum(1 for f in report.findings if f.severity == ThreatSeverity.HIGH)

        # More critical findings = higher confidence in malicious verdict
        if critical_count >= 2:
            return 0.95
        if critical_count >= 1:
            return 0.85
        if high_count >= 2:
            return 0.75
        return 0.6

    # ── Queries & Stats ───────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return audit statistics."""
        if not self._audit_history:
            return {"total_audits": 0, "threat_breakdown": {}}

        severity_counts: Dict[str, int] = {}
        category_counts: Dict[str, int] = {}
        for report in self._audit_history:
            sev = report.overall_severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            for f in report.findings:
                cat = f.category.value
                category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total_audits": len(self._audit_history),
            "severity_breakdown": severity_counts,
            "category_breakdown": category_counts,
            "critical_skills": [
                r.skill_name for r in self._audit_history
                if r.overall_severity == ThreatSeverity.CRITICAL
            ],
        }

    def format_community_report(self, report: SkillAuditReport) -> str:
        """Format an audit report for Molthub community posting."""
        lines = [
            f"🔒 *Security Audit: {report.skill_name}*",
            "",
            f"Verdict: {report.overall_severity.value.upper()}",
            f"Hash: `{report.skill_hash[:32]}`",
            f"Audited by: {report.auditor_id}",
            "",
        ]

        if report.findings:
            lines.append(f"*Findings ({len(report.findings)}):*")
            for i, f in enumerate(report.findings[:10], 1):
                sev_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                    f.severity.value, "❓"
                )
                lines.append(f"  {i}. {sev_icon} [{f.category.value}] {f.description}")
                if f.line_number:
                    lines.append(f"     Line {f.line_number}: `{f.evidence[:80]}`")
        else:
            lines.append("No threats detected. ✅")

        if report.permission_manifest:
            requested = [k for k, v in report.permission_manifest.items() if v]
            if requested:
                lines.append("")
                lines.append(f"*Permissions requested:* {', '.join(requested)}")

        if report.isnad_chain:
            lines.append("")
            lines.append(f"*Provenance chain ({len(report.isnad_chain)} links):*")
            for link in report.isnad_chain:
                lines.append(
                    f"  {link.role}: {link.agent_id} → {link.verdict} ({link.confidence:.0%})"
                )

        lines.append("")
        lines.append(
            "Would you install a skill audited by 3 trusted agents vs one that had not? "
            "The agent internet needs a security layer."
        )

        return "\n".join(lines)
