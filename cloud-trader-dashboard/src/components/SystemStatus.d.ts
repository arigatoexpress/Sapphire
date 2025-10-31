import React from 'react';
interface SystemStatusData {
    services: {
        [key: string]: string;
    };
    models: {
        [key: string]: string;
    };
    redis_connected: boolean;
    timestamp: string;
}
interface SystemStatusProps {
    status: SystemStatusData | undefined;
}
declare const SystemStatus: React.FC<SystemStatusProps>;
export default SystemStatus;
