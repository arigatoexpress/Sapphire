/**
 * Market Data Store — centralised candle / snapshot state.
 *
 * Caches OHLC data per (venue, symbol, interval) so multiple views
 * reading the same pair don't duplicate API calls.
 *
 * The basket (SYMBOLS x ASTER x 5m) is fetched once and shared.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchMarketOHLC, type OhlcCandle, connectionHealth } from '../api/client'
import { normalizeCandles, computeChange, estimateVol } from '../utils/market'

export interface MarketSnapshot {
    symbol: string
    price: number | null
    change1h: number | null
    change4h: number | null
    change6h: number | null
    volatility: number | null
    history: number[]
}

const SYMBOLS = ['BTC', 'ETH', 'SOL', 'BCH', 'ZEC', 'PENGU', 'XMR', 'MON', 'LIT', 'ASTER'] as const
export type Symbol = (typeof SYMBOLS)[number]
export { SYMBOLS }

export const useMarketStore = defineStore('market', () => {
    /* ── State ── */

    /** Candle cache:  `cache[venue:symbol:interval]` → normalised candles */
    const cache = ref<Record<string, OhlcCandle[]>>({})

    /** Pre-computed basket snapshots (SYMBOLS x ASTER x 5m) */
    const snapshots = ref<MarketSnapshot[]>([])

    /** Source metadata for the main charts */
    const asterMeta = ref({ symbol: '', trackingSymbol: '', source: '—', interval: '1m' })
    const lighterMeta = ref({ symbol: '', trackingSymbol: '', source: '—', interval: '1m' })

    const lastFetchAt = ref(0)
    const fetchError = ref('')
    const loading = ref(false)

    let _timer: ReturnType<typeof setInterval> | null = null
    let _subscribers = 0

    /* ── Internal helpers ── */

    function _key(venue: string, symbol: string, interval: string) {
        return `${venue}:${symbol}:${interval}`
    }

    function _parseMeta(ohlc: any, fallbackSymbol: string) {
        return {
            symbol: String(ohlc?.symbol || fallbackSymbol).toUpperCase(),
            trackingSymbol: String(ohlc?.tracking_symbol || ohlc?.symbol || fallbackSymbol).toUpperCase(),
            source: String(ohlc?.source || '—'),
            interval: String(ohlc?.interval || '1m'),
        }
    }

    /* ── Actions ── */

    /** Fetch primary chart candles + basket for a given selected symbol. */
    async function fetchAll(selectedSymbol: string) {
        loading.value = !lastFetchAt.value
        fetchError.value = ''
        try {
            const [asterOhlc, lighterOhlc, ...basketResults] = await Promise.all([
                fetchMarketOHLC({ venue: 'ASTER', symbol: selectedSymbol, interval: '1m', limit: 220 }),
                fetchMarketOHLC({ venue: 'LIGHTER', symbol: selectedSymbol, interval: '1m', limit: 220 }),
                ...SYMBOLS.map((s) => fetchMarketOHLC({ venue: 'ASTER', symbol: s, interval: '5m', limit: 120 })),
            ])

            // Cache primary candles
            cache.value[_key('ASTER', selectedSymbol, '1m')] = normalizeCandles(asterOhlc?.candles)
            cache.value[_key('LIGHTER', selectedSymbol, '1m')] = normalizeCandles(lighterOhlc?.candles)
            asterMeta.value = _parseMeta(asterOhlc, selectedSymbol)
            lighterMeta.value = _parseMeta(lighterOhlc, selectedSymbol)

            // Cache + snapshot basket
            snapshots.value = SYMBOLS.map((symbol, i) => {
                const candles = normalizeCandles(basketResults[i]?.candles)
                cache.value[_key('ASTER', symbol, '5m')] = candles
                const history = candles.map((c) => Number(c.close)).filter((v) => Number.isFinite(v))
                return {
                    symbol,
                    price: history.length ? (history[history.length - 1] ?? null) : null,
                    change1h: computeChange(history, 12),
                    change4h: computeChange(history, 48),
                    change6h: computeChange(history, 72),
                    volatility: estimateVol(history.slice(-48)),
                    history: history.slice(-30),
                }
            })

            lastFetchAt.value = Date.now()
        } catch (err) {
            fetchError.value = connectionHealth.lastErrorMessage || 'Market data unavailable'
            console.error('Market store fetch error:', err)
        } finally {
            loading.value = false
        }
    }

    /** Get cached candles. */
    function getCandles(venue: string, symbol: string, interval = '1m'): OhlcCandle[] {
        return cache.value[_key(venue, symbol, interval)] || []
    }

    /** Start polling for a given symbol. */
    function startPolling(selectedSymbol: () => string) {
        _subscribers++
        if (_subscribers === 1) {
            fetchAll(selectedSymbol())
            _timer = setInterval(() => fetchAll(selectedSymbol()), 15_000)
        }
    }

    function stopPolling() {
        _subscribers = Math.max(0, _subscribers - 1)
        if (_subscribers === 0 && _timer) {
            clearInterval(_timer)
            _timer = null
        }
    }

    return {
        // State
        cache,
        snapshots,
        asterMeta,
        lighterMeta,
        lastFetchAt,
        fetchError,
        loading,
        // Actions
        fetchAll,
        getCandles,
        startPolling,
        stopPolling,
    }
})
