import { memo, ReactNode } from 'react';
import { motion } from 'framer-motion';

interface GlassPanelProps {
    children: ReactNode;
    className?: string;
    highlight?: boolean;
    animate?: boolean;
    delay?: number;
}

/**
 * GlassPanel - Reusable glassmorphism container with optional animations.
 * Centralizes the dark glass aesthetic used throughout the app.
 */
export const GlassPanel = memo<GlassPanelProps>(({
    children,
    className = '',
    highlight = false,
    animate = true,
    delay = 0
}) => {
    const baseClasses = `
        relative overflow-hidden rounded-xl border backdrop-blur-xl
        transition-all duration-300
        ${highlight
            ? 'bg-gradient-to-br from-cyan-500/10 to-slate-900/90 border-cyan-500/30'
            : 'bg-slate-900/60 border-white/5 hover:border-white/10'
        }
    `;

    const content = (
        <div className={`${baseClasses} ${className}`}>
            {highlight && (
                <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-cyan-400 via-cyan-500/50 to-transparent" />
            )}
            {children}
        </div>
    );

    if (!animate) return content;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
                duration: 0.4,
                delay: delay * 0.1,
                ease: [0.25, 0.46, 0.45, 0.94]
            }}
        >
            {content}
        </motion.div>
    );
});

GlassPanel.displayName = 'GlassPanel';
export default GlassPanel;
