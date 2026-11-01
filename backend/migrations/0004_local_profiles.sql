-- Local metadata is user-supplied evidence; no server raw-dataset inspection is claimed.
CREATE TABLE profiles (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    contract_version integer NOT NULL CHECK (contract_version = 1),
    profile_fingerprint text NOT NULL CHECK (profile_fingerprint ~ '^[0-9a-f]{64}$'),
    input_fingerprint text NOT NULL CHECK (input_fingerprint ~ '^[0-9a-f]{64}$'),
    schema_fingerprint text NOT NULL CHECK (schema_fingerprint ~ '^[0-9a-f]{64}$'),
    settings_fingerprint text NOT NULL CHECK (settings_fingerprint ~ '^[0-9a-f]{64}$'),
    evidence text NOT NULL CHECK (evidence = 'local_profile'),
    raw_data_inspected_by_server boolean NOT NULL DEFAULT false
        CHECK (raw_data_inspected_by_server = false),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, project_id, version),
    UNIQUE (tenant_id, project_id, profile_fingerprint),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id)
);
CREATE INDEX profiles_project_idx ON profiles(tenant_id, project_id, version DESC);
