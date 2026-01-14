import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchPerformanceStats, fetchAgents } from '../api/client'

export const useMarketStore = defineStore('market', () => {
    const totalPnl = ref(0.0)
    const activePositions = ref(0)
    const winRate = ref(0)
    const systemStatus = ref('OFFLINE')
    const activeAgents = ref(0)

    async function fetchStats() {
        const data = await fetchPerformanceStats()
        if (data && data.status === 'success') {
            const metrics = data.metrics?.system || {}
            totalPnl.value = metrics.total_pnl || 0.0
            winRate.value = metrics.total_trades > 0
                ? Math.round((metrics.wins / metrics.total_trades) * 100)
                : 0

            systemStatus.value = 'ONLINE'

            // Fetch real agent count
            const agents = await fetchAgents()
            if (agents && Array.isArray(agents)) {
                activeAgents.value = agents.length
            } else {
                // Fallback to active system components or known default
                activeAgents.value = 7
            }
        }
    }

    // Poll every 10s
    function startPolling() {
        fetchStats()
        setInterval(fetchStats, 10000)
    }

    return {
        totalPnl,
        activePositions,
        winRate,
        systemStatus,
        activeAgents,
        startPolling
    }
})
