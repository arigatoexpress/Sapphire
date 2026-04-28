# Operator Communications Templates

Templates for recurring operator communications around acquisition cadence, partner operations, contractor management, live-trading ramp decisions, and prospect intro calls.

The goal: triage 5x faster on recurring scenarios. Without templates, every reply is from scratch. With them, the operator opens the matching template, swaps placeholders, edits the parts that don't fit, and sends in minutes.

## Index

| File | Audience | When to use |
|------|----------|-------------|
| [strategic-acquirer-followup-day-7.md](operator-templates/strategic-acquirer-followup-day-7.md) | Strategic acquirer contact | Day 7 after cold pitch, no reply — gentle nudge |
| [strategic-acquirer-followup-day-21.md](operator-templates/strategic-acquirer-followup-day-21.md) | Strategic acquirer contact | Day 21 after cold pitch, no reply — graceful close, pivot signal |
| [strategic-acquirer-cold-pitch.md](operator-templates/strategic-acquirer-cold-pitch.md) | Strategic acquirer / corp-dev | First-touch outreach — tuned with placeholders for the specific company, program, and proof points |
| [acquirer-positive-reply-response.md](operator-templates/acquirer-positive-reply-response.md) | Any corp-dev rep | Reply was "interested, tell me more" — books 30-min call + arms with materials |
| [acquirer-skeptical-reply-response.md](operator-templates/acquirer-skeptical-reply-response.md) | Any corp-dev rep | Reply pushed back on valuation/scope/solo-engineer concern — defensive but not deferential |
| [partner-weekly-cadence.md](operator-templates/partner-weekly-cadence.md) | Private partner group | Monday morning — what shipped / planned / blocked / questions |
| [partner-doc-bug-acknowledgement.md](operator-templates/partner-doc-bug-acknowledgement.md) | Reporting partner + copied stakeholders | Document workflow bug reported |
| [partner-site-link-broken.md](operator-templates/partner-site-link-broken.md) | Reporting partner + copied stakeholders | Generic broken-link / marketing-site reply when CMS access unclear |
| [contractor-followup-no-reply-day-3.md](operator-templates/contractor-followup-no-reply-day-3.md) | External contractor | 3 days post the alignment email if no reply — soft re-state of stakes |
| [contractor-integration-memo-share.md](operator-templates/contractor-integration-memo-share.md) | External contractor | When contractor reply lands — share boundary memo BEFORE they write workspace structure |
| [live-trade-cap-bump-self-approval.md](operator-templates/live-trade-cap-bump-self-approval.md) | Operator self-doc | Before a documented cap-rung bump — full audit trail of soak gates |
| [live-trade-incident-report.md](operator-templates/live-trade-incident-report.md) | Operator self-doc + acquirer audit | Anything unexpected with a live trade — 5-section structured report |
| [intro-call-prep-template.md](operator-templates/intro-call-prep-template.md) | Operator self-doc | 5-10 minutes before any new prospect/inbound/corp-dev call |

## Placeholder legend

Every template uses double-curly-brace placeholders. Do a find-and-replace before sending — `grep '{{' <file>` to confirm none remain.

| Placeholder | Meaning |
|-------------|---------|
| `{{first_name}}` | Recipient's first name |
| `{{operator_name}}` | Sender signature name to use after the template is filled |
| `{{system_name}}` | Product/system name to mention in outbound acquisition materials |
| `{{their_role}}` | Their job title |
| `{{their_company}}` | Their employer / company name |
| `{{their_team}}` | Specific team within their company |
| `{{target_company}}` | Company being followed up with or pitched |
| `{{target_platform_or_program}}` | Program, product surface, or acquisition lane that could be a fit |
| `{{date}}` | The date this template is being filled / sent (use ISO YYYY-MM-DD where formal, friendlier formats for partner mail) |
| `{{date_sent}}` | Original send date for follow-up emails |
| `{{date_original_sent}}` | Same as above, used in some templates for clarity |
| `{{followup_date}}` | Target date for the follow-up action |
| `{{original_subject}}` | Subject line of the email being followed up on |
| `{{calendar_link}}` | Operator's scheduler URL (Calendly etc.) |
| `{{microsite_url}}` | Acquirer microsite |
| `{{diligence_pr_url}}` | Link to the 10-doc diligence packet (current state: PR #341 + later) |
| `{{deck_url}}` | Pitch deck (slides) link |
| `{{evidence_doc_link}}` | Specific diligence document to point a skeptical reader at |
| `{{call_focus_area}}` | What the call should center on (e.g. "security posture", "data flow") |
| `{{specific_objection_paraphrase}}` | The skeptic's objection in your own words |
| `{{smaller_acquirer_name}}` | Backup acquirer to name when pivoting after no reply |
| `{{backup_acquirer_segment}}` | Generic segment for fallback outreach if no specific company should be named |
| `{{proof_point_summary}}` | Freshly verified, non-sensitive proof point for outbound acquisition materials |
| `{{execution_endpoint_summary}}` | Freshly verified, non-sensitive description of any integration endpoint or execution surface |
| `{{cap_ladder_summary}}` | Freshly verified, non-sensitive description of the current trading cap ladder |
| `{{performance_summary}}` | Freshly verified, non-sensitive performance summary, or `not included` |
| `{{week_of}}` | ISO date of the Monday for the partner weekly |
| `{{business_app_name}}` | Internal app/system name to use in partner updates |
| `{{cloud_run_revision}}` | Current deployment revision, if non-sensitive and verified |
| `{{customer_count}}` | Current customer count, only if approved to share with the recipients |
| `{{pdf_template_count}}` | Current document-template count, only if approved to share with the recipients |
| `{{shipped_bullets}}` / `{{planned_bullets}}` / `{{blocked_bullets}}` | Bullet lists for the partner weekly |
| `{{questions_for_partners}}` | Specific operator questions to surface in the partner weekly |
| `{{bug_short_description}}` | Brief description of a partner-reported bug |
| `{{repro_acknowledgement}}` | Sentence confirming the bug reproduces (or doesn't, but probably does) |
| `{{expected_fix_window}}` | Realistic fix window — "today by EOD", "within 24-48 hours" |
| `{{retest_customer_name}}` | Fictional customer name for partners to re-test against (NEVER a real customer) |
| `{{broken_url}}` | The 404'ing URL the reporter provided |
| `{{site_domain}}` | Site domain with the broken asset |
| `{{site_platform_hint}}` | CMS/platform guess, if known |
| `{{filename_or_page}}` | The asset filename (`MH-Checklist.pdf` etc.) |
| `{{memo_url_or_attachment}}` | Link to the integration boundary memo |
| `{{first_deliverable_date}}` | The date the contractor proposed for first deliverable |
| `{{specific_contractor_reply_paraphrase}}` | Specific reference to one thing in the contractor's reply |
| `{{workspace_tool_name}}` | Workspace tool being configured by the contractor |
| `{{existing_system_name}}` | Existing production system that must remain source of truth |
| `{{existing_system_context}}` | Non-sensitive summary of existing system scope |
| `{{alternate_contact_channel}}` | Alternate contact channel, only if already established |
| `{{decision_date}}` | The date a cap bump or incident is being filed |
| `{{from_cap}}` / `{{to_cap}}` | Cap-bump source and destination values |
| `{{maximum_documented_cap}}` | Highest cap currently approved by the governing runbook |
| `{{soak_window_start}}` / `{{soak_window_end}}` | The 14-trading-day window evaluated for the bump |
| `{{sortino_value}}` | Computed Sortino over the soak window |
| `{{paper_drift_summary}}` | Sentence on paper-vs-live drift in the window |
| `{{readiness_sweep_result}}` | Output from `scripts/ops/production_readiness_sweep.py` |
| `{{kill_switch_status}}` / `{{confirmation_firewall_status}}` | "engaged" / "idle" / "disabled" / etc. |
| `{{incident_date}}` / `{{order_id}}` / `{{symbol}}` / `{{notional}}` | Incident-report identifiers |
| `{{filed_by}}` / `{{filed_at}}` | Who filed the incident, and when |
| `{{call_date}}` / `{{their_name}}` / `{{call_duration_min}}` / `{{intro_source}}` | Intro-call prep identifiers |
| `{{their_company_short_summary}}` | 2-3 sentence summary of what their company does |
| `{{strongest_verified_proof_point}}` / `{{second_verified_proof_point}}` / `{{third_verified_proof_point}}` | Current, non-sensitive proof points for intro-call prep |
| `{{three_questions}}` / `{{three_things_to_mention}}` / `{{hard_pass_triggers}}` | Self-explanatory; intro-call prep fields |

## Conventions

- **No real PII in templates**: names, relationship context, customer names, and email addresses are placeholders. Operational specifics such as customer counts, trade identifiers, performance claims, and dollar figures are also placeholders unless repo-grounded, non-sensitive, and freshly verified before sending.
- **Operator's voice**: direct, specific, technical when warranted, warm with trusted partners. The "Notes for the operator" section in each template explains tone calibration.
- **Sent-message vs operator-only**: the section above `## Notes for the operator (NOT in the sent message)` is what gets sent. Everything below that heading is internal — never include it in the email.
- **Self-documentation templates** (cap bump, incident report, intro-call prep) follow a slightly different shape — they're audit / prep documents, not outbound messages. The "audience" frontmatter field flags them.

## Maintenance

- Update `last_updated` and `provenance_sha` (= `git rev-parse HEAD` at edit time) whenever a template is meaningfully edited.
- Templates that go stale should be deprecated, not deleted — move to `operator-templates/_deprecated/` with a comment explaining why and when. Future-you needs to know what voice you used to use.
- New scenarios should be added with the same frontmatter shape. Don't break the convention; future ingestion (e.g. by a Sapphire plugin tool) will rely on the YAML structure.

## Provenance sidecar

`operator-templates/.envelope.json` lists every template plus the head SHA at write time, for audit-trail purposes. Re-run the sidecar generator when adding or meaningfully editing templates.
