CREATE TABLE IF NOT EXISTS factory_workloads (
    workload_id VARCHAR(64) PRIMARY KEY,
    tenant VARCHAR(128) NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    document TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_factory_workloads_tenant
    ON factory_workloads (tenant);

CREATE TABLE IF NOT EXISTS integration_outbox (
    message_id VARCHAR(64) PRIMARY KEY,
    destination VARCHAR(128) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL,
    last_error VARCHAR(256) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS ix_integration_outbox_pending
    ON integration_outbox (status, available_at);
