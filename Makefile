# Sapphire OS — developer entrypoints.
# Mac uses /usr/local/bin/python3 (brew 3.14 lacks pytest).
PY ?= /usr/local/bin/python3
RUFF ?= ruff
PYTEST ?= $(PY) -m pytest

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ---------- setup ----------

.PHONY: install install-hooks install-test
install:  ## Install dev tooling (ruff, pytest, pre-commit)
	$(PY) -m pip install -e '.[dev]'

install-test:  ## Install the pinned CI test dep set (matches requirements-test.txt)
	$(PY) -m pip install -r requirements-test.txt

install-hooks:  ## Install pre-commit + commit-msg hooks
	pre-commit install
	pre-commit install --hook-type commit-msg

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

.PHONY: content-generate content-publish heartbeat-status
content-generate:  ## Generate weekly report draft
	$(PY) -m lib.content generate

content-publish:  ## Promote draft → ready/
	$(PY) -m lib.content publish

heartbeat-status:  ## Print heartbeat daemon last known state
	cat data/heartbeat_state.json 2>/dev/null | $(PY) -m json.tool || echo "no heartbeat state yet"

# ---------- CI mirror ----------

.PHONY: ci
ci: lint test test-plugin registry  ## Mirror CI locally (no secrets scan)
	@echo "✓ local CI mirror passed"
