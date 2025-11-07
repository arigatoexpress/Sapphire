import React from 'react';
import AuroraField from './visuals/AuroraField';

interface LandingPageProps {
  onEnterApp: () => void;
}

const LandingPage: React.FC<LandingPageProps> = ({ onEnterApp }) => {
  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-midnight via-brand-abyss to-brand-midnight text-brand-ice relative overflow-hidden">
      {/* Enhanced Aurora Background Effects */}
      <AuroraField className="-left-72 top-[-14rem] h-[800px] w-[800px]" variant="sapphire" intensity="bold" />
      <AuroraField className="right-[-12rem] bottom-[-10rem] h-[700px] w-[700px]" variant="emerald" intensity="soft" />
      <AuroraField className="left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px]" variant="amber" intensity="soft" />
      <div className="absolute inset-0 bg-sapphire-mesh opacity-60" />

      {/* Floating Elements */}
      <div className="absolute top-20 left-20 animate-pulse">
        <div className="h-4 w-4 bg-accent-sapphire rounded-full opacity-60"></div>
      </div>
      <div className="absolute top-40 right-32 animate-pulse delay-1000">
        <div className="h-6 w-6 bg-accent-emerald rounded-full opacity-40"></div>
      </div>
      <div className="absolute bottom-32 left-16 animate-pulse delay-2000">
        <div className="h-3 w-3 bg-accent-aurora rounded-full opacity-50"></div>
      </div>

      {/* Main Content */}
      <div className="relative z-10">
        {/* Hero Section */}
        <section className="px-6 py-32 lg:px-8 min-h-screen flex items-center">
          <div className="mx-auto max-w-7xl text-center">
            {/* Status Badge */}
            <div className="mb-12 flex items-center justify-center">
              <span className="inline-flex items-center gap-3 rounded-full border border-accent-sapphire/60 bg-brand-abyss/80 backdrop-blur-sm px-6 py-3 text-sm font-bold uppercase tracking-[0.2em] text-accent-sapphire shadow-lg">
                <div className="h-2 w-2 bg-accent-sapphire rounded-full animate-pulse"></div>
                LIVE TRADING ACTIVE
              </span>
            </div>

            {/* Main Headline */}
            <h1 className="text-6xl sm:text-8xl lg:text-9xl xl:text-[12rem] font-black leading-none text-transparent bg-clip-text bg-gradient-to-r from-brand-ice via-accent-sapphire to-accent-aurora mb-8 animate-fade-in">
              SAPPHIRE
            </h1>

            <h2 className="text-3xl sm:text-5xl lg:text-7xl font-bold text-brand-ice mb-12">
              AI Trading Intelligence
            </h2>

            {/* Key Stats */}
            <div className="grid grid-cols-3 gap-8 max-w-2xl mx-auto mb-16">
              <div className="text-center">
                <div className="text-4xl sm:text-6xl font-black text-accent-emerald mb-2">$247K+</div>
                <div className="text-sm uppercase tracking-wider text-brand-ice/70">Portfolio Value</div>
              </div>
              <div className="text-center">
                <div className="text-4xl sm:text-6xl font-black text-accent-sapphire mb-2">4</div>
                <div className="text-sm uppercase tracking-wider text-brand-ice/70">AI Agents</div>
              </div>
              <div className="text-center">
                <div className="text-4xl sm:text-6xl font-black text-accent-aurora mb-2">24/7</div>
                <div className="text-sm uppercase tracking-wider text-brand-ice/70">Trading</div>
              </div>
            </div>

            {/* CTA Button */}
            <div className="mb-16">
              <button
                onClick={onEnterApp}
                className="group relative inline-flex items-center gap-4 rounded-3xl bg-gradient-to-r from-accent-sapphire via-accent-emerald to-accent-aurora px-12 py-6 text-2xl font-black text-brand-midnight shadow-2xl shadow-sapphire/50 transition-all duration-300 hover:scale-110 hover:shadow-sapphire/70 hover:rotate-1"
              >
                <span>ENTER DASHBOARD</span>
                <svg className="h-8 w-8 transition-transform group-hover:translate-x-2 group-hover:scale-110" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </button>
            </div>

            {/* Social Proof */}
            <div className="flex items-center justify-center gap-8 text-brand-ice/60">
              <a
                href="https://twitter.com/rari_sui"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 hover:text-accent-sapphire transition-colors duration-300"
              >
                <span className="text-2xl">🐦</span>
                <span className="font-semibold">@rari_sui</span>
              </a>
              <div className="h-6 border-l border-brand-ice/30"></div>
              <span className="text-sm font-medium">Solo-Built • Competition-Ready • Live Trading</span>
            </div>
          </div>
        </section>

        {/* Features Section - Big Visual Cards */}
        <section className="px-6 py-32 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <div className="text-center mb-20">
              <h2 className="text-5xl sm:text-7xl font-black text-brand-ice mb-6">
                POWERFUL <span className="text-accent-sapphire">FEATURES</span>
              </h2>
            </div>

            <div className="grid gap-12 md:grid-cols-2">
              {/* AI Agents Card */}
              <div className="group relative overflow-hidden rounded-3xl bg-gradient-to-br from-accent-sapphire/20 to-accent-sapphire/5 border border-accent-sapphire/30 p-12 shadow-2xl transition-all duration-500 hover:scale-105 hover:shadow-accent-sapphire/20">
                <div className="absolute inset-0 bg-accent-sapphire/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <div className="relative">
                  <div className="text-center mb-8">
                    <div className="inline-flex h-24 w-24 items-center justify-center rounded-3xl bg-accent-sapphire/30 text-6xl mb-6">
                      🤖
                    </div>
                    <h3 className="text-4xl font-black text-brand-ice mb-4">4 AI AGENTS</h3>
                    <p className="text-xl text-brand-ice/80">DeepSeek • Qwen • FinGPT • Lag-Llama</p>
                  </div>
                  <div className="text-center">
                    <div className="inline-block rounded-2xl bg-accent-sapphire/20 px-6 py-3">
                      <span className="text-2xl font-bold text-accent-sapphire">SWARM INTELLIGENCE</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Risk Management Card */}
              <div className="group relative overflow-hidden rounded-3xl bg-gradient-to-br from-accent-emerald/20 to-accent-emerald/5 border border-accent-emerald/30 p-12 shadow-2xl transition-all duration-500 hover:scale-105 hover:shadow-accent-emerald/20">
                <div className="absolute inset-0 bg-accent-emerald/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <div className="relative">
                  <div className="text-center mb-8">
                    <div className="inline-flex h-24 w-24 items-center justify-center rounded-3xl bg-accent-emerald/30 text-6xl mb-6">
                      🛡️
                    </div>
                    <h3 className="text-4xl font-black text-brand-ice mb-4">RISK CONTROL</h3>
                    <p className="text-xl text-brand-ice/80">Circuit Breakers • Kelly Criterion • Stop Losses</p>
                  </div>
                  <div className="text-center">
                    <div className="inline-block rounded-2xl bg-accent-emerald/20 px-6 py-3">
                      <span className="text-2xl font-bold text-accent-emerald">ENTERPRISE GRADE</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Live Trading Card */}
              <div className="group relative overflow-hidden rounded-3xl bg-gradient-to-br from-accent-aurora/20 to-accent-aurora/5 border border-accent-aurora/30 p-12 shadow-2xl transition-all duration-500 hover:scale-105 hover:shadow-accent-aurora/20">
                <div className="absolute inset-0 bg-accent-aurora/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <div className="relative">
                  <div className="text-center mb-8">
                    <div className="inline-flex h-24 w-24 items-center justify-center rounded-3xl bg-accent-aurora/30 text-6xl mb-6">
                      📈
                    </div>
                    <h3 className="text-4xl font-black text-brand-ice mb-4">LIVE TRADING</h3>
                    <p className="text-xl text-brand-ice/80">Real Capital • Aster DEX • 24/7 Operation</p>
                  </div>
                  <div className="text-center">
                    <div className="inline-block rounded-2xl bg-accent-aurora/20 px-6 py-3">
                      <span className="text-2xl font-bold text-accent-aurora">$247K+ PORTFOLIO</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* GCP Infrastructure Card */}
              <div className="group relative overflow-hidden rounded-3xl bg-gradient-to-br from-purple-500/20 to-purple-500/5 border border-purple-500/30 p-12 shadow-2xl transition-all duration-500 hover:scale-105 hover:shadow-purple-500/20">
                <div className="absolute inset-0 bg-purple-500/5 opacity-0 group-hover:opacity-100 transition-opacity duration-500"></div>
                <div className="relative">
                  <div className="text-center mb-8">
                    <div className="inline-flex h-24 w-24 items-center justify-center rounded-3xl bg-purple-500/30 text-6xl mb-6">
                      ☁️
                    </div>
                    <h3 className="text-4xl font-black text-brand-ice mb-4">GCP NATIVE</h3>
                    <p className="text-xl text-brand-ice/80">Cloud Run • Vertex AI • Pub/Sub • Terraform</p>
                  </div>
                  <div className="text-center">
                    <div className="inline-block rounded-2xl bg-purple-500/20 px-6 py-3">
                      <span className="text-2xl font-bold text-purple-300">ENTERPRISE INFRA</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Call to Action */}
        <section className="px-6 py-32 lg:px-8">
          <div className="mx-auto max-w-5xl text-center">
            <h2 className="text-5xl sm:text-7xl font-black text-brand-ice mb-8">
              READY TO <span className="text-accent-sapphire">TRADE</span>?
            </h2>
            <p className="text-2xl text-brand-ice/70 mb-16 max-w-3xl mx-auto">
              Experience institutional-grade AI trading with real-time performance monitoring
            </p>

            <button
              onClick={onEnterApp}
              className="group relative inline-flex items-center gap-6 rounded-3xl bg-gradient-to-r from-accent-sapphire via-accent-emerald to-accent-aurora px-16 py-8 text-3xl font-black text-brand-midnight shadow-2xl shadow-sapphire/50 transition-all duration-300 hover:scale-110 hover:shadow-sapphire/70"
            >
              <span>LAUNCH DASHBOARD</span>
              <svg className="h-10 w-10 transition-transform group-hover:translate-x-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </button>

            <div className="mt-12 flex items-center justify-center gap-8 text-brand-ice/50">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 bg-accent-sapphire rounded-full animate-pulse"></div>
                <span className="text-sm font-medium">LIVE TRADING</span>
              </div>
              <div className="h-6 border-l border-brand-ice/30"></div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 bg-accent-emerald rounded-full animate-pulse delay-1000"></div>
                <span className="text-sm font-medium">REAL CAPITAL</span>
              </div>
              <div className="h-6 border-l border-brand-ice/30"></div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 bg-accent-aurora rounded-full animate-pulse delay-2000"></div>
                <span className="text-sm font-medium">24/7 OPERATION</span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default LandingPage;
