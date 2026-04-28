"""Operator-seeded live trade ledger.

No live broker APIs are called here. The ledger only persists fills that an
operator has confirmed and supplied as JSON. Raw account identifiers are
rejected; callers must store only per-account hashes.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable

from lib.core.provenance import ProvenanceEnvelope
from lib.security.pii_redactor import per_tenant_hash, redact_text

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER_ROOT = REPO_ROOT / "data" / "live_portfolio"
ACCOUNT_TENANT = "live_portfolio"

_RAW_ACCOUNT_HINT_RE = re.compile(r"(\.{3}\d{4}|\b\d{4,}\b)")
_SAFE_ACCOUNT_RE = re.compile(r"^(tenant_[a-z0-9_\-]+_[0-9a-f]{16}|EXAMPLE-[A-Za-z0-9_.\-]+)$")
_VALID_SIDE = {"buy", "sell"}
_VALID_ORDER_TYPE = {"limit", "market", "stop", "stop_limit"}


def parse_utc(value: str | datetime) -> datetime:
    """Parse an ISO timestamp and normalize it to UTC."""

    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value).strip()
        if not raw:
            raise ValueError("timestamp is required")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0)


def hash_account(raw_account: str, *, salt: str | None = None) -> str:
    """Return a per-account hash suitable for ledger paths.

    The raw account value may be a redacted string from the operator UI (for
    example ``Individual (...5966)``). It is still treated as sensitive and is
    never persisted by this helper.
    """

    return per_tenant_hash(str(raw_account), ACCOUNT_TENANT, salt=salt)


def ensure_account_hash(account_hash: str) -> str:
    account = str(account_hash or "").strip()
    if not account:
        raise ValueError("account_hash is required")
    if _RAW_ACCOUNT_HINT_RE.search(account):
        raise ValueError("raw account identifiers are not allowed in the live ledger")
    if not _SAFE_ACCOUNT_RE.match(account):
        raise ValueError("account_hash must be a per-tenant hash or EXAMPLE-* fixture id")
    return account


def redact_source_reference(value: str | None) -> str | None:
    """Redact email/message/order references while preserving a short prefix."""

    if value is None:
        return None
    redacted = redact_text(str(value))
    compact = " ".join(redacted.split()).strip()
    if not compact:
        return None
    if len(compact) <= 32:
        return compact
    prefix = re.sub(r"[^A-Za-z0-9]", "", compact)[:6] or "source"
    return f"{prefix}...redacted"


def _positive_float(name: str, value: Any, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if allow_zero:
        if number < 0:
            raise ValueError(f"{name} must be >= 0")
    elif number <= 0:
        raise ValueError(f"{name} must be > 0")
    return number


@dataclass(frozen=True)
class LiveTradeRecord:
    """One operator-confirmed live fill."""

    trade_id: str
    account_hash: str
    exchange: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    fill_price: float
    fill_at: str
    notional: float
    fee: float
    total_cost: float
    ramp_tier: int
    source_email_message_id_redacted: str | None = None
    provenance_envelope: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.trade_id).strip():
            raise ValueError("trade_id is required")
        ensure_account_hash(self.account_hash)
        if not str(self.exchange).strip():
            raise ValueError("exchange is required")
        symbol = str(self.symbol).strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        side = str(self.side).strip().lower()
        if side not in _VALID_SIDE:
            raise ValueError(f"side must be one of {sorted(_VALID_SIDE)}")
        order_type = str(self.order_type).strip().lower()
        if order_type not in _VALID_ORDER_TYPE:
            raise ValueError(f"order_type must be one of {sorted(_VALID_ORDER_TYPE)}")
        quantity = _positive_float("quantity", self.quantity)
        fill_price = _positive_float("fill_price", self.fill_price)
        notional = _positive_float("notional", self.notional)
        fee = _positive_float("fee", self.fee, allow_zero=True)
        total_cost = _positive_float("total_cost", self.total_cost)
        ramp_tier = int(self.ramp_tier)
        if ramp_tier < 1:
            raise ValueError("ramp_tier must be >= 1")
        fill_at = parse_utc(self.fill_at).isoformat()
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "order_type", order_type)
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "fill_price", fill_price)
        object.__setattr__(self, "fill_at", fill_at)
        object.__setattr__(self, "notional", notional)
        object.__setattr__(self, "fee", fee)
        object.__setattr__(self, "total_cost", total_cost)
        object.__setattr__(self, "ramp_tier", ramp_tier)
        object.__setattr__(
            self,
            "source_email_message_id_redacted",
            redact_source_reference(self.source_email_message_id_redacted),
        )

    @property
    def fill_date(self) -> date:
        return parse_utc(self.fill_at).date()

    @property
    def dedupe_key(self) -> tuple[str, str]:
        return (self.trade_id, self.fill_at)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LiveTradeRecord":
        if not isinstance(payload, dict):
            raise ValueError("trade record must be a JSON object")
        data = dict(payload)
        if "account" in data:
            if "account_hash" not in data:
                # Tolerated migration path: lift raw `account` to the auto-redact slot.
                data["account_hash"] = data.pop("account")
            else:
                # Raw `account` smuggled in alongside an explicit `account_hash`
                # (potentially `None`) is a leakage shape; reject loudly.
                raise ValueError(
                    "raw `account` is not a permitted field; pre-hash via "
                    "ensure_account_hash and pass `account_hash` only"
                )
        if "type" in data and "order_type" not in data:
            data["order_type"] = data.pop("type")
        return cls(**data)

    @classmethod
    def build(
        cls,
        payload: dict[str, Any],
        *,
        generator: str = "live_portfolio.ledger",
        source_paths: tuple[str | Path, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "LiveTradeRecord":
        """Build a record and stamp it with a provenance envelope."""

        data = dict(payload)
        data.pop("provenance_envelope", None)
        provisional = cls(**{**data, "provenance_envelope": {}})
        envelope = ProvenanceEnvelope.build(
            provisional.to_dict(),
            generator=generator,
            source_paths=source_paths,
            metadata=metadata or {"surface": "live_capital_ledger"},
        ).to_dict()
        return cls(**{**data, "provenance_envelope": envelope})


class LiveLedger:
    """JSONL-backed live trade ledger."""

    def __init__(self, root: str | Path = DEFAULT_LEDGER_ROOT) -> None:
        self.root = Path(root)

    def trade_path(self, record: LiveTradeRecord) -> Path:
        return self.root / record.account_hash / record.fill_date.isoformat() / "trades.jsonl"

    def iter_paths(self, account_hash: str | None = None) -> Iterable[Path]:
        if account_hash is not None:
            account_dir = self.root / ensure_account_hash(account_hash)
            yield from sorted(account_dir.glob("*/trades.jsonl"))
            return
        if not self.root.exists():
            return
        yield from sorted(self.root.glob("*/20*/trades.jsonl"))

    def load(self, account_hash: str | None = None, *, strict: bool = False) -> list[LiveTradeRecord]:
        records: list[LiveTradeRecord] = []
        for path in self.iter_paths(account_hash):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                if strict:
                    raise
                continue
            for line in lines:
                if not line.strip():
                    continue
                try:
                    records.append(LiveTradeRecord.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    if strict:
                        raise
                    continue
        records.sort(key=lambda r: (r.fill_at, r.trade_id))
        return records

    def append(self, record: LiveTradeRecord) -> bool:
        """Append a record. Returns ``False`` when it is a duplicate."""

        existing = {r.dedupe_key for r in self.load(record.account_hash)}
        if record.dedupe_key in existing:
            return False
        path = self.trade_path(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return True

    def accounts(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())

    def summary(self, account_hash: str | None = None) -> dict[str, Any]:
        records = self.load(account_hash)
        total_notional = sum(r.notional for r in records)
        total_fees = sum(r.fee for r in records)
        by_symbol: dict[str, int] = {}
        for record in records:
            by_symbol[record.symbol] = by_symbol.get(record.symbol, 0) + 1
        latest = records[-1].to_dict() if records else None
        if latest:
            latest.pop("provenance_envelope", None)
        return {
            "accounts": self.accounts() if account_hash is None else [account_hash],
            "trade_count": len(records),
            "total_notional": round(total_notional, 8),
            "total_fees": round(total_fees, 8),
            "symbols": by_symbol,
            "latest_trade": latest,
        }
