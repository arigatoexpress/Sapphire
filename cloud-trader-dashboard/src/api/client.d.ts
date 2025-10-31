export interface HealthResponse {
    running: boolean;
    paper_trading: boolean;
    last_error: string | null;
    status?: string;
    service?: string;
}
export interface PortfolioResponse {
    totalWalletBalance: string;
    totalPositionInitialMargin: string;
    positions: Array<{
        symbol: string;
        positionAmt: string;
        entryPrice: string;
        unrealizedProfit: string;
        leverage: number;
        positionSide: string;
    }>;
}
interface ActionResponse {
    status: string;
}
export declare const fetchHealth: () => Promise<HealthResponse>;
export declare const fetchPortfolio: () => Promise<PortfolioResponse>;
export declare const postStart: () => Promise<ActionResponse>;
export declare const postStop: () => Promise<ActionResponse>;
export declare const emergencyStop: () => Promise<ActionResponse>;
export {};
