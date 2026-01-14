
import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
    LayoutDashboard,
    Briefcase,
    Layers,
    Cpu
} from 'lucide-react';

export const CommandDock: React.FC = () => {
    const location = useLocation();
    const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

    const dockItems = [
        { to: '/', icon: <LayoutDashboard className="w-6 h-6" />, label: 'Dashboard' },
        { to: '/agents', icon: <Cpu className="w-6 h-6" />, label: 'Agents' },
        { to: '/portfolio', icon: <Briefcase className="w-6 h-6" />, label: 'Portfolio' },
        { to: '/about', icon: <Layers className="w-6 h-6" />, label: 'About' },
    ];

    return (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-[100] perspective-[1000px]">
            {/*
                THE HYPER-DOCK (v2: Resized & Premium)
                - Glassmorphism: backdrop-blur-2xl + bg-opacity
                - Border: Shiny gradient border effect
                - Animation: Smooth hover scale
            */}
            <div
                className="flex items-end gap-3 px-6 py-4 bg-[#0a0b10]/70 backdrop-blur-2xl border border-white/10 rounded-3xl shadow-[0_20px_40px_rgba(0,0,0,0.6)] transition-all duration-300 hover:bg-[#0a0b10]/80 hover:border-blue-500/30 hover:shadow-[0_0_50px_rgba(59,130,246,0.2)]"
                onMouseLeave={() => setHoveredIndex(null)}
            >
                {dockItems.map((item, index) => {
                    const isActive = location.pathname === item.to;

                    // Mac-style magnification logic
                    let scale = 1;
                    if (hoveredIndex !== null) {
                        const dist = Math.abs(hoveredIndex - index);
                        if (dist === 0) scale = 1.35;
                        else if (dist === 1) scale = 1.15;
                    }

                    return (
                        <Link
                            key={item.to}
                            to={item.to!}
                            onMouseEnter={() => setHoveredIndex(index)}
                            className="relative group flex flex-col items-center justify-end transition-all duration-200 ease-out"
                            style={{
                                transform: `scale(${scale}) translateY(${hoveredIndex === index ? '-12px' : '0'})`
                            }}
                        >
                            {/* Icon Container */}
                            <div className={`
                                w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-200
                                ${isActive
                                    ? 'bg-blue-600 shadow-[0_0_20px_rgba(59,130,246,0.6)] text-white ring-2 ring-blue-400/50'
                                    : 'bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white hover:shadow-[0_0_15px_rgba(255,255,255,0.1)]'
                                }
                            `}>
                                {item.icon}
                            </div>

                            {/* Active Dot - Floating below */}
                            {isActive && (
                                <div className="absolute -bottom-3 w-1.5 h-1.5 bg-blue-400 rounded-full shadow-[0_0_8px_#60a5fa]" />
                            )}

                            {/* Tooltip Label (Enhanced) */}
                            <div className="absolute -top-14 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-[#0f1016] backdrop-blur-xl border border-white/10 rounded-lg shadow-xl text-xs font-bold text-white tracking-wide opacity-0 group-hover:opacity-100 transition-all duration-200 whitespace-nowrap pointer-events-none translate-y-2 group-hover:translate-y-0 z-50">
                                {item.label}
                                <div className="absolute bottom-[-5px] left-1/2 -translate-x-1/2 w-2.5 h-2.5 bg-[#0f1016] border-r border-b border-white/10 transform rotate-45" />
                            </div>
                        </Link>
                    );
                })}
            </div>
        </div>
    );
};
