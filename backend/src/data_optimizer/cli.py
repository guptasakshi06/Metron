"""Command-line entry point for the shared application package."""

import argparse
from collections.abc import Sequence

from data_optimizer import __version__
from data_optimizer.config import settings
from data_optimizer.db.migrations import migrate
from data_optimizer.db.seed import seed_local


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="data-optimizer", description="Data Optimizer developer CLI"
    )
    parser.add_argument("--version", action="version", version=f"data-optimizer {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("migrate", help="apply packaged PostgreSQL migrations")
    commands.add_parser("seed-local", help="insert fixed local demo identities")
    args = parser.parse_args(argv)
    if args.command == "migrate":
        applied = migrate(str(settings.database_url))
        print(f"Applied {len(applied)} migration(s): {', '.join(applied) if applied else 'none'}")
    elif args.command == "seed-local":
        seed_local(str(settings.database_url))
        print("Inserted local demo identities (alice, bob) where absent.")


if __name__ == "__main__":
    main()
