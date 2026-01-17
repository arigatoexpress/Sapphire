import axios from 'axios'

// Sapphire V2 Backend - Claude V1.0 Architecture
const API_BASE = 'https://sapphire-v2-s77j6bxyra-uc.a.run.app'

const api = axios.create({
    baseURL: API_BASE,
    timeout: 15000,
    headers: {
        'Content-Type': 'application/json'
    }
})

// ============================================================================
// System Health & Status
// ============================================================================

export const fetchHealth = async () => {
    try {
        const response = await api.get('/health')
        return response.data
    } catch (error) {
        console.error('Failed to fetch health:', error)
        return null
    }
}

export const fetchSystemStatus = async () => {
    try {
        const response = await api.get('/')
        return response.data
    } catch (error) {
        console.error('Failed to fetch system status:', error)
        return null
    }
}

// ============================================================================
// Performance & Analytics
// ============================================================================

export const fetchPerformanceStats = async () => {
    try {
        const response = await api.get('/api/analytics/performance/stats')
        return response.data
    } catch (error) {
        console.error('Failed to fetch performance stats:', error)
        return null
    }
}

// ============================================================================
// AI Agents
// ============================================================================

export const fetchAgents = async () => {
    try {
        const response = await api.get('/api/agents/list')
        return response.data?.agents
    } catch (error) {
        console.error('Failed to fetch agents:', error)
        return null
    }
}

export const fetchAgentStatus = async (agentId: string) => {
    try {
        const response = await api.get(`/api/agents/${agentId}/status`)
        return response.data
    } catch (error) {
        console.error(`Failed to fetch agent ${agentId}:`, error)
        return null
    }
}

// ============================================================================
// Positions & Trading
// ============================================================================

export const fetchAllPositions = async () => {
    try {
        const response = await api.get('/positions/all')
        return response.data
    } catch (error) {
        console.error('Failed to fetch positions:', error)
        return null
    }
}

export const executeTrade = async (tradeRequest: {
    symbol: string
    side: 'BUY' | 'SELL'
    quantity: number
    order_type?: string
    platform?: string
}) => {
    try {
        const response = await api.post('/api/v2/trade', tradeRequest)
        return response.data
    } catch (error) {
        console.error('Failed to execute trade:', error)
        throw error
    }
}

// ============================================================================
// V2 Platform Routes
// ============================================================================

export const fetchPlatformStatus = async () => {
    try {
        const response = await api.get('/api/v2/platforms/status')
        return response.data
    } catch (error) {
        console.error('Failed to fetch platform status:', error)
        return null
    }
}

export const fetchRoutingInfo = async () => {
    try {
        const response = await api.get('/api/v2/trade/routing')
        return response.data
    } catch (error) {
        console.error('Failed to fetch routing info:', error)
        return null
    }
}

// ============================================================================
// Symphony Agents (Monad Treasury)
// ============================================================================

export const fetchSymphonyStatus = async () => {
    try {
        const response = await api.get('/api/v2/symphony/status')
        return response.data
    } catch (error) {
        console.error('Failed to fetch Symphony status:', error)
        return null
    }
}

export const fetchMITStatus = async () => {
    try {
        const response = await api.get('/api/v2/symphony/mit/status')
        return response.data
    } catch (error) {
        console.error('Failed to fetch MIT status:', error)
        return null
    }
}

// ============================================================================
// Memory System
// ============================================================================

export const fetchMemoryHealth = async () => {
    try {
        const response = await api.get('/api/v2/memory/health')
        return response.data
    } catch (error) {
        console.error('Failed to fetch memory health:', error)
        return null
    }
}

// ============================================================================
// Logs
// ============================================================================

export const fetchSystemLogs = async () => {
    try {
        const response = await api.get('/logs/system')
        return response.data
    } catch (error) {
        return []
    }
}

export const fetchPlatformLogs = async (platform: string, limit: number = 50) => {
    try {
        const response = await api.get(`/logs/${platform}?limit=${limit}`)
        return response.data
    } catch (error) {
        return []
    }
}

export default api
