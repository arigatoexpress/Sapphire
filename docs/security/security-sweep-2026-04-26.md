# Security Sweep — 2026-04-26

End-to-end defensive sweep run against `lib/security/` modules in static / no-credential mode. The agent had no access to `~/.ollama`, no Tailscale subprocess capability, and no live mesh reachability, so model integrity verification and live network probes were intentionally skipped. Everything below is reproducible from the worktree at `chore/security-sweep-2026-04-26`.

## Methodology

| Scanner                 | What ran                                                                                                                                                                                          | What did not                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dependency_scanner`    | Parsed every `requirements*.txt` + `pyproject.toml` in the repo (12 files). Queried `https://api.osv.dev/v1/query` for each pinned (`==X.Y.Z`) declaration. CVE/advisory results listed below.    | Did not enumerate the live `importlib.metadata` set (would have reflected the agent's host, not the repo). PyPI latest-version lookups skipped to focus on declared advisories. |
| `model_monitor`         | Parsed `services/inference-proxy/app.py` `MODEL_TIERS`/`GPU_ONLY_MODELS`/`PI_MODELS` + `CLAUDE.md` to enumerate every Ollama model tag the codebase routes to. Documented expected manifest path layout. | Did not read `~/.ollama` (agent has no access to that dir); did not verify SHA-256 of any blob; did not scan template files.                              |
| `network_mapper`        | Static read of `infra/tailscale-acl.json` + the hardcoded `KNOWN_NODES` map in `lib/security/network_mapper.py`. Built node list, computed trust zones, computed declared-port unauth counts.     | No `tailscale status --json` subprocess and no TCP probes (`probe_ports=False`). Online status, real port states, and discovered/unknown peers all unknown.|

### External-auth requirements (catalogued)

- **OSV.dev** (`api.osv.dev/v1/query`): no API key required, but rate-limited. Reachable from this runtime once SSL CAs were resolved (see Caveat 1).
- **PyPI** (`pypi.org/pypi/<pkg>/json`): no auth required. Not exercised in this sweep.
- **Tailscale**: requires the `tailscale` CLI on the host plus an active session for `tailscale status --json`. Not invoked.
- **Ollama**: blob verification is filesystem-only (`~/.ollama/models/{manifests,blobs}`); the API fallback (`/api/tags`) requires the daemon to be reachable. Not invoked.

## Dependency findings

OSV.dev returned advisories for **5 distinct packages, 25 total advisories**, all clustered in `requirements-test.txt` and `services/alpha/requirements.txt`. Severity field came back as `unknown` from OSV (the published `severity[]` array did not contain CVSS scores in the GHSA records this batch).

| Package        | Declared version | Source                                            | Advisories | Suggested fixed version | Notes                                                                                         |
| -------------- | ---------------- | ------------------------------------------------- | ---------- | ----------------------- | --------------------------------------------------------------------------------------------- |
| `aiohttp`      | `3.11.11`        | `services/alpha/requirements.txt`                 | 19         | `3.13.4`                | Heaviest cluster: HTTP smuggling, header injection, cookie/proxy-auth leak, multipart DoS. `requirements-test.txt` already pins `3.13.5`, which is clean. |
| `cryptography` | `44.0.0`         | `requirements-test.txt`                           | 3          | `46.0.6`                | OpenSSL bundled-wheel CVE (`GHSA-79v4-65xg-pq4g`) + DNS name-constraint enforcement gap + SECT subgroup-validation issue. Two-major-version jump — investigate transitively before bumping. |
| `flask`        | `3.0.3`          | `services/analytics_dashboard/requirements.txt`   | 1          | `3.1.3`                 | `Vary: Cookie` advisory `GHSA-68rp-wp8r-4726`. `requirements-test.txt` already pins `3.1.3`. Patch-class minor bump within Flask 3.x. |
| `orjson`       | `3.10.13`        | `requirements-test.txt`                           | 1          | `3.11.6`                | Recursion-depth DoS (`CVE-2025-67221`). Note: `services/alpha/requirements.txt` already declares `>=3.11.6` so the alpha service is unaffected. |
| `python-dotenv`| `1.0.1`          | `requirements-test.txt`                           | 1          | `1.2.2`                 | `set_key()` symlink-following allows arbitrary file overwrite via cross-device rename fallback (`GHSA-mf9w-mj56-hr94`). Test-only path. |

Packages cleared (no advisories on the pinned version):

- `aiohttp 3.13.5`, `certifi 2026.2.25`, `fastapi 0.136.0`, `firebase-admin 6.9.0`, `flask 3.1.3`, `google-cloud-firestore 2.27.0`, `google-cloud-pubsub 2.27.1` and `2.37.0`, `google-cloud-storage 2.19.0`, `google-generativeai 0.8.4`, `gunicorn 22.0.0`, `httpx 0.28.1`, `loguru 0.7.3`, `numpy 2.4.4`, `pandas 2.2.3`, `pydantic 2.13.2`, `pytest 9.0.3`, `pytest-asyncio 1.3.0`, `pytest-cov 7.1.0`, `python-dateutil 2.9.0.post0`, `pyyaml 6.0.3`, `redis 5.2.1`, `requests 2.33.1`, `scikit-learn 1.6.0`, `scipy 1.15.0`, `tweepy 4.14.0`, `uvloop 0.21.0`, `websockets 14.1`.

Unbounded declarations (`>=X` floors with no upper bound) were not queried — OSV needs an exact version. They are flagged as a structural risk in Action items.

## Model surface

Every Ollama model tag the codebase will route to. None were verified — the agent has no read access to `~/.ollama/models/`. The expected SHA-256 verification surface is filesystem-bound on the Mac commander.

| Tag                       | Tier alias                   | Where referenced                                                                              |
| ------------------------- | ---------------------------- | --------------------------------------------------------------------------------------------- |
| `hermes3:8b`              | `auto`, `balanced`           | `services/inference-proxy/app.py` MODEL_TIERS                                                  |
| `nemotron-mini:latest`    | `fast`, `quick`              | proxy + `PI_MODELS` (Pi-eligible)                                                              |
| `qwen2.5:0.5b`            | `tiny`                       | proxy + `PI_SERVE_MODELS` + `PI_DEFAULT_MODEL`                                                 |
| `qwen3:14b`               | `deep`                       | proxy + `GPU_ONLY_MODELS`                                                                      |
| `gemma4:latest`           | `code`, `fast-code`          | proxy + `GPU_ONLY_MODELS`                                                                      |
| `deepseek-r1:14b`         | `reason`                     | proxy + `GPU_ONLY_MODELS`                                                                      |
| `qwen3.5:9b`              | `qwen-reason`, `fast-reason` | proxy + `GPU_ONLY_MODELS`                                                                      |
| `qwen2.5:32b`             | `large`                      | proxy + `GPU_ONLY_MODELS`                                                                      |
| `nemotron-cascade-2`      | `cascade`, `moe`             | proxy + `GPU_ONLY_MODELS`                                                                      |
| `qwen3.6:27b`             | `qwen3.6`                    | proxy (Windows primary, Mac exact fallback)                                                    |
| `qwen2.5-coder:14b`       | `qwen2.5-coder` (legacy)     | proxy + `GPU_ONLY_MODELS`                                                                      |
| `phi4:latest`             | `phi4` (legacy)              | proxy + `GPU_ONLY_MODELS`                                                                      |
| `gemma2:2b`               | (Pi inventory)               | `PI_MODELS`                                                                                    |
| `smollm2:1.7b`            | (Pi inventory)               | `PI_MODELS`                                                                                    |
| `kimi-cloud`              | `kimi*`, `cloud`, `research` | proxy → Moonshot/OpenRouter route; not an Ollama blob, no SHA verification applies             |

### Expected manifest layout

`ModelMonitor._load_manifest()` reads `<ollama_dir>/models/manifests/registry.ollama.ai/<namespace>/<name>/<tag>`, where `<namespace>` defaults to `library` for official models. Each manifest's `layers[].digest` is the SHA-256 to verify; the corresponding blob lives at `<ollama_dir>/models/blobs/sha256-<hex>` (the `:` becomes `-`).

### Operator verification (run on the Mac commander)

```bash
# from the repo root, with the same Python the proxy uses
python3 - <<'PY'
import json
from lib.security.model_monitor import ModelMonitor
result = ModelMonitor(verify_sha256=True, scan_templates=True).scan()
print(json.dumps(result.to_dict(), indent=2, default=str))
PY
```

The Windows GPU node and both Pis hold their own copies; the same scan must be run on each host where blob integrity matters. There is no remote-attestation path today — `_verify_blob` is filesystem-local.

## Network surface

Static read only. No live `tailscale status` and no TCP probes.

### Topology summary (4 nodes, all owned by `aristotlespec@`)

| Hostname (ACL alias) | Tailscale IP    | Trust zone | Role      | Declared inbound (from `KNOWN_NODES`)                                                  |
| -------------------- | --------------- | ---------- | --------- | --------------------------------------------------------------------------------------- |
| `mac-commander`      | `100.67.171.79` | `core`     | commander | `8082` (auth), `8080` (auth), `18081`, `11435`, `6900`, `6379`, `11434`                 |
| `windows-gpu`        | `100.71.10.48`  | `trusted`  | gpu       | `11434`, `9090`, `3001`                                                                 |
| `pi-rari1`           | `100.120.191.1` | `dmz`      | edge      | `11434`                                                                                 |
| `pi-rari2`           | `100.87.225.89` | `dmz`      | edge      | `11434`                                                                                 |

### Trust zones

- **`core`** — `mac-commander`. Policy: authenticated access only, no external exposure. Two of seven declared services are flagged authenticated (`control-plane:8082`, `dashboard:8080`); the other five (`signal-logger:18081`, `inference-proxy:11435`, `openbb:6900`, `redis:6379`, `ollama-local:11434`) are declared unauthenticated. They are protected only by the Tailscale ACL.
- **`trusted`** — `windows-gpu`. All three declared inbound ports are unauthenticated services (`ollama:11434`, `webhook:9090`, `telemetry:3001`).
- **`dmz`** — both Pis. Each exposes `ollama:11434` only.

### Tailscale ACL summary (`infra/tailscale-acl.json`)

- Mac commander → all nodes on full Sapphire service-port set.
- Mesh-wide allow on Mac service ports (`22, 6379, 6900, 8080, 8082, 11434, 11435, 18081`) so any node can reach the commander.
- Mesh allow on `22 + 11434` for Pis and Windows.
- Webhook port `9090` on Windows is restricted to the Mac.
- SSH rules: Mac→all, mesh→Mac, owner-from-anywhere on tailnet (autogroup:owner). All allow user `aribs` (and `pi` for Pi nodes).
- AutoApprovers: only the four declared `/32` Tailscale IPs.
- Tailscale's deny-by-default covers everything else; no explicit deny rule needed.

The ACL JSON contains a `tests` block (`"tests": [...]`) intended for `tailscale policy check` validation — that file is not currently exercised in CI.

### Static attack-surface scoring

Per `_score_node` (deterministic from declared metadata + zone — does not need a live probe):

| Node            | Trust-zone penalty | Discovered/unverified penalty | Static score |
| --------------- | ------------------ | ----------------------------- | ------------ |
| `mac-commander` | 0                  | 0                             | 0.0          |
| `windows-gpu`   | 5                  | 0                             | 5.0          |
| `pi-rari1`      | 15                 | 0                             | 15.0         |
| `pi-rari2`      | 15                 | 0                             | 15.0         |

Aggregate static score: **57.4 / 100** (penalties: 30 from declared unauthenticated ports, 0 unknown nodes, 0 offline-pct since `online_nodes` was unknown, ~3 from the average-node-score factor). With `probe_ports=False` the open-port and unauthenticated-port penalties degrade to declared metadata only — they understate or overstate reality depending on which ACL-permitted services are actually bound. A live run is required to make this score meaningful.

## Action items

1. **Fix the silent SSL failure in `dependency_scanner._query_osv`.** The scanner's `urllib.request.urlopen(...)` does not pass a CA bundle, so on macOS runtimes without the system trust store wired into Python, every OSV call fails with `SSL: CERTIFICATE_VERIFY_FAILED` and is swallowed by the catch-all `except (urllib.error.URLError, TimeoutError, json.JSONDecodeError)`. The scanner returns `[]` and the report says "no advisories" — but actually every call failed. Fix: build an `ssl.create_default_context(cafile=certifi.where())` once at construction and pass it via `urlopen(..., context=ctx)` for both `_query_osv` and `_check_pypi_latest`. Same fix in the model-monitor's `urllib.request.urlopen(url, timeout=5)` for `/api/tags`. (Out of scope for this PR per the no-modify constraint on `lib/security/`.)
2. **Bump `services/analytics_dashboard/requirements.txt` Flask `3.0.3` → `3.1.3`.** Single advisory, fixed version is already used elsewhere in the repo, no breaking changes between Flask 3.0 and 3.1 per Pallets release notes. Shipped in a separate follow-up PR (see PR body for link).
3. **Bump `services/alpha/requirements.txt` `aiohttp==3.11.11` → `3.13.4` (or `3.13.5` to match `requirements-test.txt`)** in a focused PR after a manual smoke test of the alpha signal logger. 19 advisories cleared in a single bump. Not shipped here — the alpha service is critical-path trading code and merits a dedicated review pass; out of this PR's scope and outside the auto-bump rule.
4. **Bump `requirements-test.txt` `orjson==3.10.13` → `3.11.6`.** Test-only dep, but it appears in `requirements-test.txt` which is loaded by CI; the recursion-depth DoS only matters if untrusted JSON ever reaches `orjson.loads`, which is plausible for fixtures. Not shipped here because we batch test-deps separately.
5. **Bump `requirements-test.txt` `python-dotenv==1.0.1` → `1.2.2`.** Test-only path; symlink-following in `set_key` is unlikely to be hit in CI but worth closing.
6. **Audit `cryptography==44.0.0` → `46.x`.** Two-major bump; transitive impact on `firebase-admin`, `web3`, `eth-account` and crypto helpers in `lib/portfolio/` and `services/webhook/` should be verified before bumping. Not shipped here — needs an actual integration pass.
7. **Pin lower-bound-only declarations.** `services/dashboard/requirements.txt` (`flask>=2.3.0`, `aiohttp>=3.8.0`, `firebase-admin>=6.2.0`), `services/aster/requirements.txt`, `services/hyperliquid/requirements.txt`, and several others use `>=` floors with no ceiling. OSV cannot scan these and a pip resolution drift can pull a future-CVE'd build silently. Recommend tightening to `~=` or pinning at install time via lockfile.
8. **Wire `tailscale policy check infra/tailscale-acl.json` into CI.** The ACL has a hand-written `tests` block — no current job runs it. A 5-line GitHub Action (run on changes to `infra/tailscale-acl.json`) would catch ACL drift before deployment.
9. **Document the operator-side model verification commands in `docs/security/`** so the model surface is reproducibly auditable. (Already partially captured under "Operator verification" above; could be expanded into a runbook in a follow-up.)

## Caveats

1. **`dependency_scanner` is silently broken on this runtime.** As noted in Action item 1, every `_query_osv` call returned `[]` because the scanner does not pass a CA bundle. To get the findings in this report I re-ran the same request payloads with `ssl.create_default_context(cafile=certifi.where())` outside the scanner. Anything operators see in `data/security/<date>/pipeline.json` from the scheduled `services/security_pipeline/run.py` should be treated as a lower bound until that fix lands. The pipeline itself uses `pip-audit` (a separate tool), so its dep findings are not affected — only direct invocations of `lib.security.dependency_scanner` are.
2. **No live network reachability was used.** `network_mapper.scan(probe_ports=True)` requires TCP connectivity to Tailscale peers; the agent has none. Online status, actual open/closed ports, and any discovered/unverified peers on the tailnet are unknown.
3. **No filesystem access to `~/.ollama`.** Manifest digests, blob SHA-256s, and Jinja2 template content all need the Mac commander's filesystem. The model-surface section is a static reference list, not a verification result.
4. **Unbounded version specs were skipped** for OSV queries. Anything declared as `>=X` could resolve to a newer (clean) version or to a future CVE'd one; the current sweep is inconclusive on those rows.
5. **Severity field came back as `unknown`** for every advisory because the GHSA records returned by OSV did not include a parseable CVSS score in the `severity[]` array for this batch. Severity should be re-derived from the GHSA pages or NVD when prioritising.
6. **Sweep is point-in-time.** OSV continuously publishes new advisories; today's "clear" packages may be flagged tomorrow. The scheduled `dependency-security-scan` cron (Wed 4 AM) is the longitudinal control.
7. **Test framework deps (`pytest`, `pytest-asyncio`, `pytest-cov`) returned no advisories**, but they execute inside CI runners and a future advisory in any of them is high-impact for supply-chain integrity. Worth keeping these on a tight pin and watching Dependabot.
