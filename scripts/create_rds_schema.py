#!/usr/bin/env python3

import argparse
from pathlib import Path
import re
import sys

import pymysql

REPO_ROOT = Path(__file__).resolve().parents[1]
PLATFORM_BACKEND = REPO_ROOT / "platform" / "backend"
sys.path.insert(0, str(PLATFORM_BACKEND))

from schema_app import ensure_core_schema, schema_status, seed_core_data


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create the Bug Daddy platform schema, microservice tables, and seed/reference rows."
    )
    parser.add_argument("--host", required=True, help="RDS endpoint hostname")
    parser.add_argument("--port", type=int, default=3306, help="MySQL port")
    parser.add_argument("--user", required=True, help="MySQL username")
    parser.add_argument("--password", required=True, help="MySQL password")
    parser.add_argument("--schema", default="bug_daddy", help="Schema name")
    parser.add_argument("--no-seed", action="store_true", help="Create tables without inserting demo/reference rows")
    return parser.parse_args()


def main():
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.schema):
        print("Schema name may only contain letters, numbers, and underscores", file=sys.stderr)
        return 1

    try:
        connection = pymysql.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=10,
        )
    except Exception as exc:
        print(f"Failed to connect to MySQL: {exc}", file=sys.stderr)
        return 1

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{args.schema}`")
            cursor.execute(f"USE `{args.schema}`")
        ensure_core_schema(connection)
        if not args.no_seed:
            seed_core_data(connection)
        status = schema_status(connection)
        created = status["tables"].get("service_exception_log", -1) >= 0
    finally:
        connection.close()

    if created:
        table_count = len(status["tables"])
        seeded_count = sum(max(0, value) for value in status["tables"].values())
        print(f"Created or verified {table_count} tables in {args.schema} on {args.host}")
        print(f"Reference/demo rows visible across tracked tables: {seeded_count}")
        return 0

    print(
        f"Schema {args.schema} was not verified after creation attempt",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
