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

const safePost = async <T>(path: string, payload?: Record<string, unknown>): Promise<T | null> => {
    try {
        const response = await api.post(path, payload || {})
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
    primary_execution_plane: string
    primary_execution_venues: string[]
    dex_execution_stage: string
    dex_live_dispatch_enabled: boolean
    dex_stage_multiplier: number
    dex_effective_quantity: number
    dex_base_quantity: number
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

export type ForumLane = 'security' | 'deploy' | 'research' | 'trading' | 'governance' | 'external'
export type ForumState = 'open' | 'queued' | 'needs_owner' | 'blocked' | 'resolved'
export type ForumPriority = 'low' | 'medium' | 'high' | 'critical'

export interface ForumReply {
    reply_id: string
    topic_id: string
    author: string
    body: string
    kind: string
    source: string
    created_at: number
    redactions: number
}

export interface ForumTopic {
    topic_id: string
    title: string
    body: string
    summary: string
    lane: ForumLane
    state: ForumState
    priority: ForumPriority
    author: string
    source: string
    tags: string[]
    created_at: number
    updated_at: number
    reply_count: number
    last_reply_at: number
    redactions?: number
}

export interface ForumTopicsResponse {
    ok: boolean
    topics: ForumTopic[]
    total: number
    lane_counts: Record<string, number>
    state_counts: Record<string, number>
    control: {
        pending_autonomy_decisions: number
        owner_directive: string
        failure_pressure: number
    }
    timestamp: number
}

export interface ForumTopicDetailResponse {
    ok: boolean
    topic: ForumTopic & {
        replies: ForumReply[]
    }
    timestamp: number
}

export interface ForumCreateTopicResponse {
    ok: boolean
    topic: ForumTopic
    timestamp: number
}

export interface ForumCreateReplyResponse {
    ok: boolean
    reply: ForumReply
    timestamp: number
}

export interface ForumScoutStatusResponse {
    ok: boolean
    profile: {
        agent_id: string
        role: string
        sensitive_data_access: string
        allowed_actions: string[]
        blocked_actions: string[]
    }
    registration: {
        registered: boolean
        username: string
        display_name: string
        registered_at: number
        last_dispatch: Record<string, unknown>
    }
    external_bridge: {
        register_url_configured: boolean
        post_url_configured: boolean
        api_token_configured: boolean
    }
    timestamp: number
}

export interface ForumScoutRegisterResponse {
    ok: boolean
    registration: {
        username: string
        display_name: string
        bio_redactions: number
    }
    dispatch: {
        dispatched: boolean
        reason: string
        status?: number
        response_excerpt?: string
    }
    profile: Record<string, unknown>
    timestamp: number
}

export interface ForumScoutPublishResponse {
    ok: boolean
    topic_id: string
    created_topic_id: string
    created_reply_id: string
    redactions: number
    dispatch: {
        dispatched: boolean
        reason: string
        status?: number
        response_excerpt?: string
    }
    timestamp: number
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

export const fetchForumTopics = async (params?: {
    lane?: string
    state?: string
    tag?: string
    q?: string
    limit?: number
}): Promise<ForumTopicsResponse | null> =>
    safeGet<ForumTopicsResponse>('/api/v2/forum/topics', {
        lane: params?.lane || '',
        state: params?.state || '',
        tag: params?.tag || '',
        q: params?.q || '',
        limit: params?.limit || 80,
    })

export const fetchForumTopicDetail = async (topicId: string): Promise<ForumTopicDetailResponse | null> =>
    safeGet<ForumTopicDetailResponse>(`/api/v2/forum/topics/${encodeURIComponent(topicId)}`)

export const createForumTopic = async (payload: {
    title: string
    body: string
    lane?: ForumLane
    state?: ForumState
    priority?: ForumPriority
    author?: string
    tags?: string[] | string
}): Promise<ForumCreateTopicResponse | null> =>
    safePost<ForumCreateTopicResponse>('/api/v2/forum/topics', payload as Record<string, unknown>)

export const createForumReply = async (
    topicId: string,
    payload: {
        body: string
        author?: string
        kind?: string
        state?: ForumState
    },
): Promise<ForumCreateReplyResponse | null> =>
    safePost<ForumCreateReplyResponse>(
        `/api/v2/forum/topics/${encodeURIComponent(topicId)}/replies`,
        payload as Record<string, unknown>,
    )

export const fetchForumScoutStatus = async (): Promise<ForumScoutStatusResponse | null> =>
    safeGet<ForumScoutStatusResponse>('/api/v2/forum/scout/status')

export const registerForumScout = async (payload: {
    username: string
    display_name?: string
    bio?: string
}): Promise<ForumScoutRegisterResponse | null> =>
    safePost<ForumScoutRegisterResponse>(
        '/api/v2/forum/scout/register',
        payload as Record<string, unknown>,
    )

export const publishForumScoutNote = async (payload: {
    topic_id?: string
    title?: string
    body: string
    author?: string
    kind?: string
    lane?: ForumLane
    state?: ForumState
    priority?: ForumPriority
    tags?: string[] | string
}): Promise<ForumScoutPublishResponse | null> =>
    safePost<ForumScoutPublishResponse>(
        '/api/v2/forum/scout/publish',
        payload as Record<string, unknown>,
    )

export default api
