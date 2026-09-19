CREATE TABLE IF NOT EXISTS factory_workloads (
    workload_id VARCHAR(64) PRIMARY KEY,
    tenant VARCHAR(128) NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    document TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_factory_workloads_tenant
    ON factory_workloads (tenant);
