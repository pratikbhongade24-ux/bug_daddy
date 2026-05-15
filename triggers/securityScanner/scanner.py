"""
Security Scanner — orchestrator / entry point.

Ties together:
  aws_inventory          → discover EC2, Lambda, RDS assets
  lambda_package_extractor → enrich Lambda assets with deployed package deps
  cve_lookup             → query NVD + OSV for each component
  report                 → build structured report, upload to S3

Usage:
    python scanner.py [options]

    --region        AWS region (default: $AWS_REGION or ap-south-1)
    --bucket        S3 bucket for the report (default: $SECURITY_SCANNER_BUCKET)
    --output        Local JSON output path (default: security_report.json)
    --nvd-api-key   Optional NVD API key for higher rate limits ($NVD_API_KEY)
    --no-upload     Skip S3 upload; write locally only

AWS credentials must be present in the environment or via an IAM role.
All AWS API calls are read-only except the final S3 PutObject for the report.
"""

from __future__ import annotations

import argparse
import json
import os

import boto3

from aws_inventory import inventory_all
from cve_lookup import lookup_cves
from lambda_package_extractor import extract_lambda_dependencies
from report import build_report, print_summary, upload_to_s3


def _enrich_lambda_with_packages(assets: list[dict], region: str) -> None:
    """
    For each Lambda asset, download its deployment zip and inject the
    discovered packages as additional components (type="pip_package" or
    "npm_package"). Mutates assets in-place.
    """
    lambda_client = boto3.client("lambda", region_name=region)
    for asset in assets:
        if asset["asset_type"] != "lambda":
            continue
        if asset.get("package_type") == "Image":
            continue  # ECR image inspection is out of scope

        print(f"[scanner] Extracting packages from: {asset['service']}")
        packages = extract_lambda_dependencies(lambda_client, asset["service"])

        runtime = asset.get("runtime", "")
        comp_type = "npm_package" if runtime.startswith("nodejs") else "pip_package"

        for pkg in packages:
            asset["components"].append({
                "type": comp_type,
                "name": pkg["name"],
                "version": pkg["version"],
            })


def _run_cve_phase(assets: list[dict], nvd_api_key: str | None) -> list[dict]:
    all_findings: list[dict] = []
    for asset in assets:
        service = asset.get("service", "?")
        asset_type = asset.get("asset_type", "?")
        print(f"\n[scanner] {asset_type.upper()}: {service}")
        for component in asset.get("components", []):
            findings = lookup_cves(component, service, asset_type, nvd_api_key)
            if findings:
                print(f"  {component['name']} {component['version']} → {len(findings)} CVE(s)")
            all_findings.extend(findings)
    return all_findings


def run(
    region: str,
    bucket: str,
    output_path: str,
    nvd_api_key: str | None,
    no_upload: bool,
) -> dict:
    print(f"[scanner] Starting | region={region}")

    # Phase 1 — asset discovery
    print("\n[scanner] Phase 1: AWS asset inventory")
    assets = inventory_all(region)
    print(f"[scanner] Total assets: {len(assets)}")

    # Phase 1b — enrich Lambda assets with deployed package deps
    print("\n[scanner] Phase 1b: Extracting Lambda deployment packages")
    _enrich_lambda_with_packages(assets, region)

    # Phase 2 — CVE lookup
    print("\n[scanner] Phase 2: CVE lookup")
    findings = _run_cve_phase(assets, nvd_api_key)

    # Phase 3 — report
    print("\n[scanner] Phase 3: Building report")
    report = build_report(assets, findings)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"[scanner] Report saved locally: {output_path}")

    print_summary(report)

    if not no_upload:
        if not bucket:
            print("[scanner] WARNING: --bucket not set; skipping S3 upload.")
        else:
            upload_to_s3(report, bucket, region)

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AWS CVE Security Scanner")
    parser.add_argument("--region", default=os.environ.get("AWS_REGION", "ap-south-1"))
    parser.add_argument("--bucket", default=os.environ.get("SECURITY_SCANNER_BUCKET", ""))
    parser.add_argument("--output", default="security_report.json")
    parser.add_argument("--nvd-api-key", default=os.environ.get("NVD_API_KEY"))
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    run(
        region=args.region,
        bucket=args.bucket,
        output_path=args.output,
        nvd_api_key=args.nvd_api_key,
        no_upload=args.no_upload,
    )


if __name__ == "__main__":
    main()
