# Frontend Surface Inventory Runbook

Sapphire has several frontend surfaces with different audiences and risk levels.
Use the inventory before refactoring so public pages, admin consoles, local
operator workbenches, and Telegram-native controls do not blur together.

## Inventory Command

```bash
python3 scripts/ops/frontend_surface_inventory.py --pretty --fail-on-missing
```

The script is read-only. It catalogs the current Sapphire frontend estate,
checks that known entrypoints still exist, labels each surface with its
public/operator boundary, and lists the focused verification commands for that
surface.

## Current Boundaries

- `analytics_public_site`, `acquirer_public_site`, `customer_static_site`, and
  `hackathon_frontend` are public or demo-safe surfaces. Keep them readable,
  redacted, and honest about modeled or paper-only behavior.
- `analytics_admin`, `ops_dashboard_jinja`, `ops_dashboard_react_preview`,
  `control_plane_static`, and `telegram_operator_surface` are operator-sensitive
  surfaces. They can describe real runtime state, but controls need explicit
  capability scopes and confirmation states.
- `ops_dashboard_react_preview` is the best candidate for the next canonical
  workbench shell: left navigation, central evidence/artifact canvas, and right
  provenance/action rail.
- `control_plane_static` and `telegram_operator_surface` should stay local or
  operator-only until local-machine and Telegram capabilities are modeled as
  read-only metadata plus explicit confirmed actions.

## Refactor Order

1. Promote the React operations preview into the primary dashboard shell while
   keeping API calls read-only. The first promotion slice is now the React
   workbench shell: left module navigation, central evidence canvas, and a right
   evidence/action inspector backed only by `/api/v2/control-plane/summary`.
2. Split `services/analytics_dashboard` into public-safe pages and authenticated
   admin pages with tests around the passkey/admin boundary.
3. Collapse legacy dashboard Jinja pages into explicit modules using
   `scripts/ops/dashboard_surface_inventory.py --check`.
4. Move local-machine and Telegram runtime state into the runtime control-plane
   inventory before exposing any additional controls.
5. Retire or extract the hackathon frontend once the reusable demo cards are
   represented in standalone satellite repos.

## Verification

Run these checks after inventory or boundary changes:

```bash
python3 scripts/ops/frontend_surface_inventory.py --fail-on-missing
python3 scripts/ops/dashboard_surface_inventory.py --check
pytest tests/unit/test_frontend_surface_inventory.py tests/unit/test_dashboard_surface_inventory.py -q
pytest tests/unit/test_dashboard_react_preview_shell.py -q
npm --prefix services/dashboard/frontend run build
```

For visible UI changes, also run the relevant local server and verify the page
in a browser with the primary buttons clicked against real routes.
