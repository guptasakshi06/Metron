-- PostgreSQL is the business record and transactional dispatch outbox.
ALTER TABLE datasets ADD UNIQUE (tenant_id, project_id, id);
ALTER TABLE profiles ADD UNIQUE (tenant_id, project_id, id);
ALTER TABLE requirements_snapshots ADD UNIQUE (tenant_id, project_id, id);
CREATE TABLE assessments (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    dataset_id uuid,
    profile_id uuid,
    requirements_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 1 AND 128),
    input_fingerprint text NOT NULL,
    request_fingerprint text NOT NULL,
    request jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('needs_input','queued','profiling','benchmarking','scoring','completed','failed','cancelled')),
    progress jsonb NOT NULL DEFAULT '{}'::jsonb,
    attempts integer NOT NULL DEFAULT 0,
    cancel_requested boolean NOT NULL DEFAULT false,
    lease_token uuid,
    lease_until timestamptz,
    dispatch_after timestamptz NOT NULL DEFAULT now(),
    dispatched_at timestamptz,
    stop_reason text,
    result_key text,
    result_sha256 text,
    result_bytes bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    cleaned_at timestamptz,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id),
    FOREIGN KEY (tenant_id, project_id, dataset_id) REFERENCES datasets(tenant_id, project_id, id),
    FOREIGN KEY (tenant_id, project_id, profile_id) REFERENCES profiles(tenant_id, project_id, id),
    FOREIGN KEY (tenant_id, project_id, requirements_id) REFERENCES requirements_snapshots(tenant_id, project_id, id),
    CHECK (dataset_id IS NULL OR profile_id IS NULL)
);
-- Versioned append-only snapshots bind server profiles, candidate manifests, raw
-- experiments, prices and recommendations to the same immutable assessment input.
CREATE TABLE assessment_evidence (
    tenant_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    kind text NOT NULL CHECK (kind IN ('profile','candidates','experiment','price_snapshot','recommendation')),
    fingerprint text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, assessment_id, kind, fingerprint),
    FOREIGN KEY (tenant_id, assessment_id) REFERENCES assessments(tenant_id, id)
);
CREATE FUNCTION protect_assessment_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.tenant_id, NEW.project_id, NEW.dataset_id, NEW.profile_id, NEW.requirements_id,
        NEW.idempotency_key, NEW.input_fingerprint, NEW.request_fingerprint, NEW.request)
       IS DISTINCT FROM
       (OLD.tenant_id, OLD.project_id, OLD.dataset_id, OLD.profile_id, OLD.requirements_id,
        OLD.idempotency_key, OLD.input_fingerprint, OLD.request_fingerprint, OLD.request)
    THEN RAISE EXCEPTION 'assessment inputs are immutable'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER immutable_assessment_inputs BEFORE UPDATE ON assessments
FOR EACH ROW EXECUTE FUNCTION protect_assessment_inputs();
CREATE FUNCTION protect_evidence_updates() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'assessment evidence is immutable'; END $$;
CREATE TRIGGER immutable_assessment_evidence BEFORE UPDATE ON assessment_evidence
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE TRIGGER immutable_requirements_snapshot BEFORE UPDATE ON requirements_snapshots
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE INDEX assessments_dispatch_idx ON assessments(dispatch_after, created_at)
WHERE status IN ('queued','profiling','benchmarking','scoring');
CREATE INDEX assessments_tenant_status_idx ON assessments(tenant_id, status);
