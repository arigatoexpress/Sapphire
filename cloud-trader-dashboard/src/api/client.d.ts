export interface HealthResponse {
    running: boolean;
    paper_trading: boolean;
    last_error: string | null;
    status?: string;
    service?: string;
}
interface ActionResponse {
    status: string;
}
export interface DashboardPosition {
    symbol: string;
    notional?: number;
    side?: string;
    size?: number;
    entry_price?: number;
    current_price?: number;
    pnl?: number;
    pnl_percent?: number;
    leverage?: number;
    agent_id?: string;
    timestamp?: string;
}
export interface DashboardPortfolio {
    balance?: number;
    total_exposure?: number;
    available_balance?: number;
    positions?: Record<string, DashboardPosition>;
    source?: string;
    alerts?: string[];
}
export interface DashboardTargets {
    daily_pnl_target: number;
    max_drawdown_limit: number;
    min_confidence_threshold: number;
    target_win_rate: number;
    alerts: string[];
}
export interface DashboardSystemStatus {
    services: Record<string, string>;
    models: Record<string, string>;
    redis_connected: boolean;
    timestamp: string;
}
export interface DashboardTrade {
    symbol: string;
    side: string;
    price: number;
    quantity: number;
    notional: number;
    agent_id?: string | null;
    model?: string | null;
    timestamp: string;
    status?: string;
    source?: string;
}
export interface DashboardAgent {
    id: string;
    name: string;
    model: string;
    emoji: string;
    status: string;
    symbols: string[];
    description: string;
    total_pnl: number;
    exposure: number;
    total_trades: number;
    win_rate: number;
    last_trade?: string | null;
    positions: DashboardPosition[];
    performance: Array<{
        timestamp: string;
        equity: number;
    }>;
}
export interface DashboardResponse {
    portfolio: DashboardPortfolio;
    positions: DashboardPosition[];
    recent_trades: DashboardTrade[];
    model_performance: any[];
    agents: DashboardAgent[];
    model_reasoning: any[];
    system_status: DashboardSystemStatus;
    targets: DashboardTargets;
}
export declare const fetchHealth: () => Promise<HealthResponse>;
export declare const fetchDashboard: () => Promise<DashboardResponse>;
export declare const startTrader: () => Promise<ActionResponse>;
export declare const stopTrader: () => Promise<ActionResponse>;
export {};
