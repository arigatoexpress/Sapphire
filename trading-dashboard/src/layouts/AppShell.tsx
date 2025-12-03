import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Activity,
  MessageSquare,
  TrendingUp,
  Menu,
  X,
  Bell,
  Settings,
  Zap,
  BarChart3,
  Briefcase,
  Target,
  Info,
  Network,
  Terminal
} from 'lucide-react';
import { format } from 'date-fns';

interface AppShellProps {
  children: React.ReactNode;
  connectionStatus: 'connected' | 'disconnected' | 'connecting';
}

export const AppShell: React.FC<AppShellProps> = ({ children, connectionStatus }) => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const location = useLocation();

  const statusColor = {
    connected: 'bg-emerald-500',
    disconnected: 'bg-rose-500',
    connecting: 'bg-amber-500'
  }[connectionStatus];

  const statusText = {
    connected: 'System Online',
    disconnected: 'Offline',
    connecting: 'Connecting...'
  }[connectionStatus];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-100 font-sans relative overflow-hidden">
      {/* Ultra-Modern Background Effects - Quantum Field */}
      <div className="fixed inset-0 z-0 pointer-events-none">
        {/* Primary gradient layers */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-blue-950/20 to-slate-950"></div>

        {/* Animated particle field */}
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-gradient-to-br from-blue-500/8 via-purple-500/6 to-cyan-500/4 rounded-full blur-[140px] animate-pulse duration-4000"></div>
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-gradient-to-br from-purple-500/6 via-pink-500/4 to-blue-500/6 rounded-full blur-[120px] animate-pulse duration-5000 delay-1000"></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[900px] h-[900px] bg-gradient-to-br from-cyan-500/3 via-transparent to-indigo-500/3 rounded-full blur-[150px] animate-pulse duration-6000 delay-2000"></div>

        {/* Subtle grid overlay */}
        <div className="absolute inset-0 opacity-[0.02]"
             style={{
               backgroundImage: `
                 linear-gradient(rgba(59, 130, 246, 0.1) 1px, transparent 1px),
                 linear-gradient(90deg, rgba(59, 130, 246, 0.1) 1px, transparent 1px)
               `,
               backgroundSize: '60px 60px'
             }}>
        </div>

        {/* Floating geometric shapes */}
        <div className="absolute top-20 left-20 w-2 h-2 bg-blue-400/30 rounded-full animate-bounce duration-3000"></div>
        <div className="absolute top-40 right-32 w-1 h-1 bg-purple-400/40 rounded-full animate-ping duration-4000 delay-1000"></div>
        <div className="absolute bottom-32 left-1/3 w-1.5 h-1.5 bg-cyan-400/25 rounded-full animate-pulse duration-5000 delay-2000"></div>
      </div>

      {/* Ultra-Premium Navigation Bar - Glassmorphism Masterpiece */}
      <header className="sticky top-0 z-50 backdrop-blur-2xl bg-slate-950/80 border-b border-slate-700/50 shadow-2xl shadow-slate-900/20">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-900/10 via-transparent to-purple-900/10 pointer-events-none"></div>
        <div className="relative flex h-20 items-center justify-between px-6 lg:px-8">
          <div className="flex items-center gap-8">
            {/* Premium Mobile Menu Button */}
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="lg:hidden relative group p-3 text-slate-400 hover:text-white transition-all duration-300 active:scale-95"
              aria-label="Toggle Menu"
            >
              <div className="absolute inset-0 bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
              <div className="relative z-10">
                {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
              </div>
            </button>

            {/* Ultra-Premium Brand Identity */}
            <Link to="/" className="flex items-center gap-5 group">
              <div className="relative">
                {/* Multi-layer glow effects */}
                <div className="absolute -inset-3 bg-gradient-to-r from-blue-600/20 via-purple-600/30 to-cyan-600/20 rounded-2xl blur-xl opacity-0 group-hover:opacity-100 transition-all duration-500"></div>
                <div className="absolute -inset-2 bg-gradient-to-br from-blue-500/40 to-purple-500/40 rounded-xl blur-lg group-hover:blur-xl transition-all duration-300"></div>
                <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-800/90 border border-slate-600/50 shadow-2xl group-hover:shadow-blue-500/20 group-hover:scale-105 transition-all duration-300 backdrop-blur-sm">
                  <span className="text-3xl filter drop-shadow-2xl animate-pulse">💎</span>
                  {/* Inner glow */}
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-blue-400/10 to-purple-400/10 animate-pulse duration-2000"></div>
                </div>
              </div>

              <div className="hidden sm:block">
                <h1 className="text-3xl font-black tracking-tight bg-gradient-to-r from-white via-blue-100 to-purple-200 bg-clip-text text-transparent group-hover:from-blue-200 group-hover:via-purple-200 group-hover:to-pink-200 transition-all duration-300">
                  Sapphire
                  <span className="text-transparent bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text ml-2">Trade</span>
                </h1>
                <p className="text-xs font-semibold text-slate-400 tracking-[0.2em] uppercase mt-1 group-hover:text-slate-300 transition-colors duration-300">Quantum Intelligence</p>
                {/* Subtle animated underline */}
                <div className="h-0.5 w-0 bg-gradient-to-r from-blue-500 to-purple-500 rounded-full mt-1 group-hover:w-full transition-all duration-500"></div>
              </div>
            </Link>

            {/* Ultra-Modern Desktop Navigation */}
            <nav className="hidden lg:flex items-center gap-1 ml-12">
              <NavLink
                to="/dashboard"
                active={location.pathname === '/dashboard'}
                icon={<LayoutDashboard size={18} />}
                label="Dashboard"
              />
              <NavLink
                to="/agents"
                active={location.pathname === '/agents'}
                icon={<MessageSquare size={18} />}
                label="Agents"
              />
              <NavLink
                to="/analytics"
                active={location.pathname === '/analytics'}
                icon={<BarChart3 size={18} />}
                label="Analytics"
              />
              <NavLink
                to="/portfolio"
                active={location.pathname === '/portfolio'}
                icon={<Briefcase size={18} />}
                label="Portfolio"
              />
              <NavLink
                to="/mission-control"
                active={location.pathname === '/mission-control'}
                icon={<Target size={18} />}
                label="Mission Control"
              />
              <NavLink
                to="/command"
                active={location.pathname === '/command'}
                icon={<Terminal size={18} />}
                label="Command"
              />
              <NavLink
                to="/architecture"
                active={location.pathname === '/architecture'}
                icon={<Network size={18} />}
                label="Architecture"
              />
            </nav>
          </div>

          <div className="flex items-center gap-4">
            {/* Enhanced Status Indicator */}
            <div className="relative group">
              <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-gradient-to-r from-slate-900/80 to-slate-800/80 backdrop-blur-sm border border-slate-700/50 shadow-lg">
                <div className={`relative`}>
                  <span className={`h-3 w-3 rounded-full ${statusColor} animate-pulse shadow-lg`} />
                  <span className={`absolute inset-0 h-3 w-3 rounded-full ${statusColor} animate-ping opacity-75`} />
                </div>
                <span className="text-sm font-semibold text-slate-300 hidden sm:inline-block">
                {statusText}
              </span>
              </div>
              {/* Tooltip */}
              <div className="absolute top-full mt-2 left-1/2 transform -translate-x-1/2 bg-slate-800 text-white text-xs px-3 py-1 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap border border-slate-700">
                System Status: {statusText}
              </div>
            </div>

            {/* Enhanced Notification Bell */}
            <div className="relative group">
              <button className="relative p-3 text-slate-400 hover:text-white transition-all duration-300 rounded-xl hover:bg-slate-800/50 backdrop-blur-sm border border-transparent hover:border-slate-700/50">
              <Bell size={20} />
                <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center shadow-lg shadow-blue-500/25">
                  <span className="text-xs font-bold text-white">3</span>
                </span>
                <span className="absolute inset-0 rounded-xl bg-gradient-to-r from-blue-500/10 to-purple-500/10 opacity-0 group-hover:opacity-100 transition-opacity"></span>
              </button>

              {/* Notification Tooltip */}
              <div className="absolute top-full mt-2 right-0 bg-slate-800 text-white text-xs px-3 py-2 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap border border-slate-700 min-w-[200px]">
                <div className="font-semibold mb-1">Recent Notifications</div>
                <div className="space-y-1 text-slate-300">
                  <div>• Trade executed: BTCUSDT</div>
                  <div>• Agent performance updated</div>
                  <div>• System optimization complete</div>
                </div>
              </div>
            </div>

            {/* Settings Button */}
            <button className="p-3 text-slate-400 hover:text-white transition-all duration-300 rounded-xl hover:bg-slate-800/50 backdrop-blur-sm border border-transparent hover:border-slate-700/50">
              <Settings size={20} />
            </button>
          </div>
        </div>
      </header>

      {/* Full Screen Mobile Menu - Solid & Immersive */}
      {isMobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 z-[100] bg-[#020617] animate-in fade-in duration-200">
          {/* Header Area */}
          <div className="flex items-center justify-between px-4 h-20 border-b border-slate-800/60 bg-[#020617]">
            <div className="flex items-center gap-4">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 border border-slate-700 shadow-lg">
                <span className="text-xl">💎</span>
              </div>
              <div>
                <div className="text-white font-bold text-lg tracking-tight">Sapphire AI</div>
                <div className="text-slate-500 text-[10px] uppercase tracking-widest font-medium">Menu</div>
              </div>
            </div>
            <button
              onClick={() => setIsMobileMenuOpen(false)}
              className="p-2.5 text-slate-400 hover:text-white hover:bg-slate-800/50 rounded-xl transition-all active:scale-95"
            >
              <X size={28} />
            </button>
          </div>

          {/* Menu Content */}
          <div className="p-6 h-[calc(100vh-80px)] overflow-y-auto bg-gradient-to-b from-[#020617] to-[#0f172a]">
            <div className="space-y-3">
              <MobileNavLink
                to="/dashboard"
                active={location.pathname === '/dashboard'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<LayoutDashboard size={24} />}
            label="Dashboard"
                description="Live trading overview & performance"
          />
              <MobileNavLink
                to="/agents"
                active={location.pathname === '/agents'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<MessageSquare size={24} />}
                label="Agents"
                description="Manage & configure AI agents"
              />
              <MobileNavLink
                to="/analytics"
                active={location.pathname === '/analytics'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<BarChart3 size={24} />}
                label="Analytics"
                description="Deep dive into trading metrics"
              />
              <MobileNavLink
                to="/portfolio"
                active={location.pathname === '/portfolio'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<Briefcase size={24} />}
                label="Portfolio"
                description="Asset allocation & balances"
          />
              <MobileNavLink
                to="/mission-control"
                active={location.pathname === '/mission-control'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<Target size={24} />}
                label="Mission Control"
                description="System logs & configuration"
              />
              <MobileNavLink
                to="/command"
                active={location.pathname === '/command'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<Terminal size={24} />}
                label="Command Center"
                description="Live infrastructure telemetry"
              />
              <MobileNavLink
                to="/architecture"
                active={location.pathname === '/architecture'}
                onClick={() => setIsMobileMenuOpen(false)}
                icon={<Network size={24} />}
                label="Architecture"
                description="System diagram & data flow"
              />
            </div>

            <div className="mt-8 pt-8 border-t border-slate-800/60">
              <div className="text-slate-500 text-xs uppercase tracking-wider font-bold mb-4 pl-2">System Status</div>
              <div className="bg-slate-900/50 rounded-2xl border border-slate-800 p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-slate-300 font-medium">Connection</span>
                  <span className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-bold ${statusColor.replace('bg-', 'text-')} bg-slate-950 border border-current`}>
                    <span className={`w-2 h-2 rounded-full ${statusColor}`}></span>
                    {statusText}
                  </span>
                </div>
                <div className="text-xs text-slate-500">
                  Connected to Sapphire Quantum Cloud
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Ultra-Modern Main Content Area */}
      <main className="relative z-10 p-6 lg:p-8 max-w-[1800px] mx-auto">
        <div className="animate-in fade-in duration-700 delay-200">
          {children}
        </div>
      </main>
    </div>
  );
};

const NavLink = ({ to, active, icon, label }: any) => (
  <Link
    to={to}
    className={`relative group flex items-center gap-3 px-5 py-3 rounded-2xl text-sm font-semibold transition-all duration-300 overflow-hidden
      ${active
        ? 'bg-gradient-to-r from-blue-600/20 via-purple-600/15 to-blue-600/20 text-white border border-blue-500/30 shadow-lg shadow-blue-500/10'
        : 'text-slate-400 hover:text-white hover:bg-gradient-to-r hover:from-slate-800/50 hover:to-slate-700/30 border border-transparent hover:border-slate-600/50 hover:shadow-lg hover:shadow-slate-900/20'
      }`}
  >
    {/* Active indicator glow */}
    {active && (
      <div className="absolute inset-0 bg-gradient-to-r from-blue-500/10 via-purple-500/5 to-blue-500/10 animate-pulse"></div>
    )}

    {/* Hover glow effect */}
    <div className={`absolute inset-0 bg-gradient-to-r from-blue-500/5 to-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-300 rounded-2xl`}></div>

    <div className="relative z-10 flex items-center gap-3">
      <div className={`p-1.5 rounded-lg transition-all duration-300 ${
        active
          ? 'bg-blue-500/20 text-blue-400 shadow-lg shadow-blue-500/20'
          : 'bg-slate-700/50 text-slate-400 group-hover:bg-slate-600/70 group-hover:text-slate-300'
      }`}>
        {React.cloneElement(icon, {
          size: 16,
          className: 'transition-colors duration-300'
        })}
      </div>
      <span className="tracking-wide">{label}</span>
    </div>

    {/* Animated border on hover */}
    <div className={`absolute bottom-0 left-0 h-0.5 bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300 ${
      active ? 'w-full' : 'w-0 group-hover:w-full'
    }`}></div>
  </Link>
);

const NavButton = ({ active, onClick, icon, label }: any) => (
  <button
    onClick={onClick}
    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors
      ${active
        ? 'bg-slate-800 text-white'
        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
      }`}
  >
    {icon}
    {label}
  </button>
);

const MobileNavLink = ({ to, active, onClick, icon, label, description }: any) => (
  <Link
    to={to}
    onClick={onClick}
    className={`w-full flex items-start gap-4 p-4 rounded-2xl transition-all duration-300 group border relative overflow-hidden
      ${active
        ? 'bg-gradient-to-r from-blue-900/20 to-indigo-900/20 border-blue-500/30'
        : 'hover:bg-slate-800/30 border-transparent hover:border-slate-700/50'
      }`}
  >
    {active && (
      <div className="absolute inset-0 bg-blue-500/5 animate-pulse"></div>
    )}
    <div className={`p-3 rounded-xl shrink-0 transition-colors duration-300 ${active ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-800/50 text-slate-400 group-hover:text-slate-200 group-hover:bg-slate-700/50'}`}>
      {icon}
    </div>
    <div className="relative z-10">
      <div className={`font-bold text-lg tracking-tight ${active ? 'text-white' : 'text-slate-300 group-hover:text-white'}`}>
        {label}
      </div>
      {description && (
        <div className={`text-sm mt-0.5 leading-relaxed ${active ? 'text-blue-200/60' : 'text-slate-500 group-hover:text-slate-400'}`}>
          {description}
        </div>
      )}
    </div>
  </Link>
);

const MobileNavButton = ({ active, onClick, icon, label }: any) => (
  <button
    onClick={onClick}
    className={`w-full flex items-center gap-3 px-4 py-4 rounded-xl text-base font-medium transition-colors
      ${active
        ? 'bg-slate-800 text-white'
        : 'text-slate-400 hover:bg-slate-900'
      }`}
  >
    {icon}
    {label}
  </button>
);
