CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id)
);

CREATE TABLE principals (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    issuer text NOT NULL,
    subject text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject),
    UNIQUE (tenant_id, id)
);

CREATE TABLE projects (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    owner_principal_id uuid NOT NULL,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
    business_context text,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, owner_principal_id) REFERENCES principals(tenant_id, id)
);

CREATE TABLE datasets (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    project_id uuid NOT NULL,
    previous_dataset_id uuid,
    version integer NOT NULL CHECK (version > 0),
    state text NOT NULL CHECK (state IN ('pending', 'ready', 'delete_pending', 'deleted', 'failed')),
    declared_format text NOT NULL CHECK (declared_format IN ('csv', 'ndjson', 'parquet')),
    detected_format text CHECK (detected_format IN ('csv', 'ndjson', 'parquet')),
    display_filename text NOT NULL,
    declared_semantics jsonb NOT NULL DEFAULT '{}'::jsonb,
    original_bytes bigint CHECK (original_bytes >= 0),
    decompressed_bytes bigint CHECK (decompressed_bytes >= 0),
    sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    retention_days integer NOT NULL CHECK (retention_days BETWEEN 1 AND 30),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    deleted_at timestamptz,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, project_id, version),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id),
    FOREIGN KEY (tenant_id, previous_dataset_id) REFERENCES datasets(tenant_id, id),
    CHECK ((state <> 'ready') OR (detected_format IS NOT NULL AND original_bytes IS NOT NULL AND sha256 IS NOT NULL))
);

CREATE TABLE upload_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    state text NOT NULL CHECK (state IN ('pending', 'receiving', 'uploaded', 'validating', 'complete', 'failed', 'delete_pending', 'deleted')),
    expected_bytes bigint CHECK (expected_bytes >= 0),
    expected_sha256 text CHECK (expected_sha256 IS NULL OR expected_sha256 ~ '^[0-9a-f]{64}$'),
    object_key text NOT NULL UNIQUE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, dataset_id) REFERENCES datasets(tenant_id, id)
);

CREATE TABLE artifacts (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    dataset_id uuid NOT NULL,
    upload_session_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('original')),
    state text NOT NULL CHECK (state IN ('staging', 'ready', 'delete_pending', 'deleted')),
    object_key text NOT NULL UNIQUE,
    byte_count bigint CHECK (byte_count >= 0),
    sha256 text CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, dataset_id) REFERENCES datasets(tenant_id, id),
    FOREIGN KEY (tenant_id, upload_session_id) REFERENCES upload_sessions(tenant_id, id)
);

CREATE TABLE requirements_snapshots (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    contract_version integer NOT NULL CHECK (contract_version > 0),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, project_id, version),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id)
);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    actor_principal_id uuid,
    resource_type text NOT NULL,
    resource_id uuid NOT NULL,
    action text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (tenant_id, actor_principal_id) REFERENCES principals(tenant_id, id)
);

CREATE INDEX projects_tenant_created_idx ON projects(tenant_id, created_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX datasets_project_idx ON datasets(tenant_id, project_id, version DESC);
CREATE INDEX upload_sessions_expiry_idx ON upload_sessions(state, expires_at);
CREATE INDEX artifacts_dataset_idx ON artifacts(tenant_id, dataset_id);
CREATE INDEX audit_events_resource_idx ON audit_events(tenant_id, resource_type, resource_id, created_at DESC);
