import React from 'react';
interface TopBarProps {
    onRefresh: () => void;
    lastUpdated?: string;
    healthRunning?: boolean;
    mobileMenuOpen?: boolean;
    setMobileMenuOpen?: (open: boolean) => void;
}
declare const TopBar: React.FC<TopBarProps>;
export default TopBar;
