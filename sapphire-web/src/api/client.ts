import axios from 'axios'

const api = axios.create({
    baseURL: 'https://sapphire-alpha-267358751314.us-central1.run.app',
    timeout: 10000,
    headers: {
        'Content-Type': 'application/json'
    }
})

export const fetchPerformanceStats = async () => {
    try {
        const response = await api.get('/api/analytics/performance/stats')
        return response.data
    } catch (error) {
        console.error('Failed to fetch performance stats:', error)
        return null
    }
}

export const fetchAgents = async () => {
    try {
        const response = await api.get('/api/agents/list')
        return response.data?.agents
    } catch (error) {
        console.error('Failed to fetch agents:', error)
        return null
    }
}

export const fetchSystemLogs = async () => {
    try {
        const response = await api.get('/logs/system')
        return response.data
    } catch (error) {
        return []
    }
}

export default api
