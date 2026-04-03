"""Strategy-ops payload builders extracted from the unified frontend monolith."""

from __future__ import annotations

import math
import os
from datetime import UTC, datetime, timedelta

from firebase_admin import firestore


def _coerce_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        val = value.strip()
        if not val:
            return None
        if val.endswith("Z"):
            try:
                return datetime.fromisoformat(val[:-1]).replace(tzinfo=UTC)
            except Exception:
                pass
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
            except Exception:
                pass
        try:
            dt = datetime.fromisoformat(val)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None
    if hasattr(value, "to_datetime"):
        try:
            dt = value.to_datetime()
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None
    return None


def _iso_or_default(value, default=None):
    if value is None:
        return default
    dt = _coerce_datetime(value)
    if dt is None:
        return default
    return dt.replace(microsecond=0).isoformat()


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, min_value, max_value):
    if value < min_value:
        return min_value
    if value > max_value:
        return max_value
    return value


def _strategy_lane_info(row: dict) -> tuple[str, str]:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    strategy = str(
        row.get("strategy")
        or metadata.get("strategy")
        or metadata.get("strategy_id")
        or metadata.get("system")
        or ""
    ).strip().lower()
    timeframe = str(
        row.get("timeframe")
        or metadata.get("timeframe")
        or metadata.get("tf")
        or metadata.get("interval")
        or ""
    ).strip().lower()
    return (strategy or "unknown", timeframe or "unknown")


def _norm_symbol(value) -> str:
    sym = str(value or "").strip().upper()
    if not sym:
        return "UNKNOWN"
    for suffix in ("/USDT", "/USD", "USDT", "USD", "-PERP"):
        if sym.endswith(suffix):
            sym = sym[: -len(suffix)]
    return sym or "UNKNOWN"


def _bucket(label: str) -> dict:
    return {
        "label": label,
        "sample_size": 0,
        "filled_success_count": 0,
        "reject_skip_count": 0,
        "hard_failed_count": 0,
        "accepted_no_fill_count": 0,
        "net_pnl_after_fees_usd": 0.0,
        "estimated_fees_usd": 0.0,
        "estimated_slippage_usd": 0.0,
    }


def build_strategy_scorecard(
    *,
    db_client,
    days: int = 7,
    platform: str = 'lighter',
    limit: int = 1800,
) -> dict:
    if db_client is None:
        return {
            'generated_at': datetime.now(UTC).isoformat(),
            'platform': str(platform or 'lighter').strip().lower(),
            'window': {'days': max(1, int(days or 7))},
            'totals': {'sample_size': 0, 'lanes': 0, 'error': 'firestore_unavailable'},
            'ranked': [],
        }

    safe_days = max(1, min(int(days or 7), 30))
    safe_limit = max(300, min(int(limit or 1800), 4000))
    platform_norm = str(platform or 'lighter').strip().lower()
    now_utc = datetime.now(UTC)
    since = now_utc - timedelta(days=safe_days)

    def _to_float(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _estimate_notional_usd(row: dict) -> float:
        metadata = row.get('metadata', {}) if isinstance(row.get('metadata'), dict) else {}
        direct = (
            row.get('notional_usd')
            or metadata.get('notional_usd')
            or row.get('order_notional_usd')
            or metadata.get('order_notional_usd')
        )
        direct_val = _to_float(direct, 0.0)
        if direct_val > 0:
            return direct_val
        qty = _to_float(
            row.get('filled_quantity') or row.get('quantity') or metadata.get('filled_quantity'),
            0.0,
        )
        px = _to_float(
            row.get('avg_price') or row.get('price') or metadata.get('avg_price') or metadata.get('price'),
            0.0,
        )
        notional = qty * px
        return notional if notional > 0 else 0.0

    default_payoff = max(0.1, float(os.getenv('STRATEGY_OPS_DEFAULT_PAYOFF_RATIO', '1.2')))
    fee_pct = float(os.getenv('STRATEGY_OPS_FEE_BPS', '7.0')) / 100.0
    slippage_pct = float(os.getenv('STRATEGY_OPS_SLIPPAGE_BPS', '5.0')) / 100.0
    promote_min_samples = max(
        10,
        int(_to_float(os.getenv('STRATEGY_OPS_PROMOTE_MIN_SAMPLES', '40'), 40)),
    )
    hold_reject_tax_pct = _to_float(os.getenv('STRATEGY_OPS_HOLD_REJECT_TAX_PCT', '70.0'), 70.0)
    hold_hard_fail_pct = _to_float(os.getenv('STRATEGY_OPS_HOLD_HARD_FAIL_PCT', '15.0'), 15.0)
    min_confident_samples = max(
        10,
        int(_to_float(os.getenv('STRATEGY_OPS_MIN_CONFIDENT_SAMPLE', '40'), 40)),
    )
    bayes_alpha = max(0.1, _to_float(os.getenv('STRATEGY_OPS_BAYES_ALPHA', '2.0'), 2.0))
    bayes_beta = max(0.1, _to_float(os.getenv('STRATEGY_OPS_BAYES_BETA', '2.0'), 2.0))
    promote_min_ev = _to_float(os.getenv('STRATEGY_OPS_PROMOTE_MIN_EV_PCT', '0.20'), 0.20)
    monitor_min_ev = _to_float(os.getenv('STRATEGY_OPS_MONITOR_MIN_EV_PCT', '0.05'), 0.05)
    depri_max_ev = _to_float(os.getenv('STRATEGY_OPS_DEPRIORITIZE_MAX_EV_PCT', '-0.05'), -0.05)
    fee_bps = float(os.getenv('STRATEGY_OPS_FEE_BPS', '7.0'))
    slippage_bps = float(os.getenv('STRATEGY_OPS_SLIPPAGE_BPS', '5.0'))

    def _lane_recommendation(row: dict) -> str:
        sample = int(row.get('sample_size', 0) or 0)
        reject_tax = _to_float(row.get('reject_tax_pct'), 0.0)
        hard_fail = _to_float(row.get('hard_fail_pct'), 0.0)
        ev_adj = _to_float(row.get('ev_adjusted_pct'), 0.0)
        pnl_net = _to_float(row.get('net_pnl_after_fees_usd'), 0.0)
        if sample < 12:
            return 'research'
        if reject_tax >= hold_reject_tax_pct or hard_fail >= hold_hard_fail_pct:
            return 'hold'
        if ev_adj >= promote_min_ev and sample >= promote_min_samples and pnl_net > 0:
            return 'promote'
        if ev_adj >= monitor_min_ev:
            return 'monitor'
        if ev_adj <= -0.35 and sample >= 20:
            return 'block'
        if ev_adj <= depri_max_ev:
            return 'deprioritize'
        return 'hold'

    exec_rows = []
    execution_collection = os.environ.get('TRADE_EXECUTIONS_COLLECTION', 'trade_executions')
    try:
        docs = list(
            db_client.collection('execution_verifications')
            .where('platform', '==', platform_norm)
            .where('recorded_at', '>=', since)
            .order_by('recorded_at', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        exec_rows = [doc.to_dict() or {} for doc in docs]
    except Exception:
        docs = list(
            db_client.collection('execution_verifications')
            .order_by('recorded_at', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        for doc in docs:
            row = doc.to_dict() or {}
            if str(row.get('platform', '')).strip().lower() != platform_norm:
                continue
            ts = _coerce_datetime(row.get('recorded_at') or row.get('timestamp'))
            if ts and ts < since:
                continue
            exec_rows.append(row)

    pnl_rows = []
    try:
        docs = list(
            db_client.collection(execution_collection)
            .where('timestamp', '>=', since.isoformat())
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        pnl_rows = [doc.to_dict() or {} for doc in docs]
    except Exception:
        docs = list(
            db_client.collection(execution_collection)
            .order_by('timestamp', direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        for doc in docs:
            row = doc.to_dict() or {}
            ts = _coerce_datetime(row.get('timestamp'))
            if ts and ts < since:
                continue
            pnl_rows.append(row)

    agg = {}
    equity_events: list[tuple[datetime, float]] = []

    def _slot(strategy: str, timeframe: str) -> dict:
        key = f'{strategy}@{timeframe}'
        if key not in agg:
            agg[key] = {
                'strategy': strategy,
                'timeframe': timeframe,
                'sample_size': 0,
                'filled_success_count': 0,
                'reject_skip_count': 0,
                'hard_failed_count': 0,
                'accepted_no_fill_count': 0,
                'net_realized_pnl_usd': 0.0,
                'net_pnl_after_fees_usd': 0.0,
                'estimated_fees_usd': 0.0,
                'estimated_slippage_usd': 0.0,
                'gross_win_pnl_usd': 0.0,
                'gross_loss_pnl_usd': 0.0,
                'trade_wins': 0,
                'trade_losses': 0,
                'total_notional_usd': 0.0,
                'trade_count': 0,
                'signal_conf_sum': 0.0,
                'signal_conf_count': 0,
                'latency_ms_sum': 0.0,
                'latency_ms_count': 0,
            }
        return agg[key]

    for row in exec_rows:
        strategy, timeframe = _strategy_lane_info(row)
        slot = _slot(strategy, timeframe)
        slot['sample_size'] += 1
        outcome = str(row.get('outcome', '')).strip().lower()
        if outcome == 'filled_success':
            slot['filled_success_count'] += 1
        elif outcome in {'policy_noop', 'policy_reject', 'noop'}:
            slot['reject_skip_count'] += 1
        elif outcome == 'hard_failed':
            slot['hard_failed_count'] += 1
        elif outcome == 'accepted_no_fill':
            slot['accepted_no_fill_count'] += 1
        conf_val = _to_float(
            row.get('confidence')
            or (row.get('signal_metadata', {}) or {}).get('confidence')
            or (row.get('metadata', {}) or {}).get('confidence'),
            -1.0,
        )
        if conf_val >= 0:
            slot['signal_conf_sum'] += conf_val
            slot['signal_conf_count'] += 1
        latency_val = _to_float(
            row.get('latency_ms')
            or row.get('processing_latency_ms')
            or (row.get('metadata', {}) or {}).get('latency_ms'),
            -1.0,
        )
        if latency_val >= 0:
            slot['latency_ms_sum'] += latency_val
            slot['latency_ms_count'] += 1

    for row in pnl_rows:
        row_platform = str(row.get('platform', '') or '').strip().lower()
        if row_platform and row_platform != platform_norm:
            continue
        strategy, timeframe = _strategy_lane_info(row)
        slot = _slot(strategy, timeframe)
        pnl = _to_float(row.get('realized_pnl'), 0.0)
        notional = _estimate_notional_usd(row)
        fees = max(0.0, notional * (fee_bps / 10000.0))
        slippage = max(0.0, notional * (slippage_bps / 10000.0))
        net_after_cost = pnl - fees - slippage

        slot['net_realized_pnl_usd'] += pnl
        slot['estimated_fees_usd'] += fees
        slot['estimated_slippage_usd'] += slippage
        slot['net_pnl_after_fees_usd'] += net_after_cost
        slot['total_notional_usd'] += notional
        if pnl > 0:
            slot['gross_win_pnl_usd'] += pnl
            slot['trade_wins'] += 1
        elif pnl < 0:
            slot['gross_loss_pnl_usd'] += abs(pnl)
            slot['trade_losses'] += 1
        slot['trade_count'] += 1
        ts = _coerce_datetime(row.get('timestamp'))
        if ts is not None:
            equity_events.append((ts, net_after_cost))

    ranked = []
    for lane in agg.values():
        sample = max(1, int(lane.get('sample_size', 0) or 0))
        fill_pct = (float(lane.get('filled_success_count', 0)) / sample) * 100.0
        reject_pct = (float(lane.get('reject_skip_count', 0)) / sample) * 100.0
        hard_fail_pct = (float(lane.get('hard_failed_count', 0)) / sample) * 100.0
        pnl = _to_float(lane.get('net_realized_pnl_usd'), 0.0)
        trade_wins = int(lane.get('trade_wins', 0) or 0)
        trade_losses = int(lane.get('trade_losses', 0) or 0)
        observed_n = trade_wins + trade_losses
        p_win_obs = (trade_wins / observed_n) if observed_n > 0 else 0.5
        p_win_post = (trade_wins + bayes_alpha) / (observed_n + bayes_alpha + bayes_beta)
        p_loss_post = max(0.0, 1.0 - p_win_post)

        total_notional = max(0.0, _to_float(lane.get('total_notional_usd'), 0.0))
        trade_count = max(1, int(lane.get('trade_count', 0) or 0))
        avg_notional = total_notional / trade_count if total_notional > 0 else 4.0
        avg_win_usd = (
            _to_float(lane.get('gross_win_pnl_usd'), 0.0) / max(1, trade_wins)
            if trade_wins > 0
            else 0.0
        )
        avg_loss_usd = (
            _to_float(lane.get('gross_loss_pnl_usd'), 0.0) / max(1, trade_losses)
            if trade_losses > 0
            else 0.0
        )
        if avg_loss_usd <= 0:
            avg_loss_usd = max(avg_notional * 0.0035, 0.02)
        if avg_win_usd <= 0:
            avg_win_usd = avg_loss_usd * default_payoff

        expected_win_pct = max(0.0, (avg_win_usd / max(avg_notional, 1e-9)) * 100.0)
        expected_loss_pct = max(0.0, (avg_loss_usd / max(avg_notional, 1e-9)) * 100.0)
        ev_raw_pct = (
            (p_win_post * expected_win_pct)
            - (p_loss_post * expected_loss_pct)
            - fee_pct
            - slippage_pct
        )
        uncertainty_std = math.sqrt(max(0.0, p_win_post * (1.0 - p_win_post) / max(1, observed_n)))
        uncertainty_penalty_pct = uncertainty_std * max(expected_win_pct, expected_loss_pct, 0.15)
        sample_penalty_pct = 0.0
        if observed_n < min_confident_samples:
            sample_penalty_pct = (
                (min_confident_samples - observed_n) / max(1, min_confident_samples)
            ) * 0.25
        ev_adjusted_pct = ev_raw_pct - uncertainty_penalty_pct - sample_penalty_pct
        payoff_ratio = avg_win_usd / max(avg_loss_usd, 1e-9)

        avg_conf = (
            _to_float(lane.get('signal_conf_sum'), 0.0) / max(1, int(lane.get('signal_conf_count', 0) or 0))
            if int(lane.get('signal_conf_count', 0) or 0) > 0
            else 0.5
        )
        confidence_calibration_error_pct = abs(avg_conf - p_win_obs) * 100.0

        net_after_fees = _to_float(lane.get('net_pnl_after_fees_usd'), 0.0)
        realized_net_return_pct = (
            (net_after_fees / max(total_notional, 1e-9)) * 100.0 if total_notional > 0 else 0.0
        )
        expected_value_error_pct = abs(realized_net_return_pct - ev_adjusted_pct)
        avg_latency_ms = (
            _to_float(lane.get('latency_ms_sum'), 0.0) / max(1, int(lane.get('latency_ms_count', 0) or 0))
            if int(lane.get('latency_ms_count', 0) or 0) > 0
            else 0.0
        )
        score = (
            (ev_adjusted_pct * 100.0)
            - (confidence_calibration_error_pct * 0.12)
            - (reject_pct * 0.05)
            - (hard_fail_pct * 0.10)
        )
        row = {
            **lane,
            'filled_success_pct': round(fill_pct, 2),
            'reject_tax_pct': round(reject_pct, 2),
            'hard_fail_pct': round(hard_fail_pct, 2),
            'net_realized_pnl_usd': round(pnl, 6),
            'net_pnl_after_fees_usd': round(net_after_fees, 6),
            'estimated_fees_usd': round(_to_float(lane.get('estimated_fees_usd'), 0.0), 6),
            'estimated_slippage_usd': round(_to_float(lane.get('estimated_slippage_usd'), 0.0), 6),
            'total_notional_usd': round(total_notional, 6),
            'p_win_observed': round(p_win_obs, 4),
            'p_win': round(p_win_post, 4),
            'p_loss': round(p_loss_post, 4),
            'payoff_ratio': round(payoff_ratio, 4),
            'expected_win_pct': round(expected_win_pct, 5),
            'expected_loss_pct': round(expected_loss_pct, 5),
            'ev_raw_pct': round(ev_raw_pct, 5),
            'ev_adjusted_pct': round(ev_adjusted_pct, 5),
            'uncertainty_penalty_pct': round(uncertainty_penalty_pct, 5),
            'sample_penalty_pct': round(sample_penalty_pct, 5),
            'confidence_mean': round(avg_conf, 4),
            'confidence_calibration_error_pct': round(confidence_calibration_error_pct, 4),
            'expected_value_error_pct': round(expected_value_error_pct, 5),
            'realized_net_return_pct': round(realized_net_return_pct, 5),
            'avg_latency_ms': round(avg_latency_ms, 2),
            'score': round(score, 4),
        }
        row['recommendation'] = _lane_recommendation(row)
        ranked.append(row)

    ranked.sort(
        key=lambda item: (
            _to_float(item.get('ev_adjusted_pct'), 0.0),
            -_to_float(item.get('expected_value_error_pct'), 0.0),
            _to_float(item.get('score'), 0.0),
            int(item.get('sample_size', 0) or 0),
        ),
        reverse=True,
    )

    max_drawdown_pct = 0.0
    max_drawdown_usd = 0.0
    if equity_events:
        equity_events.sort(key=lambda item: item[0])
        equity = float(os.getenv('STRATEGY_OPS_EQUITY_BASE_USD', '100.0'))
        peak = equity
        trough = equity
        max_dd = 0.0
        for _, pnl_after_cost in equity_events:
            equity += float(pnl_after_cost or 0.0)
            peak = max(peak, equity)
            trough = min(trough, equity)
            drawdown = ((peak - equity) / peak) if peak > 0 else 0.0
            max_dd = max(max_dd, drawdown)
        max_drawdown_pct = min(100.0, max_dd * 100.0)
        max_drawdown_usd = max(0.0, peak - trough)

    totals = {
        'lanes': len(ranked),
        'sample_size': sum(int(item.get('sample_size', 0) or 0) for item in ranked),
        'filled_success_count': sum(int(item.get('filled_success_count', 0) or 0) for item in ranked),
        'reject_skip_count': sum(int(item.get('reject_skip_count', 0) or 0) for item in ranked),
        'hard_failed_count': sum(int(item.get('hard_failed_count', 0) or 0) for item in ranked),
        'net_realized_pnl_usd': round(
            sum(_to_float(item.get('net_realized_pnl_usd'), 0.0) for item in ranked), 6
        ),
        'net_pnl_after_fees_usd': round(
            sum(_to_float(item.get('net_pnl_after_fees_usd'), 0.0) for item in ranked), 6
        ),
        'estimated_fees_usd': round(
            sum(_to_float(item.get('estimated_fees_usd'), 0.0) for item in ranked), 6
        ),
        'estimated_slippage_usd': round(
            sum(_to_float(item.get('estimated_slippage_usd'), 0.0) for item in ranked), 6
        ),
        'total_notional_usd': round(
            sum(_to_float(item.get('total_notional_usd'), 0.0) for item in ranked), 6
        ),
    }
    denom = max(1, int(totals['sample_size']))
    totals['filled_success_pct'] = round((float(totals['filled_success_count']) / denom) * 100.0, 2)
    totals['fill_rate_pct'] = totals['filled_success_pct']
    totals['reject_tax_pct'] = round((float(totals['reject_skip_count']) / denom) * 100.0, 2)
    totals['hard_fail_pct'] = round((float(totals['hard_failed_count']) / denom) * 100.0, 2)
    totals['max_drawdown_pct'] = round(max_drawdown_pct, 4)
    totals['max_drawdown_usd'] = round(max_drawdown_usd, 6)
    totals['equity_base_usd'] = round(float(os.getenv('STRATEGY_OPS_EQUITY_BASE_USD', '100.0')), 4)
    totals['ev_adjusted_pct'] = round(
        sum(_to_float(item.get('ev_adjusted_pct'), 0.0) for item in ranked) / max(1, len(ranked)),
        5,
    )
    totals['expected_value_error_pct'] = round(
        (
            sum(
                _to_float(item.get('expected_value_error_pct'), 0.0) * max(1, int(item.get('sample_size', 0) or 0))
                for item in ranked
            )
            / max(
                1,
                sum(max(1, int(item.get('sample_size', 0) or 0)) for item in ranked),
            )
        ),
        5,
    )
    totals['north_star'] = {
        'net_pnl_after_fees': totals['net_pnl_after_fees_usd'],
        'max_drawdown_pct': totals['max_drawdown_pct'],
        'reject_tax_pct': totals['reject_tax_pct'],
        'fill_rate_pct': totals['fill_rate_pct'],
        'expected_value_error_pct': totals['expected_value_error_pct'],
    }

    return {
        'generated_at': now_utc.isoformat(),
        'platform': platform_norm,
        'window': {
            'days': safe_days,
            'since': since.isoformat(),
            'until': now_utc.isoformat(),
        },
        'totals': totals,
        'ranked': ranked,
    }


def build_signal_outcome_attribution(
    *,
    db_client,
    days: int = 7,
    platform: str = "lighter",
    limit: int = 2200,
) -> dict:
    now_utc = datetime.now(UTC)
    safe_days = max(1, min(int(days or 7), 30))
    safe_limit = max(200, min(int(limit or 2200), 5000))
    platform_norm = str(platform or "lighter").strip().lower()
    since = now_utc - timedelta(days=safe_days)

    trade_collection = os.environ.get("TRADE_EXECUTIONS_COLLECTION", "trade_executions")
    fee_rate = float(os.environ.get("STRATEGY_OPS_FEE_BPS", "7.0")) / 10000.0
    slippage_rate = float(os.environ.get("STRATEGY_OPS_SLIPPAGE_BPS", "5.0")) / 10000.0

    if db_client is None:
        return {
            "generated_at": now_utc.isoformat(),
            "platform": platform_norm,
            "window": {"days": safe_days, "since": since.isoformat(), "until": now_utc.isoformat()},
            "schema": {"version": "v1", "fields": []},
            "summary": {"sample_size": 0, "error": "firestore_unavailable"},
            "windows": {},
            "by_reason": [],
            "by_outcome": [],
            "by_lane": [],
            "rows": [],
        }

    def _estimate_notional_usd(row: dict) -> float:
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        direct = (
            row.get("notional_usd")
            or metadata.get("notional_usd")
            or row.get("order_notional_usd")
            or metadata.get("order_notional_usd")
        )
        direct_val = _safe_float(direct, 0.0)
        if direct_val > 0:
            return direct_val
        qty = _safe_float(
            row.get("filled_quantity") or row.get("quantity") or metadata.get("filled_quantity"),
            0.0,
        )
        px = _safe_float(
            row.get("avg_price") or row.get("price") or metadata.get("avg_price") or metadata.get("price"),
            0.0,
        )
        notional = qty * px
        return notional if notional > 0 else 0.0

    def _reason_code(outcome: str, reason_text: str) -> str:
        outcome_norm = str(outcome or "").strip().lower()
        text = str(reason_text or "").strip().lower()
        if outcome_norm == "filled_success":
            return "filled"
        if outcome_norm == "accepted_no_fill":
            return "accepted_no_fill"
        if outcome_norm in {"policy_noop", "policy_reject", "noop"}:
            if not text:
                return "policy_filtered"
            if "symbol" in text and "allow" in text:
                return "symbol_scope_mismatch"
            if "timeframe" in text:
                return "timeframe_mismatch"
            if "strategy" in text:
                return "strategy_mismatch"
            if "confidence" in text:
                return "confidence_below_floor"
            if "cap" in text or "notional" in text:
                return "cap_or_notional_guard"
            if "cooldown" in text:
                return "cooldown_guard"
            if "tp" in text or "sl" in text:
                return "invalid_tp_sl_geometry"
            return "policy_filtered"
        if outcome_norm == "hard_failed":
            if "timeout" in text:
                return "exchange_timeout"
            if "insufficient" in text or "margin" in text or "balance" in text:
                return "insufficient_margin"
            if "signature" in text or "signer" in text:
                return "signature_failure"
            if "credential" in text or "auth" in text or "forbidden" in text:
                return "auth_or_credentials"
            if "connection" in text or "host" in text or "dns" in text:
                return "connectivity_error"
            return "execution_error"
        return outcome_norm or "unknown"

    verification_rows = []
    try:
        docs = list(
            db_client.collection("execution_verifications")
            .where("platform", "==", platform_norm)
            .where("recorded_at", ">=", since)
            .order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        verification_rows = [doc.to_dict() or {} for doc in docs]
    except Exception:
        docs = list(
            db_client.collection("execution_verifications")
            .order_by("recorded_at", direction=firestore.Query.DESCENDING)
            .limit(max(500, min(safe_limit * 2, 8000)))
            .stream()
        )
        for doc in docs:
            row = doc.to_dict() or {}
            if str(row.get("platform", "")).strip().lower() != platform_norm:
                continue
            ts = _coerce_datetime(row.get("recorded_at") or row.get("timestamp"))
            if ts and ts < since:
                continue
            verification_rows.append(row)

    trade_rows = []
    try:
        docs = list(
            db_client.collection(trade_collection)
            .where("timestamp", ">=", since.isoformat())
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(safe_limit)
            .stream()
        )
        trade_rows = [doc.to_dict() or {} for doc in docs]
    except Exception:
        docs = list(
            db_client.collection(trade_collection)
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(max(500, min(safe_limit * 2, 8000)))
            .stream()
        )
        for doc in docs:
            row = doc.to_dict() or {}
            ts = _coerce_datetime(row.get("timestamp"))
            if ts and ts < since:
                continue
            trade_rows.append(row)

    trades_by_signal = {}
    for row in trade_rows:
        row_platform = str(row.get("platform", "") or "").strip().lower()
        if row_platform and row_platform != platform_norm:
            continue
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        signal_id = str(
            row.get("signal_id")
            or metadata.get("signal_id")
            or row.get("execution_id")
            or ""
        ).strip()
        if not signal_id:
            continue
        pnl = _safe_float(row.get("realized_pnl"), 0.0)
        notional = _estimate_notional_usd(row)
        fees = max(0.0, notional * fee_rate)
        slippage = max(0.0, notional * slippage_rate)
        slot = trades_by_signal.setdefault(
            signal_id,
            {
                "trade_count": 0,
                "realized_pnl_usd": 0.0,
                "notional_usd": 0.0,
                "fees_usd": 0.0,
                "slippage_usd": 0.0,
                "net_pnl_after_fees_usd": 0.0,
            },
        )
        slot["trade_count"] += 1
        slot["realized_pnl_usd"] += pnl
        slot["notional_usd"] += notional
        slot["fees_usd"] += fees
        slot["slippage_usd"] += slippage
        slot["net_pnl_after_fees_usd"] += pnl - fees - slippage

    reason_counts = {}
    outcome_counts = {}
    by_lane = {}
    windows = {"1h": _bucket("1h"), "6h": _bucket("6h"), "24h": _bucket("24h")}
    rows = []
    latest_signal_at = None

    for idx, row in enumerate(verification_rows):
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
        signal_meta = row.get("signal_metadata", {}) if isinstance(row.get("signal_metadata"), dict) else {}
        strategy, timeframe = _strategy_lane_info(row)
        outcome = str(row.get("outcome", "")).strip().lower() or "unknown"
        reason_text = str(
            row.get("policy_reason")
            or row.get("noop_reason")
            or row.get("error_message")
            or ""
        ).strip()
        reason = _reason_code(outcome, reason_text)
        ts = _coerce_datetime(row.get("recorded_at") or row.get("timestamp")) or now_utc
        signal_id = str(
            row.get("signal_id")
            or signal_meta.get("signal_id")
            or metadata.get("signal_id")
            or ""
        ).strip()
        if not signal_id:
            signal_id = f"anon-{idx}-{int(ts.timestamp())}"

        source = str(
            row.get("signal_source")
            or row.get("source")
            or signal_meta.get("source")
            or metadata.get("source")
            or "unknown"
        ).strip().lower()
        symbol = _norm_symbol(
            row.get("symbol")
            or signal_meta.get("symbol")
            or metadata.get("symbol")
            or metadata.get("pair")
        )
        side = str(
            row.get("side")
            or signal_meta.get("side")
            or metadata.get("side")
            or ""
        ).strip().lower() or "unknown"
        confidence = _safe_float(
            row.get("confidence")
            or signal_meta.get("confidence")
            or metadata.get("confidence"),
            0.0,
        )
        latency_ms = _safe_float(
            row.get("latency_ms")
            or row.get("processing_latency_ms")
            or metadata.get("latency_ms"),
            0.0,
        )

        trade = trades_by_signal.get(signal_id, {})
        realized_pnl = _safe_float(trade.get("realized_pnl_usd"), 0.0)
        net_after_fees = _safe_float(trade.get("net_pnl_after_fees_usd"), 0.0)
        fees_usd = _safe_float(trade.get("fees_usd"), 0.0)
        slippage_usd = _safe_float(trade.get("slippage_usd"), 0.0)
        notional = _safe_float(trade.get("notional_usd"), 0.0)

        canonical = {
            "signal_id": signal_id,
            "timestamp": ts.isoformat(),
            "platform": platform_norm,
            "symbol": symbol,
            "side": side,
            "source": source or "unknown",
            "strategy": strategy,
            "timeframe": timeframe,
            "confidence": round(confidence, 4),
            "latency_ms": round(latency_ms, 2),
            "outcome": outcome,
            "reason_code": reason,
            "reason_text": reason_text[:220],
            "trade_count": int(trade.get("trade_count", 0) or 0),
            "notional_usd": round(notional, 6),
            "realized_pnl_usd": round(realized_pnl, 6),
            "fees_usd": round(fees_usd, 6),
            "slippage_usd": round(slippage_usd, 6),
            "net_pnl_after_fees_usd": round(net_after_fees, 6),
            "expected_ev_pct": round(
                _safe_float(
                    row.get("expected_ev_pct")
                    or metadata.get("expected_ev_pct")
                    or signal_meta.get("expected_ev_pct"),
                    0.0,
                ),
                5,
            ),
        }
        rows.append(canonical)

        if latest_signal_at is None or ts > latest_signal_at:
            latest_signal_at = ts
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
        outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

        lane_key = f"{strategy}@{timeframe}"
        lane = by_lane.setdefault(lane_key, _bucket(lane_key))
        lane["sample_size"] += 1
        if outcome == "filled_success":
            lane["filled_success_count"] += 1
        elif outcome in {"policy_noop", "policy_reject", "noop"}:
            lane["reject_skip_count"] += 1
        elif outcome == "hard_failed":
            lane["hard_failed_count"] += 1
        elif outcome == "accepted_no_fill":
            lane["accepted_no_fill_count"] += 1
        lane["net_pnl_after_fees_usd"] += net_after_fees
        lane["estimated_fees_usd"] += fees_usd
        lane["estimated_slippage_usd"] += slippage_usd

        age_h = max(0.0, (now_utc - ts).total_seconds() / 3600.0)
        for label, threshold in (("1h", 1.0), ("6h", 6.0), ("24h", 24.0)):
            if age_h <= threshold:
                win = windows[label]
                win["sample_size"] += 1
                if outcome == "filled_success":
                    win["filled_success_count"] += 1
                elif outcome in {"policy_noop", "policy_reject", "noop"}:
                    win["reject_skip_count"] += 1
                elif outcome == "hard_failed":
                    win["hard_failed_count"] += 1
                elif outcome == "accepted_no_fill":
                    win["accepted_no_fill_count"] += 1
                win["net_pnl_after_fees_usd"] += net_after_fees
                win["estimated_fees_usd"] += fees_usd
                win["estimated_slippage_usd"] += slippage_usd

    for group in [*windows.values(), *by_lane.values()]:
        denom = max(1, int(group.get("sample_size", 0) or 0))
        group["fill_rate_pct"] = round((float(group.get("filled_success_count", 0)) / denom) * 100.0, 2)
        group["reject_tax_pct"] = round((float(group.get("reject_skip_count", 0)) / denom) * 100.0, 2)
        group["hard_fail_pct"] = round((float(group.get("hard_failed_count", 0)) / denom) * 100.0, 2)
        group["net_pnl_after_fees_usd"] = round(float(group.get("net_pnl_after_fees_usd", 0.0) or 0.0), 6)
        group["estimated_fees_usd"] = round(float(group.get("estimated_fees_usd", 0.0) or 0.0), 6)
        group["estimated_slippage_usd"] = round(float(group.get("estimated_slippage_usd", 0.0) or 0.0), 6)

    total = max(1, len(rows))
    summary = _bucket("summary")
    for row in rows:
        summary["sample_size"] += 1
        outcome = row.get("outcome")
        if outcome == "filled_success":
            summary["filled_success_count"] += 1
        elif outcome in {"policy_noop", "policy_reject", "noop"}:
            summary["reject_skip_count"] += 1
        elif outcome == "hard_failed":
            summary["hard_failed_count"] += 1
        elif outcome == "accepted_no_fill":
            summary["accepted_no_fill_count"] += 1
        summary["net_pnl_after_fees_usd"] += _safe_float(row.get("net_pnl_after_fees_usd"), 0.0)
        summary["estimated_fees_usd"] += _safe_float(row.get("fees_usd"), 0.0)
        summary["estimated_slippage_usd"] += _safe_float(row.get("slippage_usd"), 0.0)
    summary["fill_rate_pct"] = round((summary["filled_success_count"] / total) * 100.0, 2)
    summary["reject_tax_pct"] = round((summary["reject_skip_count"] / total) * 100.0, 2)
    summary["hard_fail_pct"] = round((summary["hard_failed_count"] / total) * 100.0, 2)
    summary["net_pnl_after_fees_usd"] = round(summary["net_pnl_after_fees_usd"], 6)
    summary["estimated_fees_usd"] = round(summary["estimated_fees_usd"], 6)
    summary["estimated_slippage_usd"] = round(summary["estimated_slippage_usd"], 6)
    summary["latest_signal_at"] = latest_signal_at.isoformat() if latest_signal_at else None

    by_reason_rows = [
        {"reason_code": reason, "count": count, "share_pct": round((count / total) * 100.0, 2)}
        for reason, count in sorted(reason_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    by_outcome_rows = [
        {"outcome": outcome, "count": count, "share_pct": round((count / total) * 100.0, 2)}
        for outcome, count in sorted(outcome_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    lane_rows = []
    for lane_key, lane in by_lane.items():
        strategy_value, timeframe_value = lane_key.split("@", 1)
        lane_rows.append({"strategy": strategy_value, "timeframe": timeframe_value, **lane})
    lane_rows.sort(
        key=lambda item: (
            _safe_float(item.get("net_pnl_after_fees_usd"), 0.0),
            _safe_float(item.get("fill_rate_pct"), 0.0),
            -_safe_float(item.get("reject_tax_pct"), 0.0),
            int(item.get("sample_size", 0) or 0),
        ),
        reverse=True,
    )

    rows.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
    return {
        "generated_at": now_utc.isoformat(),
        "platform": platform_norm,
        "window": {"days": safe_days, "since": since.isoformat(), "until": now_utc.isoformat()},
        "schema": {
            "version": "v1",
            "fields": [
                "signal_id", "timestamp", "platform", "symbol", "side", "source", "strategy", "timeframe",
                "confidence", "latency_ms", "outcome", "reason_code", "reason_text",
                "trade_count", "notional_usd", "realized_pnl_usd", "fees_usd", "slippage_usd",
                "net_pnl_after_fees_usd", "expected_ev_pct",
            ],
        },
        "summary": summary,
        "windows": windows,
        "by_reason": by_reason_rows[:12],
        "by_outcome": by_outcome_rows,
        "by_lane": lane_rows[:16],
        "rows": rows[:240],
    }


def build_data_quality_snapshot(
    *,
    attribution: dict,
    market_payload: dict,
    intel_summary_payload: dict,
) -> dict:
    now_utc = datetime.now(UTC)

    def _age_minutes(timestamp_value) -> float | None:
        ts = _coerce_datetime(timestamp_value)
        if ts is None:
            return None
        return max(0.0, (now_utc - ts).total_seconds() / 60.0)

    def _source_health(
        name: str,
        timestamp_value,
        missingness_pct: float,
        drift_pct: float,
        warn_min: int,
        crit_min: int,
    ):
        age_min = _age_minutes(timestamp_value)
        if age_min is None:
            freshness = "unknown"
        elif age_min >= crit_min:
            freshness = "critical"
        elif age_min >= warn_min:
            freshness = "stale"
        else:
            freshness = "fresh"
        degraded = (
            freshness in {"stale", "critical", "unknown"}
            or float(missingness_pct or 0.0) >= 20.0
            or float(drift_pct or 0.0) >= 25.0
        )
        confidence_penalty = 0.0
        if freshness == "stale":
            confidence_penalty += 0.08
        elif freshness in {"critical", "unknown"}:
            confidence_penalty += 0.16
        confidence_penalty += min(0.18, float(missingness_pct or 0.0) / 100.0 * 0.18)
        confidence_penalty += min(0.14, float(drift_pct or 0.0) / 100.0 * 0.14)
        return {
            "source": name,
            "timestamp": _iso_or_default(timestamp_value),
            "age_minutes": None if age_min is None else round(age_min, 2),
            "freshness": freshness,
            "missingness_pct": round(float(missingness_pct or 0.0), 2),
            "drift_pct": round(float(drift_pct or 0.0), 2),
            "degraded": degraded,
            "confidence_penalty": round(confidence_penalty, 4),
        }

    market = market_payload or {}
    tracked = [str(sym).upper() for sym in (market.get("tracked_symbols") or []) if str(sym).strip()]
    tracked_count = max(1, len(tracked))
    missing_quotes = sum(1 for sym in tracked if _safe_float((market.get(sym) or {}).get("price"), 0.0) <= 0)
    market_missingness = (missing_quotes / tracked_count) * 100.0

    intel_summary = intel_summary_payload or {}
    intel_count = int(((intel_summary.get("intel") or {}).get("count", 0)) or 0)
    intel_missingness = 100.0 if intel_count == 0 else 0.0

    windows = attribution.get("windows", {}) if isinstance(attribution.get("windows"), dict) else {}
    win_1h = windows.get("1h", {}) if isinstance(windows.get("1h"), dict) else {}
    win_24h = windows.get("24h", {}) if isinstance(windows.get("24h"), dict) else {}
    fill_1h = _safe_float(win_1h.get("fill_rate_pct"), 0.0)
    fill_24h = _safe_float(win_24h.get("fill_rate_pct"), 0.0)
    execution_drift = abs(fill_1h - fill_24h)
    reason_rows = attribution.get("by_reason", []) if isinstance(attribution.get("by_reason"), list) else []
    unknown_share = 0.0
    for row in reason_rows:
        if str(row.get("reason_code", "")).strip().lower() == "unknown":
            unknown_share = _safe_float(row.get("share_pct"), 0.0)
            break

    sources = [
        _source_health(
            "execution_outcomes",
            (attribution.get("summary") or {}).get("latest_signal_at"),
            unknown_share,
            execution_drift,
            warn_min=15,
            crit_min=60,
        ),
        _source_health(
            "market_prices",
            market.get("timestamp") if isinstance(market, dict) else None,
            market_missingness,
            0.0,
            warn_min=6,
            crit_min=20,
        ),
        _source_health(
            "intel_summary",
            intel_summary.get("timestamp") if isinstance(intel_summary, dict) else None,
            intel_missingness,
            0.0,
            warn_min=15,
            crit_min=45,
        ),
    ]
    total_penalty = sum(_safe_float(row.get("confidence_penalty"), 0.0) for row in sources)
    degraded_sources = [row["source"] for row in sources if bool(row.get("degraded", False))]
    confidence_multiplier = _clamp(1.0 - total_penalty, 0.35, 1.0)
    return {
        "generated_at": now_utc.isoformat(),
        "degraded": bool(degraded_sources),
        "degraded_sources": degraded_sources,
        "confidence_multiplier": round(confidence_multiplier, 4),
        "sources": sources,
    }


def build_operator_decision_brief(
    *,
    scorecard: dict,
    reject_tax: dict,
    assessment: dict,
    attribution: dict,
    data_quality: dict,
) -> dict:
    totals = scorecard.get("totals", {}) if isinstance(scorecard.get("totals"), dict) else {}
    ranked = scorecard.get("ranked", []) if isinstance(scorecard.get("ranked"), list) else []
    north_star = totals.get("north_star", {}) if isinstance(totals.get("north_star"), dict) else {}
    windows = attribution.get("windows", {}) if isinstance(attribution.get("windows"), dict) else {}
    lanes = attribution.get("by_lane", []) if isinstance(attribution.get("by_lane"), list) else []

    fill_rate = _safe_float(north_star.get("fill_rate_pct"), _safe_float(totals.get("fill_rate_pct"), 0.0))
    reject_pct = _safe_float(north_star.get("reject_tax_pct"), _safe_float(reject_tax.get("reject_tax_pct"), 0.0))
    ev_error_pct = _safe_float(
        north_star.get("expected_value_error_pct"),
        _safe_float(totals.get("expected_value_error_pct"), 0.0),
    )
    net_pnl_after_fees = _safe_float(
        north_star.get("net_pnl_after_fees"),
        _safe_float(totals.get("net_pnl_after_fees_usd"), 0.0),
    )
    drawdown_pct = _safe_float(north_star.get("max_drawdown_pct"), _safe_float(totals.get("max_drawdown_pct"), 0.0))
    drawdown_usd = _safe_float(totals.get("max_drawdown_usd"), 0.0)
    confidence_multiplier = _safe_float(data_quality.get("confidence_multiplier"), 1.0)

    max_ev_error_pct = float(os.environ.get("STRATEGY_OPS_GONOGO_MAX_EV_ERROR_PCT", "0.35") or 0.35)
    max_drawdown_pct = float(os.environ.get("STRATEGY_OPS_GONOGO_MAX_DRAWDOWN_PCT", "6.0") or 6.0)
    blockers = list(assessment.get("reasons") or [])
    if bool(data_quality.get("degraded", False)):
        degraded = ", ".join(data_quality.get("degraded_sources", [])[:3]) or "unknown sources"
        blockers.append(f"data_quality degraded: {degraded}")
    if ev_error_pct > max_ev_error_pct:
        blockers.append(f"expected_value_error {ev_error_pct:.3f}% exceeds model tolerance")
    if drawdown_pct > max_drawdown_pct:
        blockers.append(f"max_drawdown {drawdown_pct:.2f}% exceeds threshold")

    go = bool(assessment.get("go", False)) and len(blockers) == 0
    label = "GO" if go else "NO-GO"

    top_actions = []
    if reject_pct >= 55.0:
        top_actions.append({
            "priority": "P0",
            "title": "Reduce reject tax now",
            "why": f"Reject tax is {reject_pct:.1f}% and is eroding realized edge.",
            "action": "Tighten source/timeframe scope and disable highest-reject lanes for next cycle.",
        })
    if ev_error_pct >= 0.20:
        top_actions.append({
            "priority": "P1",
            "title": "Recalibrate EV model",
            "why": f"Expected-value error is {ev_error_pct:.3f}% versus realized outcomes.",
            "action": "Increase sample penalty and update friction assumptions for active lanes.",
        })
    promote_lane = next((row for row in ranked if str(row.get("recommendation", "")).lower() == "promote"), None)
    if isinstance(promote_lane, dict):
        lane_name = f"{promote_lane.get('strategy', 'unknown')}@{promote_lane.get('timeframe', 'unknown')}"
        top_actions.append({
            "priority": "P1",
            "title": f"Promote {lane_name} cautiously",
            "why": (
                f"Adjusted EV {float(promote_lane.get('ev_adjusted_pct', 0.0) or 0.0):+.3f}% "
                f"with reject tax {float(promote_lane.get('reject_tax_pct', 0.0) or 0.0):.1f}%."
            ),
            "action": "Advance lane from paper/capped live to next gate with strict notional ceiling.",
        })
    weak_lane = next((row for row in lanes if _safe_float(row.get("reject_tax_pct"), 0.0) >= 70.0), None)
    if isinstance(weak_lane, dict):
        lane_name = f"{weak_lane.get('strategy', 'unknown')}@{weak_lane.get('timeframe', 'unknown')}"
        top_actions.append({
            "priority": "P0",
            "title": f"Demote high-friction lane {lane_name}",
            "why": f"Lane reject tax is {float(weak_lane.get('reject_tax_pct', 0.0) or 0.0):.1f}%.",
            "action": "Move lane back to paper and require new promotion artifact before re-entry.",
        })
    if bool(data_quality.get("degraded", False)):
        top_actions.append({
            "priority": "P0",
            "title": "Stabilize data quality before scaling",
            "why": "Confidence is being downgraded due to stale/missing market or execution inputs.",
            "action": "Fix degraded feeds and hold scaling decisions until quality is green.",
        })

    dedup_actions = []
    seen = set()
    for item in top_actions:
        title = str(item.get("title", "")).strip().lower()
        if not title or title in seen:
            continue
        seen.add(title)
        dedup_actions.append(item)
    if not dedup_actions:
        dedup_actions = [{
            "priority": "P1",
            "title": "Maintain capped live posture",
            "why": "No critical blockers detected but lane confidence remains moderate.",
            "action": "Keep cap fixed and continue collecting labeled outcomes before scaling.",
        }]

    w1 = windows.get("1h", {}) if isinstance(windows.get("1h"), dict) else {}
    w6 = windows.get("6h", {}) if isinstance(windows.get("6h"), dict) else {}
    w24 = windows.get("24h", {}) if isinstance(windows.get("24h"), dict) else {}
    delta = {
        "fill_rate_pct_1h": _safe_float(w1.get("fill_rate_pct"), 0.0),
        "fill_rate_pct_6h": _safe_float(w6.get("fill_rate_pct"), 0.0),
        "fill_rate_pct_24h": _safe_float(w24.get("fill_rate_pct"), 0.0),
        "reject_tax_pct_1h": _safe_float(w1.get("reject_tax_pct"), 0.0),
        "reject_tax_pct_6h": _safe_float(w6.get("reject_tax_pct"), 0.0),
        "reject_tax_pct_24h": _safe_float(w24.get("reject_tax_pct"), 0.0),
        "net_pnl_after_fees_usd_1h": _safe_float(w1.get("net_pnl_after_fees_usd"), 0.0),
        "net_pnl_after_fees_usd_6h": _safe_float(w6.get("net_pnl_after_fees_usd"), 0.0),
        "net_pnl_after_fees_usd_24h": _safe_float(w24.get("net_pnl_after_fees_usd"), 0.0),
    }
    confidence_score = _clamp(
        (50.0 + (fill_rate * 0.35) - (reject_pct * 0.30) - (drawdown_pct * 0.90)) * confidence_multiplier,
        0.0,
        100.0,
    )
    why_now = (
        f"Net after-fees PnL is {net_pnl_after_fees:+.4f} with fill rate {fill_rate:.1f}% and reject tax "
        f"{reject_pct:.1f}%. Max drawdown is ${drawdown_usd:.2f} ({drawdown_pct:.2f}%). "
        f"Confidence is {'downgraded' if confidence_multiplier < 0.9 else 'stable'} "
        f"({confidence_score:.1f}/100)."
    )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "go": go,
        "label": label,
        "confidence_score": round(confidence_score, 2),
        "confidence_multiplier": round(confidence_multiplier, 4),
        "why_this_matters_now": why_now,
        "kpis": {
            "net_pnl_after_fees_usd": round(net_pnl_after_fees, 6),
            "max_drawdown_pct": round(drawdown_pct, 4),
            "max_drawdown_usd": round(drawdown_usd, 6),
            "reject_tax_pct": round(reject_pct, 2),
            "fill_rate_pct": round(fill_rate, 2),
            "expected_value_error_pct": round(ev_error_pct, 5),
        },
        "thresholds": {
            "max_expected_value_error_pct": round(max_ev_error_pct, 5),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "max_reject_tax_pct": float((assessment.get("thresholds") or {}).get("max_reject_tax_pct", 0.0) or 0.0),
            "max_hard_fail_pct": float((assessment.get("thresholds") or {}).get("max_hard_fail_pct", 0.0) or 0.0),
            "min_sample_size": int((assessment.get("thresholds") or {}).get("min_sample_size", 0) or 0),
        },
        "deltas": delta,
        "hard_blockers": blockers[:8],
        "top_actions": dedup_actions[:3],
    }
