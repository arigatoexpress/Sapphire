
import React from 'react';

interface FiredancerLayoutProps {
    children: React.ReactNode;
}

const FiredancerLayout: React.FC<FiredancerLayoutProps> = ({ children }) => {
    return (
        <div className="min-h-screen bg-fd-bg text-gray-300 font-mono overflow-hidden">
            {/* Top Status Border (Glowing) */}
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-fd-blue to-transparent opacity-50 shadow-[0_0_10px_rgba(0,209,255,0.5)] z-50"></div>

            {/* Main Content Container */}
            <div className="relative h-screen flex flex-col p-4">
                {/* Header / Status Strip Area (Placeholder for now) */}
                <header className="flex items-center justify-between mb-4 px-2 py-1 border-b border-fd-border">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-fd-success animate-pulse"></div>
                        <span className="text-xs font-bold tracking-widest text-fd-success uppercase">System Active</span>
                    </div>
                    <div className="font-tech text-fd-blue tracking-[0.2em] text-sm opacity-80">
                        SAPPHIRE HUD v2.0
                    </div>
                    <div className="text-xs text-fd-muted">
                        <span className="mr-4">NET: MAINNET-BETA</span>
                        <span>CONN: 24ms</span>
                    </div>
                </header>

                {/* Dynamic Content Grid */}
                <main className="flex-1 overflow-hidden relative grid grid-cols-12 gap-4">
                    {children}
                </main>
            </div>

            {/* Background Grid Mesh (Cyberpunk feel) */}
            <div className="absolute inset-0 pointer-events-none z-0 opacity-[0.03]"
                style={{
                    backgroundImage: 'linear-gradient(#1E1E1E 1px, transparent 1px), linear-gradient(90deg, #1E1E1E 1px, transparent 1px)',
                    backgroundSize: '20px 20px'
                }}>
            </div>
        </div>
    );
};

export default FiredancerLayout;
