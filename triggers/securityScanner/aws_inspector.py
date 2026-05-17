"""
AWS Inspector finding collector.

Inspector already understands AWS workload context and container/image package
metadata, so its findings are treated as a vulnerability source alongside OSV
and NVD rather than as an inventory source.
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError


def _severity(value: str | None) -> str:
    raw = (value or "UNKNOWN").upper()
    if raw in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        return raw
    if raw == "INFORMATIONAL":
        return "LOW"
    return "UNKNOWN"


def _best_score(finding: dict) -> float | None:
    if finding.get("inspectorScore") is not None:
        return finding.get("inspectorScore")
    details = finding.get("packageVulnerabilityDetails") or {}
    for cvss in details.get("cvss", []):
        if cvss.get("baseScore") is not None:
            return cvss.get("baseScore")
    return None


def _resource_context(resource: dict) -> tuple[str, str, str]:
    resource_id = resource.get("id") or resource.get("details", {}).get("awsEc2Instance", {}).get("instanceId") or "unknown"
    resource_type = (resource.get("type") or "aws_resource").lower()
    service = resource_id.rsplit("/", 1)[-1].rsplit(":", 1)[-1] if resource_id != "unknown" else "unknown"
    return resource_id, resource_type, service


def _vulnerable_packages(finding: dict) -> list[dict]:
    details = finding.get("packageVulnerabilityDetails") or {}
    packages = details.get("vulnerablePackages") or []
    if packages:
        return packages
    return [{
        "name": details.get("source") or finding.get("title") or "unknown",
        "version": "unknown",
        "fixedInVersion": "",
        "packageManager": "",
    }]


def _finding_to_records(finding: dict) -> list[dict]:
    details = finding.get("packageVulnerabilityDetails") or {}
    vuln_id = details.get("vulnerabilityId") or finding.get("findingArn", "unknown")
    aliases = [vuln_id]
    related = details.get("relatedVulnerabilities") or []
    aliases.extend(v for v in related if v and v not in aliases)

    resources = finding.get("resources") or [{}]
    packages = _vulnerable_packages(finding)
    records: list[dict] = []
    for resource in resources:
        asset_id, asset_type, service = _resource_context(resource)
        for package in packages:
            records.append({
                "cve_id": vuln_id,
                "aliases": aliases,
                "source": "inspector",
                "tool_name": "AWS Inspector",
                "severity": _severity(finding.get("severity")),
                "cvss_score": _best_score(finding),
                "description": (finding.get("description") or finding.get("title") or "")[:500],
                "published": str(details.get("sourceUrl") or finding.get("firstObservedAt") or "")[:10],
                "component": package.get("name") or "unknown",
                "component_type": "package",
                "affected_version": package.get("version") or "unknown",
                "fixed_version": package.get("fixedInVersion") or "",
                "package_manager": package.get("packageManager") or "",
                "service": service,
                "asset_id": asset_id,
                "asset_type": asset_type,
                "finding_arn": finding.get("findingArn"),
                "inspector_status": finding.get("status"),
                "remediation": finding.get("remediation", {}),
            })
    return records


def collect_inspector_findings(region: str, session=None, max_pages: int = 20) -> tuple[list[dict], dict]:
    if session is None:
        import boto3
        session = boto3.Session(region_name=region)

    try:
        client = session.client("inspector2", region_name=region)
        paginator = client.get_paginator("list_findings")
        findings: list[dict] = []
        pages = 0
        for page in paginator.paginate(
            filterCriteria={
                "findingStatus": [{"comparison": "EQUALS", "value": "ACTIVE"}],
            },
            PaginationConfig={"PageSize": 100},
        ):
            pages += 1
            for finding in page.get("findings", []):
                findings.extend(_finding_to_records(finding))
            if pages >= max_pages:
                break
        return findings, {
            "tool": "aws_inspector",
            "category": "vulnerability_source",
            "status": "ok",
            "findings": len(findings),
            "pages": pages,
            "message": "",
        }
    except (ClientError, BotoCoreError) as exc:
        return [], {
            "tool": "aws_inspector",
            "category": "vulnerability_source",
            "status": "error",
            "findings": 0,
            "pages": 0,
            "message": str(exc)[:500],
        }
    except Exception as exc:
        return [], {
            "tool": "aws_inspector",
            "category": "vulnerability_source",
            "status": "error",
            "findings": 0,
            "pages": 0,
            "message": f"{type(exc).__name__}: {exc}"[:500],
        }
