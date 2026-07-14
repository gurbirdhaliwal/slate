# Slate — dev shortcuts. Production runs everything via docker-compose.yml.

.PHONY: up down infra api worker dashboard test-worker build

## Local infra only (Postgres + MinIO) — run api/worker/dashboard natively against it
infra:
	docker compose up -d postgres minio minio-init

## Full stack in containers
up:
	docker compose up -d --build

down:
	docker compose down

## Run each service natively for development
api:
	cd apps/api && mvn spring-boot:run

worker:
	cd apps/worker && pip install -e ".[dev]" -q && slate-worker

dashboard:
	cd apps/dashboard && npm install --no-audit --no-fund && npm run dev

test-worker:
	cd apps/worker && python -m pytest tests/ -q

build:
	cd apps/api && mvn -q -DskipTests package
	cd apps/dashboard && npm run build
