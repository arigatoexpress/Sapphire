import React, { useState } from 'react';
import {
    Settings,
    Shield,
    Key,
    Bell,
    Moon,
    Zap,
    Database,
    Cpu,
    ToggleLeft,
    ToggleRight,
    Save,
    Wifi
} from 'lucide-react';
import { useTradingData } from '../contexts/TradingContext';

const ConfigSection: React.FC<{ title: string; icon: React.ReactNode; children: React.ReactNode }> = ({ title, icon, children }) => (
    <div className="bg-[#0a0b10] border border-white/10 rounded-2xl p-6 mb-6 relative overflow-hidden group hover:border-blue-500/30 transition-colors">
        <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 group-hover:text-blue-300 transition-colors">
                {icon}
            </div>
            <h3 className="text-lg font-bold text-white tracking-wide">{title}</h3>
        </div>
        <div className="space-y-4 relative z-10">
            {children}
        </div>
        {/* Glow Effect */}
        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2 pointer-events-none" />
    </div>
);

const SettingRow: React.FC<{ label: string; desc: string; type?: 'toggle' | 'input'; value?: string; active?: boolean }> = ({ label, desc, type = 'toggle', value, active }) => (
    <div className="flex items-center justify-between p-4 rounded-xl bg-white/5 hover:bg-white/10 transition-colors border border-white/5">
        <div>
            <div className={`text - sm font - bold ${active !== undefined ? (active ? 'text-emerald-400' : 'text-rose-400') : 'text-slate-200'} `}>
                {label}
            </div>
            <div className="text-xs text-slate-500 mt-0.5">{desc}</div>
        </div>
        {type === 'toggle' ? (
            <button className={`${(active === true || active === undefined) ? 'text-blue-500 hover:text-blue-400' : 'text-slate-600'} transition - colors`}>
                <ToggleRight size={32} />
            </button>
        ) : (
            <input
                type="text"
                defaultValue={value}
                className="bg-[#0f1016] border border-white/10 rounded px-3 py-1.5 text-sm text-white focus:border-blue-500 focus:outline-none w-64 text-right"
            />
        )}
    </div>
);

export const SystemConfig: React.FC = () => {
    const { connected } = useTradingData();

    return (
        <div className="max-w-5xl mx-auto pb-32">

            <div className="flex items-center justify-between mb-8">
                <div>
                    <h1 className="text-3xl font-black text-white mb-2 flex items-center gap-3">
                        <Settings className="text-slate-400" /> SYSTEM CONFIGURATION
                    </h1>
                    <p className="text-slate-400 font-mono text-sm max-w-2xl flex items-center gap-2">
                        <span className={`w - 2 h - 2 rounded - full ${connected ? 'bg-emerald-500' : 'bg-red-500'} animate - pulse`} />
                        {connected ? 'CORE SYSTEM ONLINE' : 'CONTROL PLANE DISCONNECTED'}
                    </p>
                </div>
                <button className="flex items-center gap-2 px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-bold transition-all shadow-[0_0_20px_rgba(37,99,235,0.3)] hover:shadow-[0_0_30px_rgba(37,99,235,0.5)]">
                    <Save size={18} />
                    SAVE CHANGES
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* 🛡️ RISK MANAGEMENT */}
                <ConfigSection title="Risk Management Protocols" icon={<Shield size={24} />}>
                    <SettingRow label="Max Drawdown Halt" desc="Stop all trading if equity drops by X%" type="input" value="5.0%" />
                    <SettingRow label="Position Sizing Limit" desc="Max capital allocation per agent" type="input" value="$10,000" />
                    <SettingRow label="Kill Switch" desc="Global emergency stop for all agents" type="toggle" />
                </ConfigSection>

                {/* 🔑 API & CREDENTIALS */}
                <ConfigSection title="API Gateways" icon={<Key size={24} />}>
                    <SettingRow label="Coinbase Advanced Trade" desc="API Key ending in ...8x92" type="input" value="••••••••••••••••" />
                    <SettingRow label="OpenAI GPT-4 Turbo" desc="Model integration status" type="toggle" active={true} />
                    <SettingRow label="Vertex AI Prediction" desc={connected ? "Cloud Run endpoint active" : "Connection lost"} type="toggle" active={connected} />
                </ConfigSection>

                {/* 🔔 NOTIFICATIONS */}
                <ConfigSection title="Telemetry Stream" icon={<Bell size={24} />}>
                    <SettingRow label="Telegram Uplink" desc="Send signals to @SapphireAlphaBot" type="toggle" active={true} />
                    <SettingRow label="Critical Alerts" desc="Email admin on system failure" type="toggle" />
                    <SettingRow label="Voice Synthesis" desc="Text-to-Speech for major events" type="toggle" />
                </ConfigSection>

                {/* ⚡ PERFORMANCE */}
                <ConfigSection title="Compute & Latency" icon={<Zap size={24} />}>
                    <SettingRow label="High-Frequency Mode" desc="Poll WebSocket at 10ms intervals" type="toggle" active={connected} />
                    <SettingRow label="Debug Logging" desc="Verbose output to browser console" type="toggle" />
                    <SettingRow label="Cache Persistence" desc="Local storage retention" type="input" value="24 Hours" />
                </ConfigSection>
            </div>
        </div>
    );
}
