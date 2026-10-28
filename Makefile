# DevSync commands (spec §16.6). Run `make help` for the list.
# Everything Python runs in containers (python:3.12); the host needs Docker, Node 20, make.

SHELL := /bin/bash
COMPOSE      := docker compose -f docker-compose.yml -f docker-compose.dev.yml
COMPOSE_TEST := docker compose -p devsync-test -f docker-compose.yml -f docker-compose.test.yml
# Demo-day stack (spec §17.0): production settings, two API replicas, offline (Mailpit).
COMPOSE_DEMO := DEVSYNC_DB_NAME=devsync_demo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.demo.yml
PYTEST       := $(COMPOSE_TEST) run --rm tests pytest
PHASE ?= $(shell p=$$(cat .phase 2>/dev/null); [ "$$p" = "none" -o -z "$$p" ] && echo 0 || echo $$p)

.DEFAULT_GOAL := help
.PHONY: help env certs up down logs migrate build lock openapi seed-demo create-admin \
	test test-unit test-backend test-frontend e2e a11y visual visual-update stills security fuzz zap \
	load chaos gate demo-check demo-up demo-down demo-reset demo-preflight erd experiments backup \
	restore-drill docs test-stack-up test-stack-down deps-update ledger-report \
	question-bank question-checks demo-answer-key

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

erd: ## Generate docs/design/erd.svg from the models (spec §17.0)
	$(COMPOSE_TEST) run --rm --no-deps -v $(CURDIR)/docs:/docs-rw -e ERD_PATH=/docs-rw/design/erd.svg tests python scripts/gen_erd.py

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

DEMO_STAGE ?= $(or $(STAGE),1)
# Seeded passwords are random and printed once; DEMO_PASSWORD=… (12+ characters) gives every
# demo account that one password for rehearsals.
DEMO_ACCOUNTS = runs/demos/accounts-$(DEMO_STAGE).txt

# The demo targets run one-off containers with --no-deps, so they never recreate a running
# stack's services (Postgres must be up: `make demo-up`).
seed-demo: ## Load demo data for a stage on the demo stack: make seed-demo STAGE=1 (spec §18)
	@mkdir -p runs/demos
	umask 077; $(COMPOSE_DEMO) run --rm --no-deps -T -e DEMO_PASSWORD worker \
	  python scripts/seed_demo.py --stage $(DEMO_STAGE) | tee $(DEMO_ACCOUNTS); exit $${PIPESTATUS[0]}

demo-reset: ## Reset and reload the demo seed (prints accounts): make demo-reset STAGE=1
	$(COMPOSE_DEMO) run --rm --no-deps migrate
	$(COMPOSE_DEMO) run --rm --no-deps --entrypoint python migrate scripts/demo_reset.py
	@rm -f $(DEMO_ACCOUNTS)
	@$(MAKE) --no-print-directory seed-demo STAGE=$(DEMO_STAGE)

demo-up: ## Start the production-style demo stack and load the seed: make demo-up STAGE=1 (§17.0)
	@test -s infra/nginx/certs/dev.crt || infra/nginx/make-certs.sh
	$(COMPOSE_DEMO) up -d --build --wait
	@$(MAKE) --no-print-directory demo-reset STAGE=$(DEMO_STAGE)
	@echo "Demo ready: https://localhost   Mailpit (emails and texts): http://127.0.0.1:8025   accounts: $(DEMO_ACCOUNTS)"

demo-down: ## Stop the demo stack (data kept; `make up` returns to development)
	$(COMPOSE_DEMO) down

demo-answer-key: ## Operator answer key on a 2nd screen: DEVSYNC_DEMO_TOOLS=1 make demo-answer-key USER=rafsan
	@python3 backend/scripts/demo_answer_key.py --user $(USER) --watch

demo-preflight: ## Pre-presentation checks (Docker, replicas, ports, cert trust, disk, seed)
	@python3 backend/scripts/demo_preflight.py --stage $(DEMO_STAGE)

demo-check: ## Full Demo-N readiness: gates, seed, walkthrough x3 on 4 browsers, report (§17.0)
	@python3 backend/scripts/demo_check.py --demo $(or $(DEMO),1)

# Contract fuzzing (spec §16.1, §16.6): schemathesis against the OpenAPI document — anonymous,
# signed in as each role, and the stateful create → publish → bid → edit → withdraw sequence —
# plus the hypothesis property tests of the algorithms. Seeded, so two runs generate the same
# requests. FUZZ_EXAMPLES / FUZZ_AUTH_EXAMPLES / FUZZ_STATEFUL_EXAMPLES change the budget
# (the gate's step 11 uses the defaults: 200 per operation anonymous, 20 per role, 8 sequences).
# Question bank (role assessment spec §13): YAML sources → frozen seed, and the execution checks
# of every code question against a throwaway PostgreSQL 16 (the stack's own image) on the host.
QCHECK_PG := postgres:16@sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d
QCHECK_PORT ?= 55432
QCHECK_NAME := devsync-qcheck-pg-$(QCHECK_PORT)
QCHECK_PY := $(if $(wildcard backend/.venv/bin/python),backend/.venv/bin/python,python3)
question-bank: ## Validate the question bank YAML and rebuild alembic/seed/question_bank_v2.json
	$(QCHECK_PY) backend/scripts/build_question_bank.py

question-checks: ## Run every code question's execution check (Python, Node, PostgreSQL)
	@docker rm -f $(QCHECK_NAME) >/dev/null 2>&1 || true
	@docker run -d --rm --name $(QCHECK_NAME) -e POSTGRES_PASSWORD=qcheck \
	  -p 127.0.0.1:$(QCHECK_PORT):5432 $(QCHECK_PG) >/dev/null
	@for i in $$(seq 1 60); do docker exec $(QCHECK_NAME) pg_isready -q -U postgres && break; sleep 1; done
	@status=0; QCHECK_DSN=postgresql://postgres:qcheck@127.0.0.1:$(QCHECK_PORT)/postgres \
	  $(QCHECK_PY) backend/scripts/question_checks/run_checks.py $(if $(ONLY),--only $(ONLY)) \
	  $(if $(JSON),--json $(JSON)) || status=$$?; \
	  docker rm -f $(QCHECK_NAME) >/dev/null; exit $$status

fuzz: test-stack-up ## Contract fuzzing (schemathesis) + property tests on the test stack
	$(COMPOSE_TEST) run --rm -T \
	  -e FUZZ_EXAMPLES -e FUZZ_AUTH_EXAMPLES -e FUZZ_STATEFUL_EXAMPLES -e FUZZ_STATEFUL_STEPS \
	  tests pytest -q -p no:cacheprovider -m "fuzz or property" $(PYTEST_ARGS)

zap load chaos experiments backup restore-drill docs deps-update ledger-report: ## Arrive in later phases
	@echo "make $@: available from the phase that builds it (see DEVSYNC_BUILD_SPEC.md §16.6 / §17)"
