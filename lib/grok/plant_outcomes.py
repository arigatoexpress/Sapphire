"""Helpers for plant to record closed-trade lessons (no broker I/O).

Contract: data/grok-web-exports/2026-08-08_genome-broker-reconcile-contract.md
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from lib.grok.genome import (
    SOURCE_AUTO_ESTIMATE,
    SOURCE_BROKER,
    LessonBook,
    lesson_from_closed_trade,
    realized_pnl_long,
)


def record_closed_trade(
    book_path: Path,
    *,
    trade_id: str,
    symbol: str,
    rail: str,
    realized_pnl_usd: float,
    thesis: str = "",
    tags: Iterable[str] | None = None,
    source: str = SOURCE_BROKER,
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load LessonBook, append one closed trade, save, return summary.

    Prefer source=broker when fill prices are confirmed. Plant currently uses
    source=auto_estimate for snapshot notional closes; broker rows supersede
    matching auto_estimate ids (see LessonBook.append).
    """
    book = LessonBook.load(book_path)
    book.append(
        lesson_from_closed_trade(
            trade_id=trade_id,
            symbol=symbol,
            rail=rail,
            realized_pnl_usd=realized_pnl_usd,
            thesis=thesis,
            tags=tags,
            source=source,
            meta=meta,
        )
    )
    book.save(book_path)
    return book.summary()


def record_long_close_from_fills(
    book_path: Path,
    *,
    trade_id: str,
    symbol: str,
    rail: str,
    entry_price: float,
    exit_price: float,
    qty: float,
    multiplier: float = 1.0,
    fees_usd: float = 0.0,
    thesis: str = "",
    tags: Iterable[str] | None = None,
    source: str = SOURCE_BROKER,
    meta: Mapping[str, Any] | None = None,
    reconcile: str = "rh_mcp",
) -> dict[str, Any]:
    """Compute long PnL from fills and record (broker path helper)."""
    pnl = realized_pnl_long(
        entry_price=entry_price,
        exit_price=exit_price,
        qty=qty,
        multiplier=multiplier,
        fees_usd=fees_usd,
    )
    merged: dict[str, Any] = {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "qty": qty,
        "multiplier": multiplier,
        "fees_usd": fees_usd,
        "reconcile": reconcile,
    }
    if meta:
        merged.update(dict(meta))
    return record_closed_trade(
        book_path,
        trade_id=trade_id,
        symbol=symbol,
        rail=rail,
        realized_pnl_usd=pnl,
        thesis=thesis,
        tags=tags,
        source=source,
        meta=merged,
    )


__all__ = [
    "SOURCE_AUTO_ESTIMATE",
    "SOURCE_BROKER",
    "record_closed_trade",
    "record_long_close_from_fills",
    "realized_pnl_long",
]
