import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Loader, CheckCircle, AlertCircle } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface TradeFormProps {
    onTradeComplete: () => void;
}

export const SymphonyTradeForm: React.FC<TradeFormProps> = ({ onTradeComplete }) => {
    const { user } = useAuth();
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

    const [formData, setFormData] = useState({
        tradeType: 'perpetual',
        symbol: 'BTC-USDC',
        side: 'LONG',
        size: '20',
        leverage: '2'
    });

    const quickTrade = async (symbol: string, side: string) => {
        if (!user) {
            setResult({ success: false, message: 'Please log in to trade' });
            return;
        }

        setLoading(true);
        setResult(null);

        try {
            const token = await user.getIdToken();
            const response = await fetch(
                `${import.meta.env.VITE_API_URL}/api/symphony/trade/perpetual`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        symbol,
                        side,
                        size: 10,  // Small size for activation
                        leverage: 1  // Minimum leverage
                    })
                }
            );

            const data = await response.json();

            if (data.success) {
                setResult({
                    success: true,
                    message: `✅ Trade executed! Progress: ${data.activation_progress.current}/5`
                });
                onTradeComplete();
            } else {
                setResult({ success: false, message: data.error || 'Trade failed' });
            }
        } catch (error) {
            console.error('Trade error:', error);
            setResult({ success: false, message: String(error) });
        } finally {
            setLoading(false);
        }
    };

    const executeCustomTrade = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!user) {
            setResult({ success: false, message: 'Please log in to trade' });
            return;
        }

        setLoading(true);
        setResult(null);

        try {
            const token = await user.getIdToken();
            const endpoint = formData.tradeType === 'perpetual'
                ? '/api/symphony/trade/perpetual'
                : '/api/symphony/trade/spot';

            const body = formData.tradeType === 'perpetual'
                ? {
                    symbol: formData.symbol,
                    side: formData.side,
                    size: parseFloat(formData.size),
                    leverage: parseInt(formData.leverage)
                }
                : {
                    symbol: formData.symbol,
                    side: formData.side === 'LONG' ? 'BUY' : 'SELL',
                    quantity: parseFloat(formData.size) / 45000, // Rough BTC price estimate
                    order_type: 'market'
                };

            const response = await fetch(
                `${import.meta.env.VITE_API_URL}${endpoint}`,
                {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${token}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(body)
                }
            );

            const data = await response.json();

            if (data.success) {
                setResult({
                    success: true,
                    message: `✅ ${data.message} Progress: ${data.activation_progress.current}/5`
                });
                onTradeComplete();
            } else {
                setResult({ success: false, message: data.error || 'Trade failed' });
            }
        } catch (error) {
            console.error('Trade error:', error);
            setResult({ success: false, message: String(error) });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-purple-900/20 backdrop-blur-sm border border-purple-500/30 rounded-xl p-6">
            <h3 className="text-xl font-bold text-purple-100 mb-4">Quick Activation Trades</h3>
            <p className="text-sm text-gray-400 mb-6">
                Execute small trades to activate your fund. Minimum 5 trades required.
            </p>

            {/* Quick Trade Buttons */}
            <div className="grid grid-cols-2 gap-3 mb-6">
                <button
                    onClick={() => quickTrade('BTC-USDC', 'LONG')}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 px-4 py-3 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded-lg text-green-300 font-medium transition-all disabled:opacity-50"
                >
                    <TrendingUp className="w-5 h-5" />
                    Long BTC ($10)
                </button>
                <button
                    onClick={() => quickTrade('BTC-USDC', 'SHORT')}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 px-4 py-3 bg-red-600/20 hover:bg-red-600/30 border border-red-500/30 rounded-lg text-red-300 font-medium transition-all disabled:opacity-50"
                >
                    <TrendingDown className="w-5 h-5" />
                    Short BTC ($10)
                </button>
                <button
                    onClick={() => quickTrade('ETH-USDC', 'LONG')}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 px-4 py-3 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded-lg text-green-300 font-medium transition-all disabled:opacity-50"
                >
                    <TrendingUp className="w-5 h-5" />
                    Long ETH ($10)
                </button>
                <button
                    onClick={() => quickTrade('SOL-USDC', 'LONG')}
                    disabled={loading}
                    className="flex items-center justify-center gap-2 px-4 py-3 bg-green-600/20 hover:bg-green-600/30 border border-green-500/30 rounded-lg text-green-300 font-medium transition-all disabled:opacity-50"
                >
                    <TrendingUp className="w-5 h-5" />
                    Long SOL ($10)
                </button>
            </div>

            {/* Custom Trade Form */}
            <div className="border-t border-purple-500/20 pt-6">
                <h4 className="text-sm font-semibold text-purple-200 mb-3">Custom Trade</h4>
                <form onSubmit={executeCustomTrade} className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Symbol</label>
                            <select
                                value={formData.symbol}
                                onChange={(e) => setFormData({ ...formData, symbol: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none"
                            >
                                <option>BTC-USDC</option>
                                <option>ETH-USDC</option>
                                <option>SOL-USDC</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Side</label>
                            <select
                                value={formData.side}
                                onChange={(e) => setFormData({ ...formData, side: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none"
                            >
                                <option value="LONG">Long</option>
                                <option value="SHORT">Short</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Size (USDC)</label>
                            <input
                                type="number"
                                value={formData.size}
                                onChange={(e) => setFormData({ ...formData, size: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none"
                                min="10"
                                max="100"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-gray-400 mb-1">Leverage</label>
                            <select
                                value={formData.leverage}
                                onChange={(e) => setFormData({ ...formData, leverage: e.target.value })}
                                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:border-purple-500 focus:outline-none"
                            >
                                <option>1</option>
                                <option>2</option>
                                <option>3</option>
                                <option>5</option>
                            </select>
                        </div>
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full px-4 py-3 bg-purple-600 hover:bg-purple-700 rounded-lg text-white font-medium transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {loading ? (
                            <>
                                <Loader className="w-5 h-5 animate-spin" />
                                Executing...
                            </>
                        ) : (
                            <>Execute Trade</>
                        )}
                    </button>
                </form>
            </div>

            {/* Result Message */}
            {result && (
                <div className={`mt-4 p-3 rounded-lg flex items-start gap-2 ${result.success
                        ? 'bg-green-500/20 border border-green-500/30 text-green-300'
                        : 'bg-red-500/20 border border-red-500/30 text-red-300'
                    }`}>
                    {result.success ? (
                        <CheckCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    ) : (
                        <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                    )}
                    <p className="text-sm">{result.message}</p>
                </div>
            )}
        </div>
    );
};

export default SymphonyTradeForm;
