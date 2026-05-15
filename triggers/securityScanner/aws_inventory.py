"""
AWS asset inventory — read-only enumeration of EC2, Lambda, and RDS resources.

Each function returns a list of asset dicts with a consistent shape:
    {
        "asset_type": str,          # "ec2" | "lambda" | "rds"
        "service":    str,          # human-readable name / identifier
        "components": [             # things we will look up CVEs for
            {"type": str, "name": str, "version": str},
            ...
        ],
        ...                         # asset-type-specific metadata
    }
"""

from __future__ import annotations

from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# EC2
# ---------------------------------------------------------------------------

def get_ec2_assets(ec2_client, ssm_client) -> list[dict]:
    assets = []
    paginator = ec2_client.get_paginator("describe_instances")
    for page in paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]
    ):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                instance_id = instance["InstanceId"]
                name = next(
                    (t["Value"] for t in instance.get("Tags", []) if t["Key"] == "Name"),
                    instance_id,
                )
                platform = instance.get("Platform", "linux")
                ami_id = instance.get("ImageId", "")

                os_version = (
                    _ssm_os_version(ssm_client, instance_id)
                    or _ami_description(ec2_client, ami_id)
                    or "unknown"
                )

                components = [{"type": "os", "name": platform, "version": os_version}]
                components.extend(_ssm_installed_packages(ssm_client, instance_id))

                assets.append({
                    "asset_type": "ec2",
                    "service": name,
                    "instance_id": instance_id,
                    "ami_id": ami_id,
                    "components": components,
                })

    return assets


def _ssm_os_version(ssm_client, instance_id: str) -> str | None:
    try:
        resp = ssm_client.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [instance_id]}]
        )
        info = resp.get("InstanceInformationList", [])
        return info[0].get("PlatformVersion") if info else None
    except ClientError:
        return None


def _ami_description(ec2_client, ami_id: str) -> str | None:
    if not ami_id:
        return None
    try:
        resp = ec2_client.describe_images(ImageIds=[ami_id])
        images = resp.get("Images", [])
        return (images[0].get("Description") or images[0].get("Name")) if images else None
    except ClientError:
        return None


def _ssm_installed_packages(ssm_client, instance_id: str) -> list[dict]:
    try:
        resp = ssm_client.list_inventory_entries(
            InstanceId=instance_id,
            TypeName="AWS:Application",
            MaxResults=50,
        )
        return [
            {"type": "package", "name": e["Name"], "version": e.get("Version", "unknown")}
            for e in resp.get("Entries", [])
            if e.get("Name")
        ]
    except ClientError:
        return []


# ---------------------------------------------------------------------------
# Lambda
# ---------------------------------------------------------------------------

def get_lambda_assets(lambda_client) -> list[dict]:
    assets = []
    paginator = lambda_client.get_paginator("list_functions")
    for page in paginator.paginate():
        for fn in page["Functions"]:
            runtime = fn.get("Runtime", "unknown")
            package_type = fn.get("PackageType", "Zip")  # "Zip" | "Image"
            assets.append({
                "asset_type": "lambda",
                "service": fn["FunctionName"],
                "function_arn": fn["FunctionArn"],
                "runtime": runtime,
                "package_type": package_type,
                "components": [
                    {"type": "runtime", "name": runtime, "version": _runtime_version(runtime)},
                ],
            })
    return assets


def _runtime_version(runtime: str) -> str:
    for prefix in ("python", "nodejs", "java", "dotnet", "ruby", "go"):
        if runtime.startswith(prefix):
            return runtime[len(prefix):].replace(".x", "")
    return runtime


# ---------------------------------------------------------------------------
# RDS
# ---------------------------------------------------------------------------

def get_rds_assets(rds_client) -> list[dict]:
    assets = []
    paginator = rds_client.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page["DBInstances"]:
            engine = db.get("Engine", "unknown")
            version = db.get("EngineVersion", "unknown")
            assets.append({
                "asset_type": "rds",
                "service": db.get("DBInstanceIdentifier", "unknown"),
                "engine": engine,
                "components": [
                    {"type": "db_engine", "name": engine, "version": version},
                ],
            })
    return assets


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def inventory_all(region: str, session=None) -> list[dict]:
    if session is None:
        import boto3
        session = boto3.Session(region_name=region)

    ec2 = session.client("ec2")
    ssm = session.client("ssm")
    lmb = session.client("lambda")
    rds = session.client("rds")

    print("[inventory] Scanning EC2...")
    ec2_assets = get_ec2_assets(ec2, ssm)
    print(f"[inventory]   {len(ec2_assets)} EC2 instance(s)")

    print("[inventory] Scanning Lambda...")
    lambda_assets = get_lambda_assets(lmb)
    print(f"[inventory]   {len(lambda_assets)} Lambda function(s)")

    print("[inventory] Scanning RDS...")
    rds_assets = get_rds_assets(rds)
    print(f"[inventory]   {len(rds_assets)} RDS instance(s)")

    return ec2_assets + lambda_assets + rds_assets
