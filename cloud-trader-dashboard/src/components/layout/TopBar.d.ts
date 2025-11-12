import React from 'react';
interface TopBarProps {
    onRefresh: () => void;
    lastUpdated?: string;
    healthRunning?: boolean;
    mobileMenuOpen?: boolean;
    setMobileMenuOpen?: (open: boolean) => void;
    onBackToHome?: () => void;
    connectionStatus?: 'connecting' | 'connected' | 'disconnected';
    error?: string | null;
    autoRefreshEnabled?: boolean;
    onToggleAutoRefresh?: () => void;
}
declare const TopBar: React.FC<TopBarProps>;
export default TopBar;
