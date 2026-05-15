"""
Lambda deployment package extractor.

Downloads the Lambda function's zip from the pre-signed URL that
lambda:GetFunction returns, then inspects the zip contents to extract
the exact packages that were installed — without writing anything to disk.

Two extraction strategies (tried in order):
  1. *.dist-info/METADATA  — most reliable; pip writes this for every
     installed package, and it contains the exact Name + Version.
  2. requirements.txt      — fallback for packages that were vendored
     without going through pip (less common in Lambda zips).

For Image-based Lambdas this module returns an empty list; ECR image
inspection is out of scope for now.
"""

from __future__ import annotations

import io
import re
import zipfile

import requests
from botocore.exceptions import ClientError


# Match "Name: requests" / "Version: 2.31.0" in dist-info METADATA
_METADATA_NAME_RE = re.compile(r"^Name:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_METADATA_VER_RE = re.compile(r"^Version:\s*(.+)$", re.MULTILINE | re.IGNORECASE)

# Match "requests==2.31.0" or "requests>=2.31.0" in requirements.txt
_REQ_LINE_RE = re.compile(r"^([A-Za-z0-9_\-\.]+)[=><!\s]+([A-Za-z0-9_\.\-]+)")


def extract_lambda_dependencies(lambda_client, function_name: str) -> list[dict]:
    """
    Return a list of {"name": str, "version": str} dicts for the given Lambda.
    Returns [] if the function is image-based or if extraction fails.
    """
    code_location = _get_code_location(lambda_client, function_name)
    if not code_location:
        return []

    zip_bytes = _download_zip(code_location)
    if not zip_bytes:
        return []

    packages = _extract_from_zip(zip_bytes)
    print(f"[extractor]   {function_name}: {len(packages)} package(s) found in deployment zip")
    return packages


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_code_location(lambda_client, function_name: str) -> str | None:
    try:
        resp = lambda_client.get_function(FunctionName=function_name)
        package_type = resp.get("Configuration", {}).get("PackageType", "Zip")
        if package_type == "Image":
            print(f"[extractor]   {function_name}: image-based Lambda, skipping zip extraction")
            return None
        location = resp.get("Code", {}).get("Location")
        if not location:
            print(f"[extractor]   {function_name}: no code location returned")
        return location
    except ClientError as exc:
        print(f"[extractor]   {function_name}: GetFunction failed — {exc}")
        return None


def _download_zip(url: str) -> bytes | None:
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        print(f"[extractor]   download failed — {exc}")
        return None


def _extract_from_zip(zip_bytes: bytes) -> list[dict]:
    packages: dict[str, str] = {}  # name → version (deduped)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()

            # Strategy 1: *.dist-info/METADATA
            metadata_files = [n for n in names if n.endswith(".dist-info/METADATA") or "/METADATA" in n and ".dist-info" in n]
            for path in metadata_files:
                name, version = _parse_dist_info_metadata(zf.read(path).decode("utf-8", errors="replace"))
                if name and version:
                    packages[name.lower()] = version

            # Strategy 2: requirements.txt (only if dist-info found nothing)
            if not packages:
                req_files = [n for n in names if n.endswith("requirements.txt")]
                for path in req_files:
                    for name, version in _parse_requirements_txt(zf.read(path).decode("utf-8", errors="replace")):
                        if name and version:
                            packages[name.lower()] = version

    except zipfile.BadZipFile as exc:
        print(f"[extractor]   bad zip file — {exc}")

    return [{"name": name, "version": version} for name, version in packages.items()]


def _parse_dist_info_metadata(content: str) -> tuple[str, str]:
    name_match = _METADATA_NAME_RE.search(content)
    ver_match = _METADATA_VER_RE.search(content)
    name = name_match.group(1).strip() if name_match else ""
    version = ver_match.group(1).strip() if ver_match else ""
    return name, version


def _parse_requirements_txt(content: str) -> list[tuple[str, str]]:
    results = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _REQ_LINE_RE.match(line)
        if m:
            results.append((m.group(1), m.group(2)))
    return results
