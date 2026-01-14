import React, { useState, useEffect, useRef, memo, useCallback } from 'react';
import { getApiUrl } from '../utils/apiConfig';
import { Send, Heart, MessageCircle, Sparkles, TrendingUp, Bot, Lock, Trophy, RefreshCw, AlertCircle, CheckCircle, Zap, X } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface ChatMessage {
    id: string;
    user_id: string;
    username: string;
    display_name: string;
    avatar: string;
    content: string;
    tickers: string[];
    timestamp: string;
    is_bot: boolean;
    bot_replied: boolean;
    points_awarded: number;
    award_reason: string;
    likes: number;
    reply_to: string | null;
}

interface UserProfile {
    username: string;
    display_name: string;
    total_points: number;
    chat_points: number;
    advice_taken: number;
    is_advisor: boolean;
}

type ToastType = 'success' | 'error' | 'info';

interface Toast {
    id: number;
    type: ToastType;
    message: string;
}

const API_URL = getApiUrl();

// Quick ticker buttons
const QUICK_TICKERS = ['$BTC', '$ETH', '$SOL', '$XRP'];

// Highlight tickers in message content
const formatMessage = (content: string) => {
    const tickerRegex = /\$([A-Z]{2,10})/gi;
    const parts = content.split(tickerRegex);

    return parts.map((part, i) => {
        if (i % 2 === 1) {
            return (
                <span key={i} className="inline-flex items-center bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded text-xs font-bold">
                    ${part.toUpperCase()}
                </span>
            );
        }
        return part;
    });
};

// Time ago formatter
const timeAgo = (timestamp: string): string => {
    const seconds = Math.floor((Date.now() - new Date(timestamp).getTime()) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
};

// Toast Component
const ToastNotification: React.FC<{ toast: Toast; onClose: () => void }> = ({ toast, onClose }) => {
    useEffect(() => {
        const timer = setTimeout(onClose, 4000);
        return () => clearTimeout(timer);
    }, [onClose]);

    const colors = {
        success: 'bg-emerald-500/20 border-emerald-500/30 text-emerald-400',
        error: 'bg-red-500/20 border-red-500/30 text-red-400',
        info: 'bg-cyan-500/20 border-cyan-500/30 text-cyan-400',
    };

    const icons = {
        success: <CheckCircle size={14} />,
        error: <AlertCircle size={14} />,
        info: <Zap size={14} />,
    };

    return (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${colors[toast.type]} animate-slide-in`}>
            {icons[toast.type]}
            <span className="text-xs">{toast.message}</span>
            <button onClick={onClose} className="ml-auto opacity-60 hover:opacity-100">
                <X size={12} />
            </button>
        </div>
    );
};

// Message Component
const ChatMessageItem: React.FC<{
    message: ChatMessage;
    onLike: (id: string) => void;
    currentUserId?: string;
}> = ({ message, onLike, currentUserId }) => {
    const isBot = message.is_bot;
    const isOwn = currentUserId && message.user_id === currentUserId;

    return (
        <div className={`group p-3 rounded-lg transition-all ${isBot
                ? 'bg-gradient-to-r from-purple-500/10 to-slate-800/50 border border-purple-500/20'
                : message.points_awarded > 0
                    ? 'bg-gradient-to-r from-yellow-500/10 to-slate-800/50 border border-yellow-500/20'
                    : isOwn
                        ? 'bg-cyan-500/5 border border-cyan-500/10'
                        : 'bg-slate-800/30 hover:bg-slate-800/50 border border-transparent'
            }`}>
            {message.points_awarded > 0 && (
                <div className="flex items-center gap-2 mb-2 text-xs">
                    <div className="flex items-center gap-1 bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded-full animate-pulse">
                        <Sparkles size={12} />
                        <span className="font-bold">+{message.points_awarded} pts</span>
                    </div>
                    <span className="text-slate-500">{message.award_reason}</span>
                </div>
            )}

            <div className="flex items-center gap-2 mb-1">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm ${isBot ? 'bg-purple-500/30' : isOwn ? 'bg-cyan-500/30' : 'bg-slate-700'
                    }`}>
                    {isBot ? <Bot size={14} className="text-purple-400" /> : message.avatar || '👤'}
                </div>
                <span className={`text-sm font-medium ${isBot ? 'text-purple-400' : isOwn ? 'text-cyan-400' : 'text-white'
                    }`}>
                    {message.display_name || message.username}
                    {isOwn && <span className="text-[9px] ml-1 opacity-60">(you)</span>}
                </span>
                {isBot && (
                    <span className="text-[9px] bg-purple-500/30 text-purple-300 px-1.5 py-0.5 rounded">BOT</span>
                )}
                <span className="text-[10px] text-slate-600 ml-auto">
                    {timeAgo(message.timestamp)}
                </span>
            </div>

            <p className="text-sm text-slate-300 leading-relaxed ml-8">
                {formatMessage(message.content)}
            </p>

            <div className="flex items-center gap-3 mt-2 ml-8">
                <button
                    onClick={() => onLike(message.id)}
                    className="flex items-center gap-1 text-xs text-slate-500 hover:text-red-400 transition-colors"
                >
                    <Heart size={12} className={message.likes > 0 ? 'fill-red-400 text-red-400' : ''} />
                    {message.likes > 0 && <span>{message.likes}</span>}
                </button>
                {message.tickers.length > 0 && (
                    <div className="flex items-center gap-1 text-[10px] text-slate-600">
                        <TrendingUp size={10} />
                        {message.tickers.join(', ')}
                    </div>
                )}
                {message.bot_replied && !isBot && (
                    <span className="text-[10px] text-purple-400 flex items-center gap-1">
                        <Bot size={10} /> Bot engaged
                    </span>
                )}
            </div>
        </div>
    );
};

export const LiveChatPanel: React.FC = () => {
    const { user, loading: authLoading } = useAuth();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [newMessage, setNewMessage] = useState('');
    const [loading, setLoading] = useState(true);
    const [sending, setSending] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [profile, setProfile] = useState<UserProfile | null>(null);
    const [showUsernameModal, setShowUsernameModal] = useState(false);
    const [usernameInput, setUsernameInput] = useState('');
    const [usernameError, setUsernameError] = useState('');
    const [toasts, setToasts] = useState<Toast[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const toastIdRef = useRef(0);

    const addToast = useCallback((type: ToastType, message: string) => {
        const id = ++toastIdRef.current;
        setToasts(prev => [...prev, { id, type, message }]);
    }, []);

    const removeToast = useCallback((id: number) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const fetchMessages = useCallback(async (showRefresh = false) => {
        if (showRefresh) setRefreshing(true);
        setError(null);

        try {
            const res = await fetch(`${API_URL}/api/chat/messages?limit=50`);
            if (res.ok) {
                const data = await res.json();
                setMessages(data.messages || []);
            } else {
                throw new Error(`Failed to fetch: ${res.status}`);
            }
        } catch (e) {
            console.error('Failed to fetch messages:', e);
            setError('Unable to load messages');
        } finally {
            setLoading(false);
            if (showRefresh) setRefreshing(false);
        }
    }, []);

    const fetchProfile = useCallback(async () => {
        if (!user) return;

        try {
            const token = await user.getIdToken();
            const res = await fetch(`${API_URL}/api/user/profile`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (res.ok) {
                const data = await res.json();
                if (!data.error) {
                    setProfile(data);
                    if (data.username && data.username.startsWith('user_')) {
                        setShowUsernameModal(true);
                    }
                }
            }
        } catch (e) {
            console.error('Failed to fetch profile:', e);
        }
    }, [user]);

    useEffect(() => {
        fetchMessages();
        if (user) fetchProfile();
    }, [fetchMessages, fetchProfile, user]);

    useEffect(() => {
        const interval = setInterval(() => fetchMessages(false), 5000);
        return () => clearInterval(interval);
    }, [fetchMessages]);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    const handleSend = async () => {
        if (!user) {
            addToast('error', 'Please sign in to send messages');
            return;
        }

        if (!newMessage.trim()) {
            addToast('error', 'Please enter a message');
            return;
        }

        setSending(true);
        try {
            const token = await user.getIdToken();
            const res = await fetch(`${API_URL}/api/chat/send`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ content: newMessage }),
            });

            if (res.status === 401) {
                addToast('error', 'Session expired. Please log out and back in.');
                return;
            }

            const data = await res.json();
            if (res.ok && data.success) {
                setNewMessage('');
                addToast('success', 'Message sent!');
                await fetchMessages();
                inputRef.current?.focus();
            } else {
                addToast('error', data.error || data.message || 'Failed to send message');
            }
        } catch (e) {
            console.error('Failed to send message:', e);
            addToast('error', 'Network error - please try again');
        } finally {
            setSending(false);
        }
    };

    const handleLike = async (messageId: string) => {
        if (!user) {
            addToast('info', 'Sign in to like messages');
            return;
        }

        try {
            const token = await user.getIdToken();
            const res = await fetch(`${API_URL}/api/chat/like`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({ message_id: messageId }),
            });

            if (res.ok) {
                await fetchMessages();
            }
        } catch (e) {
            console.error('Failed to like message:', e);
        }
    };

    const insertTicker = (ticker: string) => {
        setNewMessage(prev => prev + (prev.endsWith(' ') || prev === '' ? '' : ' ') + ticker + ' ');
        inputRef.current?.focus();
    };

    const handleSetUsername = async () => {
        if (!user || !usernameInput.trim()) return;

        setUsernameError('');

        try {
            const token = await user.getIdToken();
            const res = await fetch(`${API_URL}/api/user/profile`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    username: usernameInput.trim(),
                    display_name: usernameInput.trim(),
                }),
            });

            const data = await res.json();

            if (data.error) {
                setUsernameError(data.error);
            } else {
                setShowUsernameModal(false);
                addToast('success', `Welcome, ${usernameInput}!`);
                await fetchProfile();
            }
        } catch (e) {
            setUsernameError('Failed to set username');
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    };

    return (
        <div className="flex flex-col h-full bg-slate-900/60 backdrop-blur-xl rounded-xl border border-white/5 overflow-hidden relative">
            <div className="absolute top-12 right-3 z-50 space-y-2">
                {toasts.map(toast => (
                    <ToastNotification key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
                ))}
            </div>

            <div className="flex items-center justify-between p-3 border-b border-white/5">
                <div className="flex items-center gap-2">
                    <MessageCircle className="w-4 h-4 text-cyan-400" />
                    <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">Community Intelligence</span>
                    <div className={`w-2 h-2 rounded-full ${error ? 'bg-red-400' : 'bg-emerald-400'} ${!error && 'animate-pulse'}`} />
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => fetchMessages(true)}
                        disabled={refreshing}
                        className="p-1.5 text-slate-500 hover:text-cyan-400 transition-colors disabled:opacity-50"
                        title="Refresh messages"
                    >
                        <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
                    </button>
                    {profile && (
                        <div className="flex items-center gap-2 text-xs">
                            <span className="text-slate-500">{profile.username}</span>
                            <div className="flex items-center gap-1 bg-yellow-500/20 text-yellow-400 px-2 py-0.5 rounded-full">
                                <Trophy size={10} />
                                <span className="font-bold">{profile.chat_points || 0}</span>
                            </div>
                        </div>
                    )}
                </div>
            </div>

            <div className="px-3 py-2 bg-gradient-to-r from-purple-500/10 to-cyan-500/10 border-b border-white/5">
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                    <span>💡 Mention tickers like <span className="text-cyan-400">$BTC</span></span>
                    <span>•</span>
                    <span>Tag <span className="text-purple-400">@Sapphire</span> for bot response</span>
                    <span>•</span>
                    <span>Earn <span className="text-yellow-400">+50 pts</span> when bots act on your advice!</span>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {loading ? (
                    <div className="flex items-center justify-center h-full text-slate-500">
                        <div className="animate-spin w-6 h-6 border-2 border-cyan-400 border-t-transparent rounded-full" />
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm">
                        <AlertCircle size={32} className="mb-2 text-red-400" />
                        <p className="text-red-400">{error}</p>
                        <button
                            onClick={() => fetchMessages(true)}
                            className="mt-2 text-xs text-cyan-400 hover:underline"
                        >
                            Try again
                        </button>
                    </div>
                ) : messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-slate-500 text-sm">
                        <MessageCircle size={32} className="mb-2 opacity-50" />
                        <p>No messages yet</p>
                        <p className="text-xs text-slate-600">Be the first to share trading insights!</p>
                    </div>
                ) : (
                    messages.map((msg) => (
                        <ChatMessageItem
                            key={msg.id}
                            message={msg}
                            onLike={handleLike}
                            currentUserId={user?.uid}
                        />
                    ))
                )}
                <div ref={messagesEndRef} />
            </div>

            {!authLoading && user ? (
                <div className="p-3 border-t border-white/5 space-y-2">
                    <div className="flex items-center gap-1">
                        <span className="text-[10px] text-slate-600 mr-1">Quick:</span>
                        {QUICK_TICKERS.map(ticker => (
                            <button
                                key={ticker}
                                onClick={() => insertTicker(ticker)}
                                className="px-2 py-0.5 text-[10px] bg-slate-800/50 text-cyan-400 rounded hover:bg-cyan-500/20 transition-colors"
                            >
                                {ticker}
                            </button>
                        ))}
                        <button
                            onClick={() => insertTicker('@Sapphire')}
                            className="px-2 py-0.5 text-[10px] bg-slate-800/50 text-purple-400 rounded hover:bg-purple-500/20 transition-colors"
                        >
                            @Sapphire
                        </button>
                    </div>

                    <div className="flex items-center gap-2">
                        <input
                            ref={inputRef}
                            type="text"
                            value={newMessage}
                            onChange={(e) => setNewMessage(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Share your trading insights..."
                            className="flex-1 bg-slate-800/50 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 focus:ring-1 focus:ring-cyan-500/20"
                            maxLength={500}
                            disabled={sending}
                        />
                        <button
                            onClick={handleSend}
                            disabled={!newMessage.trim() || sending}
                            className="p-2.5 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed transition-all flex items-center gap-1"
                        >
                            {sending ? (
                                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                            ) : (
                                <Send size={16} />
                            )}
                        </button>
                    </div>

                    <div className="flex items-center justify-between text-[10px] text-slate-600">
                        <span>{newMessage.length}/500</span>
                        <span>Press Enter or click Send</span>
                    </div>
                </div>
            ) : !authLoading ? (
                <div className="p-4 border-t border-white/5 bg-slate-800/30">
                    <div className="flex flex-col items-center gap-2 text-sm text-slate-400">
                        <Lock size={20} className="text-slate-500" />
                        <span>Sign in to participate in community chat</span>
                        <a href="/login" className="text-cyan-400 hover:underline text-xs">
                            Sign in →
                        </a>
                    </div>
                </div>
            ) : null}

            {showUsernameModal && (
                <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                    <div className="bg-slate-900 border border-white/10 rounded-xl p-6 max-w-sm w-full mx-4 shadow-2xl">
                        <h3 className="text-lg font-bold text-white mb-2">Choose Your Username</h3>
                        <p className="text-sm text-slate-400 mb-4">
                            Pick a unique username to identify yourself in the community.
                        </p>
                        <input
                            type="text"
                            value={usernameInput}
                            onChange={(e) => setUsernameInput(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                            placeholder="username"
                            className="w-full bg-slate-800/50 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50 mb-2"
                            maxLength={20}
                        />
                        {usernameError && (
                            <p className="text-xs text-red-400 mb-2">{usernameError}</p>
                        )}
                        <p className="text-[10px] text-slate-600 mb-4">
                            3-20 characters, letters, numbers, and underscores only
                        </p>
                        <div className="flex gap-2">
                            <button
                                onClick={() => setShowUsernameModal(false)}
                                className="flex-1 px-4 py-2 bg-slate-800 text-slate-400 rounded-lg hover:bg-slate-700 transition-all"
                            >
                                Skip
                            </button>
                            <button
                                onClick={handleSetUsername}
                                disabled={usernameInput.length < 3}
                                className="flex-1 px-4 py-2 bg-cyan-500 text-white rounded-lg hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                            >
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default memo(LiveChatPanel);
