#!/usr/bin/env python3

import argparse
import sys

import pymysql


TABLE_SQL = """
CREATE TABLE IF NOT EXISTS {schema}.service_exception_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  fingerprint VARCHAR(255) NOT NULL,
  service_name VARCHAR(255) NOT NULL,
  issue_type VARCHAR(255) NOT NULL,
  source VARCHAR(64) NOT NULL COMMENT 'cloudwatch / sonarqube / cve / techdebt',
  description TEXT,
  stack_trace LONGTEXT,
  frequency BIGINT NOT NULL DEFAULT 1,
  first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  status VARCHAR(64) NOT NULL DEFAULT 'open' COMMENT 'open / in_progress / resolved / no_action',
  assigned_to VARCHAR(255),
  resolution_pr VARCHAR(255),
  resolution_jira VARCHAR(255),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at DATETIME,
  PRIMARY KEY (id),
  KEY idx_fingerprint (fingerprint),
  KEY idx_service_name (service_name),
  KEY idx_status (status),
  KEY idx_source (source),
  KEY idx_last_seen (last_seen)
)
""".strip()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create an RDS schema and the service_exception_log table."
    )
    parser.add_argument("--host", required=True, help="RDS endpoint hostname")
    parser.add_argument("--port", type=int, default=3306, help="MySQL port")
    parser.add_argument("--user", required=True, help="MySQL username")
    parser.add_argument("--password", required=True, help="MySQL password")
    parser.add_argument("--schema", default="bug_daddy", help="Schema name")
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        connection = pymysql.connect(
            host=args.host,
            port=args.port,
            user=args.user,
            password=args.password,
            autocommit=True,
            connect_timeout=10,
        )
    except Exception as exc:
        print(f"Failed to connect to MySQL: {exc}", file=sys.stderr)
        return 1

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {args.schema}")
            cursor.execute(TABLE_SQL.format(schema=args.schema))
            cursor.execute(
                f"SHOW TABLES IN {args.schema} LIKE 'service_exception_log'"
            )
            created = cursor.fetchone() is not None
    finally:
        connection.close()

    if created:
        print(
            f"Created or verified table {args.schema}.service_exception_log on {args.host}"
        )
        return 0

    print(
        f"Table {args.schema}.service_exception_log was not found after creation attempt",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
