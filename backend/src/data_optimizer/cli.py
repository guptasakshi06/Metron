"""Command-line entry point for the shared application package."""

import argparse
from collections.abc import Sequence

from data_optimizer import __version__
from data_optimizer.config import settings
from data_optimizer.db.migrations import migrate
from data_optimizer.db.seed import seed_local
from data_optimizer.storage.retention import cleanup_expired
from data_optimizer.storage.s3 import S3Storage


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="data-optimizer", description="Data Optimizer developer CLI"
    )
    parser.add_argument("--version", action="version", version=f"data-optimizer {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("migrate", help="apply packaged PostgreSQL migrations")
    commands.add_parser("seed-local", help="insert fixed local demo identities")
    commands.add_parser("storage-init", help="create the configured private artifact bucket")
    commands.add_parser("cleanup-expired", help="retry expired artifact deletion")
    args = parser.parse_args(argv)
    if args.command == "migrate":
        applied = migrate(str(settings.database_url))
        print(f"Applied {len(applied)} migration(s): {', '.join(applied) if applied else 'none'}")
    elif args.command == "seed-local":
        if settings.auth_mode != "local" or settings.app_env != "development":
            parser.error("seed-local is allowed only with local authentication in development")
        seed_local(str(settings.database_url))
        print("Inserted local demo identities (alice, bob) where absent.")
    elif args.command == "storage-init":
        S3Storage(settings).ensure_bucket()
        print(f"Initialized private bucket {settings.s3_bucket}.")
    elif args.command == "cleanup-expired":
        deleted, failed = cleanup_expired(settings)
        print(f"Deleted {deleted} artifact(s); {failed} remain pending for retry.")


if __name__ == "__main__":
    main()
