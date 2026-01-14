
import React from 'react';
import { motion } from 'framer-motion';

interface GlassCardProps {
    title?: string;
    children: React.ReactNode;
    className?: string;
    height?: number | string;
}

export const GlassCard: React.FC<GlassCardProps> = ({ title, children, className = '', height = 'auto' }) => {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className={`
                bg-[#0a0b10]/80 backdrop-blur-xl border border-white/5
                rounded-xl shadow-2xl overflow-hidden flex flex-col
                ${className}
            `}
            style={{ height }}
        >
            {title && (
                <div className="px-4 py-3 border-b border-white/5 flex items-center justify-between bg-white/5">
                    <h3 className="text-xs font-bold text-gray-400 tracking-wider uppercase">
                        {title}
                    </h3>
                    <div className="flex gap-1">
                        <div className="w-1 h-1 rounded-full bg-white/20" />
                        <div className="w-1 h-1 rounded-full bg-white/20" />
                    </div>
                </div>
            )}
            <div className="p-4 flex-1 overflow-auto custom-scrollbar relative">
                {children}
            </div>
        </motion.div>
    );
};
