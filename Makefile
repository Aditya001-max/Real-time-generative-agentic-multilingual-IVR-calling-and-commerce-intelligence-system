.PHONY: help setup install install-tts run worker test smoke clean docker-up docker-down chatwoot-up

help:
	@echo "AI Call System — common tasks"
	@echo ""
	@echo "  make setup         Interactive first-time setup (recommended)"
	@echo "  make install       Install core dependencies only"
	@echo "  make install-tts   Add Coqui XTTS-v2 (open-source TTS, ~2GB)"
	@echo "  make run           Start the API in dev mode"
	@echo "  make worker        Start the Celery retry worker"
	@echo "  make test          Run unit tests"
	@echo "  make smoke         Run smoke test against a running API"
	@echo "  make docker-up     Start API + Redis + worker via Docker"
	@echo "  make docker-down   Stop everything"
	@echo "  make chatwoot-up   Start open-source ticketing (Chatwoot)"
	@echo "  make clean         Remove caches, build artifacts"

setup:
	@./scripts/setup.sh

install:
	@python3 -m venv .venv 2>/dev/null || true
	@. .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

install-tts:
	@. .venv/bin/activate && pip install -r requirements-tts.txt

run:
	@. .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	@. .venv/bin/activate && celery -A app.workers.celery_worker.celery worker --loglevel=info

test:
	@. .venv/bin/activate && pytest tests/ -v

smoke:
	@./scripts/smoke_test.sh

docker-up:
	@docker compose up -d
	@echo "API: http://localhost:8000/docs"

docker-down:
	@docker compose --profile chatwoot --profile chatwoot-db down

chatwoot-up:
	@docker compose --profile chatwoot up -d
	@echo "Chatwoot: http://localhost:3000  (wait ~30s for first boot)"

clean:
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	@find . -name .pytest_cache -type d -exec rm -rf {} + 2>/dev/null || true
	@rm -f db.sqlite3
