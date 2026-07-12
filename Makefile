# AI 销售助手 — 常用命令（详见 CLAUDE.md）
.PHONY: dev test lint eval migrate seed gen-api

dev:
	docker compose up --build

test:
	cd backend && uv run pytest -m "not eval"
	cd frontend && npm run test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests scripts
	cd frontend && npm run lint && npm run typecheck

eval:
	cd backend && uv run pytest evals -m eval

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python scripts/seed.py

gen-api:
	cd backend && uv run python -m scripts.export_openapi ../frontend/openapi.json
	cd frontend && npm run gen-api

e2e:  # 需要后端已起且已 seed
	cd frontend && npm run e2e

prod:
	docker compose -f docker-compose.prod.yml up -d --build
