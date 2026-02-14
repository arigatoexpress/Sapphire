/**
 * Control Store — centralised execution / system state.
 *
 * Merges data from:
 *   GET /api/v2/control/status
 *   GET /api/analytics/performance/stats
 *   GET /api/v2/platforms/status
 *
 * One 15-second polling loop serves every view.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
    fetchControlStatus,
    fetchPerformanceStats,
    fetchPlatformStatus,
    connectionHealth,
} from '../api/client'

export const useControlStore = defineStore('control', () => {
    /* ── State ── */
    const executionStage = ref('PAPER')
    const stageMultiplier = ref(0)
    const dexLiveDispatch = ref(false)
    const killSwitchActive = ref(false)
    const pendingDecisions = ref(0)

    // Performance
    const totalTrades = ref(0)
    const winRate = ref(0)
    const realizedPnl = ref(0)

    // Platform
    const platforms = ref<any>(null)
    const asterPrice = ref<number | null>(null)
    const lighterPrice = ref<number | null>(null)

    // Raw control payload (views that need extra fields can access this)
    const rawControl = ref<any>(null)

    // Freshness
    const lastFetchAt = ref(0)
    const fetchError = ref('')
    const loading = ref(false)

    let _timer: ReturnType<typeof setInterval> | null = null
    let _subscribers = 0

    /* ── Getters ── */
    const dataAge = computed(() => {
        if (!lastFetchAt.value) return null
        return Math.floor((Date.now() - lastFetchAt.value) / 1000)
    })

    const isStale = computed(() => (dataAge.value ?? 999) > 30)

    /* ── Actions ── */

    async function refresh() {
        loading.value = !lastFetchAt.value
        fetchError.value = ''
        try {
            const [controlPayload, stats, plat] = await Promise.all([
                fetchControlStatus(),
                fetchPerformanceStats(),
                fetchPlatformStatus(),
            ])

            if (controlPayload?.ok) {
                rawControl.value = controlPayload
                executionStage.value = String(controlPayload.dex_execution_stage || 'PAPER').toUpperCase()
                stageMultiplier.value = Number(controlPayload.dex_stage_multiplier || 0)
                dexLiveDispatch.value = Boolean(controlPayload.dex_live_dispatch_enabled)
                killSwitchActive.value = Boolean(controlPayload.kill_switch_active)
                pendingDecisions.value = Number(controlPayload.pending_autonomy_decisions || 0)
            }

            if (stats?.ok) {
                totalTrades.value = Number(stats?.metrics?.system?.total_trades || 0)
                winRate.value = Number(stats?.metrics?.system?.win_rate || 0)
                realizedPnl.value = Number(stats?.metrics?.system?.realized_pnl || 0)
            }

            if (plat) {
                platforms.value = plat
                const entries = (plat as any)?.platforms || (plat as any)?.data || plat || {}
                const toPrice = (v: unknown): number | null => {
                    const n = Number(v)
                    return Number.isFinite(n) && n > 0 ? n : null
                }
                asterPrice.value = toPrice(
                    (entries as any)?.aster?.price ??
                    (entries as any)?.aster?.mark_price ??
                    (entries as any)?.aster?.mid_price,
                )
                lighterPrice.value = toPrice(
                    (entries as any)?.lighter?.price ??
                    (entries as any)?.lighter?.mark_price ??
                    (entries as any)?.lighter?.mid_price,
                )
            }

            lastFetchAt.value = Date.now()
        } catch (err) {
            fetchError.value = connectionHealth.lastErrorMessage || 'Connection failed'
            console.error('Control store refresh error:', err)
        } finally {
            loading.value = false
        }
    }

    /** Subscribe a view — starts the polling loop once. */
    function subscribe() {
        _subscribers++
        if (_subscribers === 1) {
            refresh()
            _timer = setInterval(refresh, 15_000)
        }
    }

    /** Unsubscribe a view — stops polling when no views are mounted. */
    function unsubscribe() {
        _subscribers = Math.max(0, _subscribers - 1)
        if (_subscribers === 0 && _timer) {
            clearInterval(_timer)
            _timer = null
        }
    }

    return {
        // State
        executionStage,
        stageMultiplier,
        dexLiveDispatch,
        killSwitchActive,
        pendingDecisions,
        totalTrades,
        winRate,
        realizedPnl,
        platforms,
        asterPrice,
        lighterPrice,
        rawControl,
        lastFetchAt,
        fetchError,
        loading,
        // Getters
        dataAge,
        isStale,
        // Actions
        refresh,
        subscribe,
        unsubscribe,
    }
})
