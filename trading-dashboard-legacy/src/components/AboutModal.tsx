
import { Dialog } from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, Zap, Terminal } from 'lucide-react';
import { GlassCard } from './GlassCard';

interface AboutModalProps {
    open: boolean;
    onClose: () => void;
}

export const AboutModal: React.FC<AboutModalProps> = ({ open, onClose }) => {
    return (
        <Dialog
            open={open}
            onClose={onClose}
            maxWidth="md"
            fullWidth
            PaperProps={{
                style: {
                    backgroundColor: 'transparent',
                    boxShadow: 'none',
                    overflow: 'visible'
                }
            }}
        >
            <AnimatePresence>
                {open && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        exit={{ opacity: 0, scale: 0.9 }}
                        transition={{ duration: 0.3 }}
                    >
                        <GlassCard title="SYSTEM MANIFESTO" height="auto" className="border-blue-500/30 shadow-[0_0_50px_rgba(59,130,246,0.3)]">
                            <div className="flex flex-col gap-6 text-slate-300">
                                <div className="text-center pb-6 border-b border-white/10">
                                    <h1 className="text-3xl font-black text-white mb-2 tracking-tight">
                                        SAPPHIRE <span className="text-blue-500">AI</span>
                                    </h1>
                                    <p className="text-blue-200 font-mono text-xs uppercase tracking-widest">
                                        Autonomous High-Frequency Trading Swarm
                                    </p>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                                    <div>
                                        <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                                            <Brain size={16} className="text-purple-400" />
                                            NEURAL CORE
                                        </h3>
                                        <p className="text-xs leading-relaxed text-slate-400">
                                            Powered by a custom <b>Agent Consensus Engine</b> (ACE) that aggregates signals from specialized autonomous agents using a weighted voting mechanism. The system learns from every trade, adjusting agent weights in real-time based on PnL performance (Sortino/Sharpe optimization).
                                        </p>
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
                                            <Zap size={16} className="text-yellow-400" />
                                            SWARM EXECUTION
                                        </h3>
                                        <p className="text-xs leading-relaxed text-slate-400">
                                            Trades are executed via a <b>Gather-Vote-Execute</b> loop. Agents collaboratively scan the market, submit thesis-driven signals, and the swarm executes only high-conviction opportunities with asymmetric sizing (1x - 5x leverage).
                                        </p>
                                    </div>
                                </div>

                                <div className="bg-black/40 rounded-lg p-4 font-mono text-[10px] text-green-400 border border-white/5 overflow-hidden relative">
                                    <div className="absolute top-0 right-0 p-2 opacity-20">
                                        <Terminal size={14} />
                                    </div>
                                    <div className="flex flex-col gap-1">
                                        <span>$ system_status --all</span>
                                        <span className="text-slate-500"> Checking Neural Link... [OK]</span>
                                        <span className="text-slate-500"> Verifying Sentinel Policies... [OK]</span>
                                        <span className="text-slate-500"> Syncing Exchange Data... [OK]</span>
                                        <span className="text-white mt-1">{`> SWARM STATE: ACTIVE`}</span>
                                        <span className="text-white">{`> MODE: ASYMMETRIC_AGGRESIVE`}</span>
                                    </div>
                                </div>
                            </div>
                        </GlassCard>
                    </motion.div>
                )}
            </AnimatePresence>
        </Dialog>
    );
};
