"""LinkedIn BD outreach.

Builds personalized, data-grounded outreach messages. The angle is always
a concrete Sapphire artifact (a prediction stat, a paper trade, a CVE) —
never generic networking copy. Every message references the data it came
from, so the recipient can verify.

`build_bd_message` takes a Lead and an angle kind; the caller supplies the
Lead fields (name, role, company, hook). This module does not scrape or
contact anyone — it only produces draft text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from . import report_generator as rg

AngleKind = Literal["crypto_perf", "agent_infra", "security"]


@dataclass
class Lead:
    name: str
    role: str = ""
    company: str = ""
    # A specific thing you noticed about them — post, article, project, etc.
    context: str = ""


@dataclass
class OutreachDraft:
    lead: Lead
    angle: AngleKind
    subject: str
    body: str
    char_count: int
    generated_at: str
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "lead": self.lead.__dict__,
            "angle": self.angle,
            "subject": self.subject,
            "body": self.body,
            "char_count": self.char_count,
            "generated_at": self.generated_at,
            "sources": self.sources,
        }


def _salutation(lead: Lead) -> str:
    first = lead.name.split()[0] if lead.name else "there"
    return f"Hi {first},"


def _context_line(lead: Lead) -> str:
    if lead.context:
        return f"Saw your note on {lead.context} — relevant to what I'm building."
    if lead.company:
        return f"Been watching {lead.company}'s work — relevant to what I'm building."
    return "Reaching out because what I'm building overlaps with your work."


def _crypto_angle() -> tuple[str, list[str]]:
    report = rg.generate_weekly_crypto_brief()
    preds = report.facts["predictions"]
    port = report.facts["portfolio"]
    line = (
        f"Sapphire's 6-factor TA model is at "
        f"{preds['accuracy'] * 100:.1f}% across {preds['total']} scored forecasts; "
        f"BTC track is {preds['by_symbol'].get('BTC', {}).get('accuracy', 0) * 100:.0f}%. "
        f"Paper book at {port['pnl_pct']:+.2f}% on $100K, "
        f"{port['open_positions']} open."
    )
    return line, report.sources


def _agent_angle() -> tuple[str, list[str]]:
    report = rg.generate_ai_intel_report()
    f = report.facts
    line = (
        f"Sapphire's agent mesh logged {f['event_count']} events across "
        f"{len(f['agent_counts'])} agents and "
        f"{len(f['device_counts'])} devices this cycle, "
        f"with {f['tracked_projects']} projects under orchestration."
    )
    return line, report.sources


def _security_angle() -> tuple[str, list[str]]:
    report = rg.generate_security_digest()
    f = report.facts
    top = f["top_cves"][0] if f["top_cves"] else None
    if top:
        line = (
            f"Sapphire's threat-intel pulled {f['count']} priority CVEs this cycle; "
            f"top is {top['cve']} (CVSS {top.get('cvss', '?')}, "
            f"{'KEV' if top['exploited'] else 'not KEV'})."
        )
    else:
        line = "Sapphire's threat-intel had a quiet cycle — 0 priority CVEs."
    return line, report.sources


ANGLE_BUILDERS = {
    "crypto_perf": _crypto_angle,
    "agent_infra": _agent_angle,
    "security": _security_angle,
}

ASK_BY_ANGLE = {
    "crypto_perf": "Worth a 15-min call to compare notes on signal quality?",
    "agent_infra": "Open to trading notes on agent routing for 15 minutes?",
    "security": "15-min call on how you're triaging KEV right now?",
}

SUBJECT_BY_ANGLE = {
    "crypto_perf": "Signal accuracy notes",
    "agent_infra": "Agent mesh notes",
    "security": "CVE triage notes",
}


def build_bd_message(lead: Lead, angle: AngleKind = "crypto_perf") -> OutreachDraft:
    data_line, sources = ANGLE_BUILDERS[angle]()
    ask = ASK_BY_ANGLE[angle]
    body = "\n\n".join([
        _salutation(lead),
        _context_line(lead),
        data_line,
        ask,
        "— Sapphire",
    ])
    return OutreachDraft(
        lead=lead,
        angle=angle,
        subject=SUBJECT_BY_ANGLE[angle],
        body=body,
        char_count=len(body),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        sources=sources,
    )
