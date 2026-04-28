# Operator Communications Templates

Templates for the recurring communications scenarios the operator (Ari) handles around acquisition cadence, THO partner ops, contractor management, live-trading ramp decisions, and prospect intro calls.

The goal: triage 5x faster on recurring scenarios. Without templates, every reply is from scratch. With them, the operator opens the matching template, swaps placeholders, edits the parts that don't fit, and sends in minutes.

## Index

| File | Audience | When to use |
|------|----------|-------------|
| [palantir-followup-day-7.md](operator-templates/palantir-followup-day-7.md) | Foundry PM / FDE | Day 7 after cold pitch, no reply — gentle nudge |
| [palantir-followup-day-21.md](operator-templates/palantir-followup-day-21.md) | Foundry PM / FDE | Day 21 after cold pitch, no reply — graceful close, pivot signal |
| [robinhood-cortex-cold-pitch.md](operator-templates/robinhood-cortex-cold-pitch.md) | Robinhood Cortex / corp-dev | First-touch outreach — mirrors Palantir shape, retail/crypto-native tuning |
| [acquirer-positive-reply-response.md](operator-templates/acquirer-positive-reply-response.md) | Any corp-dev rep | Reply was "interested, tell me more" — books 30-min call + arms with materials |
| [acquirer-skeptical-reply-response.md](operator-templates/acquirer-skeptical-reply-response.md) | Any corp-dev rep | Reply pushed back on valuation/scope/solo-engineer concern — defensive but not deferential |
| [tho-weekly-cadence.md](operator-templates/tho-weekly-cadence.md) | Celeste, Mark, Ben | Monday morning — what shipped / planned / blocked / questions |
| [tho-doc-bug-acknowledgement.md](operator-templates/tho-doc-bug-acknowledgement.md) | Reporting partner + others | Document Center / XFA fill bug reported |
| [tho-celeste-link-broken.md](operator-templates/tho-celeste-link-broken.md) | Celeste + cc list | Generic broken-link / marketing-site reply when CMS access unclear |
| [etai-followup-no-reply-day-3.md](operator-templates/etai-followup-no-reply-day-3.md) | Etai (Upwork contractor) | 3 days post the 4-question email if no reply — soft re-state of stakes |
| [etai-integration-memo-share.md](operator-templates/etai-integration-memo-share.md) | Etai (Upwork contractor) | When his reply lands — share boundary memo BEFORE he writes Notion structure |
| [live-trade-cap-bump-self-approval.md](operator-templates/live-trade-cap-bump-self-approval.md) | Operator self-doc | Before $5→$50 (or $50→$500) cap bump — full audit trail of soak gates |
| [live-trade-incident-report.md](operator-templates/live-trade-incident-report.md) | Operator self-doc + acquirer audit | Anything unexpected with a live trade — 5-section structured report |
| [intro-call-prep-template.md](operator-templates/intro-call-prep-template.md) | Operator self-doc | 5-10 minutes before any new prospect/inbound/corp-dev call |

## Placeholder legend

Every template uses double-curly-brace placeholders. Do a find-and-replace before sending — `grep '{{' <file>` to confirm none remain.

| Placeholder | Meaning |
|-------------|---------|
| `{{first_name}}` | Recipient's first name |
| `{{their_role}}` | Their job title (e.g. "Director, Foundry FDE") |
| `{{their_company}}` | Their employer / company name |
| `{{their_team}}` | Specific team within their company (e.g. "Cortex", "Crypto Product") |
| `{{date}}` | The date this template is being filled / sent (use ISO YYYY-MM-DD where formal, friendlier formats for partner mail) |
| `{{date_sent}}` | Original send date for follow-up emails |
| `{{date_original_sent}}` | Same as above, used in some templates for clarity |
| `{{followup_date}}` | Target date for the follow-up action |
| `{{original_subject}}` | Subject line of the email being followed up on |
| `{{calendar_link}}` | Operator's scheduler URL (Calendly etc.) |
| `{{microsite_url}}` | Sapphire acquirer microsite |
| `{{diligence_pr_url}}` | Link to the 10-doc diligence packet (current state: PR #341 + later) |
| `{{deck_url}}` | Pitch deck (slides) link |
| `{{evidence_doc_link}}` | Specific diligence document to point a skeptical reader at |
| `{{call_focus_area}}` | What the call should center on (e.g. "security posture", "data flow") |
| `{{specific_objection_paraphrase}}` | The skeptic's objection in your own words |
| `{{smaller_acquirer_name}}` | Backup acquirer to name when pivoting after Palantir silence |
| `{{week_of}}` | ISO date of the Monday for the THO weekly |
| `{{cloud_run_revision}}` | Current Project-Go-Forward Cloud Run revision number |
| `{{customer_count}}` | Current Firestore customer count (pull from `dev_pulse` tool) |
| `{{shipped_bullets}}` / `{{planned_bullets}}` / `{{blocked_bullets}}` | Bullet lists for the THO weekly |
| `{{questions_for_partners}}` | Specific operator questions to surface in the THO weekly |
| `{{bug_short_description}}` | Brief description of a partner-reported bug |
| `{{repro_acknowledgement}}` | Sentence confirming the bug reproduces (or doesn't, but probably does) |
| `{{expected_fix_window}}` | Realistic fix window — "today by EOD", "within 24-48 hours" |
| `{{retest_customer_name}}` | Fictional customer name for partners to re-test against (NEVER a real customer) |
| `{{broken_url}}` | The 404'ing URL Celeste reported |
| `{{filename_or_page}}` | The asset filename (`MH-Checklist.pdf` etc.) |
| `{{memo_url_or_attachment}}` | Link to the integration boundary memo |
| `{{first_deliverable_date}}` | The date Etai proposed for first deliverable |
| `{{specific_etai_question_paraphrase}}` | Specific reference to one thing in Etai's reply |
| `{{decision_date}}` | The date a cap bump or incident is being filed |
| `{{from_cap}}` / `{{to_cap}}` | Cap-bump source and destination ($5, $50, $500) |
| `{{soak_window_start}}` / `{{soak_window_end}}` | The 14-trading-day window evaluated for the bump |
| `{{sortino_value}}` | Computed Sortino over the soak window |
| `{{paper_drift_summary}}` | Sentence on paper-vs-live drift in the window |
| `{{readiness_sweep_result}}` | Output from `scripts/ops/production_readiness_sweep.py` |
| `{{kill_switch_status}}` / `{{confirmation_firewall_status}}` | "engaged" / "idle" / "disabled" / etc. |
| `{{incident_date}}` / `{{order_id}}` / `{{symbol}}` / `{{notional}}` | Incident-report identifiers |
| `{{filed_by}}` / `{{filed_at}}` | Who filed the incident, and when |
| `{{call_date}}` / `{{their_name}}` / `{{call_duration_min}}` / `{{intro_source}}` | Intro-call prep identifiers |
| `{{their_company_short_summary}}` | 2-3 sentence summary of what their company does |
| `{{three_questions}}` / `{{three_things_to_mention}}` / `{{hard_pass_triggers}}` | Self-explanatory; intro-call prep fields |

## Conventions

- **No real PII in templates**: customer names, email addresses, dollar figures the operator hasn't already shared in writing — none of these are hard-coded. Placeholders only.
- **Operator's voice**: direct, specific, technical when warranted, warm with family/partners. The "Notes for the operator" section in each template explains tone calibration.
- **Sent-message vs operator-only**: the section under `—Ari` is what gets sent. Everything below `## Notes for the operator (NOT in the sent message)` is internal — never include it in the email.
- **Self-documentation templates** (cap bump, incident report, intro-call prep) follow a slightly different shape — they're audit / prep documents, not outbound messages. The "audience" frontmatter field flags them.

## Maintenance

- Update `last_updated` and `provenance_sha` (= `git rev-parse HEAD` at edit time) whenever a template is meaningfully edited.
- Templates that go stale should be deprecated, not deleted — move to `operator-templates/_deprecated/` with a comment explaining why and when. Future-you needs to know what voice you used to use.
- New scenarios should be added with the same frontmatter shape. Don't break the convention; future ingestion (e.g. by a Sapphire plugin tool) will rely on the YAML structure.

## Provenance sidecar

`operator-templates/.envelope.json` lists every template plus the head SHA at write time, for audit-trail purposes. Re-run the sidecar generator when adding or meaningfully editing templates.
