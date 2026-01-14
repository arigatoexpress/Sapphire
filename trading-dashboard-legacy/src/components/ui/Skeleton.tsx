/**
 * Skeleton Loading Component (Tailwind CSS)
 *
 * First Principle: Loading states should feel responsive.
 * Users should see immediate visual feedback that content is loading,
 * with smooth animations that make the wait feel shorter.
 *
 * This component provides reusable skeleton shapes that match
 * the TerminalPro dark theme aesthetic.
 */

import React from 'react';

interface SkeletonProps {
    className?: string;
    variant?: 'text' | 'circular' | 'rectangular';
    width?: string | number;
    height?: string | number;
    animate?: boolean;
}

/**
 * Base Skeleton component with pulse animation.
 */
export const Skeleton: React.FC<SkeletonProps> = ({
    className = '',
    variant = 'text',
    width,
    height,
    animate = true,
}) => {
    const baseClasses = 'bg-white/10 rounded';
    const animationClass = animate ? 'animate-pulse' : '';

    const variantClasses = {
        text: 'h-4 rounded',
        circular: 'rounded-full',
        rectangular: 'rounded-lg',
    };

    const style: React.CSSProperties = {};
    if (width) style.width = typeof width === 'number' ? `${width}px` : width;
    if (height) style.height = typeof height === 'number' ? `${height}px` : height;

    return (
        <div
            className={`${baseClasses} ${animationClass} ${variantClasses[variant]} ${className}`}
            style={style}
        />
    );
};

/**
 * Card skeleton for dashboard widgets.
 */
export const CardSkeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
    <div className={`p-4 rounded-2xl bg-[#0a0b10] border border-white/10 ${className}`}>
        <div className="flex justify-between items-center mb-4">
            <Skeleton width="40%" height={20} />
            <Skeleton variant="circular" width={24} height={24} />
        </div>
        <Skeleton width="60%" height={32} className="mb-2" />
        <Skeleton width="30%" height={16} />
    </div>
);

/**
 * Table row skeleton for data tables.
 */
export const TableRowSkeleton: React.FC<{ columns?: number }> = ({ columns = 4 }) => (
    <div className="flex gap-4 py-3 border-b border-white/5">
        {Array.from({ length: columns }).map((_, i) => (
            <Skeleton key={i} width={`${100 / columns}%`} height={16} />
        ))}
    </div>
);

/**
 * Chart skeleton for data visualization areas.
 */
export const ChartSkeleton: React.FC<{ className?: string }> = ({ className = '' }) => (
    <div className={`p-4 rounded-2xl bg-[#0a0b10] border border-white/10 ${className}`}>
        <Skeleton width="30%" height={24} className="mb-4" />
        <div className="flex items-end gap-1 h-48">
            {Array.from({ length: 20 }).map((_, i) => (
                <Skeleton
                    key={i}
                    width="5%"
                    height={`${Math.random() * 60 + 20}%`}
                    variant="rectangular"
                />
            ))}
        </div>
    </div>
);

/**
 * Stats grid skeleton for metrics display.
 */
export const StatsGridSkeleton: React.FC = () => (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} />
        ))}
    </div>
);

/**
 * Agent card skeleton for agent grid.
 */
export const AgentCardSkeleton: React.FC = () => (
    <div className="p-4 rounded-xl bg-[#0a0b10] border border-white/10">
        <div className="flex items-center gap-3 mb-3">
            <Skeleton variant="circular" width={40} height={40} />
            <div className="flex-1">
                <Skeleton width="70%" height={18} className="mb-1" />
                <Skeleton width="40%" height={14} />
            </div>
        </div>
        <div className="space-y-2">
            <div className="flex justify-between">
                <Skeleton width="30%" height={12} />
                <Skeleton width="20%" height={12} />
            </div>
            <Skeleton width="100%" height={6} variant="rectangular" />
        </div>
    </div>
);

/**
 * Full dashboard skeleton for initial load.
 */
export const DashboardSkeleton: React.FC = () => (
    <div className="space-y-6 p-6">
        {/* Header */}
        <div className="flex justify-between items-center">
            <Skeleton width={200} height={32} />
            <Skeleton width={100} height={36} variant="rectangular" />
        </div>

        {/* Stats */}
        <StatsGridSkeleton />

        {/* Main content */}
        <div className="grid grid-cols-12 gap-6">
            <div className="col-span-12 lg:col-span-3">
                <ChartSkeleton className="h-80" />
            </div>
            <div className="col-span-12 lg:col-span-6">
                <ChartSkeleton className="h-80" />
            </div>
            <div className="col-span-12 lg:col-span-3">
                <div className="space-y-4">
                    {Array.from({ length: 3 }).map((_, i) => (
                        <AgentCardSkeleton key={i} />
                    ))}
                </div>
            </div>
        </div>
    </div>
);

export default Skeleton;
