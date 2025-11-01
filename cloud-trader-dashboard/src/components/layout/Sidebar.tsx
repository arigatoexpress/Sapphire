import React from 'react';

interface SidebarProps {
    tabs: Array<{ id: string; label: string; icon: string }>;
    activeTab: string;
    onSelect: (id: string) => void;
    mobileMenuOpen?: boolean;
    setMobileMenuOpen?: (open: boolean) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ tabs, activeTab, onSelect, mobileMenuOpen, setMobileMenuOpen }) => {
    const handleTabSelect = (id: string) => {
        onSelect(id);
        if (setMobileMenuOpen) {
            setMobileMenuOpen(false);
        }
    };

    return (
        <>
            {/* Mobile overlay */}
            {mobileMenuOpen && (
                <div
                    className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm lg:hidden"
                    onClick={() => setMobileMenuOpen?.(false)}
                />
            )}

            <aside className={`fixed lg:static top-0 left-0 z-50 h-full w-64 flex-col gap-6 bg-surface-100/95 border-r border-surface-200/60 backdrop-blur-sm p-6 transition-transform duration-300 lg:translate-x-0 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:flex'
                }`}>
                <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-primary-500 via-primary-400 to-accent-teal flex items-center justify-center shadow-glass">
                        <span className="text-lg font-semibold text-white">CT</span>
                    </div>
                    <div>
                        <p className="text-sm uppercase tracking-widest text-slate-400">Aster Labs</p>
                        <h1 className="text-xl font-semibold text-white">Cloud Trader</h1>
                    </div>
                </div>

                <nav className="flex-1">
                    <ul className="space-y-1">
                        {tabs.map((tab) => {
                            const isActive = tab.id === activeTab;
                            return (
                                <li key={tab.id}>
                                    <button
                                        type="button"
                                        onClick={() => handleTabSelect(tab.id)}
                                        className={`group relative flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left transition-all duration-200 overflow-hidden ${isActive
                                            ? 'bg-primary-500/20 text-white shadow-glass scale-[1.02]'
                                            : 'text-slate-400 hover:text-white hover:bg-surface-200/60 hover:scale-[1.01]'
                                            }`}
                                    >
                                        <div className={`absolute inset-0 bg-gradient-to-r ${isActive ? 'from-primary-500/10 to-accent-teal/10' : 'from-white/5 to-transparent'} opacity-0 group-hover:opacity-100 transition-opacity duration-200`} />
                                        <span className={`text-lg transition-transform duration-200 ${isActive ? 'scale-110' : 'group-hover:scale-105'}`}>{tab.icon}</span>
                                        <span className="font-medium relative z-10">{tab.label}</span>
                                        {isActive && (
                                            <span className="ml-auto h-2 w-2 rounded-full bg-accent-emerald shadow-glass animate-pulse" />
                                        )}
                                        {!isActive && (
                                            <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-xs">→</span>
                                        )}
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </nav>

                <div className="rounded-xl border border-surface-200/60 bg-surface-100/80 p-4 text-sm text-slate-300">
                    <p className="font-semibold text-white">Operator Status</p>
                    <p className="mt-1 text-xs text-slate-400">Live telemetry streaming every 5s · WebSocket upgrade coming soon</p>
                </div>
            </aside>
        </>
    );
};

export default Sidebar;

