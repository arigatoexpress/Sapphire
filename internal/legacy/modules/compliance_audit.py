"""
Compliance and audit system for regulatory requirements and audit trails.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of auditable events."""

    TRADE_EXECUTION = "trade_execution"
    RISK_ASSESSMENT = "risk_assessment"
    POSITION_CHANGE = "position_change"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIGURATION_CHANGE = "configuration_change"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    ERROR_OCCURRED = "error_occurred"
    COMPLIANCE_CHECK = "compliance_check"


class ComplianceLevel(Enum):
    """Compliance requirement levels."""

    BASIC = "basic"
    ENHANCED = "enhanced"
    STRICT = "strict"


@dataclass
class AuditEvent:
    """Represents an auditable event."""

    event_id: str
    event_type: AuditEventType
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource: Optional[str] = None
    action: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    compliance_flags: List[str] = field(default_factory=list)
    hash_chain: Optional[str] = None  # For tamper-proof audit trail


@dataclass
class ComplianceRule:
    """Represents a compliance rule."""

    rule_id: str
    name: str
    description: str
    severity: str
    category: str
    check_function: Optional[callable] = None
    enabled: bool = True
    last_checked: Optional[datetime] = None
    violations: List[Dict[str, Any]] = field(default_factory=list)


class ComplianceAuditor:
    """Comprehensive compliance and audit system."""

    def __init__(self, compliance_level: ComplianceLevel = ComplianceLevel.ENHANCED):
        self.compliance_level = compliance_level
        self.audit_log: List[AuditEvent] = []
        self.compliance_rules: Dict[str, ComplianceRule] = {}
        self.audit_enabled = True
        self.hash_key = "sapphire-trading-audit-chain"  # In production, use proper key management

        # Initialize compliance rules
        self._initialize_compliance_rules()

    def _initialize_compliance_rules(self):
        """Initialize compliance rules based on compliance level."""
        rules = [
            ComplianceRule(
                rule_id="trade_reporting",
                name="Trade Reporting",
                description="All trades must be reported within regulatory timeframes",
                severity="high",
                category="reporting",
                check_function=self._check_trade_reporting,
            ),
            ComplianceRule(
                rule_id="position_limits",
                name="Position Limits",
                description="Positions must not exceed regulatory limits",
                severity="critical",
                category="risk",
                check_function=self._check_position_limits,
            ),
            ComplianceRule(
                rule_id="market_manipulation",
                name="Market Manipulation Prevention",
                description="Detect and prevent potential market manipulation",
                severity="critical",
                category="conduct",
                check_function=self._check_market_manipulation,
            ),
            ComplianceRule(
                rule_id="data_retention",
                name="Data Retention",
                description="Trading data must be retained for required periods",
                severity="medium",
                category="data",
                check_function=self._check_data_retention,
            ),
            ComplianceRule(
                rule_id="access_controls",
                name="Access Controls",
                description="Access to trading systems must be properly controlled",
                severity="high",
                category="security",
                check_function=self._check_access_controls,
            ),
        ]

        if self.compliance_level in [ComplianceLevel.ENHANCED, ComplianceLevel.STRICT]:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="best_execution",
                        name="Best Execution",
                        description="Trades must achieve best execution standards",
                        severity="medium",
                        category="execution",
                        check_function=self._check_best_execution,
                    ),
                    ComplianceRule(
                        rule_id="record_keeping",
                        name="Record Keeping",
                        description="All trading activities must be properly recorded",
                        severity="high",
                        category="record",
                        check_function=self._check_record_keeping,
                    ),
                ]
            )

        if self.compliance_level == ComplianceLevel.STRICT:
            rules.extend(
                [
                    ComplianceRule(
                        rule_id="real_time_monitoring",
                        name="Real-time Monitoring",
                        description="Continuous monitoring of trading activities",
                        severity="high",
                        category="monitoring",
                        check_function=self._check_real_time_monitoring,
                    ),
                    ComplianceRule(
                        rule_id="circuit_breakers",
                        name="Circuit Breakers",
                        description="Automatic trading halts during extreme conditions",
                        severity="critical",
                        category="safety",
                        check_function=self._check_circuit_breakers,
                    ),
                ]
            )

        for rule in rules:
            self.compliance_rules[rule.rule_id] = rule

    async def audit_event(
        self,
        event_type: AuditEventType,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        resource: Optional[str] = None,
        compliance_flags: Optional[List[str]] = None,
    ) -> str:
        """Record an auditable event."""
        if not self.audit_enabled:
            return ""

        event = AuditEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            timestamp=datetime.now(),
            user_id=user_id,
            session_id=session_id,
            resource=resource,
            action=action,
            details=details or {},
            compliance_flags=compliance_flags or [],
        )

        # Create hash chain for tamper-proof audit trail
        event.hash_chain = self._create_hash_chain(event)

        # Store event
        self.audit_log.append(event)

        # Keep only recent events (last 30 days)
        cutoff = datetime.now() - timedelta(days=30)
        self.audit_log = [e for e in self.audit_log if e.timestamp > cutoff]

        logger.info(f"Audit Event: {event_type.value} - {action}")
        return event.event_id

    def _generate_event_id(self) -> str:
        """Generate a unique event ID."""
        return f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(datetime.now()) % 10000}"

    def _create_hash_chain(self, event: AuditEvent) -> str:
        """Create a hash chain for tamper-proof audit trail."""
        # Get previous event hash
        prev_hash = ""
        if self.audit_log:
            prev_hash = self.audit_log[-1].hash_chain or ""

        # Create event data string
        event_data = f"{event.event_id}{event.event_type.value}{event.timestamp.isoformat()}{event.action}{json.dumps(event.details, sort_keys=True)}"

        # Create hash
        combined = f"{prev_hash}{event_data}".encode()
        current_hash = hmac.new(self.hash_key.encode(), combined, hashlib.sha256).hexdigest()

        return current_hash

    async def run_compliance_checks(self) -> Dict[str, Any]:
        """Run all compliance checks."""
        results = {
            "timestamp": datetime.now(),
            "compliance_level": self.compliance_level.value,
            "rules_checked": 0,
            "violations_found": 0,
            "critical_violations": 0,
            "rule_results": {},
        }

        for rule_id, rule in self.compliance_rules.items():
            if not rule.enabled:
                continue

            try:
                if rule.check_function:
                    violations = await rule.check_function()
                    rule.violations = violations
                    rule.last_checked = datetime.now()

                    results["rules_checked"] += 1

                    if violations:
                        results["violations_found"] += len(violations)
                        critical_count = len(
                            [v for v in violations if v.get("severity") == "critical"]
                        )
                        results["critical_violations"] += critical_count

                    results["rule_results"][rule_id] = {
                        "status": "checked",
                        "violations": len(violations),
                        "critical": critical_count,
                        "last_checked": rule.last_checked,
                    }
                else:
                    results["rule_results"][rule_id] = {
                        "status": "no_check_function",
                        "violations": 0,
                        "critical": 0,
                    }

            except Exception as e:
                logger.error(f"Error checking compliance rule {rule_id}: {e}")
                results["rule_results"][rule_id] = {"status": "error", "error": str(e)}

        return results

    async def generate_compliance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive compliance report."""
        compliance_results = await self.run_compliance_checks()

        report = {
            "generated_at": datetime.now(),
            "compliance_level": self.compliance_level.value,
            "overall_status": (
                "compliant" if compliance_results["critical_violations"] == 0 else "non_compliant"
            ),
            "summary": {
                "rules_checked": compliance_results["rules_checked"],
                "total_violations": compliance_results["violations_found"],
                "critical_violations": compliance_results["critical_violations"],
            },
            "rules": {},
            "audit_trail_integrity": self._verify_audit_trail_integrity(),
            "recommendations": [],
        }

        # Add rule details
        for rule_id, rule in self.compliance_rules.items():
            rule_result = compliance_results["rule_results"].get(rule_id, {})
            report["rules"][rule_id] = {
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity,
                "category": rule.category,
                "status": rule_result.get("status", "unknown"),
                "violations": rule.violations,
                "last_checked": rule.last_checked,
            }

        # Generate recommendations
        if compliance_results["critical_violations"] > 0:
            report["recommendations"].append(
                "Immediate action required for critical compliance violations"
            )
        if compliance_results["violations_found"] > 5:
            report["recommendations"].append(
                "Multiple compliance violations detected - review system configuration"
            )

        return report

    def _verify_audit_trail_integrity(self) -> bool:
        """Verify the integrity of the audit trail."""
        if len(self.audit_log) <= 1:
            return True

        for i in range(1, len(self.audit_log)):
            prev_event = self.audit_log[i - 1]
            curr_event = self.audit_log[i]

            # Recalculate expected hash
            event_data = f"{curr_event.event_id}{curr_event.event_type.value}{curr_event.timestamp.isoformat()}{curr_event.action}{json.dumps(curr_event.details, sort_keys=True)}"
            combined = f"{prev_event.hash_chain}{event_data}".encode()
            expected_hash = hmac.new(self.hash_key.encode(), combined, hashlib.sha256).hexdigest()

            if expected_hash != curr_event.hash_chain:
                logger.error(f"Audit trail integrity violation at event {curr_event.event_id}")
                return False

        return True

    # Compliance check implementations
    async def _check_trade_reporting(self) -> List[Dict[str, Any]]:
        """Check trade reporting compliance."""
        violations = []
        # Implementation would check trade reporting timeliness
        # This is a placeholder for the actual implementation
        return violations

    async def _check_position_limits(self) -> List[Dict[str, Any]]:
        """Check position limit compliance."""
        violations = []
        # Implementation would check position sizes against limits
        # This is a placeholder for the actual implementation
        return violations

    async def _check_market_manipulation(self) -> List[Dict[str, Any]]:
        """Check for market manipulation patterns."""
        violations = []
        # Implementation would analyze trading patterns for manipulation
        # This is a placeholder for the actual implementation
        return violations

    async def _check_data_retention(self) -> List[Dict[str, Any]]:
        """Check data retention compliance."""
        violations = []
        # Implementation would verify data retention periods
        # This is a placeholder for the actual implementation
        return violations

    async def _check_access_controls(self) -> List[Dict[str, Any]]:
        """Check access control compliance."""
        violations = []
        # Implementation would verify access controls
        # This is a placeholder for the actual implementation
        return violations

    async def _check_best_execution(self) -> List[Dict[str, Any]]:
        """Check best execution compliance."""
        violations = []
        # Implementation would verify best execution standards
        # This is a placeholder for the actual implementation
        return violations

    async def _check_record_keeping(self) -> List[Dict[str, Any]]:
        """Check record keeping compliance."""
        violations = []
        # Implementation would verify record keeping standards
        # This is a placeholder for the actual implementation
        return violations

    async def _check_real_time_monitoring(self) -> List[Dict[str, Any]]:
        """Check real-time monitoring compliance."""
        violations = []
        # Implementation would verify real-time monitoring
        # This is a placeholder for the actual implementation
        return violations

    async def _check_circuit_breakers(self) -> List[Dict[str, Any]]:
        """Check circuit breaker compliance."""
        violations = []
        # Implementation would verify circuit breaker functionality
        # This is a placeholder for the actual implementation
        return violations

    def get_audit_events(
        self,
        event_type: Optional[AuditEventType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Retrieve audit events with optional filtering."""
        events = self.audit_log

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if start_time:
            events = [e for e in events if e.timestamp >= start_time]

        if end_time:
            events = [e for e in events if e.timestamp <= end_time]

        return events[-limit:]


# Global compliance auditor instance
_compliance_auditor: Optional[ComplianceAuditor] = None


def get_compliance_auditor() -> ComplianceAuditor:
    """Get the global compliance auditor instance."""
    global _compliance_auditor
    if _compliance_auditor is None:
        _compliance_auditor = ComplianceAuditor()
    return _compliance_auditor


# Convenience functions
async def audit_trade_execution(trade_details: Dict[str, Any], user_id: Optional[str] = None):
    """Audit a trade execution."""
    auditor = get_compliance_auditor()
    await auditor.audit_event(
        AuditEventType.TRADE_EXECUTION,
        "trade_executed",
        details=trade_details,
        user_id=user_id,
        compliance_flags=["trade_reporting", "best_execution"],
    )


async def audit_risk_assessment(risk_details: Dict[str, Any]):
    """Audit a risk assessment."""
    auditor = get_compliance_auditor()
    await auditor.audit_event(
        AuditEventType.RISK_ASSESSMENT,
        "risk_assessed",
        details=risk_details,
        compliance_flags=["position_limits", "risk_management"],
    )


async def generate_compliance_report() -> Dict[str, Any]:
    """Generate a compliance report."""
    auditor = get_compliance_auditor()
    return await auditor.generate_compliance_report()
