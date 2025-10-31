import { HealthResponse } from '../api/client';
interface ControlsPanelProps {
    health: HealthResponse | null;
    loading: boolean;
    onStart: () => void;
    onStop: () => void;
    onRefresh: () => void;
}
declare const ControlsPanel: React.FC<ControlsPanelProps>;
export default ControlsPanel;
