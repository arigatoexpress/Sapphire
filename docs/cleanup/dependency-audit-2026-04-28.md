# Dependency Audit - 2026-04-28

Scope: Agent B overnight dependency hygiene pass for
`/Users/aribs/Code/Sapphire`.

## Commands

```bash
pip-audit . --progress-spinner off
pip-audit -r requirements-test.txt -r services/control-plane/requirements.txt \
  -r services/analytics_dashboard/requirements.txt -r services/alpha/requirements.txt \
  -r services/aster/requirements.txt -r services/hyperliquid/requirements.txt \
  -r services/dashboard/requirements.txt -r services/pm_bot/requirements.txt \
  -r tools/sui_event_scanner/requirements.txt -r clients/blanga/requirements.txt \
  -r infra/gcp/cloud_functions/gcs_to_bq/requirements.txt --progress-spinner off
ruff --version
```

The combined requirements audit hit a resolver conflict between pytest version
constraints, so each requirements file was audited individually after that.

## Root Project

`pip-audit . --progress-spinner off` reported no known vulnerabilities. It also
warned that `pyproject.toml` has no root `dependencies` list, which is expected
for this workspace-oriented repo.

`ruff --version` returned `ruff 0.15.10`. The root `pyproject.toml` currently
allows `ruff>=0.7.4` for dev installs. No ruff security finding was reported.

## Vulnerability Findings

| File | Package | Current | Advisory | Fixed version | Agent B action |
|---|---|---:|---|---:|---|
| `requirements-test.txt` | `orjson` | `3.10.13` | `GHSA-hx9q-6w63-j58v` | `3.11.6` | Left unchanged; test dependency file is outside Agent B's edit allow-list. |
| `requirements-test.txt` | `python-dotenv` | `1.0.1` | `GHSA-mf9w-mj56-hr94` | `1.2.2` | Left unchanged; test dependency file is outside Agent B's edit allow-list. |
| `services/control-plane/requirements.txt` | `pytest` | `8.4.2` | `GHSA-6w46-j5rx-g56g` | `9.0.3` | Left unchanged; fixed version is a major bump and the mission forbids major-version dependency bumps. |
| `services/alpha/requirements.txt` | `aiohttp` | `3.11.11` | `GHSA-p998-jp59-783m`, `GHSA-hcc4-c3v8-rx92`, `GHSA-m5qp-6w8w-w647`, `GHSA-3wq7-rqq7-wx6j`, `GHSA-mwh4-6h8g-pg8w`, `GHSA-966j-vmvw-g2g9`, `GHSA-63hf-3vf5-4wqf`, `GHSA-c427-h43c-vf67`, `GHSA-9548-qrrj-x5pj`, `GHSA-6mq8-rvhq-8wgg`, `GHSA-69f9-5gxw-wvc2`, `GHSA-6jhg-hg63-jvvf`, `GHSA-g84x-mcqj-x9qq`, `GHSA-fh55-r93g-j68g`, `GHSA-54jq-c3m8-4m76`, `GHSA-jj3x-wxrx-4x23`, `GHSA-mqqc-3gqh-h2x8`, `GHSA-w2fm-2cpv-w7v5`, `GHSA-2vrm-gr82-f7m5` | `3.13.4` | Left unchanged; `services/alpha/**` is forbidden for Agent B. |
| `services/alpha/requirements.txt` | `python-dotenv` | `1.0.1` | `GHSA-mf9w-mj56-hr94` | `1.2.2` | Left unchanged; `services/alpha/**` is forbidden for Agent B. |

## Clean Files

Individual audits found no known vulnerabilities in:

- `services/analytics_dashboard/requirements.txt`
- `services/aster/requirements.txt`
- `services/hyperliquid/requirements.txt`
- `services/dashboard/requirements.txt`
- `services/pm_bot/requirements.txt`
- `tools/sui_event_scanner/requirements.txt`
- `clients/blanga/requirements.txt`
- `infra/gcp/cloud_functions/gcs_to_bq/requirements.txt`

## Recommended Follow-Up

1. Open a test-tooling PR for `requirements-test.txt` to bump `orjson` to
   `3.11.6` and `python-dotenv` to `1.2.2`.
2. Defer the `pytest` advisory until the repo is ready for a pytest 9 migration
   or an upstream 8.x fixed release exists.
3. Assign the `services/alpha/requirements.txt` bumps to the owner of the alpha
   surface because that path is explicitly outside Agent B's lane.
