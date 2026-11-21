PYTHON := .venv/bin/python

.PHONY: setup dev test build eval docker deploy
setup:
	uv venv --python 3.11 .venv
	uv pip sync --python $(PYTHON) backend/requirements.txt
	npm --prefix frontend ci

dev:
	$(PYTHON) scripts/dev.py

test:
	$(PYTHON) -m pytest backend/tests -q
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

build:
	npm --prefix frontend run build
	$(PYTHON) -m compileall -q backend/app

eval:
	$(PYTHON) eval/run_eval.py

docker:
	docker build -t shikayat .

deploy:
	@echo "Deployment pending: configure EC2, DOMAIN and Caddy first. See README.md."

# Sends real demo emails and confirms the synthetic demo receipt.
.PHONY: warm
warm:
	$(PYTHON) scripts/demo_e2e.py
