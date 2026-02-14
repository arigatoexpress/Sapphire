/**
 * Shared formatting utilities — extracted from TradeView + AlphaView.
 */

export const formatPrice = (v: number | null): string => {
    if (v === null || !Number.isFinite(v) || v <= 0) return 'n/a'
    if (v >= 1000) return `$${v.toFixed(2)}`
    if (v >= 100) return `$${v.toFixed(3)}`
    return `$${v.toFixed(4)}`
}

export const formatPct = (v: number | null, d = 2): string => {
    if (v === null || !Number.isFinite(v)) return 'n/a'
    return `${v >= 0 ? '+' : ''}${v.toFixed(d)}%`
}

export const toPrice = (v: unknown): number | null => {
    const n = Number(v)
    return Number.isFinite(n) && n > 0 ? n : null
}
