from __future__ import annotations

from lib.grok.genome import LessonBook, lesson_from_closed_trade


def test_seed_and_summary():
    book = LessonBook()
    book.seed_axti_and_dens()
    book.seed_axti_and_dens()  # idempotent
    s = book.summary()
    assert s["count"] == 2
    assert s["wins"] == 1
    assert s["blocked"] == 1


def test_lesson_from_closed_trade_win_loss():
    w = lesson_from_closed_trade(
        trade_id="1", symbol="AXTI", rail="rh_agentic", realized_pnl_usd=50
    )
    assert w.outcome == "win"
    l = lesson_from_closed_trade(trade_id="2", symbol="X", rail="rh_l2", realized_pnl_usd=-3)
    assert l.outcome == "loss"
