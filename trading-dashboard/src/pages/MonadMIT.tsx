import React, { useState, useEffect } from 'react';
import { Zap, TrendingUp, Shield, Users, CheckCircle, Circle } from 'lucide-react';
import { motion } from 'framer-motion';
import { SymphonyTradeForm } from '../components/SymphonyTradeForm';

interface ActivationProgress {
    current: number;
    required: number;
    percentage: number;
    activated: boolean;
}

interface MITFund {
    id?: string;
    name: string;
    description: string;
    balance: number;
    is_activated: boolean;
    trades_count: number;
}

export const MonadMIT: React.FC = () => {
    const [activationProgress, setActivationProgress] = useState<ActivationProgress>({
        current: 0,
        required: 5,
        percentage: 0,
        activated: false
    });

    const [fund, setFund] = useState<MITFund | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        fetchMITStatus();
    }, []);

    const fetchMITStatus = async () => {
        try {
            const apiUrl = import.meta.env.VITE_API_URL || 'https://cloud-trader-267358751314.europe-west1.run.app';
            const response = await fetch(`${apiUrl}/api/symphony/status`);
            const data = await response.json();

            setFund(data.fund);
            setActivationProgress({
                current: Math.min(data.trades_count || 0, 5),
                required: 5,
                percentage: Math.min(((data.trades_count || 0) / 5) * 100, 100),
                activated: data.is_activated || false
            });
        } catch (error) {
            console.error('Failed to fetch MIT status:', error);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-[#0a0a0f] via-[#1a0a2e] to-[#0a0a0f] text-white p-8 flex items-center justify-center">
                <div className="text-center">
                    <div className="w-16 h-16 border-4 border-purple-600 border-t-transparent rounded-full animate-spin mb-4 mx-auto" />
                    <p className="text-purple-300">Loading MIT Dashboard...</p>
                </div>
            </div>
        );
    }

    const renderActivationSteps = () => {
        const steps = [1, 2, 3, 4, 5];
        return (
            <div className="flex items-center justify-between mb-8">
                {steps.map((step, index) => (
                    <React.Fragment key={step}>
                        <div className="flex flex-col items-center">
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ delay: index * 0.1 }}
                                className={`w-12 h-12 rounded-full flex items-center justify-center border-2 ${step <= activationProgress.current
                                    ? 'bg-purple-600 border-purple-400 text-white'
                                    : 'bg-gray-800 border-gray-600 text-gray-500'
                                    }`}
                            >
                                {step <= activationProgress.current ? (
                                    <CheckCircle className="w-6 h-6" />
                                ) : (
                                    <Circle className="w-6 h-6" />
                                )}
                            </motion.div>
                            <span className="mt-2 text-xs text-gray-400">Trade {step}</span>
                        </div>
                        {index < steps.length - 1 && (
                            <div className="flex-1 h-0.5 mx-2 bg-gray-700 relative">
                                <motion.div
                                    initial={{ width: 0 }}
                                    animate={{
                                        width: step < activationProgress.current ? '100%' : '0%'
                                    }}
                                    transition={{ delay: index * 0.1 + 0.2 }}
                                    className="absolute inset-0 bg-purple-600"
                                />
                            </div>
                        )}
                    </React.Fragment>
                ))}
            </div>
        );
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-[#0a0a0f] via-[#1a0a2e] to-[#0a0a0f] text-white p-8">
            {/* Header */}
            <div className="max-w-6xl mx-auto">
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-center mb-12"
                >
                    <div className="inline-flex items-center gap-3 mb-4">
                        <Zap className="w-10 h-10 text-purple-400" />
                        <h1 className="text-5xl font-bold bg-gradient-to-r from-purple-400 via-purple-300 to-purple-500 bg-clip-text text-transparent">
                            MIT
                        </h1>
                    </div>
                    <p className="text-xl text-purple-300 font-medium">
                        Monad Implementation Treasury
                    </p>
                    <p className="text-gray-400 mt-2">
                        Autonomous AI Agent Trading on Symphony
                    </p>
                </motion.div>

                {/* Activation Status Card */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-gradient-to-br from-purple-900/30 via-purple-800/20 to-purple-900/30 backdrop-blur-xl border border-purple-500/30 rounded-2xl p-8 mb-8"
                >
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-2xl font-bold text-purple-100">
                            Activate Your Agentic Fund
                        </h2>
                        {activationProgress.activated && (
                            <div className="px-4 py-2 bg-green-500/20 border border-green-400/50 rounded-full flex items-center gap-2">
                                <CheckCircle className="w-5 h-5 text-green-400" />
                                <span className="text-green-300 font-medium">Activated</span>
                            </div>
                        )}
                    </div>

                    {/* Progress Bar */}
                    <div className="mb-6">
                        <div className="flex justify-between text-sm mb-2">
                            <span className="text-purple-300">Activation Progress</span>
                            <span className="text-purple-200 font-bold">
                                {activationProgress.current}/{activationProgress.required} trades
                            </span>
                        </div>
                        <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
                            <motion.div
                                initial={{ width: 0 }}
                                animate={{ width: `${activationProgress.percentage}%` }}
                                transition={{ duration: 1, ease: 'easeOut' }}
                                className="h-full bg-gradient-to-r from-purple-600 to-purple-400"
                            />
                        </div>
                    </div>

                    {/* Activation Steps */}
                    {renderActivationSteps()}

                    {/* Status Message */}
                    <div className="bg-purple-950/50 border border-purple-500/30 rounded-xl p-6">
                        {activationProgress.activated ? (
                            <div>
                                <h3 className="text-lg font-semibold text-purple-200 mb-2">
                                    🎉 Fund Activated!
                                </h3>
                                <p className="text-gray-300">
                                    Your agentic fund is now live. You can start accepting subscribers and earning management fees.
                                </p>
                            </div>
                        ) : (
                            <div>
                                <h3 className="text-lg font-semibold text-purple-200 mb-2">
                                    Welcome! Get started by making your first trade
                                </h3>
                                <p className="text-gray-300 mb-4">
                                    Your agentic fund is not yet activated. Complete{' '}
                                    <span className="text-purple-400 font-semibold">
                                        {5 - activationProgress.current} more trade{5 - activationProgress.current !== 1 ? 's' : ''}
                                    </span>{' '}
                                    to activate it and begin accepting subscribers.
                                </p>
                                <ul className="space-y-2 text-sm text-gray-400">
                                    <li className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 bg-purple-400 rounded-full" />
                                        Execute trades via perpetuals or spot markets
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 bg-purple-400 rounded-full" />
                                        Maintain full custody through your Symphony smart account
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <div className="w-1.5 h-1.5 bg-purple-400 rounded-full" />
                                        Set custom fee structures once activated
                                    </li>
                                </ul>
                            </div>
                        )}
                    </div>
                </motion.div>

                {/* Features Grid */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <FeatureCard
                        icon={<TrendingUp className="w-6 h-6" />}
                        title="Autonomous Trading"
                        description="AI-powered execution on Monad's high-performance blockchain"
                    />
                    <FeatureCard
                        icon={<Shield className="w-6 h-6" />}
                        title="Full Custody"
                        description="Your funds stay in your Symphony smart account"
                    />
                    <FeatureCard
                        icon={<Users className="w-6 h-6" />}
                        title="Subscriber Fees"
                        description="Earn management fees once your fund is activated"
                    />
                </div>

                {/* Trading Interface - Only show if not activated */}
                {!activationProgress.activated && (
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.3 }}
                        className="mt-8"
                    >
                        <SymphonyTradeForm onTradeComplete={fetchMITStatus} />
                    </motion.div>
                )}
            </div>
        </div>
    );
};

interface FeatureCardProps {
    icon: React.ReactNode;
    title: string;
    description: string;
}

const FeatureCard: React.FC<FeatureCardProps> = ({ icon, title, description }) => {
    return (
        <motion.div
            whileHover={{ scale: 1.02 }}
            className="bg-purple-900/20 backdrop-blur-sm border border-purple-500/20 rounded-xl p-6 hover:border-purple-400/40 transition-all"
        >
            <div className="w-12 h-12 bg-purple-600/20 rounded-lg flex items-center justify-center mb-4 text-purple-400">
                {icon}
            </div>
            <h3 className="text-lg font-semibold text-purple-100 mb-2">{title}</h3>
            <p className="text-gray-400 text-sm">{description}</p>
        </motion.div>
    );
};

export default MonadMIT;
