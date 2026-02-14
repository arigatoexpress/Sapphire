/**
 * Control Store — centralised execution / system state.
 *
 * Merges data from:
 *   GET /api/v2/control/status
 *   GET /api/analytics/performance/stats
 *   GET /api/v2/platforms/status
 *
 * Primary: WebSocket push (5s snapshots via /ws)
 * Fallback: REST polling every 60s (activates when WS is disconnected)
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
    fetchControlStatus,
    fetchPerformanceStats,
    fetchPlatformStatus,
    connectionHealth,
} from '../api/client'
import { useWebSocket, type WsMessage } from '../composables/useWebSocket'

const REST_FALLBACK_INTERVAL = 60_000 // 60s when WS connected, REST as backup
const REST_PRIMARY_INTERVAL = 15_000  // 15s when WS disconnected

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
    let _wsConnected = false

    const ws = useWebSocket()

    /* ── Getters ── */
    const dataAge = computed(() => {
        if (!lastFetchAt.value) return null
        return Math.floor((Date.now() - lastFetchAt.value) / 1000)
    })

    const isStale = computed(() => (dataAge.value ?? 999) > 30)

    /* ── Shared parsing logic ── */

    function _applyControl(controlPayload: any): void {
        if (!controlPayload) return
        rawControl.value = controlPayload
        executionStage.value = String(controlPayload.dex_execution_stage || 'PAPER').toUpperCase()
        stageMultiplier.value = Number(controlPayload.dex_stage_multiplier || 0)
        dexLiveDispatch.value = Boolean(controlPayload.dex_live_dispatch_enabled)
        killSwitchActive.value = Boolean(controlPayload.kill_switch_active)
        pendingDecisions.value = Number(controlPayload.pending_autonomy_decisions || 0)
    }

    function _applyPerformance(stats: any): void {
        if (!stats?.metrics?.system) return
        totalTrades.value = Number(stats.metrics.system.total_trades || 0)
        winRate.value = Number(stats.metrics.system.win_rate || 0)
        realizedPnl.value = Number(stats.metrics.system.realized_pnl || 0)
    }

    function _applyPlatforms(plat: any): void {
        if (!plat) return
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

    /* ── WebSocket handler ── */

    function _handleWsSnapshot(msg: WsMessage): void {
        fetchError.value = ''
        _applyControl(msg.control as any)
        _applyPerformance(msg.performance as any)
        _applyPlatforms(msg.platforms as any)
        lastFetchAt.value = Date.now()
        loading.value = false
    }

    /* ── REST Actions ── */

    async function refresh() {
        loading.value = !lastFetchAt.value
        fetchError.value = ''
        try {
            const [controlPayload, stats, plat] = await Promise.all([
                fetchControlStatus(),
                fetchPerformanceStats(),
                fetchPlatformStatus(),
            ])

            if (controlPayload?.ok) _applyControl(controlPayload)
            if (stats?.ok) _applyPerformance(stats)
            if (plat) _applyPlatforms(plat)

            lastFetchAt.value = Date.now()
        } catch (err) {
            fetchError.value = connectionHealth.lastErrorMessage || 'Connection failed'
            console.error('Control store refresh error:', err)
        } finally {
            loading.value = false
        }
    }

    /* ── Polling management ── */

    function _startPolling(): void {
        _stopPolling()
        const interval = _wsConnected ? REST_FALLBACK_INTERVAL : REST_PRIMARY_INTERVAL
        refresh()
        _timer = setInterval(refresh, interval)
    }

    function _stopPolling(): void {
        if (_timer) {
            clearInterval(_timer)
            _timer = null
        }
    }

    /** Adjust polling interval when WS status changes. */
    watch(ws.status, (status) => {
        const wasConnected = _wsConnected
        _wsConnected = status === 'connected'

        if (_subscribers > 0 && wasConnected !== _wsConnected) {
            _startPolling() // restart with new interval
        }
    })

    /** Subscribe a view — starts WS + polling loop once. */
    function subscribe() {
        _subscribers++
        if (_subscribers === 1) {
            // Register WS listener for snapshots
            ws.onMessage('init', _handleWsSnapshot)
            ws.onMessage('snapshot', _handleWsSnapshot)
            ws.connect()
            _startPolling()
        }
    }

    /** Unsubscribe a view — stops polling when no views are mounted. */
    function unsubscribe() {
        _subscribers = Math.max(0, _subscribers - 1)
        if (_subscribers === 0) {
            _stopPolling()
            ws.offMessage('init', _handleWsSnapshot)
            ws.offMessage('snapshot', _handleWsSnapshot)
            ws.disconnect()
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
