-- Assistance is separate from authoritative metrics and immutable accepted requirements.
CREATE TABLE intake_proposals (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, project_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id)
);
CREATE TABLE intake_confirmations (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    proposal_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    accepted_request jsonb NOT NULL,
    requirements_fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, version),
    FOREIGN KEY (tenant_id, project_id, proposal_id)
        REFERENCES intake_proposals(tenant_id, project_id, id)
);
CREATE TABLE assistance_usage (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    project_id uuid NOT NULL,
    scope_id uuid NOT NULL,
    reserved_tokens integer NOT NULL CHECK (reserved_tokens > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id)
);
CREATE INDEX assistance_scope_idx ON assistance_usage(tenant_id, scope_id);
ALTER TABLE assessments ADD COLUMN intake_confirmation_id uuid;
ALTER TABLE assessments ADD FOREIGN KEY (tenant_id, project_id, intake_confirmation_id)
    REFERENCES intake_confirmations(tenant_id, project_id, id);
CREATE TRIGGER immutable_intake_proposals BEFORE UPDATE ON intake_proposals
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE TRIGGER immutable_intake_confirmations BEFORE UPDATE ON intake_confirmations
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE FUNCTION protect_intake_reference() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.intake_confirmation_id IS DISTINCT FROM OLD.intake_confirmation_id
    THEN RAISE EXCEPTION 'intake confirmation is immutable'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER immutable_intake_reference BEFORE UPDATE ON assessments
FOR EACH ROW EXECUTE FUNCTION protect_intake_reference();
