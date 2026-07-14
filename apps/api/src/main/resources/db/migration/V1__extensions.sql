-- Requires the timescale/timescaledb-ha:pg16 image (bundles TimescaleDB + pgvector).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS timescaledb;
