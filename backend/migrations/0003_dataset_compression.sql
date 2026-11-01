ALTER TABLE datasets
    ADD COLUMN compression text CHECK (compression IS NULL OR compression IN ('gzip'));
