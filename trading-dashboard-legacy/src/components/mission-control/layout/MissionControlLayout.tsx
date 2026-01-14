
import React from 'react';
import { Activity, Shield, Cpu, Wifi } from 'lucide-react';

interface MissionControlLayoutProps {
    children: React.ReactNode;
}

export const MissionControlLayout: React.FC<MissionControlLayoutProps> = ({ children }) => {
    return (
        <div className="flex h-screen w-full bg-[#050508] text-white overflow-hidden relative">
            {/* Background Effects */}
            <div className="holographic-grid" />
            <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-cyan-500/50 to-transparent z-50 animate-pulse-slow" />

            {/* Main Content Area */}
            <main className="flex-1 flex flex-col h-full relative z-10">

                {/* HUD Header */}
                <header className="h-14 border-b border-white/10 bg-black/40 backdrop-blur-md flex items-center justify-between px-6 flex-shrink-0">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-[0_0_10px_#22d3ee]" />
                            <span className="font-tech text-lg tracking-widest text-white glow-text-blue">SAPPHIRE</span>
                            <span className="text-xs text-cyan-500/80 font-mono border border-cyan-500/20 px-1 rounded">OS v2.0</span>
                        </div>
                    </div>

                    <div className="flex items-center gap-6 text-xs text-slate-400 font-mono">
                        <div className="flex items-center gap-2">
                            <Cpu size={14} className="text-emerald-500" />
                            <span>CPU: 12%</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <Activity size={14} className="text-purple-500" />
                            <span>MEM: 4.2GB</span>
                        </div>
                        <div className="flex items-center gap-2">
                            <Wifi size={14} className="text-cyan-500" />
                            <span>NET: 4ms</span>
                        </div>
                        <div className="flex items-center gap-2 px-3 py-1 bg-white/5 rounded border border-white/10">
                            <Shield size={14} className="text-amber-400" />
                            <span>GUARD: ACTIVE</span>
                        </div>
                    </div>
                </header>

                {/* Content Viewport */}
                <div className="flex-1 overflow-hidden p-4">
                    {children}
                </div>

            </main>
        </div>
    );
};
