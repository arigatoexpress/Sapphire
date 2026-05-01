"""MegaETH live-trading executor scaffold (testnet-only, fail-closed).

This module is **scaffolding only**. It is intentionally NOT wired into any
scheduler, LaunchAgent, signal pipeline, plugin manifest, or dispatch
entrypoint. There is no top-level ``run`` / ``main`` / CLI hook.

Mirrors the safety pattern from ``services/hyperliquid/src/hyperliquid_bot/
risk.py`` (PRs #443-#456):

- per-order USD cap (default $5)
- daily realized-loss cap (default $25), persisted across restarts at
  ``data/megaeth_daily_pnl.json``
- file-based killswitch (``~/.sapphire/megaeth_trading_pause``) checked on
  every send
- ``signing_verified: bool = False`` policy field — flipping it requires a
  source-code change, not env / config
- mainnet path raises ``NotImplementedError`` until ``signing_verified=True``
- testnet path works against a testnet RPC, but defaults to dry-run

Activation gates (every flip is a code change unless noted):
    1. ``HyperliquidLivePolicy``-style ``policy.signing_verified=True`` on
       :class:`MegaETHLivePolicy` (CODE).
    2. Kill switch absent: ``~/.sapphire/megaeth_trading_pause`` does not
       exist (filesystem).
    3. Order notional <= ``policy.max_order_notional_usd`` (CODE default).
    4. Daily realized loss < ``policy.daily_realized_loss_cap_usd`` (CODE
       default; auto-trips from persisted ledger).
    5. ``SAPPHIRE_MEGAETH_TESTNET_KEY`` env var set (RUNTIME). Loading from
       a file or hardcoded value is intentionally not supported.
    6. ``SAPPHIRE_MEGAETH_DRY_RUN`` not set to ``1`` (RUNTIME).
    7. ``MAINNET_CHAIN_ID`` constant in this module is a TODO placeholder.
       Until a real value is filled in *and* ``policy.signing_verified=True``
       is flipped, ``send_transaction`` on mainnet raises
       ``NotImplementedError`` (CODE).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KILLSWITCH_PATH_DEFAULT = "~/.sapphire/megaeth_trading_pause"
TRADE_LOG_PATH_DEFAULT = "data/megaeth_trades.jsonl"
DAILY_PNL_PATH_DEFAULT = "data/megaeth_daily_pnl.json"

# MegaETH testnet chain ID — public testnet is 6342 ("MegaETH Testnet").
TESTNET_CHAIN_ID = 6342

# TODO(megaeth-mainnet): MegaETH mainnet has not launched at the time of
# this scaffold (2026-04-30). Fill in the canonical mainnet chain_id only
# after MegaETH publishes it AND after policy.signing_verified=True has
# been flipped via a code change. Until then, any attempt to use this
# value as the constructor's ``chain_id`` will be refused.
MAINNET_CHAIN_ID: int | None = None

ENV_KEY_TESTNET = "SAPPHIRE_MEGAETH_TESTNET_KEY"
ENV_DRY_RUN = "SAPPHIRE_MEGAETH_DRY_RUN"


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MegaETHLivePolicy:
    """Hard caps and toggles for MegaETH live execution.

    Mirrors :class:`hyperliquid_bot.risk.HyperliquidLivePolicy`. The
    ``signing_verified`` field is the single source-code gate that must be
    flipped to allow the mainnet path; it is intentionally not configurable
    via env or constructor kwargs.
    """

    max_order_notional_usd: float = 5.0
    daily_realized_loss_cap_usd: float = 25.0
    killswitch_path: str = KILLSWITCH_PATH_DEFAULT
    trade_log_path: str = TRADE_LOG_PATH_DEFAULT
    daily_pnl_path: str = DAILY_PNL_PATH_DEFAULT
    # Source-of-truth gate. Flip this to True in code (here, a literal source
    # edit) ONLY after a clean testnet trade and a published mainnet chain id.
    signing_verified: bool = False

    def __post_init__(self) -> None:
        if self.max_order_notional_usd <= 0:
            raise ValueError("max_order_notional_usd must be positive")
        if self.daily_realized_loss_cap_usd <= 0:
            raise ValueError("daily_realized_loss_cap_usd must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Killswitch + daily PnL ledger (mirrors hyperliquid risk module)
# ---------------------------------------------------------------------------


def killswitch_active(policy: MegaETHLivePolicy) -> bool:
    """True iff the killswitch sentinel file exists on disk."""
    return Path(policy.killswitch_path).expanduser().exists()


def _daily_realized_loss_today(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0.0
    today = date.today().isoformat()
    entry = body.get(today) if isinstance(body, dict) else None
    if not isinstance(entry, dict):
        return 0.0
    try:
        return float(entry.get("realized_loss_usd", 0.0))
    except (TypeError, ValueError):
        return 0.0


def record_realized_pnl(policy: MegaETHLivePolicy, pnl_usd: float) -> None:
    """Append realized P&L into today's bucket. Loss encoded as positive USD.

    Persists to disk so the daily-loss cap survives process restarts —
    matching the hyperliquid pattern.
    """
    path = Path(policy.daily_pnl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body: dict[str, Any] = {}
    if path.exists():
        try:
            body = json.loads(path.read_text(encoding="utf-8")) or {}
        except (OSError, json.JSONDecodeError):
            body = {}
    today = date.today().isoformat()
    bucket = body.get(today) or {"realized_loss_usd": 0.0, "trade_count": 0}
    if pnl_usd < 0:
        bucket["realized_loss_usd"] = round(
            float(bucket.get("realized_loss_usd", 0.0)) + abs(pnl_usd), 6
        )
    bucket["trade_count"] = int(bucket.get("trade_count", 0)) + 1
    bucket["last_pnl_usd"] = round(pnl_usd, 6)
    body[today] = bucket
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class SendResult:
    """One transaction's outcome.

    ``status`` contract: "signed_dry_run" | "blocked" | "error". The scaffold
    never returns a ``broadcast`` status — broadcasting is the operator's
    job after activation review.
    """

    status: str
    chain_id: int
    reason: str | None = None
    signed_tx_hex: str | None = None
    blockers: tuple[str, ...] = ()
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "chain_id": self.chain_id,
            "reason": self.reason,
            "signed_tx_hex": self.signed_tx_hex,
            "blockers": list(self.blockers),
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class MegaETHExecutor:
    """Fail-closed MegaETH transaction signer scaffold.

    This class deliberately exposes only signing primitives — no "trade
    now" entrypoint, no batching, no order-management surface. It is meant
    to be imported by future callers, not driven by today's pipelines.

    Construction enforces:
      - ``chain_id`` is testnet (or refused).
      - Mainnet ``chain_id`` requires both ``policy.signing_verified=True``
        AND a non-None ``MAINNET_CHAIN_ID`` constant.
      - The private key env var is read only at sign time, never cached on
        the instance, never read from disk.
    """

    def __init__(
        self,
        rpc_url: str,
        chain_id: int,
        *,
        policy: MegaETHLivePolicy | None = None,
        per_order_cap_usd: float | None = None,
        daily_loss_cap_usd: float | None = None,
    ) -> None:
        if not rpc_url:
            raise ValueError("rpc_url is required")
        if chain_id <= 0:
            raise ValueError("chain_id must be a positive int")

        # Allow constructor overrides while keeping the dataclass frozen.
        base_policy = policy or MegaETHLivePolicy()
        if per_order_cap_usd is not None or daily_loss_cap_usd is not None:
            base_policy = MegaETHLivePolicy(
                max_order_notional_usd=(
                    per_order_cap_usd
                    if per_order_cap_usd is not None
                    else base_policy.max_order_notional_usd
                ),
                daily_realized_loss_cap_usd=(
                    daily_loss_cap_usd
                    if daily_loss_cap_usd is not None
                    else base_policy.daily_realized_loss_cap_usd
                ),
                killswitch_path=base_policy.killswitch_path,
                trade_log_path=base_policy.trade_log_path,
                daily_pnl_path=base_policy.daily_pnl_path,
                signing_verified=base_policy.signing_verified,
            )

        # Mainnet refusal: even if a future operator hardcodes a chain_id
        # equal to MAINNET_CHAIN_ID, this constructor refuses unless
        # signing_verified has been flipped in source.
        if MAINNET_CHAIN_ID is not None and chain_id == MAINNET_CHAIN_ID:
            if not base_policy.signing_verified:
                raise NotImplementedError(
                    "MegaETH mainnet path is locked. To activate: (1) verify a "
                    "clean testnet trade, (2) flip MegaETHLivePolicy."
                    "signing_verified=True in source, (3) confirm "
                    "MAINNET_CHAIN_ID matches the official MegaETH mainnet ID."
                )

        # If the operator passes a chain_id that is neither testnet nor
        # the recorded mainnet placeholder, treat it as untrusted.
        if chain_id != TESTNET_CHAIN_ID:
            if MAINNET_CHAIN_ID is None or chain_id != MAINNET_CHAIN_ID:
                raise ValueError(
                    f"refusing unknown chain_id={chain_id}; "
                    f"expected TESTNET_CHAIN_ID={TESTNET_CHAIN_ID}"
                )

        self.rpc_url = rpc_url
        self.chain_id = chain_id
        self.policy = base_policy

    # ------------------------------------------------------------------
    # Public API — signing primitive only
    # ------------------------------------------------------------------

    def send_transaction(self, tx_dict: dict[str, Any]) -> SendResult:
        """Validate caps, killswitch, and chain; sign + return result.

        Defaults to dry-run: ``SAPPHIRE_MEGAETH_DRY_RUN=1`` (or unset, see
        below) returns a signed-but-not-broadcast result. There is no
        broadcast path in the scaffold — callers must explicitly opt in
        post-activation by adding their own broadcast step.

        ``status`` outcomes:
          - ``"blocked"``: a safety gate refused the send.
          - ``"signed_dry_run"``: signing produced a hex-encoded raw tx.
          - ``"error"``: signing or env-loading failed.
        """
        blockers: list[str] = []

        # Killswitch — checked on every call.
        if killswitch_active(self.policy):
            blockers.append("killswitch_active")

        # Per-order cap.
        notional = _safe_float(tx_dict.get("notional_usd"))
        if notional is None or notional <= 0:
            blockers.append("missing_or_invalid_notional_usd")
        elif notional > self.policy.max_order_notional_usd:
            blockers.append("per_order_cap_exceeded")

        # Daily loss cap (persisted, survives restarts).
        if (
            _daily_realized_loss_today(Path(self.policy.daily_pnl_path))
            >= self.policy.daily_realized_loss_cap_usd
        ):
            blockers.append("daily_loss_cap_reached")

        # Mainnet refusal at send time too — defense in depth.
        if MAINNET_CHAIN_ID is not None and self.chain_id == MAINNET_CHAIN_ID:
            if not self.policy.signing_verified:
                blockers.append("mainnet_locked_signing_not_verified")

        # Chain id sanity (also checked in __init__; re-check here in case
        # a caller monkey-patched it).
        if self.chain_id != TESTNET_CHAIN_ID and (
            MAINNET_CHAIN_ID is None or self.chain_id != MAINNET_CHAIN_ID
        ):
            blockers.append("unknown_chain_id")

        # tx_dict.chainId, if present, must agree.
        tx_chain_id = tx_dict.get("chainId")
        if tx_chain_id is not None and int(tx_chain_id) != self.chain_id:
            blockers.append("tx_chain_id_mismatch")

        if blockers:
            result = SendResult(
                status="blocked",
                chain_id=self.chain_id,
                reason="; ".join(blockers),
                blockers=tuple(dict.fromkeys(blockers)),
            )
            self._log(result)
            return result

        # Load private key strictly from env. Never cached, never disk.
        priv_key = os.getenv(ENV_KEY_TESTNET, "").strip()
        if not priv_key:
            result = SendResult(
                status="error",
                chain_id=self.chain_id,
                reason=(
                    f"missing env var {ENV_KEY_TESTNET}; refusing to sign. "
                    "Hardcoding or file-based loading is not supported."
                ),
                blockers=("missing_signing_key_env",),
            )
            self._log(result)
            return result

        # Default to dry-run unless explicitly overridden in code (no env
        # opt-out for mainnet — the scaffold has no broadcast path).
        dry_run_flag = os.getenv(ENV_DRY_RUN, "1").strip().lower()
        is_dry_run = dry_run_flag in ("1", "true", "yes")

        try:
            signed_hex = self._sign_transaction(tx_dict, priv_key)
        except Exception as exc:  # noqa: BLE001
            log.exception("megaeth signing failed")
            result = SendResult(
                status="error",
                chain_id=self.chain_id,
                reason=f"signing_failed: {exc}",
            )
            self._log(result)
            return result

        if not is_dry_run:
            # Scaffold contract: even when the operator opts out of dry-run,
            # this module does not broadcast. Returning the signed tx lets a
            # future caller decide what to do — but they must add the
            # broadcast step themselves AFTER the activation review.
            log.warning(
                "MegaETH executor produced a signed tx but does not broadcast; "
                "add a broadcast path explicitly post-activation review."
            )

        result = SendResult(
            status="signed_dry_run",
            chain_id=self.chain_id,
            signed_tx_hex=signed_hex,
        )
        self._log(result)
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _sign_transaction(self, tx_dict: dict[str, Any], priv_key: str) -> str:
        """Sign tx_dict with eth_account. Pure local op — no RPC."""
        # Imported lazily so unit tests can run without web3/eth-account
        # being available in every environment.
        from eth_account import Account

        # Ensure chainId is set exactly to the executor's chain_id for
        # replay-protection. Caller may have already set it; we overwrite
        # to the executor's binding for safety.
        signing_payload = dict(tx_dict)
        signing_payload["chainId"] = self.chain_id

        signed = Account.sign_transaction(signing_payload, priv_key)
        # eth-account 0.13+ exposes raw bytes as ``raw_transaction``.
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        if raw is None:
            raise RuntimeError("eth_account returned no raw transaction")
        return "0x" + raw.hex() if not raw.hex().startswith("0x") else raw.hex()

    def _log(self, result: SendResult) -> None:
        path = Path(self.policy.trade_log_path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")
        except OSError:
            log.exception("failed to append megaeth trade log")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "DAILY_PNL_PATH_DEFAULT",
    "ENV_DRY_RUN",
    "ENV_KEY_TESTNET",
    "KILLSWITCH_PATH_DEFAULT",
    "MAINNET_CHAIN_ID",
    "MegaETHExecutor",
    "MegaETHLivePolicy",
    "SendResult",
    "TESTNET_CHAIN_ID",
    "TRADE_LOG_PATH_DEFAULT",
    "killswitch_active",
    "record_realized_pnl",
]
