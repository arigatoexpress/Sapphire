/**
 * Shared market data utilities — extracted from TradeView + AlphaView.
 *
 * normalizeCandles, computeChange, estimateVol, sparklinePoints,
 * computeRSI, computeMomentum.
 */

import type { OhlcCandle } from '../api/client'

/* ── Candle normalisation ── */

export const normalizeCandles = (candles: OhlcCandle[] | null | undefined): OhlcCandle[] =>
    (candles || [])
        .filter((c) => Number.isFinite(Number(c.time)))
        .map((c) => ({
            time: Number(c.time),
            open: Number(c.open),
            high: Number(c.high),
            low: Number(c.low),
            close: Number(c.close),
            volume: Number.isFinite(Number(c.volume)) ? Number(c.volume) : 0,
        }))
        .filter(
            (c) =>
                Number.isFinite(c.open) &&
                Number.isFinite(c.high) &&
                Number.isFinite(c.low) &&
                Number.isFinite(c.close),
        )
        .sort((a, b) => a.time - b.time)

/* ── Price analytics ── */

export const computeChange = (history: number[], lookback: number): number | null => {
    if (!Array.isArray(history) || history.length <= lookback) return null
    const latest = Number(history[history.length - 1] || 0)
    const anchor = Number(history[Math.max(0, history.length - 1 - lookback)] || 0)
    if (!Number.isFinite(latest) || !Number.isFinite(anchor) || anchor <= 0) return null
    return ((latest - anchor) / anchor) * 100
}

export const estimateVol = (history: number[]): number | null => {
    if (!Array.isArray(history) || history.length < 8) return null
    const rets: number[] = []
    for (let i = 1; i < history.length; i++) {
        const p = Number(history[i - 1] || 0)
        const c = Number(history[i] || 0)
        if (!Number.isFinite(p) || !Number.isFinite(c) || p <= 0) continue
        rets.push((c - p) / p)
    }
    if (rets.length < 5) return null
    const mean = rets.reduce((s, v) => s + v, 0) / rets.length
    const variance = rets.reduce((s, v) => s + (v - mean) ** 2, 0) / rets.length
    return Math.sqrt(Math.max(variance, 0)) * 100
}

/* ── Sparkline SVG ── */

export const sparklinePoints = (values: number[], height = 38, pad = 3): string => {
    if (!Array.isArray(values) || values.length < 2) return ''
    const min = Math.min(...values)
    const max = Math.max(...values)
    const spread = Math.max(0.000001, max - min)
    return values
        .map((v, i) => {
            const x = (i / (values.length - 1)) * 100
            const y = height - ((v - min) / spread) * (height - 2 * pad) - pad
            return `${x.toFixed(2)},${y.toFixed(2)}`
        })
        .join(' ')
}

/* ── Technical indicators ── */

export const computeRSI = (prices: number[], period = 14): number | null => {
    if (prices.length < period + 1) return null
    const recent = prices.slice(-(period + 1))
    let avgGain = 0
    let avgLoss = 0
    for (let i = 1; i < recent.length; i++) {
        const change = (recent[i] ?? 0) - (recent[i - 1] ?? 0)
        if (change > 0) avgGain += change
        else avgLoss += Math.abs(change)
    }
    avgGain /= period
    avgLoss /= period
    if (avgLoss === 0) return 100
    const rs = avgGain / avgLoss
    return 100 - 100 / (1 + rs)
}

export const computeMomentum = (prices: number[], period = 10): number | null => {
    if (prices.length < period + 1) return null
    const current = prices[prices.length - 1]
    const previous = prices[prices.length - 1 - period]
    if (!current || !previous || previous <= 0) return null
    return ((current - previous) / previous) * 100
}
