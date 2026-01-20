import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchPerformanceStats, fetchAgents } from '../api/client'
import { WebSocketClient } from '../api/websocket'

export const useMarketStore = defineStore('market', () => {
    const totalPnl = ref(0.0)
    const activePositions = ref(0)
    const winRate = ref(0)
    const systemStatus = ref('OFFLINE')
    const activeAgents = ref(0)



    const wsClient = new WebSocketClient('/ws/dashboard')

    async function fetchStats() {
        const data = await fetchPerformanceStats()
        if (data && data.status === 'success') {
            updateFromData(data)
        }
    }

    function updateFromData(data: any) {
        // Backend returns: { portfolio: {...}, agents: [...], stats: {...}, ... }
        // Or via API endpoint: { status: 'success', metrics: { system: {...} } }

        // Handle WS Dashboard payload
        if (data.portfolio) {
            totalPnl.value = data.portfolio.pnl_percent || 0.0
            // win_rate might be in stats
            if (data.stats) {
                winRate.value = data.stats.win_rate || 0
            }
            if (data.agents) {
                activeAgents.value = data.agents.length
            }
            systemStatus.value = 'ONLINE'
        }
        // Handle Legacy API payload (fallback)
        else if (data.metrics?.system) {
            const metrics = data.metrics.system
            totalPnl.value = metrics.total_pnl || 0.0
            winRate.value = metrics.total_trades > 0
                ? Math.round((metrics.wins / metrics.total_trades) * 100)
                : 0
            systemStatus.value = 'ONLINE'
        }
    }

    function startStreaming() {
        // Initial fetch
        fetchStats()

        // Connect WS
        wsClient.connect()
        wsClient.subscribe((data) => {
            updateFromData(data)
        })
    }

    return {
        totalPnl,
        activePositions,
        winRate,
        systemStatus,
        activeAgents,
        startStreaming
    }
})
