import React from 'react';
import AuroraField from './visuals/AuroraField';

interface LandingPageProps {
  onEnterApp: () => void;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnterApp }) => {
  return (
    <div className="min-h-screen bg-gray-900 text-white relative overflow-hidden">
      {/* Aurora Background Effects */}
      <AuroraField className="-left-72 top-[-14rem] h-[620px] w-[620px]" variant="sapphire" intensity="bold" />
      <AuroraField className="right-[-12rem] bottom-[-10rem] h-[540px] w-[540px]" variant="emerald" intensity="soft" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.22),_transparent_65%)]" />

      {/* Main Content */}
      <div className="relative z-10">
        {/* Hero Section */}
        <section className="px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="text-center">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.35em] text-slate-100 mb-8">
                Competition-Ready AI Trading
              </span>

              <h1 className="text-5xl sm:text-7xl lg:text-8xl font-black leading-tight text-white mb-6">
                Sapphire Trade
                <span className="block text-4xl sm:text-5xl lg:text-6xl font-bold text-accent-ai mt-2">
                  Solo-Built Excellence
                </span>
              </h1>

              <p className="mx-auto max-w-3xl text-lg sm:text-xl leading-relaxed text-slate-300/90 mb-12">
                I engineered every layer—from low-latency execution bots to the GCP control plane—to prove that a focused, one-person team can ship faster, safer, and smarter than much larger shops. This entry delivers an institutional-grade experience that is ready to win the demo day stage right now.
              </p>

              <button
                onClick={onEnterApp}
                className="group relative inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-accent-ai via-accent-aurora to-emerald-400 px-8 py-4 text-lg font-bold text-white shadow-2xl shadow-accent-ai/25 transition-all duration-300 hover:scale-105 hover:shadow-accent-ai/40"
              >
                <span>Enter Trading Control</span>
                <svg className="h-5 w-5 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
            </div>
          </div>
        </section>

        {/* What Makes Sapphire Unique */}
        <section className="px-6 py-20 lg:px-8 bg-white/5 backdrop-blur-sm">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="text-4xl sm:text-5xl font-bold text-white mb-6">
                What Makes Sapphire <span className="text-accent-ai">Unique</span>
              </h2>
              <p className="mx-auto max-w-2xl text-lg text-slate-300">
                Built by one person, designed for institutions
              </p>
            </div>

            <div className="grid gap-8 md:grid-cols-2 lg:grid-cols-4">
              <div className="group relative overflow-hidden rounded-3xl border border-accent-ai/30 bg-surface-75/70 p-8 shadow-glass-xl transition-all duration-300 hover:scale-105 hover:shadow-accent-ai/20">
                <div className="absolute inset-0 bg-gradient-to-br from-accent-ai/10 via-transparent to-accent-ai/5" />
                <div className="relative">
                  <div className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-accent-ai/20 text-3xl">
                    ⚡
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Solo Speed</h3>
                  <p className="text-slate-300 leading-relaxed">
                    Every iteration ships overnight—no handoffs, no bureaucracy, just execution. Built and iterated by one set of hands.
                  </p>
                </div>
              </div>

              <div className="group relative overflow-hidden rounded-3xl border border-emerald-400/30 bg-surface-75/70 p-8 shadow-glass-xl transition-all duration-300 hover:scale-105 hover:shadow-emerald-400/20">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-400/10 via-transparent to-emerald-400/5" />
                <div className="relative">
                  <div className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-400/20 text-3xl">
                    🛡️
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Institutional Risk</h3>
                  <p className="text-slate-300 leading-relaxed">
                    Kelly-guided sizing, emergency circuit breakers, and multi-agent consensus with millisecond precision.
                  </p>
                </div>
              </div>

              <div className="group relative overflow-hidden rounded-3xl border border-sapphire-400/30 bg-surface-75/70 p-8 shadow-glass-xl transition-all duration-300 hover:scale-105 hover:shadow-sapphire-400/20">
                <div className="absolute inset-0 bg-gradient-to-br from-sapphire-400/10 via-transparent to-sapphire-400/5" />
                <div className="relative">
                  <div className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-sapphire-400/20 text-3xl">
                    🤖
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">AI Ensemble</h3>
                  <p className="text-slate-300 leading-relaxed">
                    DeepSeek, Qwen, and Phi-3 agents negotiate every trade. MCP orchestrates consensus before execution.
                  </p>
                </div>
              </div>

              <div className="group relative overflow-hidden rounded-3xl border border-purple-400/30 bg-surface-75/70 p-8 shadow-glass-xl transition-all duration-300 hover:scale-105 hover:shadow-purple-400/20">
                <div className="absolute inset-0 bg-gradient-to-br from-purple-400/10 via-transparent to-purple-400/5" />
                <div className="relative">
                  <div className="mb-6 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-400/20 text-3xl">
                    📡
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Live Telemetry</h3>
                  <p className="text-slate-300 leading-relaxed">
                    Pub/Sub streams, Prometheus metrics, and instant Telegram notifications keep stakeholders informed.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Production Architecture */}
        <section className="px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="text-4xl sm:text-5xl font-bold text-white mb-6">
                Production <span className="text-accent-aurora">Architecture</span>
              </h2>
              <p className="mx-auto max-w-2xl text-lg text-slate-300">
                GCP-native infrastructure designed for reliability and scale
              </p>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-surface-75/70 p-8 shadow-glass-xl">
                <div className="absolute inset-0 bg-gradient-to-br from-accent-ai/5 via-transparent to-accent-ai/10" />
                <div className="relative">
                  <div className="mb-6 flex items-center gap-4">
                    <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-accent-ai/20 text-2xl">
                      ☁️
                    </div>
                    <h3 className="text-2xl font-bold text-white">Cloud Native Core</h3>
                  </div>
                  <ul className="space-y-3 text-slate-300">
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-accent-ai flex-shrink-0" />
                      <span>Cloud Run & Compute Engine with autoscale and custom hardware</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-accent-ai flex-shrink-0" />
                      <span>Pub/Sub nervous system for agent coordination</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-accent-ai flex-shrink-0" />
                      <span>Vertex AI pipelines with TPU-ready model serving</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-accent-ai flex-shrink-0" />
                      <span>Terraform IaC for reproducible deployments</span>
                    </li>
                  </ul>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-surface-75/70 p-8 shadow-glass-xl">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-400/5 via-transparent to-emerald-400/10" />
                <div className="relative">
                  <div className="mb-6 flex items-center gap-4">
                    <div className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-400/20 text-2xl">
                      🎯
                    </div>
                    <h3 className="text-2xl font-bold text-white">Competition Edge</h3>
                  </div>
                  <ul className="space-y-3 text-slate-300">
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span>Real DEX trades with live capital deployment</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span>Multi-agent consensus with DeepSeek/Qwen/Phi-3</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span>Enterprise observability and security posture</span>
                    </li>
                    <li className="flex items-start gap-3">
                      <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400 flex-shrink-0" />
                      <span>Built solo, ships faster than team efforts</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 2025 Solo Roadmap */}
        <section className="px-6 py-20 lg:px-8 bg-white/5 backdrop-blur-sm">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-16">
              <h2 className="text-4xl sm:text-5xl font-bold text-white mb-6">
                2025 <span className="text-accent-ai">Solo Roadmap</span>
              </h2>
              <p className="mx-auto max-w-2xl text-lg text-slate-300">
                From competition launch to multi-chain expansion
              </p>
            </div>

            <div className="grid gap-6 md:grid-cols-3">
              <div className="relative overflow-hidden rounded-3xl border border-accent-ai/30 bg-surface-75/70 p-8 shadow-glass-xl">
                <div className="absolute inset-0 bg-gradient-to-br from-accent-ai/10 via-transparent to-accent-ai/5" />
                <div className="relative">
                  <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-accent-ai/40 bg-accent-ai/10 px-3 py-1 text-sm font-semibold text-accent-ai">
                    Q4 2025
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Competition Launch</h3>
                  <ul className="space-y-2 text-sm text-slate-300">
                    <li>• Public dashboards with real-time data</li>
                    <li>• Follower access and community engagement</li>
                    <li>• Nightly performance recaps via Telegram</li>
                    <li>• Showcase live trading edge</li>
                  </ul>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl border border-emerald-400/30 bg-surface-75/70 p-8 shadow-glass-xl">
                <div className="absolute inset-0 bg-gradient-to-br from-emerald-400/10 via-transparent to-emerald-400/5" />
                <div className="relative">
                  <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-3 py-1 text-sm font-semibold text-emerald-200">
                    Q1 2026
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Vault Strategies</h3>
                  <ul className="space-y-2 text-sm text-slate-300">
                    <li>• Auto-balancing thematic trading vaults</li>
                    <li>• Transparent risk bands and drawdown limits</li>
                    <li>• Emergency circuit breakers for all positions</li>
                    <li>• Institutional-grade risk management</li>
                  </ul>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-3xl border border-sapphire-400/30 bg-surface-75/70 p-8 shadow-glass-xl">
                <div className="absolute inset-0 bg-gradient-to-br from-sapphire-400/10 via-transparent to-sapphire-400/5" />
                <div className="relative">
                  <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-sapphire-400/40 bg-sapphire-400/10 px-3 py-1 text-sm font-semibold text-sapphire-200">
                    Q2-Q3 2026
                  </div>
                  <h3 className="mb-4 text-xl font-bold text-white">Social & Multi-Chain</h3>
                  <ul className="space-y-2 text-sm text-slate-300">
                    <li>• Strategy marketplace for trader collaboration</li>
                    <li>• Promptable AI copilots for followers</li>
                    <li>• Incentive systems and performance streaks</li>
                    <li>• Multi-chain deployment (Solana, Base)</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="px-6 py-20 lg:px-8">
          <div className="mx-auto max-w-4xl text-center">
            <h2 className="text-4xl sm:text-5xl font-bold text-white mb-6">
              Ready to Experience <span className="text-accent-ai">Sapphire</span>?
            </h2>
            <p className="text-lg text-slate-300 mb-12">
              Enter the control nexus and see institutional-grade AI trading built by one person.
            </p>

            <button
              onClick={onEnterApp}
              className="group relative inline-flex items-center gap-3 rounded-2xl bg-gradient-to-r from-accent-ai via-accent-aurora to-emerald-400 px-10 py-5 text-xl font-bold text-white shadow-2xl shadow-accent-ai/25 transition-all duration-300 hover:scale-105 hover:shadow-accent-ai/40"
            >
              <span>Launch Trading Dashboard</span>
              <svg className="h-6 w-6 transition-transform group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>

            <div className="mt-8 text-sm text-slate-400">
              <p>Built solo • Competition-ready • Live trading capable</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default LandingPage;
