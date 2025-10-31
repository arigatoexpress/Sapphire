import React from 'react';
interface TargetsData {
    daily_pnl_target: number;
    max_drawdown_limit: number;
    min_confidence_threshold: number;
    target_win_rate: number;
    alerts: string[];
}
interface TargetsAndAlertsProps {
    targets: TargetsData | undefined;
}
declare const TargetsAndAlerts: React.FC<TargetsAndAlertsProps>;
export default TargetsAndAlerts;
