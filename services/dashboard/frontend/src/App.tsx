import { useEffect, useMemo, useState } from "react";
import {
  blockedSummary,
  CardStatus,
  ControlPlaneSummary,
  EnvelopeCard,
  fetchControlPlaneSummary,
} from "./api/controlPlane";

const moduleNavigation = [
  { name: "Home / Worldline", summary: "Current posture and evidence cards." },
  { name: "Operations", summary: "Services, worktrees, PR lanes, and readiness." },
  { name: "Intelligence", summary: "Regional, cyber, market, and business loops." },
  { name: "Markets", summary: "Research-only signals, paper paths, and caveats." },
  { name: "Security", summary: "SOC, dependency, model, and credential hygiene." },
  { name: "Products / Diligence", summary: "x402, artifacts, and buyer proof." },
  { name: "Automation", summary: "Routine previews and dry-run next actions." },
  { name: "Settings / Contracts", summary: "Capabilities, confirmations, and boundaries." },
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

function cardKey(card: EnvelopeCard): string {
  return `${card.title}-${card.source.path_or_url}`;
}

function statusTone(status: CardStatus): string {
  if (status === "ok") return "Ready";
  if (status === "warn") return "Needs Review";
  if (status === "fail") return "Blocked";
  return "Unknown";
}

function Card({
  card,
  selected,
  onSelect,
}: {
  card: EnvelopeCard;
  selected: boolean;
  onSelect: (card: EnvelopeCard) => void;
}) {
  return (
    <article className={`card card-${card.status} ${selected ? "card-selected" : ""}`}>
      <div className="card-topline">
        <span className="status-dot" aria-hidden="true" />
        <span>{card.module ? `${card.module} · ${modeLabel(card)}` : modeLabel(card)}</span>
      </div>
      <h2>{card.title}</h2>
      <strong>{card.value}</strong>
      <p>{card.summary}</p>
      <button className="inspect-button" type="button" onClick={() => onSelect(card)}>
        Inspect Evidence
      </button>
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
  const [selectedCardKey, setSelectedCardKey] = useState<string | null>(null);

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
  const selectedCard = useMemo(() => {
    if (!visibleCards.length) return null;
    return visibleCards.find((card) => cardKey(card) === selectedCardKey) ?? visibleCards[0];
  }, [selectedCardKey, visibleCards]);
  const summaryStats = useMemo(() => {
    const cards = visibleCards;
    return {
      total: cards.length,
      ok: cards.filter((card) => card.status === "ok").length,
      warn: cards.filter((card) => card.status === "warn").length,
      fail: cards.filter((card) => card.status === "fail").length,
      blocked: cards.filter((card) => card.mode === "blocked").length,
    };
  }, [visibleCards]);
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

  useEffect(() => {
    if (!visibleCards.length) return;
    if (!selectedCardKey || !visibleCards.some((card) => cardKey(card) === selectedCardKey)) {
      setSelectedCardKey(cardKey(visibleCards[0]));
    }
  }, [selectedCardKey, visibleCards]);

  return (
    <main className="operator-shell">
      <aside className="rail" aria-label="Control plane modules">
        <div className="brand-lockup">
          <div className="mark">S</div>
          <div>
            <strong>Sapphire OS</strong>
            <span>Operator workbench</span>
          </div>
        </div>
        <nav>
          {moduleNavigation.map((module) => (
            <a href={`#${module.name.toLowerCase().replaceAll(" ", "-").replaceAll("/", "")}`} key={module.name}>
              <strong>{module.name}</strong>
              <span>{module.summary}</span>
            </a>
          ))}
        </nav>
      </aside>

      <section className="workspace" aria-label="Control-plane evidence canvas">
        <header className="hero">
          <div>
            <p className="eyebrow">Authenticated operator preview</p>
            <h1>Sapphire OS Control Plane</h1>
            <p>
              A read-only evidence canvas for what is happening, what changed,
              what backs it, and which actions are blocked or dry-run only.
            </p>
          </div>
          <div className={`posture posture-${summary.status}`}>
            <span>Safety posture</span>
            <strong>{statusLabel(summary)}</strong>
          </div>
        </header>

        <section className="status-strip" aria-label="Summary counts">
          <div>
            <span>Total cards</span>
            <strong>{summaryStats.total}</strong>
          </div>
          <div>
            <span>Ready</span>
            <strong>{summaryStats.ok}</strong>
          </div>
          <div>
            <span>Review</span>
            <strong>{summaryStats.warn}</strong>
          </div>
          <div>
            <span>Blocked</span>
            <strong>{summaryStats.fail + summaryStats.blocked}</strong>
          </div>
        </section>

        <section className="grid" aria-label="Evidence cards">
          {visibleCards.map((card) => (
            <Card
              card={card}
              key={cardKey(card)}
              onSelect={(nextCard) => setSelectedCardKey(cardKey(nextCard))}
              selected={selectedCard ? cardKey(card) === cardKey(selectedCard) : false}
            />
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

      <aside className="inspector" aria-label="Selected evidence inspector">
        <div className="inspector-panel">
          <p className="eyebrow">Evidence Inspector</p>
          {selectedCard ? (
            <>
              <h2>{selectedCard.title}</h2>
              <div className={`inspector-status inspector-status-${selectedCard.status}`}>
                <span>{statusTone(selectedCard.status)}</span>
                <strong>{selectedCard.value}</strong>
              </div>
              <dl>
                <div>
                  <dt>Mode</dt>
                  <dd>{modeLabel(selectedCard)}</dd>
                </div>
                <div>
                  <dt>Source</dt>
                  <dd>
                    <code>{selectedCard.source.path_or_url}</code>
                  </dd>
                </div>
                <div>
                  <dt>Generated</dt>
                  <dd>{selectedCard.source.generated_at ?? "Not available"}</dd>
                </div>
              </dl>
              <p>{selectedCard.summary}</p>
              <section className="actions" aria-label="Available action previews">
                <h3>Action posture</h3>
                {selectedCard.actions.length ? (
                  selectedCard.actions.map((action) => (
                    <div className={`action action-${action.mode}`} key={`${action.label}-${action.mode}`}>
                      <strong>{action.label}</strong>
                      <span>
                        {action.mode}
                        {action.requires_confirm ? " · confirm required" : " · no live mutation"}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="action action-blocked">
                    <strong>No action exposed</strong>
                    <span>Inspector is evidence-only for this card.</span>
                  </div>
                )}
              </section>
            </>
          ) : (
            <p>No evidence cards are loaded yet.</p>
          )}
        </div>
      </aside>
    </main>
  );
}
