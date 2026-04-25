"""Solana wallet — paper mode by default, foundation for live trading.

Paper mode (LIVE_TRADING=0 — the default):
  - Keypair is generated with ed25519 (the Solana curve) and stored
    encrypted at ~/.sapphire/wallet.enc using Fernet (AES-128 CBC + HMAC)
  - Balance / swaps are simulated against an in-memory position ledger
  - Jupiter quote API is called READ-ONLY for realistic price inputs;
    no transaction is ever signed or broadcast
  - Every executable proposal must pass the confirmation firewall first

Live mode (LIVE_TRADING=1) — NOT IMPLEMENTED HERE by design. To go live:
  1. Install the `solana`, `solders`, `base58` packages
  2. Replace `_simulate_swap()` with a real Jupiter swap transaction
  3. The confirmation firewall stays — it works for paper AND live

Files:
  ~/.sapphire/wallet.enc    — encrypted keypair (mode 0600)
  ~/.sapphire/wallet.key    — Fernet key (mode 0600, gitignored)
  data/trading/proposals.jsonl  — every proposal + approval/denial outcome

CLI:
    python3 -m lib.trading.solana_wallet init
    python3 -m lib.trading.solana_wallet balance
    python3 -m lib.trading.solana_wallet quote --input SOL --output USDC --amount 1
    python3 -m lib.trading.solana_wallet propose --input SOL --output USDC --amount 1
"""

from __future__ import annotations

import base64
import json
import logging
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
SAPPHIRE_DIR = Path.home() / ".sapphire"
WALLET_PATH = SAPPHIRE_DIR / "wallet.enc"
KEY_PATH = SAPPHIRE_DIR / "wallet.key"
PROPOSALS_LOG = ROOT / "data" / "trading" / "proposals.jsonl"
LEDGER_PATH = ROOT / "data" / "trading" / "paper_ledger.json"

PROPOSALS_LOG.parent.mkdir(parents=True, exist_ok=True)
SAPPHIRE_DIR.mkdir(parents=True, exist_ok=True)

LIVE_TRADING = os.getenv("LIVE_TRADING", "0") == "1"
JUPITER_QUOTE_API = "https://quote-api.jup.ag/v6/quote"

# Canonical mint addresses for the top tokens we paper-trade
MINTS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",
}

PAPER_STARTING_SOL = 10.0
PAPER_STARTING_USDC = 1000.0


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WalletInfo:
    pubkey_base58: str
    created_at: str
    live: bool
    path: str


@dataclass
class Proposal:
    id: str
    ts: str
    input_token: str
    output_token: str
    input_amount: float
    quoted_output: float
    quote_price: float | None
    status: str                       # PENDING | APPROVED | DENIED | EXECUTED_PAPER
    approver: str | None = None
    telegram_code: str | None = None
    reason: str = ""
    mode: str = "paper"
    audit: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base58 (minimal implementation — avoids needing a `base58` package)
# ---------------------------------------------------------------------------

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n > 0:
        n, r = divmod(n, 58)
        out = _B58_ALPHABET[r] + out
    # preserve leading zero bytes
    pad = 0
    for b in data:
        if b == 0:
            pad += 1
        else:
            break
    return ("1" * pad) + out


# ---------------------------------------------------------------------------
# Wallet
# ---------------------------------------------------------------------------


class SolanaWallet:
    """A Solana paper wallet — ed25519 keypair, encrypted on disk.

    All trade-proposing methods go through the confirmation firewall. This
    class never signs or broadcasts a real transaction — live execution is
    deliberately out of scope.
    """

    def __init__(self, *, confirmation_firewall: Any | None = None) -> None:
        self._fernet = None
        self._keypair: tuple[bytes, bytes] | None = None    # (private, public)
        self._confirmation_firewall = confirmation_firewall

    # ──────────────────────────────────────────────────────────────────
    # Init / load
    # ──────────────────────────────────────────────────────────────────

    def init_wallet(self, *, overwrite: bool = False) -> WalletInfo:
        """Generate a new keypair and persist it encrypted. Refuses to
        overwrite an existing wallet unless `overwrite=True`.
        """
        if WALLET_PATH.exists() and not overwrite:
            raise RuntimeError(
                f"wallet already exists at {WALLET_PATH} — pass overwrite=True to replace"
            )

        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            PublicFormat,
        )

        priv = Ed25519PrivateKey.generate()
        priv_bytes = priv.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption(),
        )
        pub_bytes = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        pubkey_b58 = _b58encode(pub_bytes)

        # Generate + save fernet key
        key = Fernet.generate_key()
        KEY_PATH.write_bytes(key)
        os.chmod(KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)       # 0600

        # Encrypt the keypair
        f = Fernet(key)
        payload = json.dumps({
            "priv": base64.b64encode(priv_bytes).decode(),
            "pub": base64.b64encode(pub_bytes).decode(),
            "pubkey_b58": pubkey_b58,
            "created_at": datetime.now(UTC).isoformat(),
        }).encode()
        WALLET_PATH.write_bytes(f.encrypt(payload))
        os.chmod(WALLET_PATH, stat.S_IRUSR | stat.S_IWUSR)    # 0600

        # Seed paper ledger
        if not LEDGER_PATH.exists():
            LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
            LEDGER_PATH.write_text(json.dumps({
                "SOL": PAPER_STARTING_SOL,
                "USDC": PAPER_STARTING_USDC,
            }, indent=2))

        self._fernet = f
        self._keypair = (priv_bytes, pub_bytes)

        return WalletInfo(
            pubkey_base58=pubkey_b58,
            created_at=datetime.now(UTC).isoformat(),
            live=LIVE_TRADING,
            path=str(WALLET_PATH),
        )

    def load(self) -> WalletInfo:
        """Decrypt the on-disk wallet into memory."""
        if not WALLET_PATH.exists() or not KEY_PATH.exists():
            raise RuntimeError("no wallet on disk — run init_wallet() first")
        from cryptography.fernet import Fernet

        key = KEY_PATH.read_bytes()
        self._fernet = Fernet(key)
        payload = json.loads(self._fernet.decrypt(WALLET_PATH.read_bytes()))
        self._keypair = (
            base64.b64decode(payload["priv"]),
            base64.b64decode(payload["pub"]),
        )
        return WalletInfo(
            pubkey_base58=payload["pubkey_b58"],
            created_at=payload.get("created_at", ""),
            live=LIVE_TRADING,
            path=str(WALLET_PATH),
        )

    def pubkey(self) -> str:
        if self._keypair is None:
            self.load()
        return _b58encode(self._keypair[1]) if self._keypair else ""

    # ──────────────────────────────────────────────────────────────────
    # Balance / ledger
    # ──────────────────────────────────────────────────────────────────

    def balance(self) -> dict[str, float]:
        """Return the paper ledger (or seed one on first call)."""
        if not LEDGER_PATH.exists():
            return {"SOL": PAPER_STARTING_SOL, "USDC": PAPER_STARTING_USDC}
        try:
            return json.loads(LEDGER_PATH.read_text())
        except Exception as e:
            log.warning("ledger read failed: %s — resetting", e)
            return {"SOL": PAPER_STARTING_SOL, "USDC": PAPER_STARTING_USDC}

    def _write_ledger(self, ledger: dict[str, float]) -> None:
        LEDGER_PATH.write_text(json.dumps(ledger, indent=2))

    # ──────────────────────────────────────────────────────────────────
    # Jupiter quote (read-only)
    # ──────────────────────────────────────────────────────────────────

    def quote(
        self,
        input_token: str,
        output_token: str,
        amount_in: float,
        slippage_bps: int = 50,
        timeout: float = 6.0,
    ) -> dict[str, Any] | None:
        """Fetch a Jupiter quote. Read-only — never signs a tx.

        Returns {price, out_amount, route, raw} or None on failure.
        """
        in_mint = MINTS.get(input_token.upper())
        out_mint = MINTS.get(output_token.upper())
        if not in_mint or not out_mint:
            log.warning("unknown token pair: %s/%s", input_token, output_token)
            return None

        # Jupiter expects integer lamports/atomic amounts. Approximate decimals:
        # SOL = 9, USDC/USDT = 6, default = 9. We only need this for the API call.
        decimals = {"SOL": 9, "USDC": 6, "USDT": 6, "JUP": 6, "BONK": 5}
        in_dec = decimals.get(input_token.upper(), 9)
        out_dec = decimals.get(output_token.upper(), 9)
        atomic = int(amount_in * (10 ** in_dec))

        params = {
            "inputMint": in_mint,
            "outputMint": out_mint,
            "amount": str(atomic),
            "slippageBps": str(slippage_bps),
        }
        url = f"{JUPITER_QUOTE_API}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                raw = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError) as e:
            log.warning("jupiter quote failed: %s", e)
            return None

        out_atomic = int(raw.get("outAmount", 0))
        out_amount = out_atomic / (10 ** out_dec)
        price = (out_amount / amount_in) if amount_in > 0 else None
        return {
            "input": input_token.upper(),
            "output": output_token.upper(),
            "in_amount": amount_in,
            "out_amount": round(out_amount, 6),
            "price": round(price, 6) if price is not None else None,
            "slippage_bps": slippage_bps,
            "route_plan_hops": len(raw.get("routePlan") or []),
            "raw_out_atomic": out_atomic,
        }

    # ──────────────────────────────────────────────────────────────────
    # Trade proposal (confirmation firewall)
    # ──────────────────────────────────────────────────────────────────

    def propose_swap(
        self,
        input_token: str,
        output_token: str,
        amount_in: float,
        reason: str = "",
        auto_execute_paper: bool = True,
    ) -> Proposal:
        """Create a trade proposal. Paper mode: logs + (optionally) simulates.
        Live mode: raises — deliberately not implemented.
        """
        if LIVE_TRADING:
            raise NotImplementedError(
                "live trading not implemented — remove LIVE_TRADING=1 or implement a signer"
            )

        q = self.quote(input_token, output_token, amount_in)
        if q is None:
            # Proposal is still logged so the operator can see it was attempted
            quoted_output = 0.0
            quote_price = None
            status = "DENIED"
            audit = ["quote_failed"]
            reason_full = f"{reason} [quote unavailable]".strip()
        else:
            quoted_output = q["out_amount"]
            quote_price = q["price"]
            status = "PENDING"
            audit = [f"jupiter_quote_hops={q['route_plan_hops']}"]
            reason_full = reason

        proposal = Proposal(
            id=f"prop-{uuid.uuid4().hex[:10]}",
            ts=datetime.now(UTC).isoformat(),
            input_token=input_token.upper(),
            output_token=output_token.upper(),
            input_amount=amount_in,
            quoted_output=quoted_output,
            quote_price=quote_price,
            status=status,
            reason=reason_full,
            mode="paper",
            audit=audit,
        )

        # Request firewall approval. Even in paper mode this fails closed when
        # the firewall is unavailable so an integration bug cannot execute a
        # simulated trade and teach the rest of the system a false approval path.
        approved = self._request_approval(proposal)
        if approved:
            proposal.status = "APPROVED"
            proposal.approver = "confirmation_firewall"
            if auto_execute_paper and q is not None:
                self._simulate_swap(proposal)
                proposal.status = "EXECUTED_PAPER"
                proposal.audit.append("paper_swap_simulated")
        else:
            proposal.status = "DENIED"
            proposal.audit.append("approval_not_granted")

        self._log_proposal(proposal)

        # Fire an event-bus notification regardless of outcome
        try:
            from lib.core.event_bus import get_bus
            get_bus().publish(
                "trade.proposed",
                asdict(proposal),
                source="solana_wallet",
            )
        except Exception:
            pass

        return proposal

    # ──────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────

    def _request_approval(self, proposal: Proposal) -> bool:
        """Ask the confirmation firewall to gate this trade.

        Firewall failures deny the proposal in both paper and future live mode.
        Paper execution should exercise the same authorization path instead of
        silently succeeding when imports, config, or Telegram plumbing regress.
        """
        try:
            from lib.core.confirmation_firewall import ActionRisk, ConfirmationFirewall
        except Exception:
            log.warning("confirmation firewall unavailable; denying paper proposal")
            proposal.audit.append("confirmation_firewall_unavailable")
            return False

        fw = self._confirmation_firewall or ConfirmationFirewall()
        amount_usd = self._approval_amount_usd(proposal)
        details = (
            f"{proposal.input_amount} {proposal.input_token} "
            f"for ~{proposal.quoted_output} {proposal.output_token}"
        )
        try:
            approved = bool(
                fw.request_confirmation(
                    action=f"swap {proposal.input_token}->{proposal.output_token}",
                    risk=ActionRisk.FINANCIAL,
                    details=details,
                    amount=amount_usd,
                )
            )
        except Exception:
            log.warning("confirmation firewall request failed; denying paper proposal")
            proposal.audit.append("confirmation_firewall_error")
            return False

        proposal.audit.append(
            "confirmation_firewall_approved" if approved else "confirmation_firewall_denied"
        )
        return approved

    @staticmethod
    def _approval_amount_usd(proposal: Proposal) -> float:
        """Best-effort USD notional for firewall daily-limit accounting."""
        stablecoins = {"USDC", "USDT"}
        if proposal.input_token in stablecoins:
            return max(0.0, float(proposal.input_amount))
        if proposal.output_token in stablecoins:
            return max(0.0, float(proposal.quoted_output))
        return 0.0

    def _simulate_swap(self, proposal: Proposal) -> None:
        """Update the paper ledger as if the swap filled at the quoted price."""
        ledger = self.balance()
        ledger[proposal.input_token] = round(
            ledger.get(proposal.input_token, 0.0) - proposal.input_amount, 6
        )
        ledger[proposal.output_token] = round(
            ledger.get(proposal.output_token, 0.0) + proposal.quoted_output, 6
        )
        self._write_ledger(ledger)

    def _log_proposal(self, proposal: Proposal) -> None:
        try:
            with PROPOSALS_LOG.open("a") as f:
                f.write(json.dumps(asdict(proposal), default=str) + "\n")
        except Exception as e:
            log.warning("proposal log write failed: %s", e)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Sapphire Solana paper wallet")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("balance")
    q = sub.add_parser("quote")
    q.add_argument("--input", required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--amount", type=float, required=True)
    p = sub.add_parser("propose")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--amount", type=float, required=True)
    p.add_argument("--reason", default="")
    sub.add_parser("info")

    args = parser.parse_args()
    w = SolanaWallet()

    if args.cmd == "init":
        info = w.init_wallet()
        print(json.dumps(asdict(info), indent=2))
    elif args.cmd == "info":
        info = w.load()
        print(json.dumps(asdict(info), indent=2))
    elif args.cmd == "balance":
        w.load()
        print(json.dumps(w.balance(), indent=2))
    elif args.cmd == "quote":
        w.load()
        q = w.quote(args.input, args.output, args.amount)
        print(json.dumps(q, indent=2))
    elif args.cmd == "propose":
        w.load()
        prop = w.propose_swap(args.input, args.output, args.amount, reason=args.reason)
        print(json.dumps(asdict(prop), indent=2))


if __name__ == "__main__":
    _cli()
