import axios from 'axios'

// Sapphire focused control-plane API endpoint
const API_BASE = (import.meta.env.VITE_API_URL || 'https://sapphire-alpha-s77j6bxyra-uc.a.run.app').trim()

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

export interface OhlcCandle {
    time: number
    open: number
    high: number
    low: number
    close: number
    volume?: number
}

export interface OhlcResponse {
    venue: string
    symbol: string
    interval: string
    interval_seconds: number
    limit: number
    source: string
    candles: OhlcCandle[]
    generated_at: number
}

export const fetchMarketOHLC = async (params?: {
    venue?: 'ASTER' | 'LIGHTER'
    symbol?: string
    interval?: string
    limit?: number
}): Promise<OhlcResponse | null> => {
    try {
        const response = await api.get('/api/v2/market/ohlc', {
            params: {
                venue: params?.venue || 'ASTER',
                symbol: params?.symbol || 'SOL',
                interval: params?.interval || '1m',
                limit: params?.limit || 180,
            },
        })
        if (response?.data?.ok === false) return null
        return response.data
    } catch (error) {
        console.error('Failed to fetch market OHLC:', error)
        return null
    }
}

// ============================================================================
// Aster Agents (Monad Treasury)
// ============================================================================

export const fetchAsterStatus = async () => {
    try {
        const response = await api.get('/api/v2/aster/status')
        return response.data
    } catch (error) {
        console.error('Failed to fetch Aster status:', error)
        return null
    }
}

export const fetchMITStatus = async () => {
    try {
        const response = await api.get('/api/v2/aster/mit/status')
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
