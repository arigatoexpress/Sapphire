import React from 'react';
import { cn } from '../../../utils/cn';

interface GlassPanelProps {
    children: React.ReactNode;
    className?: string;
    title?: string;
    icon?: React.ReactNode;
    action?: React.ReactNode;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({
    children,
    className,
    title,
    icon,
    action
}) => {
    return (
        <div className={cn(
            "glass-card rounded-lg flex flex-col h-full transition-all duration-300",
            className
        )}>
            {(title || icon) && (
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-white/2">
                    <div className="flex items-center gap-2">
                        {icon && <span className="text-cyan-400">{icon}</span>}
                        <h3 className="text-sm font-semibold tracking-wide text-cyan-100 uppercase font-tech glow-text-blue">
                            {title}
                        </h3>
                    </div>
                    {action && <div>{action}</div>}
                </div>
            )}
            <div className="flex-1 p-4 overflow-hidden relative">
                {children}
            </div>
        </div>
    );
};
