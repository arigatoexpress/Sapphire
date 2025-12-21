import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    ArrowDownUp,
    Zap,
    TrendingUp,
    Wallet,
    Settings,
    RefreshCw,
    ExternalLink,
    Loader2
} from 'lucide-react';
import { useWallet, useConnection } from '@solana/wallet-adapter-react';
import { WalletMultiButton } from '@solana/wallet-adapter-react-ui';
import { toast } from 'react-toastify';

interface Token {
    address: string;
    symbol: string;
    name: string;
    decimals: number;
    logoURI?: string;
}

interface Quote {
    inAmount: string;
    outAmount: string;
    priceImpactPct: number;
    routePlan: any[];
}

const JupiterSwap: React.FC = () => {
    const { publicKey, connected } = useWallet();
    const { connection } = useConnection();

    // State
    const [tokens, setTokens] = useState<Token[]>([]);
    const [inputToken, setInputToken] = useState<Token | null>(null);
    const [outputToken, setOutputToken] = useState<Token | null>(null);
    const [inputAmount, setInputAmount] = useState('');
    const [outputAmount, setOutputAmount] = useState('');
    const [quote, setQuote] = useState<Quote | null>(null);
    const [loading, setLoading] = useState(false);
    const [fetchingQuote, setFetchingQuote] = useState(false);
    const [slippage, setSlippage] = useState(0.5); // 0.5%
    const [showSettings, setShowSettings] = useState(false);

    const API_URL = import.meta.env.VITE_API_URL || 'https://cloud-trader-267358751314.europe-west1.run.app';

    // Fetch tokens on mount
    useEffect(() => {
        fetchTokens();
    }, []);

    const fetchTokens = async () => {
        try {
            const response = await fetch(`${API_URL}/api/jupiter/tokens?verified_only=true`);
            const data = await response.json();

            if (data.success) {
                setTokens(data.tokens);

                // Set default tokens: SOL → USDC
                const sol = data.tokens.find((t: Token) => t.symbol === 'SOL');
                const usdc = data.tokens.find((t: Token) => t.symbol === 'USDC');

                if (sol) setInputToken(sol);
                if (usdc) setOutputToken(usdc);
            }
        } catch (error) {
            console.error('Failed to fetch tokens:', error);
            toast.error('Failed to load token list');
        }
    };

    // Get quote when amount changes
    useEffect(() => {
        if (inputAmount && inputToken && outputToken && parseFloat(inputAmount) > 0) {
            const debounce = setTimeout(() => {
                fetchQuote();
            }, 500);
            return () => clearTimeout(debounce);
        }
    }, [inputAmount, inputToken, outputToken, slippage]);

    const fetchQuote = async () => {
        if (!inputToken || !outputToken || !inputAmount) return;

        setFetchingQuote(true);

        try {
            const amount = Math.floor(parseFloat(inputAmount) * Math.pow(10, inputToken.decimals));
            const slippageBps = Math.floor(slippage * 100);

            const response = await fetch(
                `${API_URL}/api/jupiter/quote?` +
                `input_mint=${inputToken.address}&` +
                `output_mint=${outputToken.address}&` +
                `amount=${amount}&` +
                `slippage_bps=${slippageBps}`
            );

            const data = await response.json();

            if (data.success) {
                setQuote(data.quote);
                const outAmt = parseInt(data.output_amount) / Math.pow(10, outputToken.decimals);
                setOutputAmount(outAmt.toFixed(6));
            } else {
                toast.error('Failed to get quote');
            }
        } catch (error) {
            console.error('Quote error:', error);
        } finally {
            setFetchingQuote(false);
        }
    };

    const handleSwap = async () => {
        if (!connected || !publicKey) {
            toast.error('Please connect your wallet');
            return;
        }

        if (!quote || !inputToken || !outputToken) {
            toast.error('Please get a quote first');
            return;
        }

        setLoading(true);

        try {
            const amount = Math.floor(parseFloat(inputAmount) * Math.pow(10, inputToken.decimals));
            const slippageBps = Math.floor(slippage * 100);

            const response = await fetch(`${API_URL}/api/jupiter/swap`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    input_mint: inputToken.address,
                    output_mint: outputToken.address,
                    amount: amount,
                    slippage_bps: slippageBps,
                    priority_level: 'medium'
                })
            });

            const data = await response.json();

            if (data.success) {
                toast.success(
                    <div>
                        <div>Swap successful!</div>
                        <a
                            href={data.explorer_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-400 underline text-sm"
                        >
                            View on Solscan
                        </a>
                    </div>
                );

                // Reset form
                setInputAmount('');
                setOutputAmount('');
                setQuote(null);
            } else {
                toast.error(data.message || 'Swap failed');
            }
        } catch (error) {
            console.error('Swap error:', error);
            toast.error('Swap execution failed');
        } finally {
            setLoading(false);
        }
    };

    const swapTokens = () => {
        const temp = inputToken;
        setInputToken(outputToken);
        setOutputToken(temp);
        setInputAmount(outputAmount);
        setOutputAmount(inputAmount);
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-[#0a0a0f] via-[#16102e] to-[#0a0a0f] text-white p-8">
            <div className="max-w-2xl mx-auto">
                {/* Header */}
                <motion.div
                    initial={{ opacity: 0, y: -20 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="text-center mb-8"
                >
                    <div className="inline-flex items-center gap-3 mb-4">
                        <Zap className="w-12 h-12 text-cyan-400" />
                        <h1 className="text-6xl font-bold bg-gradient-to-r from-cyan-400 via-blue-300 to-purple-500 bg-clip-text text-transparent">
                            Jupiter Swap
                        </h1>
                    </div>
                    <p className="text-xl text-gray-400 mb-2">
                        Best prices across all Solana DEXs
                    </p>
                    <div className="inline-flex items-center gap-2 text-sm text-cyan-400">
                        <TrendingUp className="w-4 h-4" />
                        <span>Powered by Jupiter Aggregator</span>
                    </div>
                </motion.div>

                {/* Wallet Connection */}
                {!connected && (
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="mb-8"
                    >
                        <div className="bg-gradient-to-r from-cyan-900/30 to-blue-900/30 border border-cyan-500/50 rounded-2xl p-8 text-center">
                            <Wallet className="w-16 h-16 text-cyan-400 mx-auto mb-4" />
                            <h2 className="text-2xl font-bold mb-2">Connect Your Wallet</h2>
                            <p className="text-gray-400 mb-6">
                                Connect your Solana wallet to start swapping tokens
                            </p>
                            <WalletMultiButton className="!bg-gradient-to-r !from-cyan-600 !to-blue-600 hover:!from-cyan-700 hover:!to-blue-700" />
                        </div>
                    </motion.div>
                )}

                {/* Swap Interface */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    className="bg-gradient-to-br from-cyan-900/20 via-blue-800/20 to-purple-900/20 backdrop-blur-xl border border-cyan-500/30 rounded-2xl p-8 relative overflow-hidden"
                >
                    {/* Settings Button */}
                    <button
                        onClick={() => setShowSettings(!showSettings)}
                        className="absolute top-6 right-6 p-2 bg-gray-800/50 hover:bg-gray-700/50 rounded-lg transition-colors"
                    >
                        <Settings className="w-5 h-5" />
                    </button>

                    {/* Settings Panel */}
                    <AnimatePresence>
                        {showSettings && (
                            <motion.div
                                initial={{ opacity: 0, height: 0 }}
                                animate={{ opacity: 1, height: 'auto' }}
                                exit={{ opacity: 0, height: 0 }}
                                className="mb-6 p-4 bg-gray-800/50 rounded-lg"
                            >
                                <h3 className="text-sm font-semibold mb-3">Slippage Tolerance</h3>
                                <div className="flex gap-2">
                                    {[0.1, 0.5, 1.0].map((s) => (
                                        <button
                                            key={s}
                                            onClick={() => setSlippage(s)}
                                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${slippage === s
                                                ? 'bg-cyan-600 text-white'
                                                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                                                }`}
                                        >
                                            {s}%
                                        </button>
                                    ))}
                                    <input
                                        type="number"
                                        value={slippage}
                                        onChange={(e) => setSlippage(parseFloat(e.target.value) || 0.5)}
                                        className="flex-1 px-3 py-2 bg-gray-700 rounded-lg text-sm"
                                        step="0.1"
                                        min="0"
                                        max="50"
                                    />
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* Input Token */}
                    <div className="mb-4">
                        <label className="block text-sm text-gray-400 mb-2">You Pay</label>
                        <div className="flex gap-4">
                            <select
                                value={inputToken?.address || ''}
                                onChange={(e) => {
                                    const token = tokens.find(t => t.address === e.target.value);
                                    setInputToken(token || null);
                                }}
                                className="w-40 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white font-medium"
                                disabled={!connected}
                            >
                                {tokens.map(token => (
                                    <option key={token.address} value={token.address}>
                                        {token.symbol}
                                    </option>
                                ))}
                            </select>
                            <input
                                type="number"
                                value={inputAmount}
                                onChange={(e) => setInputAmount(e.target.value)}
                                placeholder="0.00"
                                className="flex-1 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white text-right text-xl font-semibold"
                                disabled={!connected}
                            />
                        </div>
                    </div>

                    {/* Swap Button */}
                    <div className="flex justify-center my-4">
                        <button
                            onClick={swapTokens}
                            className="p-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-700 hover:to-blue-700 rounded-full transition-all transform hover:scale-110"
                            disabled={!connected}
                        >
                            <ArrowDownUp className="w-6 h-6" />
                        </button>
                    </div>

                    {/* Output Token */}
                    <div className="mb-6">
                        <label className="block text-sm text-gray-400 mb-2">You Receive</label>
                        <div className="flex gap-4">
                            <select
                                value={outputToken?.address || ''}
                                onChange={(e) => {
                                    const token = tokens.find(t => t.address === e.target.value);
                                    setOutputToken(token || null);
                                }}
                                className="w-40 px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white font-medium"
                                disabled={!connected}
                            >
                                {tokens.map(token => (
                                    <option key={token.address} value={token.address}>
                                        {token.symbol}
                                    </option>
                                ))}
                            </select>
                            <div className="flex-1 px-4 py-3 bg-gray-800/50 border border-gray-700 rounded-lg text-white text-right text-xl font-semibold flex items-center justify-end gap-2">
                                {fetchingQuote && <Loader2 className="w-4 h-4 animate-spin" />}
                                {outputAmount || '0.00'}
                            </div>
                        </div>
                    </div>

                    {/* Quote Info */}
                    {quote && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="mb-6 p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-lg space-y-2 text-sm"
                        >
                            <div className="flex justify-between">
                                <span className="text-gray-400">Price Impact</span>
                                <span className={quote.priceImpactPct > 1 ? 'text-red-400' : 'text-green-400'}>
                                    {quote.priceImpactPct.toFixed(3)}%
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Route</span>
                                <span className="text-cyan-300">
                                    {quote.routePlan.length} hop{quote.routePlan.length > 1 ? 's' : ''}
                                </span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Slippage Tolerance</span>
                                <span className="text-white">{slippage}%</span>
                            </div>
                        </motion.div>
                    )}

                    {/* Swap Execute Button */}
                    <button
                        onClick={handleSwap}
                        disabled={!connected || !quote || loading || !inputAmount}
                        className="w-full px-6 py-4 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-700 hover:to-blue-700 rounded-xl text-white font-bold text-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-3"
                    >
                        {loading ? (
                            <>
                                <Loader2 className="w-6 h-6 animate-spin" />
                                Swapping...
                            </>
                        ) : !connected ? (
                            <>
                                <Wallet className="w-6 h-6" />
                                Connect Wallet
                            </>
                        ) : (
                            <>
                                <Zap className="w-6 h-6" />
                                Swap
                            </>
                        )}
                    </button>
                </motion.div>

                {/* Footer */}
                <div className="mt-8 text-center">
                    <p className="text-sm text-gray-500 flex items-center justify-center gap-2">
                        <span>Powered by</span>
                        <span className="text-cyan-400 font-semibold">Jupiter</span>
                        <span>•</span>
                        <span>Best prices guaranteed</span>
                        <ExternalLink className="w-3 h-3" />
                    </p>
                </div>
            </div>
        </div>
    );
};

export default JupiterSwap;
