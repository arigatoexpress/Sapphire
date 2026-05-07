export type CardStatus = "ok" | "warn" | "fail" | "unknown";
export type CardMode = "live" | "read_only" | "paper" | "modeled" | "stale" | "blocked";

export interface EvidenceSource {
  kind: "probe" | "file" | "script" | "service" | "manual";
  path_or_url: string;
  generated_at: string | null;
  age_seconds: number | null;
}

export interface ActionPreview {
  label: string;
  mode: "dry_run" | "read_only" | "blocked";
  requires_confirm: boolean;
}

export interface EnvelopeCard {
  module?: string;
  status: CardStatus;
  mode: CardMode;
  title: string;
  value: string;
  summary: string;
  source: EvidenceSource;
  actions: ActionPreview[];
}

export interface ControlPlaneSummary {
  status: CardStatus;
  mode?: CardMode;
  generated_at: string | null;
  summary?: {
    card_count: number;
    warn_count: number;
    fail_count: number;
    blocked_mode_count: number;
  };
  modules?: {
    name: string;
    status: CardStatus;
    summary: string;
    card_count: number;
  }[];
  cards: EnvelopeCard[];
}

function dashboardUrl(path: string): string {
  const currentUrl = new URL(window.location.href);
  currentUrl.username = "";
  currentUrl.password = "";
  return new URL(path, currentUrl.origin).href;
}

export async function fetchControlPlaneSummary(): Promise<ControlPlaneSummary> {
  const response = await fetch(dashboardUrl("/api/v2/control-plane/summary"), {
    headers: {
      Accept: "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`summary endpoint returned ${response.status}`);
  }
  return (await response.json()) as ControlPlaneSummary;
}

export function blockedSummary(error: unknown): ControlPlaneSummary {
  const detail = error instanceof Error ? error.message : "summary endpoint is not wired";
  return {
    status: "unknown",
    generated_at: null,
    cards: [
      {
        status: "unknown",
        mode: "blocked",
        title: "Unified Status API",
        value: "PR 3 target",
        summary: `No mock data is displayed. /api/v2/control-plane/summary is blocked for this preview: ${detail}.`,
        source: {
          kind: "service",
          path_or_url: "/api/v2/control-plane/summary",
          generated_at: null,
          age_seconds: null,
        },
        actions: [
          {
            label: "Wire read-only adapters",
            mode: "dry_run",
            requires_confirm: false,
          },
        ],
      },
    ],
  };
}
