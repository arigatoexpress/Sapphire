
import React from 'react';

// Status phases for trading lifecycle
const PHASES = [
    { id: 'scan', label: 'SCAN', color: 'blue' },
    { id: 'signal', label: 'SIGNAL', color: 'purple' },
    { id: 'entry', label: 'ENTRY', color: 'warning' },
    { id: 'manage', label: 'MANAGE', color: 'success' },
    { id: 'exit', label: 'EXIT', color: 'error' },
];

interface StatusStripProps {
    currentPhase?: string; // 'scan' | 'signal' | 'entry' | 'manage' | 'exit'
    cycleTimeMs?: number;
}

const StatusStrip: React.FC<StatusStripProps> = ({ currentPhase = 'scan', cycleTimeMs = 800 }) => {
    return (
        <div className="flex items-center gap-1 w-full bg-fd-card border border-fd-border p-1 rounded-sm overflow-hidden">
            {PHASES.map((phase) => {
                const isActive = currentPhase === phase.id;
                const isPast = PHASES.findIndex(p => p.id === currentPhase) > PHASES.findIndex(p => p.id === phase.id);

                // Dynamic classes based on status
                const activeClass = isActive
                    ? `bg-fd-${phase.color} text-black font-bold shadow-[0_0_15px_rgba(var(--color-fd-${phase.color}),0.5)]`
                    : isPast
                        ? `bg-fd-${phase.color}/20 text-fd-${phase.color} opacity-60`
                        : 'bg-fd-bg text-gray-700 border border-fd-border';

                return (
                    <div
                        key={phase.id}
                        className={`
                        flex-1 h-6 flex items-center justify-center text-[10px] font-mono tracking-widest transition-all duration-300
                        rounded-sm relative overflow-hidden
                        ${activeClass}
                    `}
                    >
                        {/* Progress Bar for Active Phase */}
                        {isActive && (
                            <div
                                className="absolute bottom-0 left-0 h-0.5 bg-white/50 w-full animate-progress"
                                style={{ animationDuration: `${cycleTimeMs}ms` }}
                            ></div>
                        )}
                        {phase.label}
                    </div>
                )
            })}

            {/* Cycle Timer */}
            <div className="w-16 h-6 flex items-center justify-center bg-fd-bg border border-fd-border rounded-sm text-[10px] font-mono text-fd-muted">
                {cycleTimeMs}ms
            </div>
        </div>
    );
};

export default StatusStrip;
