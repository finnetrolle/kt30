PYTHON ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
GUNICORN ?= gunicorn
APP_ENV ?= development
PORT ?= 8000
TEST_MODULES ?= \
	tests.test_progress_tracker \
	tests.test_app_security \
	tests.test_job_queue \
	tests.test_rate_limiter \
	tests.test_task_api

.PHONY: install compile test test-all run-web run-worker run-gunicorn \
	health-web health-worker smoke docker-build compose-up compose-build \
	compose-down compose-logs ci

install:
	$(PYTHON) -m pip install -r requirements.txt

compile:
	$(PYTHON) -m compileall app.py config.py analysis_jobs.py job_queue.py job_worker.py rate_limiter.py worker.py ops tests

test:
	APP_ENV=testing $(PYTHON) -m unittest $(TEST_MODULES)

test-all:
	APP_ENV=testing $(PYTHON) -m unittest discover -s tests

run-web:
	APP_ENV=$(APP_ENV) $(PYTHON) app.py

run-worker:
	APP_ENV=$(APP_ENV) $(PYTHON) worker.py

run-gunicorn:
	APP_ENV=production EMBEDDED_WORKER_ENABLED=false $(GUNICORN) --bind 0.0.0.0:$(PORT) --workers 2 --threads 4 --worker-class gthread --timeout 120 --graceful-timeout 120 app:app

health-web:
	$(PYTHON) ops/healthcheck_web.py

health-worker:
	$(PYTHON) ops/healthcheck_worker.py

smoke: health-web health-worker

docker-build:
	docker build -t kt30:local .

compose-up:
	docker compose up -d

compose-build:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f app worker

ci: compile test-all docker-build
