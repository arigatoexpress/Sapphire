import React from 'react';
interface SidebarProps {
    tabs: Array<{
        id: string;
        label: string;
        icon: string;
    }>;
    activeTab: string;
    onSelect: (id: string) => void;
    mobileMenuOpen?: boolean;
    setMobileMenuOpen?: (open: boolean) => void;
}
declare const Sidebar: React.FC<SidebarProps>;
export default Sidebar;
