import React from 'react';
import { DashboardAgent } from '../api/client';
interface AgentCardProps {
    agent: DashboardAgent;
    onClick?: () => void;
    onViewHistory?: (agent: DashboardAgent) => void;
}
declare const AgentCard: React.FC<AgentCardProps>;
export default AgentCard;
