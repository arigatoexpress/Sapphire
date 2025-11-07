import React from 'react';

const ArchitectureInfo: React.FC = () => {
  return (
    <section className="relative mb-10 overflow-hidden rounded-3xl border border-sapphire-600/40 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-8 shadow-[0_0_80px_rgba(56,189,248,0.14)]">
      <div className="pointer-events-none absolute inset-0 opacity-60">
        <div className="absolute -top-32 left-1/2 h-80 w-80 -translate-x-1/2 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute -bottom-32 right-12 h-72 w-72 rounded-full bg-purple-500/20 blur-3xl" />
        <div className="absolute left-12 top-20 h-40 w-40 rounded-full bg-emerald-400/20 blur-2xl" />
      </div>

      <div className="relative mx-auto max-w-5xl space-y-5 text-center">
        <span className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 py-1 text-[0.7rem] font-semibold uppercase tracking-[0.35em] text-slate-100">
          Built end-to-end by a single founder
        </span>
        <h2 className="text-3xl font-extrabold leading-tight text-white sm:text-5xl">
          Sapphire Trade: A Solo-Built, Competition-Ready AI Trading Platform
        </h2>
        <p className="mx-auto max-w-3xl text-base text-slate-300/95 sm:text-lg">
          I engineered every layer—from low-latency execution bots to the GCP control plane—to prove that a focused, one-person team can ship faster, safer, and smarter than much larger shops. This entry delivers an institutional-grade experience that is ready to win the demo day stage right now.
        </p>
      </div>

      <div className="relative mt-10 grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-black/40 p-6 backdrop-blur-sm">
          <h3 className="text-xl font-semibold text-cyan-200">What Makes Sapphire Unique</h3>
          <ul className="mt-4 space-y-3 text-sm text-slate-200">
            <li className="flex items-start gap-3">
              <span className="mt-1 h-2 w-2 rounded-full bg-cyan-400" />
              Institutional-grade risk choreography with millisecond, multi-agent consensus while still moving at solo-founder speed.
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-1 h-2 w-2 rounded-full bg-emerald-400" />
              GCP-native observability, Pub/Sub telemetry, and automated guardrails tuned for live capital—all built and iterated by one set of hands.
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-1 h-2 w-2 rounded-full bg-purple-400" />
              End-to-end automation: bots deploy themselves, dashboards stream real-time market data, stakeholders get instant Telegram intelligence.
            </li>
            <li className="flex items-start gap-3">
              <span className="mt-1 h-2 w-2 rounded-full bg-amber-400" />
              Every iteration ships overnight—no handoffs, no bureaucracy, just execution.
            </li>
          </ul>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/40 p-6 backdrop-blur-sm">
          <h3 className="text-xl font-semibold text-emerald-200">Production Architecture</h3>
          <ul className="mt-4 space-y-3 text-sm text-slate-200">
            <li>
              <span className="font-semibold text-emerald-300">Cloud Run & Compute Engine:</span> low-latency traders with autoscale plus a dedicated VM for deterministic execution and hardware customization.
            </li>
            <li>
              <span className="font-semibold text-emerald-300">Pub/Sub Nervous System:</span> decision, reasoning, and portfolio channels keep every agent in sync without tight coupling.
            </li>
            <li>
              <span className="font-semibold text-emerald-300">Vertex AI & TPU-Ready Models:</span> DeepSeek, Qwen, and Phi-3 ensembles orchestrated through Vertex pipelines and ready to fan out on TPUs.
            </li>
            <li>
              <span className="font-semibold text-emerald-300">Terraform IaC:</span> reproducible VPC, NAT, Memorystore, secrets, and CI/CD pipelines tracked in git for instant rebuilds.
            </li>
          </ul>
        </div>

        <div className="rounded-2xl border border-white/10 bg-black/40 p-6 backdrop-blur-sm">
          <h3 className="text-xl font-semibold text-purple-200">2025-2026 Solo Roadmap</h3>
          <ul className="mt-4 space-y-3 text-sm text-slate-200">
            <li>
              <span className="font-semibold text-purple-300">Q4 · Competition Launch:</span> ✅ live trading, public dashboard, community features, Telegram notifications, token utility roadmap.
            </li>
            <li>
              <span className="font-semibold text-purple-300">Q1 · Vault Strategies:</span> auto-balancing thematic trading vaults with hidden positions and emergency circuit breakers.
            </li>
            <li>
              <span className="font-semibold text-purple-300">Q2 · Social & Multi-Chain:</span> strategy marketplace, promptable AI copilots, x402 micropayments, cross-chain execution.
            </li>
            <li>
              <span className="font-semibold text-purple-300">Q3 · Privacy Coin Integration:</span> shielded execution, Sui ecosystem hooks, community-led token development.
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
};

export default ArchitectureInfo;
