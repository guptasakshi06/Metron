-- Append-only adoption, manual observation revisions and immutable reassessment lineage.
CREATE TABLE migration_plans (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    report_fingerprint text NOT NULL,
    candidate_id text NOT NULL,
    configuration jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id), UNIQUE (tenant_id, assessment_id),
    FOREIGN KEY (tenant_id,assessment_id) REFERENCES assessments(tenant_id,id)
);
CREATE TABLE migration_plan_versions (
    tenant_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    version integer NOT NULL CHECK(version>0),
    payload jsonb NOT NULL,
    actor_principal_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,plan_id,version),
    FOREIGN KEY (tenant_id,plan_id) REFERENCES migration_plans(tenant_id,id)
);
CREATE TABLE observations (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    version integer NOT NULL CHECK(version>0),
    plan_version integer NOT NULL,
    payload jsonb NOT NULL,
    actor_principal_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,plan_id,id,version),
    FOREIGN KEY (tenant_id,plan_id,plan_version)
        REFERENCES migration_plan_versions(tenant_id,plan_id,version)
);
CREATE TABLE reassessment_links (
    tenant_id uuid NOT NULL,
    assessment_id uuid NOT NULL,
    previous_assessment_id uuid NOT NULL,
    reason text NOT NULL CHECK(length(reason) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,assessment_id),
    FOREIGN KEY (tenant_id,assessment_id) REFERENCES assessments(tenant_id,id),
    FOREIGN KEY (tenant_id,previous_assessment_id) REFERENCES assessments(tenant_id,id),
    CHECK(assessment_id<>previous_assessment_id)
);
CREATE TRIGGER immutable_migration_plan BEFORE UPDATE OR DELETE ON migration_plans
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE TRIGGER immutable_plan_versions BEFORE UPDATE OR DELETE ON migration_plan_versions
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE TRIGGER immutable_observations BEFORE UPDATE OR DELETE ON observations
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
CREATE TRIGGER immutable_reassessment_links BEFORE UPDATE OR DELETE ON reassessment_links
FOR EACH ROW EXECUTE FUNCTION protect_evidence_updates();
