from hashlib import sha256

from data_optimizer.db.migrations import MIGRATION_NAME, migration_files


def test_packaged_migrations_are_ordered_and_checksummed() -> None:
    migrations = migration_files()
    names = [name for name, _, _ in migrations]
    assert names == sorted(names)
    assert names[0] == "0001_tenant_ingestion.sql"
    for name, content, checksum in migrations:
        assert MIGRATION_NAME.fullmatch(name)
        assert checksum == sha256(content.encode()).hexdigest()
        assert "CREATE TABLE" in content
