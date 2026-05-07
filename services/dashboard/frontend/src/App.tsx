import { useEffect, useMemo, useState } from "react";
import {
  blockedSummary,
  ControlPlaneSummary,
  EnvelopeCard,
  fetchControlPlaneSummary,
} from "./api/controlPlane";

const modules = [
  "Home / Worldline",
  "Operations",
  "Intelligence",
  "Markets",
  "Security",
  "Products / Diligence",
  "Automation",
  "Settings / Contracts",
] as const;

const fallbackModuleContracts = [
  {
    name: "Operations",
    status: "unknown",
    detail: "Org status, readiness, services, worktrees, PR lanes.",
  },
  {
    name: "Markets",
    status: "unknown",
    detail: "Signals, strategy lab, portfolio, forecasts, chain and perps.",
  },
  {
    name: "Security",
    status: "unknown",
    detail: "SOC, dependency, network, model, and credential hygiene.",
  },
  {
    name: "Automation",
    status: "unknown",
    detail: "Task previews, event stream, routine pause, next actions.",
  },
];

function statusLabel(summary: ControlPlaneSummary): string {
  if (summary.generated_at) {
    return `Summary ${summary.status} at ${summary.generated_at}`;
  }
  return "Summary API not wired";
}

function modeLabel(card: EnvelopeCard): string {
  if (card.source.age_seconds === null) {
    return card.mode;
  }
  return `${card.mode} · ${card.source.age_seconds}s old`;
}

function Card({ card }: { card: EnvelopeCard }) {
  return (
    <article className={`card card-${card.status}`}>
      <div className="card-topline">
        <span className="status-dot" aria-hidden="true" />
        <span>{card.module ? `${card.module} · ${modeLabel(card)}` : modeLabel(card)}</span>
      </div>
      <h2>{card.title}</h2>
      <strong>{card.value}</strong>
      <p>{card.summary}</p>
      <footer>
        <span>{card.source.kind}</span>
        <code>{card.source.path_or_url}</code>
      </footer>
    </article>
  );
}

export function App() {
  const [summary, setSummary] = useState<ControlPlaneSummary>({
    status: "unknown",
    generated_at: null,
    cards: [],
  });

  useEffect(() => {
    let mounted = true;
    fetchControlPlaneSummary()
      .then((nextSummary) => {
        if (mounted) {
          setSummary(nextSummary);
        }
      })
      .catch((error: unknown) => {
        if (mounted) {
          setSummary(blockedSummary(error));
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  const visibleCards = useMemo(() => summary.cards, [summary.cards]);
  const moduleRows = useMemo(() => {
    if (summary.modules?.length) {
      return summary.modules.map((module) => ({
        name: module.name,
        status: module.status,
        detail: `${module.summary} ${module.card_count ? "" : "Pending adapter."}`.trim(),
      }));
    }
    return fallbackModuleContracts;
  }, [summary.modules]);

  return (
    <main className="shell">
      <aside className="rail" aria-label="Control plane modules">
        <div className="mark">S</div>
        <nav>
          {modules.map((module) => (
            <a href={`#${module.toLowerCase().replaceAll(" ", "-").replaceAll("/", "")}`} key={module}>
              {module}
            </a>
          ))}
        </nav>
      </aside>

      <section className="workspace">
        <header className="hero">
          <div>
            <p className="eyebrow">Authenticated preview</p>
            <h1>Sapphire OS Control Plane</h1>
            <p>
              A single spine for what is happening, what changed, what backs it,
              and what can be done safely next.
            </p>
          </div>
          <div className={`posture posture-${summary.status}`}>
            <span>Safety posture</span>
            <strong>{statusLabel(summary)}</strong>
          </div>
        </header>

        <section className="grid" aria-label="Evidence cards">
          {visibleCards.map((card) => (
            <Card card={card} key={`${card.title}-${card.source.path_or_url}`} />
          ))}
        </section>

        <section className="modules" aria-label="Module contracts">
          {moduleRows.map((contract) => (
            <article className="module-row" id={contract.name.toLowerCase().replaceAll(" ", "-").replaceAll("/", "")} key={contract.name}>
              <span>{contract.name}</span>
              <strong>{contract.status}</strong>
              <p>{contract.detail}</p>
            </article>
          ))}
        </section>
      </section>
    </main>
  );
}
