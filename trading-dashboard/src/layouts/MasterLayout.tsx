import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Zap, LayoutDashboard, Terminal, LogOut, User as UserIcon, Sparkles } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

interface MasterLayoutProps {
    children: React.ReactNode;
}

export const MasterLayout: React.FC<MasterLayoutProps> = ({ children }) => {
    const location = useLocation();
    const { user, logout } = useAuth();

    const isActive = (path: string) => location.pathname === path;

    return (
        <div className="min-h-screen bg-[#050508] text-white font-sans">
            {/* Background gradient */}
            <div className="fixed inset-0 z-0 pointer-events-none">
                <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-blue-900/15 via-[#050508] to-[#050508]" />
            </div>

            {/* Navigation Header */}
            <header className="relative z-20 border-b border-white/10 bg-[#050508]/80 backdrop-blur-xl">
                <div className="max-w-[1800px] mx-auto px-6 lg:px-8 py-3">
                    <nav className="flex items-center justify-between">
                        {/* Logo */}
                        <Link to="/" className="flex items-center gap-2 text-xl font-bold">
                            <Zap className="w-6 h-6 text-cyan-400" />
                            <span className="bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                                Sapphire AI
                            </span>
                        </Link>

                        {/* Navigation Links */}
                        <div className="flex items-center gap-1">
                            <Link
                                to="/"
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/')
                                    ? 'bg-cyan-500/20 text-cyan-400'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <LayoutDashboard className="w-4 h-4" />
                                Dashboard
                            </Link>
                            <Link
                                to="/terminal"
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/terminal')
                                    ? 'bg-cyan-500/20 text-cyan-400'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <Terminal className="w-4 h-4" />
                                Terminal Pro
                            </Link>
                            <Link
                                to="/mit"
                                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${isActive('/mit')
                                    ? 'bg-purple-500/20 text-purple-400'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <Sparkles className="w-4 h-4" />
                                MIT
                            </Link>
                        </div>

                        {/* User Profile / Logout */}
                        <div className="flex items-center gap-4">
                            {user && (
                                <div className="flex items-center gap-3 pl-4 border-l border-white/10">
                                    <div className="flex flex-col items-end hidden sm:flex">
                                        <span className="text-xs font-medium text-slate-300">
                                            {user.email?.split('@')[0]}
                                        </span>
                                        <span className="text-[10px] text-slate-500 line-clamp-1 max-w-[120px]">
                                            {user.email}
                                        </span>
                                    </div>
                                    <div className="w-8 h-8 rounded-full bg-slate-800 border border-white/10 flex items-center justify-center text-cyan-400">
                                        <UserIcon size={16} />
                                    </div>
                                    <button
                                        onClick={() => logout()}
                                        className="p-2 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all"
                                        title="Logout"
                                    >
                                        <LogOut size={18} />
                                    </button>
                                </div>
                            )}
                        </div>
                    </nav>
                </div>
            </header>

            {/* Main Content - Full width, clean layout */}
            <main className="relative z-10 min-h-screen">
                <div className="max-w-[1800px] mx-auto p-6 lg:p-8">
                    {children}
                </div>
            </main>
        </div>
    );
};
