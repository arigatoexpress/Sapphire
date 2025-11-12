import React from 'react';
interface CacheStatus {
    backend: string;
    connected: boolean;
}
interface SystemStatusData {
    services: {
        [key: string]: string;
    };
    models: {
        [key: string]: string;
    };
    cache: CacheStatus;
    storage_ready: boolean;
    pubsub_connected: boolean;
    feature_store_ready: boolean;
    bigquery_ready: boolean;
    timestamp: string;
}
interface SystemStatusProps {
    status: SystemStatusData | undefined;
}
declare const SystemStatus: React.FC<SystemStatusProps>;
export default SystemStatus;
