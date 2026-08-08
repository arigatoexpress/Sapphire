"""Helpers for plant to record closed-trade lessons (no broker I/O)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from lib.grok.genome import LessonBook, lesson_from_closed_trade


def record_closed_trade(
    book_path: Path,
    *,
    trade_id: str,
    symbol: str,
    rail: str,
    realized_pnl_usd: float,
    thesis: str = "",
    tags: Iterable[str] | None = None,
    source: str = "broker",
    meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load LessonBook, append one closed trade, save, return summary."""
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
