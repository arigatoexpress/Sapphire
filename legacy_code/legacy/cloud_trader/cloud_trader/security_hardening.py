"""
Security hardening measures for production trading systems.
"""

import asyncio
import hashlib
import hmac
import logging
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SecurityEventType(Enum):
    """Types of security events."""

    AUTHENTICATION_ATTEMPT = "authentication_attempt"
    AUTHORIZATION_FAILURE = "authorization_failure"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    ANOMALOUS_REQUEST = "anomalous_request"
    POTENTIAL_ATTACK = "potential_attack"


@dataclass
class SecurityConfig:
    """Security configuration settings."""

    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    suspicious_patterns: List[str] = field(
        default_factory=lambda: [
            r"union.*select",  # SQL injection
            r"<script",  # XSS
            r"\.\./",  # Path traversal
            r"eval\(",  # Code injection
        ]
    )
    enable_ip_whitelisting: bool = False
    allowed_ips: Set[str] = field(default_factory=set)
    enable_request_signing: bool = True
    session_timeout_minutes: int = 30


@dataclass
class SecurityEvent:
    """Represents a security event."""

    event_id: str
    event_type: SecurityEventType
    timestamp: datetime
    ip_address: str
    user_agent: str
    details: Dict[str, Any]
    severity: str = "medium"
    handled: bool = False


@dataclass
class RateLimitEntry:
    """Rate limiting entry for an IP/user."""

    requests: int = 0
    window_start: float = 0
    blocked_until: Optional[float] = None


class SecurityHardening:
    """Comprehensive security hardening for trading systems."""

    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        self.security_events: List[SecurityEvent] = []
        self.rate_limits: Dict[str, RateLimitEntry] = {}
        self.login_attempts: Dict[str, List[float]] = {}
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.request_signatures: Set[str] = set()

        # Keep only recent events
        self.max_events = 10000

    def generate_secure_token(self, length: int = 32) -> str:
        """Generate a cryptographically secure token."""
        return secrets.token_urlsafe(length)

    def hash_password(self, password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """Hash a password with salt."""
        if salt is None:
            salt = secrets.token_hex(16)

        # Use PBKDF2 for password hashing
        import hashlib

        hash_obj = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), 100000  # 100,000 iterations
        )

        return hash_obj.hex(), salt

    def verify_password(self, password: str, hash_str: str, salt: str) -> bool:
        """Verify a password against its hash."""
        expected_hash, _ = self.hash_password(password, salt)
        return hmac.compare_digest(expected_hash, hash_str)

    def check_rate_limit(self, identifier: str) -> tuple[bool, Optional[float]]:
        """Check if request should be rate limited."""
        now = time.time()
        entry = self.rate_limits.get(identifier, RateLimitEntry())

        # Reset window if expired
        if now - entry.window_start > self.config.rate_limit_window_seconds:
            entry.requests = 0
            entry.window_start = now

        entry.requests += 1
        self.rate_limits[identifier] = entry

        # Check if blocked
        if entry.blocked_until and now < entry.blocked_until:
            return False, entry.blocked_until - now

        # Check if limit exceeded
        if entry.requests > self.config.rate_limit_requests:
            # Block for the window duration
            entry.blocked_until = now + self.config.rate_limit_window_seconds
            self.rate_limits[identifier] = entry

            # Log security event
            self._log_security_event(
                SecurityEventType.RATE_LIMIT_EXCEEDED,
                identifier,
                "",
                {"requests": entry.requests, "limit": self.config.rate_limit_requests},
            )

            return False, self.config.rate_limit_window_seconds

        return True, None

    def check_login_attempts(self, identifier: str) -> bool:
        """Check if account is locked due to failed login attempts."""
        if identifier not in self.login_attempts:
            return True

        attempts = self.login_attempts[identifier]
        now = time.time()

        # Remove old attempts
        cutoff = now - (self.config.lockout_duration_minutes * 60)
        attempts = [a for a in attempts if a > cutoff]

        if len(attempts) >= self.config.max_login_attempts:
            # Account is locked
            self._log_security_event(
                SecurityEventType.AUTHENTICATION_ATTEMPT,
                identifier,
                "",
                {"action": "account_locked", "attempts": len(attempts)},
            )
            return False

        return True

    def record_login_attempt(self, identifier: str, success: bool):
        """Record a login attempt."""
        if success:
            # Clear failed attempts on successful login
            self.login_attempts.pop(identifier, None)
            self._log_security_event(
                SecurityEventType.AUTHENTICATION_ATTEMPT,
                identifier,
                "",
                {"action": "login_success"},
            )
        else:
            # Record failed attempt
            if identifier not in self.login_attempts:
                self.login_attempts[identifier] = []
            self.login_attempts[identifier].append(time.time())

            self._log_security_event(
                SecurityEventType.AUTHENTICATION_ATTEMPT,
                identifier,
                "",
                {"action": "login_failed", "attempts": len(self.login_attempts[identifier])},
            )

    def validate_request_signature(
        self, request_data: str, signature: str, secret_key: str
    ) -> bool:
        """Validate request signature for authenticity."""
        if not self.config.enable_request_signing:
            return True

        expected_signature = hmac.new(
            secret_key.encode(), request_data.encode(), hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    def check_suspicious_patterns(
        self, request_data: str, ip_address: str, user_agent: str
    ) -> List[str]:
        """Check for suspicious patterns in requests."""
        violations = []

        for pattern in self.config.suspicious_patterns:
            if re.search(pattern, request_data, re.IGNORECASE):
                violations.append(f"Pattern detected: {pattern}")
                self._log_security_event(
                    SecurityEventType.SUSPICIOUS_ACTIVITY,
                    ip_address,
                    user_agent,
                    {"pattern": pattern, "data": request_data[:200]},
                )

        return violations

    def create_session(self, user_id: str, ip_address: str, user_agent: str) -> str:
        """Create a new authenticated session."""
        session_id = self.generate_secure_token()

        self.active_sessions[session_id] = {
            "user_id": user_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "created_at": time.time(),
            "last_activity": time.time(),
        }

        self._log_security_event(
            SecurityEventType.AUTHENTICATION_ATTEMPT,
            ip_address,
            user_agent,
            {"action": "session_created", "user_id": user_id, "session_id": session_id},
        )

        return session_id

    def validate_session(self, session_id: str, ip_address: str = None) -> bool:
        """Validate an active session."""
        session = self.active_sessions.get(session_id)
        if not session:
            return False

        now = time.time()

        # Check session timeout
        if now - session["created_at"] > (self.config.session_timeout_minutes * 60):
            self.destroy_session(session_id)
            return False

        # Update last activity
        session["last_activity"] = now

        # Optional: Check IP consistency
        if ip_address and session["ip_address"] != ip_address:
            self._log_security_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                ip_address,
                "",
                {"action": "ip_mismatch", "original_ip": session["ip_address"]},
            )
            # Could optionally invalidate session here

        return True

    def destroy_session(self, session_id: str):
        """Destroy an active session."""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            self._log_security_event(
                SecurityEventType.AUTHENTICATION_ATTEMPT,
                session["ip_address"],
                session["user_agent"],
                {"action": "session_destroyed", "user_id": session["user_id"]},
            )
            del self.active_sessions[session_id]

    def check_ip_whitelist(self, ip_address: str) -> bool:
        """Check if IP address is whitelisted."""
        if not self.config.enable_ip_whitelisting:
            return True

        return ip_address in self.config.allowed_ips

    def sanitize_input(self, input_data: str) -> str:
        """Sanitize user input to prevent injection attacks."""
        # Basic sanitization - remove potentially dangerous characters
        sanitized = re.sub(r"[<>]", "", input_data)  # Remove angle brackets
        sanitized = re.sub(r"'", "''", sanitized)  # Escape single quotes for SQL
        sanitized = re.sub(r'"', '""', sanitized)  # Escape double quotes

        # Limit length
        if len(sanitized) > 1000:
            sanitized = sanitized[:1000] + "..."

        return sanitized

    def encrypt_sensitive_data(self, data: str, key: str) -> str:
        """Encrypt sensitive data."""
        import base64

        from cryptography.fernet import Fernet

        # Generate key from password (in production, use proper key management)
        key_bytes = hashlib.sha256(key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(fernet_key)

        encrypted = fernet.encrypt(data.encode())
        return base64.urlsafe_b64encode(encrypted).decode()

    def decrypt_sensitive_data(self, encrypted_data: str, key: str) -> str:
        """Decrypt sensitive data."""
        import base64

        from cryptography.fernet import Fernet

        key_bytes = hashlib.sha256(key.encode()).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        fernet = Fernet(fernet_key)

        encrypted_bytes = base64.urlsafe_b64decode(encrypted_data)
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()

    def _log_security_event(
        self,
        event_type: SecurityEventType,
        ip_address: str,
        user_agent: str,
        details: Dict[str, Any],
    ):
        """Log a security event."""
        event = SecurityEvent(
            event_id=f"sec_{int(time.time())}_{secrets.token_hex(4)}",
            event_type=event_type,
            timestamp=datetime.now(),
            ip_address=ip_address,
            user_agent=user_agent,
            details=details,
        )

        self.security_events.append(event)

        # Keep only recent events
        if len(self.security_events) > self.max_events:
            self.security_events = self.security_events[-self.max_events :]

        # Log to system logger
        logger.warning(f"Security Event: {event_type.value} from {ip_address}")

    def get_security_report(self) -> Dict[str, Any]:
        """Generate a security status report."""
        now = datetime.now()
        recent_events = [
            e for e in self.security_events if (now - e.timestamp).total_seconds() < 3600
        ]  # Last hour

        # Count events by type
        event_counts = {}
        for event in recent_events:
            event_type = event.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        # Active sessions
        active_sessions = len(self.active_sessions)

        # Rate limited IPs
        rate_limited = sum(
            1
            for entry in self.rate_limits.values()
            if entry.blocked_until and time.time() < entry.blocked_until
        )

        return {
            "timestamp": now,
            "active_sessions": active_sessions,
            "rate_limited_ips": rate_limited,
            "recent_security_events": event_counts,
            "total_events_logged": len(self.security_events),
            "security_config": {
                "rate_limiting_enabled": True,
                "ip_whitelisting_enabled": self.config.enable_ip_whitelisting,
                "request_signing_enabled": self.config.enable_request_signing,
                "session_timeout_minutes": self.config.session_timeout_minutes,
            },
        }

    async def security_health_check(self) -> Dict[str, Any]:
        """Perform a security health check."""
        issues = []

        # Check for excessive failed login attempts
        for identifier, attempts in self.login_attempts.items():
            recent_attempts = [a for a in attempts if time.time() - a < 3600]  # Last hour
            if len(recent_attempts) > self.config.max_login_attempts:
                issues.append(f"Excessive login attempts for {identifier}")

        # Check for high rate limiting
        high_rate_limits = sum(
            1
            for entry in self.rate_limits.values()
            if entry.requests > self.config.rate_limit_requests * 2
        )
        if high_rate_limits > 10:
            issues.append(f"High rate limiting activity: {high_rate_limits} IPs")

        # Check for suspicious patterns
        suspicious_events = [
            e
            for e in self.security_events
            if e.event_type == SecurityEventType.SUSPICIOUS_ACTIVITY
            and (datetime.now() - e.timestamp).total_seconds() < 3600
        ]
        if suspicious_events:
            issues.append(f"Suspicious activity detected: {len(suspicious_events)} events")

        return {
            "status": "healthy" if not issues else "warning",
            "issues": issues,
            "recommendations": (
                [
                    "Monitor security events regularly",
                    "Review failed authentication attempts",
                    "Consider updating security rules based on patterns",
                ]
                if issues
                else []
            ),
        }


# Global security hardening instance
_security_hardening: Optional[SecurityHardening] = None


def get_security_hardening() -> SecurityHardening:
    """Get the global security hardening instance."""
    global _security_hardening
    if _security_hardening is None:
        _security_hardening = SecurityHardening()
    return _security_hardening


# Convenience functions
def check_rate_limit(identifier: str) -> tuple[bool, Optional[float]]:
    """Check rate limiting for an identifier."""
    return get_security_hardening().check_rate_limit(identifier)


def validate_session(session_id: str, ip_address: str = None) -> bool:
    """Validate a user session."""
    return get_security_hardening().validate_session(session_id, ip_address)


def sanitize_input(input_data: str) -> str:
    """Sanitize user input."""
    return get_security_hardening().sanitize_input(input_data)


def get_security_status() -> Dict[str, Any]:
    """Get current security status."""
    hardening = get_security_hardening()
    return {
        "security_report": hardening.get_security_report(),
        "health_check": asyncio.run(hardening.security_health_check()),
    }
