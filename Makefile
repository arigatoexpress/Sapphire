# Sapphire OS — developer entrypoints.
# Mac uses /usr/local/bin/python3 (brew 3.14 lacks pytest).
PY ?= /usr/local/bin/python3
RUFF ?= ruff
PYTEST ?= $(PY) -m pytest
GOOGLE_PROJECT ?= tho-ai-agent
GOOGLE_REGION ?= us-central1
GOOGLE_MEMBERSHIPS ?= google_developer_premium google_ai_plus
GOOGLE_MEMBERSHIP_ARGS = $(foreach membership,$(GOOGLE_MEMBERSHIPS),--membership $(membership))
GOOGLE_COST_HOURS ?= 24
GOOGLE_COST_LOG_LIMIT ?= 25
GOOGLE_READINESS_OUT ?= data/google/production-readiness/latest.md
PRODUCTION_READINESS_OUT ?= data/readiness/production-readiness-latest.md

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-28s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---------- setup ----------

.PHONY: install install-hooks install-test sapphire-on-fresh-mac sapphire-demo-up sapphire-demo-down sapphire-demo-reset
install:  ## Install dev tooling (ruff, pytest, pre-commit)
	$(PY) -m pip install -e '.[dev]'

install-test:  ## Install the pinned CI test dep set (matches requirements-test.txt)
	$(PY) -m pip install -r requirements-test.txt

install-hooks:  ## Install pre-commit + commit-msg hooks
	pre-commit install
	pre-commit install --hook-type commit-msg

sapphire-on-fresh-mac:  ## Bootstrap a demo-safe fresh Mac checkout
	bash scripts/ops/bootstrap_fresh_mac.sh

sapphire-demo-up: sapphire-on-fresh-mac  ## Prepare demo-safe local files and LaunchAgents

sapphire-demo-down:  ## Remove demo LaunchAgents and fresh-mac venv, preserving secrets
	bash scripts/ops/teardown_fresh_mac.sh

sapphire-demo-reset:  ## Remove demo LaunchAgents, venv, and placeholder secrets only
	SAPPHIRE_BOOTSTRAP_RESET_SECRETS=1 bash scripts/ops/teardown_fresh_mac.sh

# ---------- quality ----------

.PHONY: lint fmt fix test test-plugin test-all typecheck registry doctor
lint:  ## Run ruff check
	$(RUFF) check

fmt:  ## Run ruff format (in place)
	$(RUFF) format .

fix:  ## Run ruff auto-fix + format
	$(RUFF) check --fix
	$(RUFF) format .

test:  ## Run core unit tests
	$(PYTEST) tests/unit/ --tb=short -q

test-plugin:  ## Run claw-sapphire plugin tests
	$(PYTEST) plugins/claw-sapphire/tests/ -q

test-all: test test-plugin  ## Run full test suite

registry:  ## Validate infra/tool-registry.yaml invariants
	$(PY) scripts/validate_tool_registry.py

doctor:  ## Run scripts/ops/doctor.sh — health check of local dev env
	bash scripts/ops/doctor.sh

# ---------- services (Mac) ----------

.PHONY: dashboard control-plane signal-logger inference-proxy
dashboard:  ## Start dashboard :8080 (requires AUTH_PASSWORD)
	cd services/dashboard && AUTH_PASSWORD=$${AUTH_PASSWORD:-sapphire} $(PY) app.py

control-plane:  ## Start control-plane :8082
	cd services/control-plane && $(PY) -m uvicorn app.main:app --port 8082 --reload

signal-logger:  ## Start signal-logger :18081
	cd services/alpha && $(PY) -m uvicorn src.signal_logger:app --port 18081

inference-proxy:  ## Start inference-proxy :11435 (with x402)
	X402_ENABLED=1 $(PY) services/inference-proxy/app.py

# ---------- data / ops ----------

.PHONY: content-generate content-publish heartbeat-status alpha-agent-status safe-merge
.PHONY: google-readiness google-readiness-offline google-readiness-cost google-readiness-artifact
.PHONY: production-readiness production-readiness-offline production-readiness-artifact hermes-runtime-readiness
content-generate:  ## Generate weekly report draft
	$(PY) -m lib.content generate

content-publish:  ## Promote draft → ready/
	$(PY) -m lib.content publish

google-readiness:  ## Print live read-only Google/GCP production-test readiness
	$(PY) scripts/ops/google_production_test_readiness.py \
		--project $(GOOGLE_PROJECT) \
		--region $(GOOGLE_REGION) \
		$(GOOGLE_MEMBERSHIP_ARGS) \
		--format markdown

google-readiness-offline:  ## Print no-external Google/GCP production-test readiness
	$(PY) scripts/ops/google_production_test_readiness.py --no-external --format markdown

google-readiness-cost:  ## Print live read-only readiness with cost posture
	$(PY) scripts/ops/google_production_test_readiness.py \
		--project $(GOOGLE_PROJECT) \
		--region $(GOOGLE_REGION) \
		$(GOOGLE_MEMBERSHIP_ARGS) \
		--include-cost \
		--cost-hours $(GOOGLE_COST_HOURS) \
		--cost-log-limit $(GOOGLE_COST_LOG_LIMIT) \
		--format markdown

google-readiness-artifact:  ## Write ignored readiness artifact with cost posture
	$(PY) scripts/ops/google_production_test_readiness.py \
		--project $(GOOGLE_PROJECT) \
		--region $(GOOGLE_REGION) \
		$(GOOGLE_MEMBERSHIP_ARGS) \
		--include-cost \
		--cost-hours $(GOOGLE_COST_HOURS) \
		--cost-log-limit $(GOOGLE_COST_LOG_LIMIT) \
		--output $(GOOGLE_READINESS_OUT)

production-readiness:  ## Print full-system read-only production readiness matrix
	$(PY) scripts/ops/production_readiness_matrix.py \
		--project $(GOOGLE_PROJECT) \
		--region $(GOOGLE_REGION) \
		$(GOOGLE_MEMBERSHIP_ARGS) \
		--include-cost \
		--format markdown

production-readiness-offline:  ## Print full-system no-external readiness matrix
	$(PY) scripts/ops/production_readiness_matrix.py --no-external --format markdown

production-readiness-artifact:  ## Write ignored full-system readiness matrix
	$(PY) scripts/ops/production_readiness_matrix.py \
		--project $(GOOGLE_PROJECT) \
		--region $(GOOGLE_REGION) \
		$(GOOGLE_MEMBERSHIP_ARGS) \
		--include-cost \
		--output $(PRODUCTION_READINESS_OUT)

hermes-runtime-readiness:  ## Print read-only Hermes runtime guard readiness
	$(PY) scripts/ops/hermes_runtime_readiness.py --format markdown

heartbeat-status:  ## Print heartbeat daemon last known state
	cat data/heartbeat_state.json 2>/dev/null | $(PY) -m json.tool || echo "no heartbeat state yet"

alpha-agent-status:  ## Show recent alpha agent logs and latest heartbeat
	@mkdir -p /Users/aribs/Library/Logs/sapphire
	@echo "== alpha-agent.out (last 40 lines) =="
	@tail -n 40 /Users/aribs/Library/Logs/sapphire/alpha-agent.out 2>/dev/null || echo "no alpha-agent stdout log yet"
	@echo
	@echo "== alpha-agent.err (last 40 lines) =="
	@tail -n 40 /Users/aribs/Library/Logs/sapphire/alpha-agent.err 2>/dev/null || echo "no alpha-agent stderr log yet"
	@echo
	@echo "== data/agents/alpha.heartbeat =="
	@if test -s data/agents/alpha.heartbeat; then \
		$(PY) -m json.tool data/agents/alpha.heartbeat; \
	else \
		echo "no alpha heartbeat yet"; \
	fi

safe-merge:  ## Squash-merge PR=<number> with explicit [skip ci] subject and scoped run cancellation
	@test -n "$(PR)" || (echo "Usage: make safe-merge PR=<number>" >&2; exit 2)
	$(PY) scripts/ops/sapphire_safe_merge.py "$(PR)"

# ---------- CI mirror ----------

.PHONY: ci
ci: lint test test-plugin registry  ## Mirror CI locally (no secrets scan)
	@echo "✓ local CI mirror passed"


# --- Grok project ---
.PHONY: grok-status grok-loop grok-bridge grok-test
grok-status:
	python3 scripts/ops/grok_project_status.py

grok-loop:
	python3 scripts/ops/grok_loop_tick.py --write

grok-bridge:
	python3 scripts/ops/grok_bridge_status.py --write-manifest

grok-test:
	python3 -m pytest tests/unit/test_grok_policy.py tests/unit/test_grok_genome.py tests/unit/test_grok_research_worker.py tests/unit/test_grok_windows.py tests/unit/test_grok_loop.py tests/unit/test_grok_bridge_status.py -q
