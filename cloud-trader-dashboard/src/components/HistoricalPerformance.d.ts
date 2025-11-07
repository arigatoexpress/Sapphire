import React from 'react';
import { DashboardAgent } from '../api/client';
interface HistoricalPerformanceProps {
    agent: DashboardAgent;
    onClose: () => void;
}
declare const HistoricalPerformance: React.FC<HistoricalPerformanceProps>;
export default HistoricalPerformance;
