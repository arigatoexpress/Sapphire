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

            <aside className={`fixed lg:static top-0 left-0 z-50 h-full w-64 flex-col gap-6 bg-gradient-to-b from-brand-abyss/95 via-brand-deep/92 to-brand-midnight/95 border-r border-brand-border/70 backdrop-blur-lg p-6 transition-transform duration-300 lg:translate-x-0 ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:flex'
                }`}>
                {/* Sapphire accent elements */}
                <div className="absolute top-0 right-0 h-32 w-32 rounded-full bg-gradient-to-br from-accent-sapphire/20 to-accent-emerald/10 blur-2xl" />
                <div className="absolute bottom-0 left-0 h-24 w-24 rounded-full bg-gradient-to-br from-accent-aurora/15 to-accent-sapphire/10 blur-xl" />

                <div className="relative flex items-center gap-3 mb-8">
                    <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-accent-sapphire via-accent-emerald to-accent-aurora flex items-center justify-center shadow-sapphire ring-2 ring-brand-border/40">
                        <span className="text-lg font-semibold text-brand-midnight">💎</span>
                    </div>
                    <div>
                        <p className="text-sm uppercase tracking-widest text-brand-muted font-medium">Sapphire Labs</p>
                        <h1 className="text-xl font-bold bg-gradient-to-r from-brand-ice via-accent-sapphire to-accent-emerald bg-clip-text text-transparent">
                            Sapphire AI
                        </h1>
                        <p className="text-xs text-brand-muted/70">Multi-Agent Trading</p>
                    </div>
                </div>

                <nav className="relative flex-1">
                    <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent-sapphire/25 to-transparent" />
                    <ul className="space-y-1">
                        {tabs.map((tab) => {
                            const isActive = tab.id === activeTab;
                            return (
                                <li key={tab.id}>
                                    <button
                                        type="button"
                                        onClick={() => handleTabSelect(tab.id)}
                                        className={`group relative flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left transition-all duration-200 overflow-hidden ${isActive
                                            ? 'text-brand-ice shadow-sapphire scale-[1.02]'
                                            : 'text-brand-muted hover:text-brand-ice hover:scale-[1.01]'
                                            }`}
                                    >
                                        <div className={`absolute inset-0 bg-gradient-to-r ${isActive ? 'from-accent-sapphire/25 via-accent-emerald/25 to-transparent' : 'from-brand-border/40 to-transparent'} opacity-0 group-hover:opacity-100 transition-opacity duration-200`} />
                                        <span className={`text-lg transition-transform duration-200 ${isActive ? 'scale-110' : 'group-hover:scale-105'}`}>{tab.icon}</span>
                                        <span className="font-medium relative z-10">{tab.label}</span>
                                        {isActive ? (
                                            <span className="ml-auto h-2 w-2 rounded-full bg-accent-emerald shadow-sapphire animate-pulse" />
                                        ) : (
                                            <span className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-xs text-brand-muted/70">→</span>
                                        )}
                                    </button>
                                </li>
                            );
                        })}
                    </ul>
                </nav>

                {/* System Status Footer */}
                <div className="relative rounded-xl border border-brand-border/60 bg-brand-abyss/80 p-4 shadow-sapphire backdrop-blur-xl">
                    {/* Mini accent */}
                    <div className="absolute top-0 right-0 h-8 w-8 rounded-full bg-gradient-to-br from-accent-sapphire/30 to-accent-emerald/20 blur-sm" />

                    <div className="relative">
                        <div className="flex items-center gap-2 mb-2">
                            <div className="h-2 w-2 rounded-full bg-accent-emerald animate-pulse shadow-sapphire" />
                            <p className="text-sm font-semibold text-brand-ice">Live Capital Engaged</p>
                        </div>

                        <div className="space-y-1 text-xs text-brand-muted">
                            <div className="flex items-center justify-between">
                                <span>Agents:</span>
                                <span className="text-accent-sapphire font-medium">4 Live Models</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span>Margin:</span>
                                <span className="text-accent-emerald font-medium">Full Access</span>
                            </div>
                            <div className="flex items-center justify-between">
                                <span>Alerts:</span>
                                <span className="text-accent-aurora font-medium">Telegram Push</span>
                            </div>
                        </div>

                        <div className="mt-3 pt-3 border-t border-brand-border/50">
                            <p className="text-xs text-brand-muted text-center">
                                💎 Sapphire AI — Live Desk
                            </p>
                        </div>
                    </div>
                </div>
            </aside>
        </>
    );
};

export default Sidebar;

