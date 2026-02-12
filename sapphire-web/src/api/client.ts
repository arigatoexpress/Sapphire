import axios from 'axios'

const API_BASE = (
    import.meta.env.VITE_API_URL || 'https://sapphire-alpha-s77j6bxyra-uc.a.run.app'
).trim()

const api = axios.create({
    baseURL: API_BASE,
    timeout: 15000,
    headers: {
        'Content-Type': 'application/json',
    },
})

const safeGet = async <T>(path: string, params?: Record<string, unknown>): Promise<T | null> => {
    try {
        const response = await api.get(path, { params })
        return response.data as T
    } catch (error) {
        console.error(`Failed API request: ${path}`, error)
        return null
    }
}

export interface HealthResponse {
    status?: string
    [key: string]: unknown
}

export interface ControlStatusResponse {
    ok: boolean
    kill_switch_active: boolean
    full_autonomy_enabled: boolean
    owner_approval_required: boolean
    tradingview_execution_enabled: boolean
    tradingview_default_quantity: number
    autonomy_dispatch_count: number
    pending_autonomy_decisions: number
    pending_sessions: Array<{
        session_key: string
        trigger: string
        created_at: number
        instruction: string
    }>
    owner_directive: string
    failure_pressure: number
    venues: Record<
        string,
        {
            allocation: number
            paused: boolean
            paused_until: number | null
            pause_reason: string
            failure_count: number
        }
    >
    timestamp: number
}

export interface PlatformStatusResponse {
    ok: boolean
    platforms: Record<
        string,
        {
            status: string
            health: string
            mode: string
            routing: string
            note: string
            price: number
            last_tick_ts: number | null
            age_seconds: number | null
            allocation: number
            paused: boolean
        }
    >
    kill_switch_active: boolean
    timestamp: number
}

export interface RoutingInfoResponse {
    ok: boolean
    mode: string
    strategy: string
    confidence: number
    routing: {
        confidence: number
        active_venues: string[]
        paused_venues: string[]
        failure_pressure: number
        kill_switch_active: boolean
    }
    timestamp: number
}

export interface PerformanceStatsResponse {
    ok: boolean
    metrics: {
        system: {
            total_trades: number
            wins: number
            losses: number
            win_rate: number
            realized_pnl: number
            uptime_seconds: number
            failure_pressure: number
            autonomy_dispatch_count: number
        }
    }
    timestamp: number
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
    ok: boolean
    venue: string
    symbol: string
    interval: string
    interval_seconds: number
    limit: number
    source: string
    candles: OhlcCandle[]
    generated_at: number
}

export interface TradingViewWorkspaceResponse {
    ok: boolean
    workspace: {
        enabled: boolean
        allow_mutations: boolean
        allow_all_assets: boolean
        community_access_enabled: boolean
        hook_url_set: boolean
        hook_token_set: boolean
        agent_id: string
        workspace_label: string
        allowed_repo_scope: string[]
        allowed_project_scope: string[]
        state: {
            active_watchlist: string
            watchlists: Record<string, string[]>
            selected_symbol: string
            selected_timeframe: string
            indicators: string[]
            strategies: string[]
            community_scripts: string[]
            assets_scope: string
            last_action: string | null
            last_updated_at: number
        }
    }
    timestamp: number
}

export interface SystemLogEntry {
    timestamp: number
    level: string
    message: string
    tags: string[]
    metadata: Record<string, unknown>
}

export const fetchHealth = async (): Promise<HealthResponse | string | null> =>
    safeGet<HealthResponse | string>('/health')

export const fetchPlatformStatus = async (): Promise<PlatformStatusResponse | null> =>
    safeGet<PlatformStatusResponse>('/api/v2/platforms/status')

export const fetchControlStatus = async (): Promise<ControlStatusResponse | null> =>
    safeGet<ControlStatusResponse>('/api/v2/control/status')

export const fetchRoutingInfo = async (): Promise<RoutingInfoResponse | null> =>
    safeGet<RoutingInfoResponse>('/api/v2/trade/routing')

export const fetchPerformanceStats = async (): Promise<PerformanceStatsResponse | null> =>
    safeGet<PerformanceStatsResponse>('/api/analytics/performance/stats')

export const fetchTradingViewWorkspace = async (): Promise<TradingViewWorkspaceResponse | null> =>
    safeGet<TradingViewWorkspaceResponse>('/api/v2/tradingview/workspace')

export const fetchMarketOHLC = async (params?: {
    venue?: 'ASTER' | 'LIGHTER'
    symbol?: string
    interval?: string
    limit?: number
}): Promise<OhlcResponse | null> =>
    safeGet<OhlcResponse>('/api/v2/market/ohlc', {
        venue: params?.venue || 'ASTER',
        symbol: params?.symbol || 'SOL',
        interval: params?.interval || '1m',
        limit: params?.limit || 180,
    })

export const fetchSystemLogs = async (limit = 80): Promise<SystemLogEntry[]> => {
    const result = await safeGet<SystemLogEntry[]>('/logs/system', { limit })
    return Array.isArray(result) ? result : []
}

export default api
