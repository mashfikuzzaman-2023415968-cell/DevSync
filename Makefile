# DevSync commands (spec §16.6). Run `make help` for the list.
# Everything Python runs in containers (python:3.12); the host needs Docker, Node 20, make.

SHELL := /bin/bash
COMPOSE      := docker compose -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_TEST := docker compose -p devsync-test -f docker-compose.yml -f docker-compose.test.yml
PYTEST       := $(COMPOSE_TEST) run --rm tests pytest
PHASE ?= $(shell p=$$(cat .phase 2>/dev/null); [ "$$p" = "none" -o -z "$$p" ] && echo 0 || echo $$p)

.DEFAULT_GOAL := help
.PHONY: help env certs up down logs migrate build lock openapi seed-demo create-admin \
	test test-unit test-backend test-frontend e2e a11y visual visual-update stills security fuzz zap \
	load chaos gate demo-check demo-up demo-reset demo-preflight erd experiments backup \
	restore-drill docs test-stack-up test-stack-down deps-update ledger-report

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-16s %s\n", $$1, $$2}'

env: ## Generate .env with strong random secrets (FORCE=1 to regenerate)
	@python3 backend/scripts/gen_env.py $(if $(FORCE),--force,)

certs: ## Create dev TLS certificate (mkcert if installed, else openssl)
	@FORCE=$(FORCE) infra/nginx/make-certs.sh

build: ## Build all images
	$(COMPOSE) build

up: ## Start the development stack (https://localhost)
	$(COMPOSE) up -d --build
	@echo "DevSync: https://localhost   Mailpit: http://127.0.0.1:8025"

down: ## Stop the development stack
	$(COMPOSE) down

logs: ## Follow logs
	$(COMPOSE) logs -f --tail=100

migrate: ## Apply database migrations (role devsync_migrator)
	$(COMPOSE) run --rm migrate

lock: ## Re-resolve hashed Python lock files (DECISIONS D1)
	cd backend && uv pip compile requirements.in --python-version 3.12 --generate-hashes -o requirements.lock
	cd backend && uv pip compile requirements-dev.in --python-version 3.12 --generate-hashes -o requirements-dev.lock

openapi: ## Regenerate docs/api/openapi.json from the code
	$(COMPOSE_TEST) run --rm --no-deps -v $(CURDIR)/docs:/docs-rw -e OPENAPI_PATH=/docs-rw/api/openapi.json tests python scripts/check_openapi.py --write

test-stack-up: ## Start the ephemeral test stack (used by tests and the gate)
	$(COMPOSE_TEST) up -d --build --wait postgres redis api nginx

test-stack-down: ## Remove the ephemeral test stack
	$(COMPOSE_TEST) down -v --remove-orphans

test: test-backend test-frontend ## Fast backend + frontend tests

test-unit: ## Unit tests only (backend + frontend)
	$(PYTEST) -m unit -q
	cd frontend && npm run test -- --run

test-backend: test-stack-up ## Backend tests (all but perf/chaos/edge)
	$(PYTEST) -m "not perf and not chaos and not edge" -q

test-frontend: ## Frontend unit/component tests
	cd frontend && npm run test -- --run

e2e: ## Playwright end-to-end tests against the test stack
	cd frontend && npm run e2e

a11y: ## Accessibility checks (axe) in Playwright
	cd frontend && npm run e2e -- --grep @a11y

security: ## Static security scans + security tests
	python3 backend/scripts/phase_gate.py --only static-security,forbidden --phase $(PHASE)

gate: ## Run the phase gate: make gate PHASE=N
	python3 backend/scripts/phase_gate.py --phase $(PHASE)

PW_IMAGE := mcr.microsoft.com/playwright:v1.63.0-noble
PW_RUN = docker run --rm -v $(CURDIR)/frontend:/web -w /web -e HOME=/tmp --user $$(id -u):$$(id -g) --ipc=host

stills: ## Re-render the 3D stills and social preview (spec §13.13)
	$(PW_RUN) $(PW_IMAGE) node scripts/render-stills.mjs

visual: ## Visual regression against committed baselines (gate step 15)
	python3 backend/scripts/phase_gate.py --phase $$(cat .phase) --only build,visual

visual-update: ## Re-create visual baselines in the pinned image (review the diff before committing)
	cd frontend && VITE_DEV_TOOLS=1 npx vite build --outDir dist-kit --emptyOutDir
	$(PW_RUN) --network container:$$($(COMPOSE_TEST) ps -q nginx) -e E2E_BASE_URL=https://localhost:8443 -e KIT_URL=http://127.0.0.1:4173 $(PW_IMAGE) \
	  sh -c "npx vite preview --outDir dist-kit --port 4173 --host 127.0.0.1 >/tmp/kit.log 2>&1 & sleep 3; npx playwright test --grep @visual --project chromium --update-snapshots"

create-admin: ## Create an administrator (prints TOTP setup and recovery codes once)
	$(COMPOSE) run --rm worker python scripts/create_admin.py

seed-demo fuzz zap load chaos demo-check demo-up demo-reset demo-preflight erd experiments backup restore-drill docs deps-update ledger-report: ## Arrive in later phases
	@echo "make $@: available from the phase that builds it (see DEVSYNC_BUILD_SPEC.md §16.6 / §17)"
