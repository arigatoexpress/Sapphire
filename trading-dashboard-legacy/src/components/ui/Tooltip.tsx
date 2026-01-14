/**
 * Tooltip Wrapper Component (Tailwind CSS)
 *
 * First Principle: Users should understand what they're looking at.
 *
 * This component wraps dashboard metrics with informative tooltips
 * that explain trading concepts in plain language.
 */

import React, { useState } from 'react';
import { Info } from 'lucide-react';

interface TooltipProps {
    content: string;
    children: React.ReactNode;
    position?: 'top' | 'bottom' | 'left' | 'right';
}

/**
 * Tooltip wrapper that displays info on hover.
 */
export const Tooltip: React.FC<TooltipProps> = ({
    content,
    children,
    position = 'top'
}) => {
    const [isVisible, setIsVisible] = useState(false);

    const positionClasses = {
        top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
        bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
        left: 'right-full top-1/2 -translate-y-1/2 mr-2',
        right: 'left-full top-1/2 -translate-y-1/2 ml-2',
    };

    return (
        <div
            className="relative inline-flex items-center"
            onMouseEnter={() => setIsVisible(true)}
            onMouseLeave={() => setIsVisible(false)}
        >
            {children}
            {isVisible && (
                <div className={`
                    absolute z-50 px-3 py-2 rounded-lg
                    bg-slate-800 border border-white/10
                    text-xs text-slate-300
                    max-w-xs whitespace-normal
                    shadow-xl backdrop-blur-sm
                    ${positionClasses[position]}
                    animate-in fade-in-0 zoom-in-95 duration-200
                `}>
                    {content}
                    {/* Arrow */}
                    <div className={`
                        absolute w-2 h-2 bg-slate-800 border-white/10
                        transform rotate-45
                        ${position === 'top' ? 'top-full left-1/2 -translate-x-1/2 -mt-1 border-b border-r' : ''}
                        ${position === 'bottom' ? 'bottom-full left-1/2 -translate-x-1/2 -mb-1 border-t border-l' : ''}
                        ${position === 'left' ? 'left-full top-1/2 -translate-y-1/2 -ml-1 border-t border-r' : ''}
                        ${position === 'right' ? 'right-full top-1/2 -translate-y-1/2 -mr-1 border-b border-l' : ''}
                    `} />
                </div>
            )}
        </div>
    );
};

/**
 * Info icon with tooltip for explaining metrics.
 */
export const InfoTooltip: React.FC<{ content: string }> = ({ content }) => (
    <Tooltip content={content}>
        <Info className="w-3.5 h-3.5 text-slate-500 hover:text-slate-400 cursor-help ml-1" />
    </Tooltip>
);

/**
 * Common trading term definitions for tooltips.
 */
export const TRADING_TERMS = {
    pnl: "Profit and Loss - The total gains or losses from your trading activity.",
    portfolioValue: "The total value of all assets in your trading account, including cash and open positions.",
    winRate: "The percentage of trades that resulted in a profit. Higher is better.",
    sharpeRatio: "A measure of risk-adjusted returns. Higher values indicate better risk-adjusted performance. Above 1.0 is considered good.",
    dailyPnl: "Profit or loss accumulated today since market open.",
    leverage: "The ratio of your position size to your collateral. Higher leverage = higher risk and reward.",
    exposure: "The total value of all your open positions. Helps measure your market risk.",
    confidence: "How certain the AI agents are about their trading signals. Higher confidence often leads to larger position sizes.",
    consensus: "When multiple AI agents agree on a trading direction. Stronger consensus = higher conviction trade.",
    streak: "The number of consecutive winning or losing trades.",
    accuracy: "How often your market predictions are correct.",
    sentiment: "The overall market mood - bullish (optimistic) or bearish (pessimistic).",
    bullish: "Expecting prices to rise. Named after a bull that attacks upward with its horns.",
    bearish: "Expecting prices to fall. Named after a bear that attacks downward with its claws.",
    neutral: "No strong expectation of price movement in either direction.",
} as const;

export default Tooltip;
