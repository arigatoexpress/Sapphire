"""Tests for the Telegram MarkdownV2 formatters."""

from __future__ import annotations

import re

import pytest

from lib.telegram import formatters as fmt

# Every MarkdownV2 special character per Telegram's spec.
MDV2_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def assert_mdv2_balanced(text: str) -> None:
    """Assert every MDV2 special outside a code span is backslash-escaped.

    This is the property that matters in production: Telegram rejects the
    whole message with a 400 if any reserved character is left bare.
    """
    # Strip fenced and inline code spans — specials are literal inside them.
    without_fences = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    without_code = re.sub(r"`[^`]*`", "", without_fences)

    i = 0
    while i < len(without_code):
        ch = without_code[i]
        if ch == "\\":
            i += 2
            continue
        if ch in MDV2_SPECIALS:
            # `*` (bold) and `_` (italic) are emphasis markers we emit
            # deliberately; every other special must arrive escaped.
            if ch not in {"*", "_"}:
                raise AssertionError(
                    f"unescaped {ch!r} at index {i} in: {without_code[max(0, i - 30) : i + 30]!r}"
                )
        i += 1


class TestEscaping:
    @pytest.mark.parametrize("char", list(MDV2_SPECIALS))
    def test_every_special_char_is_escaped(self, char):
        assert fmt.esc(char) == "\\" + char

    def test_none_becomes_em_dash(self):
        assert fmt.esc(None) == "—"

    def test_plain_text_untouched(self):
        assert fmt.esc("hello world") == "hello world"

    def test_realistic_ticker_string(self):
        assert fmt.esc("BTC-USD +5.2%") == "BTC\\-USD \\+5\\.2%"

    def test_code_escapes_backticks_and_backslashes(self):
        assert fmt.code("a`b") == "`a\\`b`"
        assert fmt.code("a\\b") == "`a\\\\b`"

    def test_bold_escapes_inner_content(self):
        assert fmt.bold("a.b") == "*a\\.b*"


class TestNumbers:
    def test_delta_arrow_thresholds(self):
        assert fmt.delta_arrow(1.0) == "🟢"
        assert fmt.delta_arrow(-1.0) == "🔴"
        assert fmt.delta_arrow(0.0) == "⚪"
        assert fmt.delta_arrow(None) == "⚪"

    def test_tiny_moves_read_as_flat(self):
        """Avoid false-positive green/red on rounding noise."""
        assert fmt.delta_arrow(0.0001) == "⚪"
        assert fmt.delta_arrow(-0.0001) == "⚪"

    @pytest.mark.parametrize(
        "value,expected",
        [
            (1234.5, "`$1,234.50`"),
            (0, "`$0.00`"),
            (-42.5, "`$-42.50`"),
            (15_000, "`$15.0K`"),
            (2_500_000, "`$2.50M`"),
        ],
    )
    def test_usd_scaling(self, value, expected):
        assert fmt.fmt_usd(value) == expected

    def test_usd_none(self):
        assert fmt.fmt_usd(None) == "`—`"

    def test_pct_carries_explicit_sign(self):
        assert "+5.20%" in fmt.fmt_pct(5.2)
        assert "-3.10%" in fmt.fmt_pct(-3.1)

    def test_pct_emoji_matches_direction(self):
        assert fmt.fmt_pct(5.2).startswith("🟢")
        assert fmt.fmt_pct(-5.2).startswith("🔴")

    def test_int_thousands_separator(self):
        assert fmt.fmt_int(1234567) == "`1,234,567`"


class TestTables:
    def test_kv_table_escapes_keys(self):
        out = fmt.kv_table([("a.b", "`v`")])
        assert "a\\.b" in out

    def test_kv_table_empty(self):
        assert fmt.kv_table([]) == "\\(empty\\)"

    def test_fixed_table_right_aligns(self):
        out = fmt.fixed_table(
            ["Sym", "Val"], [["BTC", "$1.00"], ["ETH", "$1000.00"]], align=["l", "r"]
        )
        lines = out.strip("`").strip().splitlines()
        # The short value is padded left so decimals line up.
        assert lines[2].endswith("$1.00")
        assert lines[3].endswith("$1000.00")
        assert len(lines[2]) == len(lines[3])

    def test_fixed_table_strips_backticks_so_fence_never_breaks(self):
        out = fmt.fixed_table(["A"], [["ev`il"]])
        assert "ev'il" in out
        assert out.count("```") == 2

    def test_fixed_table_handles_empty_rows(self):
        out = fmt.fixed_table(["A", "B"], [])
        assert "A" in out and "B" in out


class TestPortfolio:
    def test_sorted_by_value_descending(self):
        rows = [
            fmt.PortfolioRow("SMALL", 10.0),
            fmt.PortfolioRow("BIG", 1000.0),
            fmt.PortfolioRow("MID", 100.0),
        ]
        out = fmt.fmt_portfolio_table(rows)
        assert out.index("BIG") < out.index("MID") < out.index("SMALL")

    def test_empty_portfolio_is_actionable(self):
        out = fmt.fmt_portfolio_table([])
        assert "No holdings" in out
        assert "credentials" in out

    def test_total_and_change_in_header(self):
        out = fmt.fmt_portfolio_table(
            [fmt.PortfolioRow("BTC", 100.0)], total_usd=775.0, day_change_pct=2.5
        )
        assert "$775.00" in out
        assert "+2.50%" in out

    def test_unpriced_holding_renders_dash_not_zero(self):
        """A None price must never silently read as $0.00."""
        out = fmt.fmt_portfolio_table([fmt.PortfolioRow("MEGA", None)])
        assert "MEGA" in out
        assert "$0.00" not in out

    def test_output_is_valid_markdownv2(self):
        out = fmt.fmt_portfolio_table(
            [fmt.PortfolioRow("BTC-USD", 1234.56, 5.2)],
            total_usd=1234.56,
            day_change_pct=5.2,
            updated_at="12:00 UTC",
        )
        assert_mdv2_balanced(out)


class TestSignals:
    def test_side_emoji_mapping(self):
        long_card = fmt.fmt_signal_alert(fmt.SignalCard("BTC", "long", 80))
        short_card = fmt.fmt_signal_alert(fmt.SignalCard("BTC", "short", 80))
        assert "🟩" in long_card
        assert "🟥" in short_card

    @pytest.mark.parametrize(
        "severity,emoji",
        [("critical", "🚨"), ("warn", "⚠️"), ("info", "🟢"), ("ok", "✅")],
    )
    def test_severity_emoji(self, severity, emoji):
        out = fmt.fmt_signal_alert(fmt.SignalCard("BTC", "long", 70), severity=severity)
        assert out.startswith(emoji)

    def test_optional_fields_omitted_when_absent(self):
        out = fmt.fmt_signal_alert(fmt.SignalCard("BTC", "long", 70))
        assert "Stop" not in out
        assert "Target" not in out

    def test_signal_card_is_valid_markdownv2(self):
        out = fmt.fmt_signal_alert(
            fmt.SignalCard("BTC-USD", "long", 83.3, entry=1.5, stop=1.0, reason="RSI < 30.")
        )
        assert_mdv2_balanced(out)


class TestSecurityAndStatus:
    @pytest.mark.parametrize(
        "severity,emoji",
        [("critical", "🚨"), ("high", "⚠️"), ("medium", "🟡"), ("low", "🟢")],
    )
    def test_threat_severity_emoji(self, severity, emoji):
        out = fmt.fmt_security_card(fmt.ThreatCard("CVE-2026-1", severity))
        assert out.startswith(emoji)

    def test_security_card_valid_markdownv2(self):
        out = fmt.fmt_security_card(
            fmt.ThreatCard("CVE-2026-1234", "critical", "requests", "RCE via header.")
        )
        assert_mdv2_balanced(out)

    def test_status_snapshot_shows_kill_switch_when_armed(self):
        out = fmt.fmt_status_snapshot(
            services=[("pm-bot", "running")],
            freshness=[("Signals", "2m ago")],
            regime="neutral",
            fear_greed=27,
            kill_switch_armed=True,
        )
        assert "KILL SWITCH" in out

    def test_status_snapshot_hides_kill_switch_when_off(self):
        out = fmt.fmt_status_snapshot(
            services=[("pm-bot", "running")],
            freshness=[("Signals", "2m ago")],
            regime="neutral",
            fear_greed=27,
        )
        assert "KILL SWITCH" not in out

    def test_status_snapshot_valid_markdownv2(self):
        out = fmt.fmt_status_snapshot(
            services=[("pm-bot", "✅ running"), ("chain-refresh", "⚪ idle")],
            freshness=[("Signals", "2m ago"), ("Chain", "missing")],
            regime="risk_off",
            fear_greed=27,
            kill_switch_armed=True,
        )
        assert_mdv2_balanced(out)


class TestHeartbeat:
    def test_all_agents_up_shows_check(self):
        out = fmt.fmt_heartbeat_line(
            agents_ok=33, agents_total=33, regime="neutral", fear_greed=27, portfolio_usd=775.0
        )
        assert "✅" in out
        assert "33/33 agents" in out

    def test_degraded_shows_warning(self):
        out = fmt.fmt_heartbeat_line(
            agents_ok=30, agents_total=33, regime="neutral", fear_greed=27, portfolio_usd=775.0
        )
        assert "⚠️" in out

    def test_kill_switch_appended(self):
        out = fmt.fmt_heartbeat_line(
            agents_ok=33,
            agents_total=33,
            regime="neutral",
            fear_greed=27,
            portfolio_usd=775.0,
            kill_switch_armed=True,
        )
        assert "KILL SWITCH" in out

    def test_optional_fields_omitted(self):
        out = fmt.fmt_heartbeat_line(
            agents_ok=1, agents_total=1, regime="x", fear_greed=None, portfolio_usd=None
        )
        assert "F&G" not in out
        assert "Portfolio" not in out

    def test_heartbeat_valid_markdownv2(self):
        out = fmt.fmt_heartbeat_line(
            agents_ok=30,
            agents_total=33,
            regime="risk_off",
            fear_greed=27,
            portfolio_usd=775.42,
            kill_switch_armed=True,
        )
        assert_mdv2_balanced(out)


class TestSettingsAndReports:
    def test_settings_reflects_state(self):
        out = fmt.fmt_settings(
            heartbeat_enabled=True,
            heartbeat_hours=12,
            live_notifications=False,
            kill_switch_armed=False,
        )
        assert "ENABLED" in out
        assert "every 12h" in out
        assert "DRAFT ONLY" in out

    def test_empty_reports_message(self):
        assert "No drafts" in fmt.fmt_reports_list([])

    def test_reports_table_valid_markdownv2(self):
        out = fmt.fmt_reports_list([("ready", "Weekly Brief #1", "2026-07-25T10:00")])
        assert_mdv2_balanced(out)
