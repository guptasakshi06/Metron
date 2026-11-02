-- Grants are identifiers, never bearer credentials: every transfer rechecks verified ownership.
CREATE TABLE assessment_downloads (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    bundle_fingerprint text NOT NULL CHECK (bundle_fingerprint ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    UNIQUE (tenant_id, assessment_id, bundle_fingerprint),
    FOREIGN KEY (tenant_id, assessment_id) REFERENCES assessments(tenant_id, id),
    CHECK (expires_at > created_at)
);
