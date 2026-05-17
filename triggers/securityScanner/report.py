"""
Report assembly and S3 upload.

build_report()  — combines assets + findings into a structured dict
upload_to_s3()  — puts the JSON report into S3 under a dated key
print_summary() — prints a human-readable summary to stdout
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import boto3


_SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}


def build_report(
    assets: list[dict],
    findings: list[dict],
    dependencies: list[dict] | None = None,
    tool_results: list[dict] | None = None,
) -> dict:
    now = datetime.now(tz=timezone.utc)
    findings_sorted = sorted(
        findings,
        key=lambda f: _SEVERITY_ORDER.get(f.get("severity", "UNKNOWN"), 4),
    )
    return {
        "date": now.strftime("%Y-%m-%d"),
        "scanned_at": now.isoformat(),
        "summary": _summarise(assets, findings, dependencies or [], tool_results or []),
        "assets": assets,
        "dependencies": dependencies or [],
        "tool_results": tool_results or [],
        "findings": findings_sorted,
    }


def upload_to_s3(report: dict, bucket: str, region: str) -> str:
    key = f"security-scan-reports/{report['date']}.json"
    boto3.client("s3", region_name=region).put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report, indent=2).encode(),
        ContentType="application/json",
    )
    uri = f"s3://{bucket}/{key}"
    print(f"[report] Uploaded → {uri}")
    return uri


def print_summary(report: dict) -> None:
    s = report["summary"]
    print(f"\n{'=' * 52}")
    print(f"  SECURITY SCAN SUMMARY  ({report['date']})")
    print(f"  Assets scanned : {s['total_assets']}")
    print(f"  Total CVEs     : {s['total_cves']}")
    print(f"  CRITICAL       : {s['critical']}")
    print(f"  HIGH           : {s['high']}")
    print(f"  MEDIUM         : {s['medium']}")
    print(f"  LOW            : {s['low']}")
    print(f"{'=' * 52}\n")

    if report["findings"]:
        print("  Top findings:")
        for f in report["findings"][:10]:
            score = f"(CVSS {f['cvss_score']})" if f.get("cvss_score") else ""
            print(f"  [{f['severity']:<8}] {f['cve_id']} {score}")
            print(f"             {f['service']} — {f['component']} {f['affected_version']}")
            print(f"             {f['description'][:120]}")
            print()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _summarise(
    assets: list[dict],
    findings: list[dict],
    dependencies: list[dict],
    tool_results: list[dict],
) -> dict:
    counts: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        sev = f.get("severity", "LOW")
        if sev in counts:
            counts[sev] += 1
    return {
        "total_assets": len(assets),
        "total_dependencies": len(dependencies),
        "tools_ok": sum(1 for t in tool_results if t.get("status") == "ok"),
        "tools_error": sum(1 for t in tool_results if t.get("status") == "error"),
        "total_cves": len(findings),
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "medium": counts["MEDIUM"],
        "low": counts["LOW"],
    }
