ALTER TABLE datasets
    ADD CONSTRAINT datasets_tenant_project_id_unique UNIQUE (tenant_id, project_id, id),
    ADD CONSTRAINT datasets_previous_same_project_fk
        FOREIGN KEY (tenant_id, project_id, previous_dataset_id)
        REFERENCES datasets (tenant_id, project_id, id);

ALTER TABLE upload_sessions
    ADD CONSTRAINT upload_sessions_tenant_dataset_id_unique
        UNIQUE (tenant_id, dataset_id, id);

ALTER TABLE artifacts
    ADD CONSTRAINT artifacts_upload_same_dataset_fk
        FOREIGN KEY (tenant_id, dataset_id, upload_session_id)
        REFERENCES upload_sessions (tenant_id, dataset_id, id);
