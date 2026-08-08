"""Paper-safe free-reign multi-rail + dens + AXTI policy kernel.

Models propose; this module only evaluates. No network, no broker, no secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

# Permanent dens class (meme/honeypot) — never free-reign spam
DEFAULT_DENS_SYMBOLS: frozenset[str] = frozenset(
    {
        "SONNY",
        "BINGBONG",
        "CATE",
        "HOODSDAY",
        "NONGWAN",
    }
)

# Dust sleeve — exits only; never re-buy via free-reign placer
DEFAULT_DUST_NO_REBUY: frozenset[str] = frozenset(
    {
        "IBIT",
        "HOOD",
        "PLTR",
        "NVDA",
    }
)

# Short 0x prefixes permanently dens-listed (full match or prefix)
DEFAULT_DENS_ADDR_PREFIXES: tuple[str, ...] = (
    "0x9763",  # example genome dens from AXTI learnings
)

FREE_REIGN_DEFAULTS: dict[str, Any] = {
    "mandate": "free_reign_multi_rail",
    "rails": {
        "rh_agentic": {
            "enabled": True,
            "options_first": True,
            "dust_placer_refuses": True,
            "account_hint": "••••8144",
        },
        "rh_l2": {
            "enabled": True,
            "max_notional_usd": 10.0,
            "max_open": 1,
            "dens_enforced": True,
        },
        "moss": {
            "enabled": True,
            "require_grant_hours_left_gt": 0,
        },
        "paper": {
            "enabled": True,
        },
        "hyperliquid": {
            "enabled": True,
        },
    },
    "axti": {
        "scale_out_multiple": 2.0,
        "hard_sl_fraction": -0.40,
        "never_hold_to_worthless": True,
        "defined_risk_only": True,
        "max_dte_days": 21,
        "min_dte_days": 2,
        "require_catalyst_tag": False,
    },
    "dens_symbols": sorted(DEFAULT_DENS_SYMBOLS),
    "dust_no_rebuy": sorted(DEFAULT_DUST_NO_REBUY),
    "dens_addr_prefixes": list(DEFAULT_DENS_ADDR_PREFIXES),
    # Late-cycle / capital preservation (thesis-aligned; paper-safe defaults)
    "capital_preservation": {
        "enabled": True,
        "block_meme_l2_in_crisis": True,
        "max_options_premium_usd_per_day": 150.0,
        "max_realized_loss_usd_per_day": 75.0,
        "prefer_defined_risk": True,
    },
    "hyperliquid": {
        "enabled": True,
        "max_notional_usd": 25.0,
        "require_signing_gate": True,
        "signing_gate_armed": False,  # plant must arm explicitly
    },
    "signal_spine": {
        "require_min_sources": 1,
        "sources_hint": ["tv", "ohlcv", "chain", "regime"],
    },
}


@dataclass(frozen=True)
class OrderProposal:
    """Inbound proposal from a model or agent (not yet authorized)."""

    symbol: str
    side: str  # buy | sell
    rail: str  # rh_agentic | rh_l2 | moss | paper | hyperliquid
    asset_class: str  # equity | option | l2_token | perp
    notional_usd: float
    open_positions_on_rail: int = 0
    contract_address: str | None = None
    moss_grant_hours_left: float | None = None
    is_defined_risk_option: bool = False
    # Optional context for capital-preservation / AXTI / signal spine
    dte_days: float | None = None
    regime: str | None = None  # trend | mean_reverting | crisis | risk_on | risk_off | unknown
    day_options_premium_usd: float = 0.0
    day_realized_pnl_usd: float = 0.0
    signal_source_count: int = 1
    hyperliquid_signing_gate_armed: bool | None = None
    has_catalyst_tag: bool = False
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str
    code: str
    arm: str = "TRADE"  # TRADE | NO_TRADE
    details: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "reason": self.reason,
            "code": self.code,
            "arm": self.arm,
            "details": dict(self.details),
        }


def _norm_sym(symbol: str) -> str:
    return (symbol or "").strip().upper()


def _norm_addr(addr: str | None) -> str:
    if not addr:
        return ""
    a = addr.strip().lower()
    if a.startswith("0x"):
        return a
    return a


def is_dens_blocked(
    symbol: str,
    *,
    contract_address: str | None = None,
    dens_symbols: Iterable[str] | None = None,
    dens_addr_prefixes: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Return (blocked, reason). Permanent dens class + 0x prefix match."""
    dens = {_norm_sym(s) for s in (dens_symbols if dens_symbols is not None else DEFAULT_DENS_SYMBOLS)}
    sym = _norm_sym(symbol)
    if sym in dens:
        return True, f"dens_symbol:{sym}"
    # prefix class: symbols that start with dens tokens (e.g. SONNY*)
    for d in dens:
        if d and (sym.startswith(d) or d in sym):
            # exact already handled; only flag multi-token spam names containing dens
            if sym != d and d in sym and len(d) >= 4:
                return True, f"dens_symbol_contains:{d}"
    prefixes = dens_addr_prefixes if dens_addr_prefixes is not None else DEFAULT_DENS_ADDR_PREFIXES
    addr = _norm_addr(contract_address)
    if addr:
        for p in prefixes:
            pl = p.lower()
            if addr == pl or addr.startswith(pl):
                return True, f"dens_addr_prefix:{p}"
    return False, ""


def evaluate_proposal(
    proposal: OrderProposal,
    policy: Mapping[str, Any] | None = None,
) -> Decision:
    """Evaluate a proposal under free-reign multi-rail fences (paper-safe)."""
    pol = dict(FREE_REIGN_DEFAULTS)
    if policy:
        # shallow merge rails
        pol.update({k: v for k, v in policy.items() if k != "rails"})
        if "rails" in policy:
            rails = dict(pol.get("rails", {}))
            for rk, rv in policy["rails"].items():
                base = dict(rails.get(rk, {}))
                base.update(rv)
                rails[rk] = base
            pol["rails"] = rails

    rail = (proposal.rail or "").strip().lower()
    side = (proposal.side or "").strip().lower()
    sym = _norm_sym(proposal.symbol)
    dens_syms = pol.get("dens_symbols") or sorted(DEFAULT_DENS_SYMBOLS)
    dens_prefs = pol.get("dens_addr_prefixes") or list(DEFAULT_DENS_ADDR_PREFIXES)
    dust = {_norm_sym(s) for s in (pol.get("dust_no_rebuy") or DEFAULT_DUST_NO_REBUY)}

    if rail not in ("rh_agentic", "rh_l2", "moss", "paper", "hyperliquid"):
        return Decision(False, f"unknown rail {rail}", "UNKNOWN_RAIL", "NO_TRADE")

    rails = pol.get("rails") or {}
    rail_cfg = rails.get(rail) or {}
    if not rail_cfg.get("enabled", False):
        return Decision(False, f"rail disabled: {rail}", "RAIL_DISABLED", "NO_TRADE")

    # dens always on L2 + agentic buys of tokens/equity spam
    blocked, why = is_dens_blocked(
        sym,
        contract_address=proposal.contract_address,
        dens_symbols=dens_syms,
        dens_addr_prefixes=dens_prefs,
    )
    if blocked and side == "buy":
        return Decision(False, f"dens permanent block ({why})", "DENS_BLOCK", "NO_TRADE", {"match": why})

    # dust no re-buy
    if side == "buy" and sym in dust and rail_cfg.get("dust_placer_refuses", rail == "rh_agentic"):
        return Decision(
            False,
            f"dust sleeve no re-buy: {sym}",
            "DUST_NO_REBUY",
            "NO_TRADE",
        )

    # options-first on agentic: equity buys discouraged unless paper/explicit
    if rail == "rh_agentic" and side == "buy" and proposal.asset_class == "equity":
        if rail_cfg.get("options_first", True):
            return Decision(
                False,
                "options-first: equity buy refused on rh_agentic (use option or paper)",
                "OPTIONS_FIRST",
                "NO_TRADE",
            )

    if rail == "rh_agentic" and side == "buy" and proposal.asset_class == "option":
        axti = pol.get("axti") or {}
        if axti.get("defined_risk_only", True) and not proposal.is_defined_risk_option:
            return Decision(
                False,
                "AXTI: only defined-risk long options (premium = max loss)",
                "AXTI_DEFINED_RISK",
                "NO_TRADE",
            )

    if rail == "rh_l2":
        max_n = float(rail_cfg.get("max_notional_usd", 10.0))
        max_open = int(rail_cfg.get("max_open", 1))
        if proposal.notional_usd > max_n + 1e-9:
            return Decision(
                False,
                f"L2 notional {proposal.notional_usd} > cap {max_n}",
                "L2_NOTIONAL_CAP",
                "NO_TRADE",
                {"max_notional_usd": max_n},
            )
        if side == "buy" and proposal.open_positions_on_rail >= max_open:
            return Decision(
                False,
                f"L2 max open {max_open} already reached",
                "L2_MAX_OPEN",
                "NO_TRADE",
                {"max_open": max_open},
            )

    if rail == "moss":
        need = float(rail_cfg.get("require_grant_hours_left_gt", 0))
        hours = proposal.moss_grant_hours_left
        if hours is None or hours <= need:
            return Decision(
                False,
                f"MOSS grant required (hours_left must be > {need}); got {hours}",
                "MOSS_GRANT",
                "NO_TRADE",
            )

    if proposal.notional_usd < 0:
        return Decision(False, "negative notional", "BAD_NOTIONAL", "NO_TRADE")

    # --- capital preservation (late-cycle thesis) ---
    cap = pol.get("capital_preservation") or {}
    if cap.get("enabled", True) and side == "buy":
        if proposal.day_realized_pnl_usd <= -abs(float(cap.get("max_realized_loss_usd_per_day", 75.0))):
            return Decision(
                False,
                f"daily loss halt ({proposal.day_realized_pnl_usd})",
                "DAY_LOSS_HALT",
                "NO_TRADE",
            )
        if proposal.asset_class == "option":
            max_prem = float(cap.get("max_options_premium_usd_per_day", 150.0))
            if proposal.day_options_premium_usd + proposal.notional_usd > max_prem + 1e-9:
                return Decision(
                    False,
                    f"options premium day cap {max_prem}",
                    "OPTIONS_DAY_CAP",
                    "NO_TRADE",
                    {"max_options_premium_usd_per_day": max_prem},
                )
        regime = (proposal.regime or "").strip().lower()
        if (
            cap.get("block_meme_l2_in_crisis", True)
            and rail == "rh_l2"
            and regime in {"crisis", "risk_off"}
        ):
            return Decision(
                False,
                f"L2 buys blocked in regime={regime}",
                "REGIME_BLOCK_L2",
                "NO_TRADE",
                {"regime": regime},
            )

    # --- AXTI DTE band ---
    if rail == "rh_agentic" and side == "buy" and proposal.asset_class == "option":
        axti = pol.get("axti") or {}
        dte = proposal.dte_days
        if dte is not None:
            mn = float(axti.get("min_dte_days", 2))
            mx = float(axti.get("max_dte_days", 21))
            if dte < mn or dte > mx:
                return Decision(
                    False,
                    f"AXTI DTE {dte} outside [{mn}, {mx}]",
                    "AXTI_DTE",
                    "NO_TRADE",
                    {"dte_days": dte, "min": mn, "max": mx},
                )
        if axti.get("require_catalyst_tag") and not proposal.has_catalyst_tag:
            return Decision(False, "AXTI requires catalyst tag", "AXTI_CATALYST", "NO_TRADE")

    # --- Hyperliquid hard caps (AU-05) ---
    if rail == "hyperliquid":
        hl = pol.get("hyperliquid") or {}
        if not hl.get("enabled", True):
            return Decision(False, "hyperliquid rail disabled", "HL_DISABLED", "NO_TRADE")
        max_n = float(hl.get("max_notional_usd", 25.0))
        if proposal.notional_usd > max_n + 1e-9:
            return Decision(
                False,
                f"HL notional {proposal.notional_usd} > cap {max_n}",
                "HL_NOTIONAL_CAP",
                "NO_TRADE",
            )
        armed = proposal.hyperliquid_signing_gate_armed
        if armed is None:
            armed = bool(hl.get("signing_gate_armed", False))
        if hl.get("require_signing_gate", True) and not armed:
            return Decision(
                False,
                "Hyperliquid signing gate not armed",
                "HL_SIGNING_GATE",
                "NO_TRADE",
            )

    # --- signal spine minimum sources (TR-01) ---
    spine = pol.get("signal_spine") or {}
    min_src = int(spine.get("require_min_sources", 1))
    if side == "buy" and proposal.signal_source_count < min_src:
        return Decision(
            False,
            f"signal spine needs >= {min_src} sources (got {proposal.signal_source_count})",
            "SIGNAL_SPINE",
            "NO_TRADE",
        )

    # sells of dens/dust always allowed (exits)
    return Decision(
        True,
        "proposal passes free-reign multi-rail fences",
        "ALLOW",
        "TRADE",
        {"rail": rail, "symbol": sym, "side": side},
    )


def evaluate_scale_out(
    *,
    entry_premium: float,
    mark_premium: float,
    remaining_qty: float,
    policy: Mapping[str, Any] | None = None,
) -> Decision:
    """AXTI scale-out: half at ~2×, hard SL −40% premium, never worthless hold advice."""
    pol = {**(FREE_REIGN_DEFAULTS.get("axti") or {}), **((policy or {}).get("axti") or policy or {})}
    mult = float(pol.get("scale_out_multiple", 2.0))
    sl_frac = float(pol.get("hard_sl_fraction", -0.40))
    if entry_premium <= 0 or remaining_qty <= 0:
        return Decision(False, "invalid entry/qty", "BAD_POSITION", "NO_TRADE")

    pnl_frac = (mark_premium - entry_premium) / entry_premium
    if pnl_frac <= sl_frac:
        return Decision(
            True,
            f"hard SL hit ({pnl_frac:.1%} <= {sl_frac:.0%}) — close remaining",
            "AXTI_SL",
            "TRADE",
            {"action": "close_all", "pnl_frac": pnl_frac},
        )
    if mark_premium >= entry_premium * mult:
        return Decision(
            True,
            f"scale-out trigger (~{mult:.1f}×) — close half / trail rest",
            "AXTI_SCALE_OUT",
            "TRADE",
            {"action": "close_half_trail_rest", "pnl_frac": pnl_frac, "multiple": mark_premium / entry_premium},
        )
    return Decision(
        False,
        "hold — no AXTI scale-out or SL trigger",
        "AXTI_HOLD",
        "NO_TRADE",
        {"pnl_frac": pnl_frac},
    )


_HEX_ADDR = re.compile(r"^0x[a-fA-F0-9]{6,}$")


def looks_like_contract(addr: str) -> bool:
    return bool(_HEX_ADDR.match((addr or "").strip()))
