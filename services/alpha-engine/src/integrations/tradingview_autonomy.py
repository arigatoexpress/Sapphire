import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

import aiohttp
from loguru import logger


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class TradingViewAutonomyPlugin:
    """
    Stateful TradingView autonomy plugin.

    The plugin tracks desired TradingView workspace state and can dispatch action
    instructions to an OpenClaw hook so autonomous bots can perform the UI steps.
    """

    WORKSPACE_ACTIONS: Set[str] = {
        "tv_status",
        "workspace_status",
        "tv_workspace_status",
        "tv_assets_scope",
        "tv_watchlist_add",
        "tv_watchlist_remove",
        "tv_watchlist_replace",
        "tv_chart_set",
        "tv_indicator_add",
        "tv_indicator_remove",
        "tv_strategy_add",
        "tv_strategy_remove",
        "tv_script_add",
        "tv_script_remove",
        "tv_scan_assets",
        "tv_ta",
        "tv_custom",
    }

    MUTATING_ACTIONS: Set[str] = {
        "tv_assets_scope",
        "tv_watchlist_add",
        "tv_watchlist_remove",
        "tv_watchlist_replace",
        "tv_chart_set",
        "tv_indicator_add",
        "tv_indicator_remove",
        "tv_strategy_add",
        "tv_strategy_remove",
        "tv_script_add",
        "tv_script_remove",
    }

    @staticmethod
    def _parse_scope_items(value: str) -> Set[str]:
        cleaned = str(value or "").replace("|", ",").replace(";", ",")
        return {token.strip() for token in cleaned.split(",") if token.strip()}

    def __init__(self, market_data: Any, default_chat_id: str = "") -> None:
        self.market_data = market_data
        self.enabled = _env_flag("TRADINGVIEW_AUTONOMY_ENABLED", default=False)
        self.allow_mutations = _env_flag("TRADINGVIEW_AUTONOMY_ALLOW_MUTATIONS", default=True)
        self.allow_all_assets = _env_flag("TRADINGVIEW_ALLOW_ALL_ASSETS", default=True)
        self.community_access_enabled = _env_flag("TRADINGVIEW_COMMUNITY_ACCESS_ENABLED", default=True)
        self.hook_url = os.getenv(
            "TRADINGVIEW_AUTONOMY_HOOK_URL",
            "https://sapphire-gateway-s77j6bxyra-uc.a.run.app/hooks/agent",
        ).strip()
        self.hook_token = os.getenv("TRADINGVIEW_AUTONOMY_HOOK_TOKEN", "").strip()
        self.autonomy_agent_id = os.getenv("TRADINGVIEW_AUTONOMY_AGENT_ID", "sapphire").strip() or "sapphire"
        self.autonomy_chat_id = (
            os.getenv("TRADINGVIEW_AUTONOMY_CHAT_ID", "").strip() or str(default_chat_id or "").strip()
        )
        self.workspace_label = os.getenv("TRADINGVIEW_WORKSPACE_LABEL", "SAPPHIRE_MAIN").strip()
        self.allowed_repo_scope = self._parse_scope_items(
            os.getenv("SAPPHIRE_ALLOWED_REPOS", "arigatoexpress/Sapphire,Sapphire")
        ) or {"arigatoexpress/Sapphire", "Sapphire"}
        self.allowed_project_scope = self._parse_scope_items(
            os.getenv("SAPPHIRE_ALLOWED_GCP_PROJECTS", "sapphire-479610")
        ) or {"sapphire-479610"}
        self.blocked_scope_terms = {
            term.lower()
            for term in self._parse_scope_items(
                os.getenv("SAPPHIRE_BLOCKED_SCOPE_TERMS", "sapphireai,sapphire-inc,sapphire inc")
            )
        }
        self._serverless_token_cache: Dict[str, Dict[str, Any]] = {}
        self.state_path = Path(
            os.getenv("TRADINGVIEW_WORKSPACE_STATE_FILE", "/tmp/tradingview_workspace_state.json").strip()
        )
        self._state = self._load_state()

    def is_workspace_action(self, action: str) -> bool:
        return str(action or "").strip().lower() in self.WORKSPACE_ACTIONS

    def status_snapshot(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allow_mutations": self.allow_mutations,
            "allow_all_assets": self.allow_all_assets,
            "community_access_enabled": self.community_access_enabled,
            "hook_url_set": bool(self.hook_url),
            "hook_token_set": bool(self.hook_token),
            "agent_id": self.autonomy_agent_id,
            "workspace_label": self.workspace_label,
            "allowed_repo_scope": sorted(self.allowed_repo_scope),
            "allowed_project_scope": sorted(self.allowed_project_scope),
            "state": self._state,
        }

    def _scope_policy_line(self) -> str:
        repos = ", ".join(sorted(self.allowed_repo_scope))
        projects = ", ".join(sorted(self.allowed_project_scope))
        return f"Hard scope: repos [{repos}] and projects [{projects}] only."

    def _scope_violation_reason(self, instruction: str) -> Optional[str]:
        text = str(instruction or "").strip()
        if not text:
            return None

        lowered = text.lower()
        blocked_hits = [term for term in sorted(self.blocked_scope_terms) if term and term in lowered]
        if blocked_hits:
            return f"blocked_scope_terms:{','.join(blocked_hits[:3])}"

        allowed_repos = {item.lower() for item in self.allowed_repo_scope}
        detected_repos: Set[str] = set()
        for match in re.finditer(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", text):
            owner = match.group(1)
            repo = match.group(2)
            # Ignore domain/path matches (e.g., run.app/hooks).
            if "." in owner or "." in repo:
                continue
            detected_repos.add(f"{owner}/{repo}")

        disallowed_repos = sorted([repo for repo in detected_repos if repo.lower() not in allowed_repos])
        if disallowed_repos:
            return f"repo_scope_violation:{','.join(disallowed_repos[:3])}"

        allowed_projects = {item.lower() for item in self.allowed_project_scope}
        detected_projects: Set[str] = set()
        for pattern in (
            r"--project(?:=|\s+)([a-z][a-z0-9-]+)",
            r"projects/([a-z][a-z0-9-]+)",
        ):
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                detected_projects.add(match.group(1))

        disallowed_projects = sorted(
            [project for project in detected_projects if project.lower() not in allowed_projects]
        )
        if disallowed_projects:
            return f"project_scope_violation:{','.join(disallowed_projects[:3])}"

        return None

    def _default_state(self) -> Dict[str, Any]:
        return {
            "active_watchlist": "SAPPHIRE",
            "watchlists": {"SAPPHIRE": []},
            "selected_symbol": "SOL",
            "selected_timeframe": "15",
            "indicators": [],
            "strategies": [],
            "community_scripts": [],
            "assets_scope": "ALL" if self.allow_all_assets else "FILTERED",
            "last_action": None,
            "last_updated_at": int(time.time()),
        }

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state = self._default_state()
                state.update(raw)
                if "watchlists" not in state or not isinstance(state["watchlists"], dict):
                    state["watchlists"] = {"SAPPHIRE": []}
                return state
        except Exception as exc:
            logger.warning(f"TradingView state load failed, resetting state: {exc}")
        return self._default_state()

    def _save_state(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to persist TradingView state: {exc}")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return str(symbol or "").strip().upper()

    @staticmethod
    def _split_tokens(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            cleaned = value.replace("|", ",").replace(";", ",")
            return [token.strip() for token in cleaned.split(",") if token.strip()]
        return []

    def _resolve_agent_id(self, payload: Dict[str, Any]) -> str:
        for key in ("agent_id", "agentId", "agent", "target_agent"):
            candidate = str(payload.get(key, "")).strip().lower()
            if candidate in {"sapphire", "obsidian", "emerald"}:
                return candidate
            if candidate:
                logger.warning(
                    "Ignoring unsupported agent override '{}' for TradingView autonomy dispatch",
                    candidate,
                )
                break
        return self.autonomy_agent_id

    @staticmethod
    def _compute_sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        window = values[-period:]
        return sum(window) / float(period)

    @staticmethod
    def _compute_ema(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        k = 2.0 / (period + 1.0)
        ema = values[0]
        for value in values[1:]:
            ema = (value * k) + (ema * (1.0 - k))
        return ema

    @staticmethod
    def _compute_rsi(values: List[float], period: int = 14) -> Optional[float]:
        if len(values) < period + 1:
            return None
        gains = []
        losses = []
        for idx in range(len(values) - period, len(values)):
            delta = values[idx] - values[idx - 1]
            gains.append(max(delta, 0.0))
            losses.append(max(-delta, 0.0))
        avg_gain = sum(gains) / float(period)
        avg_loss = sum(losses) / float(period)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    async def _dispatch_to_openclaw(
        self,
        action: str,
        payload: Dict[str, Any],
        note: str,
        agent_id: str = "",
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"dispatched": False, "reason": "autonomy_disabled"}
        if not self.hook_url:
            return {"dispatched": False, "reason": "hook_url_missing"}
        if not self.hook_token:
            return {"dispatched": False, "reason": "hook_token_missing"}
        if not self.autonomy_chat_id:
            return {"dispatched": False, "reason": "chat_id_missing"}

        resolved_agent = str(agent_id or self.autonomy_agent_id).strip() or "sapphire"
        session_key = f"hook:tradingview:{action}:{int(time.time() * 1000)}"
        hook_payload = {
            "name": f"TradingView {action}",
            "agentId": resolved_agent,
            "wakeMode": "now",
            "sessionKey": session_key,
            "deliver": True,
            "channel": "telegram",
            "to": self.autonomy_chat_id,
            "message": note,
        }

        headers = {
            "Content-Type": "application/json",
            "X-OpenClaw-Token": self.hook_token,
        }
        headers.update(await self._get_serverless_auth_headers())
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.hook_url, json=hook_payload, headers=headers) as resp:
                    body = await resp.text()
                    if resp.status >= 400:
                        return {
                            "dispatched": False,
                            "reason": f"hook_http_{resp.status}",
                            "body": body[:300],
                        }
        except Exception as exc:
            return {"dispatched": False, "reason": "hook_request_error", "error": str(exc)}

        return {"dispatched": True, "session_key": session_key}

    async def _get_serverless_auth_headers(self) -> Dict[str, str]:
        """
        Add Cloud Run IAM auth for cross-service hook calls.

        OpenClaw hook endpoints use app-level token auth in `X-OpenClaw-Token`,
        while Cloud Run IAM expects an identity token. We provide IAM auth via
        `X-Serverless-Authorization` to avoid clobbering app-level auth.
        """
        if not os.getenv("K_SERVICE"):
            return {}

        parsed = urlparse(self.hook_url)
        if not parsed.scheme or not parsed.netloc:
            return {}
        audience = f"{parsed.scheme}://{parsed.netloc}"

        now = time.time()
        cached = self._serverless_token_cache.get(audience)
        if cached and now < float(cached.get("expires_at", 0)):
            token = str(cached.get("token", "")).strip()
            if token:
                return {"X-Serverless-Authorization": f"Bearer {token}"}

        token_url = (
            "http://metadata.google.internal/computeMetadata/v1/instance/"
            f"service-accounts/default/identity?audience={audience}"
        )

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    token_url,
                    headers={"Metadata-Flavor": "Google"},
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Serverless token fetch failed status={} body={}",
                            resp.status,
                            (await resp.text())[:200],
                        )
                        return {}
                    token = (await resp.text()).strip()
                    if not token:
                        return {}
        except Exception as exc:
            logger.warning(f"Serverless token fetch error: {exc}")
            return {}

        # Metadata tokens are typically valid for ~1h; refresh proactively.
        self._serverless_token_cache[audience] = {
            "token": token,
            "expires_at": now + 55 * 60,
        }
        return {"X-Serverless-Authorization": f"Bearer {token}"}

    async def dispatch_owner_instruction(self, instruction: str, agent_id: str = "") -> Dict[str, Any]:
        instruction = str(instruction or "").strip()
        if not instruction:
            return {"dispatched": False, "reason": "empty_instruction"}
        scope_violation = self._scope_violation_reason(instruction)
        if scope_violation:
            return {"dispatched": False, "reason": "scope_violation", "detail": scope_violation}

        note = (
            "Owner steering update for Sapphire-focused operations only. "
            f"{self._scope_policy_line()} "
            f"Directive: {instruction} "
            "Acknowledge in Telegram, then provide the next 3 executable steps with risk controls."
        )
        return await self._dispatch_to_openclaw(
            action="owner_steer",
            payload={"instruction": instruction},
            note=note,
            agent_id=agent_id,
        )

    async def dispatch_session_decision(
        self,
        session_key: str,
        decision: str,
        note: str = "",
        agent_id: str = "",
    ) -> Dict[str, Any]:
        session_key = str(session_key or "").strip()
        normalized_decision = str(decision or "").strip().upper()
        decision_note = str(note or "").strip()

        if not session_key:
            return {"dispatched": False, "reason": "session_key_missing"}
        if normalized_decision not in {"APPROVE", "REJECT"}:
            return {"dispatched": False, "reason": "invalid_decision"}
        if len(decision_note) > 400:
            decision_note = decision_note[:400]

        note_text = (
            f"Owner session decision for `{session_key}`: `{normalized_decision}`. "
            f"{self._scope_policy_line()} "
            "Apply this decision to the active autonomy workflow and acknowledge in Telegram with a concise action summary."
        )
        if decision_note:
            note_text += f" Owner note: {decision_note}"

        payload = {
            "session_key": session_key,
            "decision": normalized_decision,
            "note": decision_note,
        }
        return await self._dispatch_to_openclaw(
            action=f"session_{normalized_decision.lower()}",
            payload=payload,
            note=note_text,
            agent_id=agent_id,
        )

    async def dispatch_environment_instruction(
        self,
        instruction: str,
        trigger: str = "scheduled_cycle",
        context: Optional[Dict[str, Any]] = None,
        allow_code_changes: bool = True,
        allow_gcloud_changes: bool = True,
        agent_id: str = "",
    ) -> Dict[str, Any]:
        instruction = str(instruction or "").strip()
        if not instruction:
            return {"dispatched": False, "reason": "empty_instruction"}
        scope_violation = self._scope_violation_reason(instruction)
        if scope_violation:
            return {"dispatched": False, "reason": "scope_violation", "detail": scope_violation}

        context = dict(context or {})
        guardrails = [
            self._scope_policy_line(),
            "Do not touch non-Sapphire repos or external projects.",
            "Post a concise changelog + risk note back to Telegram after execution.",
        ]
        if allow_code_changes:
            guardrails.append(
                "You may edit code, run tests, commit, and push directly to main when checks pass."
            )
        else:
            guardrails.append("Code changes disabled: diagnostics and proposals only.")
        if allow_gcloud_changes:
            guardrails.append(
                "You may run gcloud mutations for Cloud Run/Scheduler/IAM/Secrets strictly in sapphire-479610."
            )
        else:
            guardrails.append("GCP mutations disabled: read-only verification only.")

        context_json = json.dumps(context, sort_keys=True)
        note = (
            "Autonomy cycle instruction for Sapphire operations. "
            f"Trigger: {trigger}. "
            f"Directive: {instruction} "
            "Operate autonomously with this policy: "
            + " ".join(guardrails)
            + f" Current runtime context: {context_json}."
        )
        payload = {
            "instruction": instruction,
            "trigger": trigger,
            "context": context,
            "allow_code_changes": bool(allow_code_changes),
            "allow_gcloud_changes": bool(allow_gcloud_changes),
        }
        return await self._dispatch_to_openclaw(
            action="environment_autonomy",
            payload=payload,
            note=note,
            agent_id=agent_id,
        )

    def _make_openclaw_instruction(self, action: str, payload: Dict[str, Any]) -> str:
        base = [
            self._scope_policy_line(),
            "Use browser automation in TradingView with configured account/session.",
            f"Workspace: {self.workspace_label}.",
            f"Requested action: {action}.",
            "Operate directly on TradingView UI and verify end-state with screenshots or explicit confirmations.",
        ]

        if action == "tv_watchlist_add":
            base.append(
                f"Add `{payload.get('symbol')}` to watchlist `{payload.get('watchlist', self._state['active_watchlist'])}`."
            )
        elif action == "tv_watchlist_remove":
            base.append(
                f"Remove `{payload.get('symbol')}` from watchlist `{payload.get('watchlist', self._state['active_watchlist'])}`."
            )
        elif action == "tv_watchlist_replace":
            base.append(
                "Replace watchlist symbols with: "
                + ", ".join(self._split_tokens(payload.get("symbols", [])))
            )
        elif action == "tv_chart_set":
            base.append(
                f"Open chart `{payload.get('symbol', self._state['selected_symbol'])}` on timeframe `{payload.get('timeframe', self._state['selected_timeframe'])}`."
            )
        elif action == "tv_indicator_add":
            base.append(f"Add indicator `{payload.get('indicator')}` to active chart.")
        elif action == "tv_indicator_remove":
            base.append(f"Remove indicator `{payload.get('indicator')}` from active chart.")
        elif action == "tv_strategy_add":
            base.append(f"Add strategy `{payload.get('strategy')}` to active chart.")
        elif action == "tv_strategy_remove":
            base.append(f"Remove strategy `{payload.get('strategy')}` from active chart.")
        elif action == "tv_script_add":
            base.append(
                f"Load community script `{payload.get('script')}` and add it to favorites if available."
            )
        elif action == "tv_script_remove":
            base.append(f"Remove community script `{payload.get('script')}` from chart/favorites.")
        elif action == "tv_assets_scope":
            base.append(
                f"Set asset universe mode to `{payload.get('scope', 'ALL')}` and ensure screener covers all assets."
            )
        elif action == "tv_scan_assets":
            base.append(
                "Scan all available assets for notable technical setups and return top opportunities."
            )
        elif action == "tv_ta":
            base.append(
                f"Run technical analysis on `{payload.get('symbol', self._state['selected_symbol'])}` with preferred indicators."
            )
        elif action == "tv_custom":
            base.append(f"Custom operator request: {payload.get('instruction', '')}")

        base.append(
            "After execution, summarize what changed in watchlists/charts/indicators/strategies/scripts."
        )
        return " ".join(base)

    async def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        action = str(action or "").strip().lower()
        payload = dict(payload or {})
        target_agent = self._resolve_agent_id(payload)

        if action not in self.WORKSPACE_ACTIONS:
            return {"accepted": "ignored", "reason": "unknown_workspace_action"}
        if action in self.MUTATING_ACTIONS and not self.allow_mutations:
            return {"accepted": "blocked", "reason": "mutations_disabled"}
        if action in {"tv_script_add", "tv_script_remove"} and not self.community_access_enabled:
            return {"accepted": "blocked", "reason": "community_access_disabled"}

        state = self._state
        changed = False

        if action in {"tv_status", "workspace_status", "tv_workspace_status"}:
            return {"accepted": "status", "workspace": self.status_snapshot()}

        if action == "tv_assets_scope":
            requested_scope = str(payload.get("scope", "ALL")).strip().upper()
            if requested_scope == "ALL" and not self.allow_all_assets:
                return {"accepted": "blocked", "reason": "all_assets_disabled"}
            state["assets_scope"] = requested_scope if requested_scope else state["assets_scope"]
            changed = True

        elif action == "tv_watchlist_add":
            watchlist = str(payload.get("watchlist", state["active_watchlist"])).strip() or state["active_watchlist"]
            symbol = self._normalize_symbol(payload.get("symbol", ""))
            if not symbol:
                return {"accepted": "blocked", "reason": "symbol_required"}
            symbols = state["watchlists"].setdefault(watchlist, [])
            if symbol not in symbols:
                symbols.append(symbol)
                changed = True
            state["active_watchlist"] = watchlist

        elif action == "tv_watchlist_remove":
            watchlist = str(payload.get("watchlist", state["active_watchlist"])).strip() or state["active_watchlist"]
            symbol = self._normalize_symbol(payload.get("symbol", ""))
            if not symbol:
                return {"accepted": "blocked", "reason": "symbol_required"}
            symbols = state["watchlists"].setdefault(watchlist, [])
            if symbol in symbols:
                symbols.remove(symbol)
                changed = True
            state["active_watchlist"] = watchlist

        elif action == "tv_watchlist_replace":
            watchlist = str(payload.get("watchlist", state["active_watchlist"])).strip() or state["active_watchlist"]
            symbols = [self._normalize_symbol(token) for token in self._split_tokens(payload.get("symbols", []))]
            state["watchlists"][watchlist] = [sym for sym in symbols if sym]
            state["active_watchlist"] = watchlist
            changed = True

        elif action == "tv_chart_set":
            symbol = self._normalize_symbol(payload.get("symbol", state["selected_symbol"]))
            timeframe = str(payload.get("timeframe", state["selected_timeframe"])).strip() or state["selected_timeframe"]
            state["selected_symbol"] = symbol
            state["selected_timeframe"] = timeframe
            changed = True

        elif action == "tv_indicator_add":
            indicator = str(payload.get("indicator", "")).strip()
            if not indicator:
                return {"accepted": "blocked", "reason": "indicator_required"}
            if indicator not in state["indicators"]:
                state["indicators"].append(indicator)
                changed = True

        elif action == "tv_indicator_remove":
            indicator = str(payload.get("indicator", "")).strip()
            if not indicator:
                return {"accepted": "blocked", "reason": "indicator_required"}
            if indicator in state["indicators"]:
                state["indicators"].remove(indicator)
                changed = True

        elif action == "tv_strategy_add":
            strategy = str(payload.get("strategy", "")).strip()
            if not strategy:
                return {"accepted": "blocked", "reason": "strategy_required"}
            if strategy not in state["strategies"]:
                state["strategies"].append(strategy)
                changed = True

        elif action == "tv_strategy_remove":
            strategy = str(payload.get("strategy", "")).strip()
            if not strategy:
                return {"accepted": "blocked", "reason": "strategy_required"}
            if strategy in state["strategies"]:
                state["strategies"].remove(strategy)
                changed = True

        elif action == "tv_script_add":
            script = str(payload.get("script", "")).strip()
            if not script:
                return {"accepted": "blocked", "reason": "script_required"}
            if script not in state["community_scripts"]:
                state["community_scripts"].append(script)
                changed = True

        elif action == "tv_script_remove":
            script = str(payload.get("script", "")).strip()
            if not script:
                return {"accepted": "blocked", "reason": "script_required"}
            if script in state["community_scripts"]:
                state["community_scripts"].remove(script)
                changed = True

        elif action == "tv_ta":
            symbol = self._normalize_symbol(payload.get("symbol", state["selected_symbol"]))
            venue = str(payload.get("venue", "ASTER")).strip().upper()
            close_values = [float(x) for x in self._split_tokens(payload.get("closes", [])) if str(x).strip()]
            if not close_values:
                price = float(self.market_data.get_price(venue, symbol) or 0.0)
                if price > 0:
                    close_values = [price] * 30
            if not close_values:
                return {"accepted": "blocked", "reason": "no_price_data"}

            sma_5 = self._compute_sma(close_values, 5)
            sma_20 = self._compute_sma(close_values, 20)
            ema_12 = self._compute_ema(close_values, 12)
            ema_26 = self._compute_ema(close_values, 26)
            rsi_14 = self._compute_rsi(close_values, 14)
            trend = "neutral"
            if sma_5 is not None and sma_20 is not None:
                trend = "bullish" if sma_5 > sma_20 else "bearish" if sma_5 < sma_20 else "neutral"

            return {
                "accepted": "ta",
                "symbol": symbol,
                "venue": venue,
                "analysis": {
                    "sma_5": sma_5,
                    "sma_20": sma_20,
                    "ema_12": ema_12,
                    "ema_26": ema_26,
                    "rsi_14": rsi_14,
                    "trend": trend,
                },
                "workspace": self.status_snapshot(),
            }

        elif action == "tv_scan_assets":
            scan_scope = state.get("assets_scope", "ALL")
            note = f"Scan requested for scope={scan_scope} across full TradingView universe."
            dispatch = await self._dispatch_to_openclaw(
                action,
                payload,
                self._make_openclaw_instruction(action, payload),
                agent_id=target_agent,
            )
            return {"accepted": "scan_requested", "dispatch": dispatch, "note": note, "workspace": self.status_snapshot()}

        elif action == "tv_custom":
            instruction = str(payload.get("instruction", "")).strip()
            if not instruction:
                return {"accepted": "blocked", "reason": "instruction_required"}
            dispatch = await self._dispatch_to_openclaw(
                action,
                payload,
                self._make_openclaw_instruction(action, payload),
                agent_id=target_agent,
            )
            return {"accepted": "custom_requested", "dispatch": dispatch, "workspace": self.status_snapshot()}

        state["last_action"] = action
        state["last_updated_at"] = int(time.time())
        if changed:
            self._save_state()

        dispatch = await self._dispatch_to_openclaw(
            action,
            payload,
            self._make_openclaw_instruction(action, payload),
            agent_id=target_agent,
        )
        return {
            "accepted": "workspace_updated" if changed else "workspace_noop",
            "action": action,
            "dispatch": dispatch,
            "workspace": self.status_snapshot(),
        }
