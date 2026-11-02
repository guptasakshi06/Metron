"""Separate local dispatcher and RQ worker commands; no credentials in queue messages."""

from __future__ import annotations

import argparse
import logging
import time

from redis import Redis
from rq import Worker
from rq.serializers import JSONSerializer

from data_optimizer.config import settings
from data_optimizer.jobs.service import cleanup, dispatch, queue


def add_commands(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in ("worker", "dispatch-jobs"):
        command = commands.add_parser(name)
        command.add_argument("--once", action="store_true", help="burst/one reconciliation pass")
    commands.add_parser("cleanup-assessments")
    commands.add_parser("job-metrics")


def run(args: argparse.Namespace) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "cleanup-assessments":
        print(f"Cleaned {cleanup(settings)} assessment workspaces/results")
    elif args.command == "job-metrics":
        import json

        import psycopg

        with psycopg.connect(str(settings.database_url)) as db:
            rows = db.execute(
                "SELECT status,count(*),max(extract(epoch from now()-created_at)) "
                "FROM assessments GROUP BY status"
            ).fetchall()
        print(
            json.dumps(
                [{"status": s, "count": n, "oldest_age_seconds": float(age)} for s, n, age in rows]
            )
        )
    elif args.command == "worker":
        Worker(
            [queue(settings)],
            connection=Redis.from_url(str(settings.redis_url)),
            serializer=JSONSerializer,
        ).work(burst=args.once, logging_level="WARNING")
    else:
        while True:
            try:
                dispatch(settings)
            except Exception:
                # Never log exception text: connection URLs may contain credentials.
                logging.warning("dispatch_dependency_unavailable")
                if args.once:
                    raise SystemExit(1) from None
            if args.once:
                return
            time.sleep(2)
