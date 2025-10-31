import { HealthResponse } from '../api/client';
interface StatusCardProps {
    health: HealthResponse | null;
    loading: boolean;
}
declare const StatusCard: React.FC<StatusCardProps>;
export default StatusCard;
