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

const TopBar: React.FC<TopBarProps> = ({
    onRefresh,
    lastUpdated,
    healthRunning,
    mobileMenuOpen,
    setMobileMenuOpen,
    onBackToHome,
    connectionStatus = 'connecting',
    error,
    autoRefreshEnabled = true,
    onToggleAutoRefresh
}) => {
    const statusLabel = healthRunning ? 'Live' : 'Paused';
    const statusColor = healthRunning ? 'bg-accent-emerald/85 text-brand-midnight' : 'bg-warning-amber/85 text-brand-midnight';

    const connectionColor = connectionStatus === 'connected' ? 'text-accent-emerald' :
        connectionStatus === 'connecting' ? 'text-accent-sapphire' : 'text-error';
    const connectionIcon = connectionStatus === 'connected' ? '🟢' :
        connectionStatus === 'connecting' ? '🟡' : '🔴';

    return (
        <header className="sticky top-0 z-40 border-b border-brand-border/70 bg-brand-abyss/80 backdrop-blur-lg">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-10">
                <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-accent-sapphire/80">Sapphire AI Trading System</p>
                    <h2 className="mt-1 text-3xl font-semibold text-brand-ice">Multi-Agent Trading Platform</h2>
                    <p className="mt-0.5 text-sm text-brand-muted/80">Real-time algorithmic trading system using reinforcement learning, statistical arbitrage, and multi-agent decision making on Aster DEX.</p>
                </div>

                <div className="flex items-center gap-4">
                    <div className="hidden text-right sm:block">
                        <p className="text-xs uppercase tracking-wide text-brand-muted/70">Last Sync</p>
                        <p className="text-sm font-medium text-brand-ice">
                            {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : '—'}
                        </p>
                        <div className="flex items-center gap-2 mt-1">
                            <span className={`text-xs ${connectionColor}`}>{connectionIcon}</span>
                            <span className="text-xs uppercase tracking-wide text-brand-muted/70">
                                {connectionStatus}
                            </span>
                        </div>
                        {error && (
                            <div className="mt-1 text-xs text-error/80 max-w-xs truncate" title={error}>
                                ⚠️ {error}
                            </div>
                        )}
                    </div>

                    <span
                        className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${statusColor}`}
                    >
                        <span className="h-2 w-2 rounded-full bg-brand-midnight" />
                        {statusLabel}
                    </span>

                    {onBackToHome && (
                        <button
                            type="button"
                            onClick={onBackToHome}
                            className="group relative overflow-hidden rounded-full border border-brand-border/60 bg-gradient-to-r from-accent-sapphire/90 to-accent-emerald/90 px-4 py-2 text-sm font-medium text-brand-midnight shadow-sapphire transition-all duration-200 hover:scale-105 active:scale-95"
                        >
                            <span className="mr-2">🏠</span>
                            Home
                            <span className="absolute inset-0 rounded-full bg-brand-ice/20 opacity-0 group-active:opacity-100 transition-opacity duration-100" />
                        </button>
                    )}

                    {onToggleAutoRefresh && (
                        <button
                            type="button"
                            onClick={onToggleAutoRefresh}
                            className={`group relative overflow-hidden rounded-full px-4 py-2 text-sm font-medium shadow-sapphire transition-all duration-200 hover:scale-105 active:scale-95 ${autoRefreshEnabled
                                ? 'bg-accent-emerald/80 text-brand-midnight hover:bg-accent-emerald'
                                : 'border border-brand-border/60 bg-brand-abyss/80 text-brand-ice hover:bg-brand-abyss/90'
                                }`}
                            title={autoRefreshEnabled ? 'Disable auto-refresh' : 'Enable auto-refresh'}
                        >
                            <span className="mr-2">{autoRefreshEnabled ? '⏸️' : '▶️'}</span>
                            Auto
                            <span className="absolute inset-0 -z-10 bg-gradient-to-r from-accent-sapphire/40 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
                            <span className="absolute inset-0 rounded-full bg-brand-ice/10 opacity-0 group-active:opacity-100 transition-opacity duration-100" />
                        </button>
                    )}

                    <button
                        type="button"
                        onClick={onRefresh}
                        className="group relative overflow-hidden rounded-full bg-accent-sapphire/85 px-4 py-2 text-sm font-medium text-brand-midnight shadow-sapphire transition-all duration-200 hover:bg-accent-sapphire hover:scale-105 active:scale-95"
                        title="Refresh data (Ctrl+R)"
                    >
                        <span className="mr-2 transition-transform duration-200 group-hover:rotate-180">🔄</span>
                        Refresh
                        <span className="absolute inset-0 -z-10 bg-gradient-to-r from-accent-emerald/50 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
                        <span className="absolute inset-0 rounded-full bg-brand-ice/10 opacity-0 group-active:opacity-100 transition-opacity duration-100" />
                    </button>

                    {/* Mobile menu button */}
                    {setMobileMenuOpen && (
                        <button
                            type="button"
                            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                            className="lg:hidden p-2 rounded-lg text-brand-muted hover:text-brand-ice hover:bg-brand-abyss/70 transition-colors duration-200"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={mobileMenuOpen ? "M6 18L18 6M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"} />
                            </svg>
                        </button>
                    )}
                </div>
            </div>
        </header>
    );
};

export default TopBar;

