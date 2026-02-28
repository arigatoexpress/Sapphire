import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Pattern, Tuple
from urllib.parse import urlparse

import aiohttp
from fastapi import FastAPI, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - optional at runtime
    firestore = None  # type: ignore[assignment]


_NUMERIC_CHALLENGE_RE = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*(\+|-|\*|x|×|/|÷)\s*(-?\d+(?:\.\d+)?)",
    flags=re.IGNORECASE,
)
_MOLTBOOK_KEY_RE = re.compile(r"\bmoltbook_[A-Za-z0-9\-_]{8,}\b", flags=re.IGNORECASE)
_INLINE_TOKEN_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*([^\s,;]+)"
)


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _split_csv(value: str) -> List[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _split_regex_list(value: str) -> List[str]:
    return [part.strip() for part in str(value or "").split(";") if part.strip()]


def _safe_excerpt(value: str, max_len: int = 500) -> str:
    text = str(value or "")[:max_len]
    text = _INLINE_TOKEN_RE.sub(r"\1=[REDACTED]", text)
    text = _MOLTBOOK_KEY_RE.sub("[REDACTED_MOLTBOOK_KEY]", text)
    return text


@dataclass(frozen=True)
class SandboxConfig:
    project_id: str
    sandbox_token: str
    register_url: str
    post_url: str
    external_api_token: str
    register_use_token: bool
    timeout_seconds: int
    max_retries: int
    dry_run: bool
    auto_verify_enabled: bool
    verify_url: str
    allowed_hosts: Tuple[str, ...]
    allowed_path_patterns: Tuple[Pattern[str], ...]
    audit_collection: str

    @classmethod
    def from_env(cls) -> "SandboxConfig":
        default_hosts = "moltbook.com,www.moltbook.com,molthub.com,www.molthub.com"
        hosts = tuple(sorted(set(_split_csv(os.getenv("SCOUT_SANDBOX_ALLOWED_HOSTS", default_hosts)))))

        default_patterns = [
            r"^/api/v1/agents/register$",
            r"^/api/v1/posts$",
            r"^/api/v1/posts/[A-Za-z0-9_-]+/comments$",
            r"^/api/v1/verify$",
        ]
        pattern_raw = os.getenv("SCOUT_SANDBOX_ALLOWED_PATH_PATTERNS", "")
        if pattern_raw.strip():
            pattern_source = _split_regex_list(pattern_raw)
        else:
            pattern_source = default_patterns

        compiled_patterns: List[Pattern[str]] = []
        for item in pattern_source:
            try:
                compiled_patterns.append(re.compile(item))
            except re.error as exc:
                logger.warning(f"Ignoring invalid SCOUT_SANDBOX path regex '{item}': {exc}")

        if not compiled_patterns:
            compiled_patterns = [re.compile(item) for item in default_patterns]

        return cls(
            project_id=str(os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))).strip(),
            sandbox_token=str(os.getenv("SCOUT_SANDBOX_TOKEN", "")).strip(),
            register_url=str(os.getenv("SCOUT_SANDBOX_REGISTER_URL", "https://www.moltbook.com/api/v1/agents/register")).strip(),
            post_url=str(os.getenv("SCOUT_SANDBOX_POST_URL", "https://www.moltbook.com/api/v1/posts")).strip(),
            external_api_token=str(os.getenv("SCOUT_SANDBOX_EXTERNAL_API_TOKEN", "")).strip(),
            register_use_token=_bool_env("SCOUT_SANDBOX_REGISTER_USE_TOKEN", False),
            timeout_seconds=_int_env("SCOUT_SANDBOX_TIMEOUT_SECONDS", 15, 5, 60),
            max_retries=_int_env("SCOUT_SANDBOX_MAX_RETRIES", 3, 1, 6),
            dry_run=_bool_env("SCOUT_SANDBOX_DRY_RUN", False),
            auto_verify_enabled=_bool_env("SCOUT_SANDBOX_AUTO_VERIFY_ENABLED", True),
            verify_url=str(os.getenv("SCOUT_SANDBOX_VERIFY_URL", "")).strip(),
            allowed_hosts=hosts,
            allowed_path_patterns=tuple(compiled_patterns),
            audit_collection=str(os.getenv("SCOUT_SANDBOX_AUDIT_COLLECTION", "scout_sandbox_audit")).strip() or "scout_sandbox_audit",
        )


class DispatchRequest(BaseModel):
    action: str = Field(pattern="^(register|publish|comment)$")
    outbound_payload: Dict[str, Any] = Field(default_factory=dict)
    external_url_hint: str = ""
    note: str = ""
    source: str = "alpha-engine"
    request_id: str = ""


class FirestoreAuditLogger:
    def __init__(self, project_id: str, collection: str):
        self._collection_name = collection
        self._client = None
        if firestore is None:
            logger.warning("google-cloud-firestore unavailable; scout sandbox audit logs will be stdout only")
            return

        try:
            self._client = firestore.Client(project=project_id or None)
        except Exception as exc:  # pragma: no cover - runtime env dependent
            logger.warning(f"Failed to initialize Firestore client for scout sandbox audit logs: {exc}")
            self._client = None

    def write(self, record: Dict[str, Any]) -> None:
        logger.info(f"scout_sandbox_audit: {json.dumps(record, default=str)[:1200]}")
        if not self._client:
            return

        try:
            audit_id = str(record.get("audit_id", "")).strip() or str(uuid.uuid4())
            self._client.collection(self._collection_name).document(audit_id).set(record)
        except Exception as exc:  # pragma: no cover - runtime env dependent
            logger.warning(f"Failed writing scout sandbox audit record: {exc}")


class ScoutSandboxBroker:
    _ALL_NUMBER_WORDS = {
        "zero", "one", "two", "three", "four", "five", "six", "seven",
        "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
        "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
        "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty",
        "ninety", "hundred", "thousand", "point", "and",
    }
    _ALL_OPERATOR_WORDS = {
        "plus", "minus", "times", "add", "subtract", "over", "divide",
        "divided", "multiplied", "another", "nother", "x",
    }
    _ALL_KNOWN_WORDS = _ALL_NUMBER_WORDS | _ALL_OPERATOR_WORDS

    def __init__(self, config: SandboxConfig):
        self.config = config
        self.audit = FirestoreAuditLogger(config.project_id, config.audit_collection)

    @staticmethod
    def _is_moltbook_api_url(url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        if not parsed.netloc:
            return False
        host = parsed.netloc.lower().split(":", 1)[0]
        return host in {"www.moltbook.com", "moltbook.com"} and parsed.path.startswith("/api/v1")

    @staticmethod
    def _derive_moltbook_verify_url(url: str) -> str:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}/api/v1/verify"

    def _is_allowed_url(self, url: str) -> Tuple[bool, str]:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme.lower() != "https":
            return False, "only_https_allowed"
        host = parsed.netloc.lower().split(":", 1)[0]
        if host not in self.config.allowed_hosts:
            return False, "host_not_allowlisted"
        path = parsed.path or "/"
        if not any(pattern.match(path) for pattern in self.config.allowed_path_patterns):
            return False, "path_not_allowlisted"
        return True, "ok"

    def _resolve_target_url(self, req: DispatchRequest) -> Tuple[str, str]:
        action = req.action
        if action == "register":
            return self.config.register_url, "register"
        if action == "publish":
            return (req.external_url_hint.strip() or self.config.post_url), "publish"
        if action == "comment":
            return req.external_url_hint.strip(), "comment"
        return "", "unknown"

    def _audit_record(self, req: DispatchRequest, target_url: str, dispatch: Dict[str, Any], latency_ms: int) -> Dict[str, Any]:
        payload_json = json.dumps(req.outbound_payload, sort_keys=True, default=str)
        payload_hash = json.dumps(
            {"sha256": __import__("hashlib").sha256(payload_json.encode("utf-8")).hexdigest()}
        )
        parsed = urlparse(str(target_url or ""))
        return {
            "audit_id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "source": req.source,
            "request_id": req.request_id or "",
            "action": req.action,
            "target_scheme": parsed.scheme,
            "target_host": parsed.netloc.split(":", 1)[0] if parsed.netloc else "",
            "target_path": parsed.path,
            "dry_run": self.config.dry_run,
            "payload_keys": sorted(list(req.outbound_payload.keys())),
            "payload_hash": payload_hash,
            "note_excerpt": _safe_excerpt(req.note, max_len=220),
            "latency_ms": latency_ms,
            "result": {
                "dispatched": bool(dispatch.get("dispatched")),
                "reason": str(dispatch.get("reason", "")).strip()[:120],
                "status": dispatch.get("status"),
                "attempt": dispatch.get("attempt"),
                "mode": dispatch.get("mode"),
            },
        }

    async def dispatch(self, req: DispatchRequest) -> Dict[str, Any]:
        started = time.time()
        target_url, mode = self._resolve_target_url(req)
        if not target_url:
            result = {
                "dispatched": False,
                "reason": "target_url_missing",
                "mode": "scout_sandbox",
            }
            self.audit.write(self._audit_record(req, target_url, result, int((time.time() - started) * 1000)))
            return result

        allowed, reason = self._is_allowed_url(target_url)
        if not allowed:
            result = {
                "dispatched": False,
                "reason": reason,
                "mode": "scout_sandbox",
                "target_url": _safe_excerpt(target_url, max_len=180),
            }
            self.audit.write(self._audit_record(req, target_url, result, int((time.time() - started) * 1000)))
            return result

        if self.config.dry_run:
            result = {
                "dispatched": True,
                "reason": "dry_run",
                "status": 200,
                "mode": "scout_sandbox",
                "target_url": _safe_excerpt(target_url, max_len=180),
            }
            self.audit.write(self._audit_record(req, target_url, result, int((time.time() - started) * 1000)))
            return result

        token = ""
        if mode in {"publish", "comment"}:
            token = self.config.external_api_token
        elif mode == "register" and self.config.register_use_token:
            token = self.config.external_api_token

        if mode in {"publish", "comment"} and not token:
            result = {
                "dispatched": False,
                "reason": "external_api_token_missing",
                "mode": "scout_sandbox",
            }
            self.audit.write(self._audit_record(req, target_url, result, int((time.time() - started) * 1000)))
            return result

        dispatch = await self._dispatch_external(target_url, req.outbound_payload, token=token)
        dispatch["mode"] = "scout_sandbox"
        dispatch["target_url"] = _safe_excerpt(target_url, max_len=180)

        latency_ms = int((time.time() - started) * 1000)
        self.audit.write(self._audit_record(req, target_url, dispatch, latency_ms))
        return dispatch

    async def _dispatch_external(self, url: str, payload: Dict[str, Any], token: str = "") -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
        last_result: Dict[str, Any] = {"dispatched": False, "reason": "request_failed:unknown"}

        for attempt in range(1, self.config.max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, json=payload, headers=headers) as response:
                        response_text = await response.text()
                        safe_excerpt = _safe_excerpt(response_text, max_len=600)

                        parsed: Dict[str, Any] = {}
                        try:
                            maybe = json.loads(response_text)
                            if isinstance(maybe, dict):
                                parsed = maybe
                        except Exception:
                            parsed = {}

                        api_success = parsed.get("success")
                        ok = 200 <= response.status < 300 and (
                            not isinstance(api_success, bool) or bool(api_success)
                        )

                        metadata: Dict[str, Any] = {}
                        if isinstance(parsed.get("error"), str):
                            metadata["api_error"] = str(parsed.get("error", ""))[:160]
                        if isinstance(parsed.get("hint"), str):
                            metadata["hint"] = str(parsed.get("hint", ""))[:220]
                        if isinstance(parsed.get("agent"), dict):
                            agent_obj = parsed.get("agent", {})
                            metadata["claim_url"] = str(agent_obj.get("claim_url", "")).strip()[:220]
                            metadata["verification_code"] = (
                                str(agent_obj.get("verification_code", "")).strip()[:80]
                            )
                        if isinstance(parsed.get("verification"), dict):
                            verification_obj = parsed.get("verification", {})
                            metadata["verification_required"] = True
                            metadata["verification_code"] = (
                                str(verification_obj.get("code", "")).strip()[:80]
                            )
                            metadata["verification_challenge"] = (
                                str(verification_obj.get("challenge", "")).strip()[:220]
                            )
                        if bool(parsed.get("verification_required")):
                            metadata["verification_required"] = True

                        reason = "ok" if ok else ("api_error" if parsed else "http_error")

                        if ok and metadata.get("verification_required") and self.config.auto_verify_enabled:
                            verify_url = self.config.verify_url or self._derive_moltbook_verify_url(url)
                            verify_result = await self._verify_moltbook_challenge(
                                verify_url=verify_url,
                                verification_code=str(metadata.get("verification_code", "")),
                                challenge=str(metadata.get("verification_challenge", "")),
                                token=token,
                                timeout_seconds=self.config.timeout_seconds,
                            )
                            metadata["verification_attempted"] = True
                            metadata["verification_reason"] = str(verify_result.get("reason", "unknown"))[:80]
                            if verify_result.get("verified"):
                                metadata["verification_status"] = "verified"
                                reason = "ok_verified"
                            else:
                                metadata["verification_status"] = "pending"
                                reason = "ok_pending_verification"

                        if not ok:
                            api_error_lower = str(metadata.get("api_error", "")).lower()
                            if (
                                int(response.status) == 429
                                or "only post once every" in api_error_lower
                                or "slow down" in api_error_lower
                                or "comment again in" in api_error_lower
                            ):
                                reason = "moltbook_rate_limited"
                            elif "pending_claim" in api_error_lower or "pending claim" in api_error_lower:
                                reason = "moltbook_pending_claim"
                            elif (
                                "already registered" in api_error_lower
                                or "already exists" in api_error_lower
                                or "already taken" in api_error_lower
                            ):
                                reason = "moltbook_already_registered"

                        result = {
                            "dispatched": ok,
                            "status": int(response.status),
                            "reason": reason,
                            "response_excerpt": safe_excerpt,
                            "metadata": metadata,
                            "attempt": attempt,
                        }

                        if ok:
                            return result

                        last_result = result
                        retryable_http = (
                            int(response.status) >= 500 or int(response.status) in {408, 429}
                        ) and reason != "moltbook_rate_limited"
                        retryable_api = result["reason"] == "api_error" and metadata.get("api_error") in {
                            "Failed to fetch posts",
                            "Internal Server Error",
                        }
                        if not (retryable_http or retryable_api) or attempt >= self.config.max_retries:
                            return result
            except Exception as exc:
                last_result = {
                    "dispatched": False,
                    "reason": f"request_failed:{_safe_excerpt(str(exc), max_len=180)}",
                    "attempt": attempt,
                }
                if attempt >= self.config.max_retries:
                    return last_result

            await asyncio.sleep(min(3.0, 0.4 * attempt))

        return last_result

    @staticmethod
    def _compute_challenge_result(left: float, operator: str, right: float) -> Optional[float]:
        op = str(operator or "").strip().lower()
        if op in {"x", "×"}:
            op = "*"
        if op == "÷":
            op = "/"
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                return None
            return left / right
        return None

    @staticmethod
    def _normalize_word_token_safe(token: str) -> str:
        value = str(token or "").strip().lower()
        if not value:
            return ""
        if value in ScoutSandboxBroker._ALL_KNOWN_WORDS:
            return value
        deduped = re.sub(r"(.)\1+", r"\1", value)
        if deduped in ScoutSandboxBroker._ALL_KNOWN_WORDS:
            return deduped
        return value

    @classmethod
    def _words_to_number(cls, tokens: List[str]) -> Optional[float]:
        units = {
            "zero": 0,
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "eleven": 11,
            "twelve": 12,
            "thirteen": 13,
            "fourteen": 14,
            "fifteen": 15,
            "sixteen": 16,
            "seventeen": 17,
            "eighteen": 18,
            "nineteen": 19,
        }
        tens = {
            "twenty": 20,
            "thirty": 30,
            "forty": 40,
            "fifty": 50,
            "sixty": 60,
            "seventy": 70,
            "eighty": 80,
            "ninety": 90,
        }
        scales = {"hundred": 100, "thousand": 1000}

        clean = [
            cls._normalize_word_token_safe(token)
            for token in tokens
            if str(token or "").strip()
        ]
        if not clean:
            return None

        total = 0
        current = 0
        decimal_mode = False
        decimal_digits = ""
        consumed = False

        for token in clean:
            if token == "and":
                continue
            if token == "point":
                decimal_mode = True
                continue
            if decimal_mode:
                if token.isdigit():
                    decimal_digits += token
                    consumed = True
                    continue
                if token in units:
                    decimal_digits += str(units[token])
                    consumed = True
                    continue
                return None

            if token.isdigit():
                current += int(token)
                consumed = True
            elif token in units:
                current += units[token]
                consumed = True
            elif token in tens:
                current += tens[token]
                consumed = True
            elif token in scales:
                factor = scales[token]
                if factor == 100:
                    current = max(1, current) * factor
                else:
                    total += max(1, current) * factor
                    current = 0
                consumed = True
            else:
                return None

        if not consumed:
            return None

        value = float(total + current)
        if decimal_digits:
            value = float(f"{int(total + current)}.{decimal_digits}")
        return value

    @classmethod
    def _solve_moltbook_challenge(cls, challenge: str) -> Optional[str]:
        raw = str(challenge or "").strip().lower()
        if not raw:
            return None

        direct = _NUMERIC_CHALLENGE_RE.search(raw)
        if direct:
            left = float(direct.group(1))
            operator = str(direct.group(2))
            right = float(direct.group(3))
            result = cls._compute_challenge_result(left, operator, right)
            if result is None:
                return None
            return f"{result:.2f}"

        cleaned = re.sub(r"[^\w\s+\-*×÷.,?!:;']", " ", raw)
        cleaned = cleaned.replace("-", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = cleaned.replace("×", " * ").replace("÷", " / ")

        replacements = [
            ("multiplied by", " * "),
            ("times", " * "),
            ("divided by", " / "),
            ("plus", " + "),
            ("minus", " - "),
            ("subtract", " - "),
            ("over", " / "),
        ]
        for source, target in replacements:
            cleaned = cleaned.replace(source, target)

        raw_tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?|[+\-*/]", cleaned)
        tokens = [cls._normalize_word_token_safe(token) if token.isalpha() else token for token in raw_tokens]
        if not tokens:
            return None

        parsed_tokens: List[Any] = []
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token in {"+", "-", "*", "/"}:
                parsed_tokens.append(token)
                idx += 1
                continue
            if re.fullmatch(r"-?\d+(?:\.\d+)?", token):
                parsed_tokens.append(float(token))
                idx += 1
                continue
            if token in cls._ALL_NUMBER_WORDS:
                end = idx
                while end < len(tokens) and tokens[end] in cls._ALL_NUMBER_WORDS:
                    end += 1
                number_value = cls._words_to_number(tokens[idx:end])
                if number_value is not None:
                    parsed_tokens.append(number_value)
                    idx = end
                    continue
            idx += 1

        for offset in range(0, len(parsed_tokens) - 2):
            left = parsed_tokens[offset]
            operator = parsed_tokens[offset + 1]
            right = parsed_tokens[offset + 2]
            if isinstance(left, (int, float)) and isinstance(operator, str) and isinstance(right, (int, float)):
                result = cls._compute_challenge_result(float(left), operator, float(right))
                if result is not None:
                    return f"{result:.2f}"

        numeric_terms = [float(item) for item in parsed_tokens if isinstance(item, (int, float))]
        if len(numeric_terms) >= 2:
            return f"{sum(numeric_terms):.2f}"

        return None

    async def _verify_moltbook_challenge(
        self,
        *,
        verify_url: str,
        verification_code: str,
        challenge: str,
        token: str = "",
        timeout_seconds: int = 15,
    ) -> Dict[str, Any]:
        url = str(verify_url or "").strip()
        code = str(verification_code or "").strip()
        if not url or not code:
            return {"verified": False, "reason": "verify_url_or_code_missing"}

        answer = self._solve_moltbook_challenge(challenge)
        if not answer:
            return {"verified": False, "reason": "challenge_unsolved"}

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        payload = {"verification_code": code, "answer": answer}
        timeout = aiohttp.ClientTimeout(total=max(5, min(int(timeout_seconds or 15), 60)))

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    response_text = await response.text()
                    safe_excerpt = _safe_excerpt(response_text, max_len=300)

                    parsed: Dict[str, Any] = {}
                    try:
                        maybe = json.loads(response_text)
                        if isinstance(maybe, dict):
                            parsed = maybe
                    except Exception:
                        parsed = {}

                    api_success = parsed.get("success")
                    verified = bool(parsed.get("verified"))
                    if not verified and isinstance(parsed.get("verification"), dict):
                        verification_obj = parsed.get("verification", {})
                        verified = (
                            str(verification_obj.get("status", "")).strip().lower() in {"verified", "complete"}
                        )
                    if (
                        not verified
                        and 200 <= int(response.status) < 300
                        and (not isinstance(api_success, bool) or bool(api_success))
                    ):
                        verified = True

                    reason = "verified" if verified else "verify_failed"
                    if not verified and int(response.status) == 429:
                        reason = "verify_rate_limited"

                    return {
                        "verified": verified,
                        "reason": reason,
                        "status": int(response.status),
                        "answer": answer,
                        "response_excerpt": safe_excerpt,
                    }
        except Exception as exc:
            return {
                "verified": False,
                "reason": f"verify_request_failed:{_safe_excerpt(str(exc), max_len=180)}",
                "answer": answer,
            }


CONFIG = SandboxConfig.from_env()
BROKER = ScoutSandboxBroker(CONFIG)
APP_STARTED_AT = int(time.time())

app = FastAPI(title="Sapphire Scout Sandbox", version="1.0.0")


def _extract_bearer_token(value: str) -> str:
    raw = str(value or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return ""


def _require_inbound_auth(authorization: str, x_scout_sandbox_token: str) -> None:
    expected = CONFIG.sandbox_token
    if not expected:
        return

    supplied = str(x_scout_sandbox_token or "").strip()
    if not supplied:
        supplied = _extract_bearer_token(authorization)

    if not supplied or supplied != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": "sapphire-scout-sandbox",
        "uptime_seconds": int(time.time()) - APP_STARTED_AT,
        "dry_run": CONFIG.dry_run,
        "allowed_hosts": list(CONFIG.allowed_hosts),
        "register_url_configured": bool(CONFIG.register_url),
        "post_url_configured": bool(CONFIG.post_url),
        "external_api_token_configured": bool(CONFIG.external_api_token),
        "sandbox_token_configured": bool(CONFIG.sandbox_token),
    }


@app.post("/v1/scout/dispatch")
async def scout_dispatch(
    request: DispatchRequest,
    authorization: Optional[str] = Header(default=""),
    x_scout_sandbox_token: Optional[str] = Header(default=""),
) -> Dict[str, Any]:
    _require_inbound_auth(authorization or "", x_scout_sandbox_token or "")
    dispatch = await BROKER.dispatch(request)
    return {
        "ok": bool(dispatch.get("dispatched")),
        "dispatch": dispatch,
        "timestamp": int(time.time()),
    }
