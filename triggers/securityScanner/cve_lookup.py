"""
CVE lookup module.

Two data sources:
  - NIST NVD API v2  (https://nvd.nist.gov/developers/vulnerabilities)
    Good for OS-level, runtime, and DB engine CVEs.
    Rate limit: 5 req / 30 s without a key; 50 req / 30 s with a key.

  - OSV.dev API  (https://osv.dev)
    Better for package-level CVEs (pip, npm, etc.).
    No rate limit documented; generous in practice.

Public interface
----------------
    lookup_cves(component, service, nvd_api_key=None) -> list[dict]

Each returned dict:
    {
        "cve_id":           str,
        "source":           "nvd" | "osv",
        "severity":         "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN",
        "cvss_score":       float | None,
        "description":      str,
        "published":        str,          # "YYYY-MM-DD"
        "component":        str,
        "component_type":   str,
        "affected_version": str,
        "service":          str,
        "asset_type":       str,
    }
"""

from __future__ import annotations

import time

import requests


NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
OSV_API_URL = "https://api.osv.dev/v1/query"

# Conservative delay between NVD calls (no key → 5 req / 30 s)
_NVD_DELAY = 7.0

# OSV ecosystem names for Lambda runtimes
_RUNTIME_TO_ECOSYSTEM: dict[str, str] = {
    "python3.8": "PyPI", "python3.9": "PyPI", "python3.10": "PyPI",
    "python3.11": "PyPI", "python3.12": "PyPI", "python3.13": "PyPI",
    "nodejs16.x": "npm", "nodejs18.x": "npm",
    "nodejs20.x": "npm", "nodejs22.x": "npm",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_cves(
    component: dict,
    service: str,
    asset_type: str,
    nvd_api_key: str | None = None,
) -> list[dict]:
    """
    Look up CVEs for a single component dict:
        {"type": str, "name": str, "version": str}

    Returns a (possibly empty) list of CVE finding dicts.
    """
    name = component.get("name", "")
    version = component.get("version", "unknown")
    comp_type = component.get("type", "")

    if not name or version in ("unknown", "latest", ""):
        return []
    if comp_type in ("os_package", "container_image"):
        return []

    results: list[dict] = []

    ecosystem = _resolve_ecosystem(name, comp_type)

    # For pip/npm packages use OSV only — it's instant, no rate limit, and
    # more accurate for package-level CVEs. NVD keyword search is too noisy
    # for individual packages and would add 7s delay per package.
    if comp_type in ("pip_package", "npm_package"):
        if ecosystem:
            results.extend(_osv_query(name, version, ecosystem))
    else:
        # OS, runtime, db_engine — use NVD (better for these) + OSV if applicable
        nvd_hits = _nvd_query(name, version, nvd_api_key)
        results.extend(nvd_hits)
        time.sleep(_NVD_DELAY)
        if ecosystem:
            osv_hits = _osv_query(name, version, ecosystem)
            existing_ids = {r["cve_id"] for r in results}
            results.extend(h for h in osv_hits if h["cve_id"] not in existing_ids)

    # Annotate with asset context
    for r in results:
        r.update({
            "component": name,
            "component_type": comp_type,
            "affected_version": version,
            "service": service,
            "asset_type": asset_type,
        })

    return results


# ---------------------------------------------------------------------------
# NVD
# ---------------------------------------------------------------------------

def _nvd_query(name: str, version: str, api_key: str | None) -> list[dict]:
    headers = {"apiKey": api_key} if api_key else {}
    try:
        resp = requests.get(
            NVD_API_URL,
            params={"keywordSearch": f"{name} {version}", "resultsPerPage": 20},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"[cve_lookup] NVD error for '{name} {version}': {exc}")
        return []

    hits = []
    for item in resp.json().get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id", "")
        description = next(
            (d["value"] for d in cve.get("descriptions", []) if d.get("lang") == "en"),
            "",
        )
        score, severity = _extract_nvd_cvss(cve.get("metrics", {}))
        hits.append({
            "cve_id": cve_id,
            "aliases": [cve_id] if cve_id else [],
            "source": "nvd",
            "tool_name": "NVD",
            "severity": severity,
            "cvss_score": score,
            "description": description[:500],
            "published": cve.get("published", "")[:10],
        })
    return hits


def _extract_nvd_cvss(metrics: dict) -> tuple[float | None, str]:
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metric_list = metrics.get(key, [])
        if not metric_list:
            continue
        data = metric_list[0].get("cvssData", {})
        score = data.get("baseScore")
        severity = (
            data.get("baseSeverity")
            or metric_list[0].get("baseSeverity", "UNKNOWN")
        ).upper()
        return score, severity
    return None, "UNKNOWN"


# ---------------------------------------------------------------------------
# OSV
# ---------------------------------------------------------------------------

def _osv_query(name: str, version: str, ecosystem: str) -> list[dict]:
    try:
        resp = requests.post(
            OSV_API_URL,
            json={"version": version, "package": {"name": name, "ecosystem": ecosystem}},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"[cve_lookup] OSV error for '{name}@{version}' ({ecosystem}): {exc}")
        return []

    hits = []
    for vuln in resp.json().get("vulns", []):
        severity, score = _extract_osv_severity(vuln.get("severity", []))
        vuln_id, aliases = _canonical_osv_id(vuln)
        hits.append({
            "cve_id": vuln_id,
            "aliases": aliases,
            "source": "osv",
            "tool_name": "OSV",
            "severity": severity,
            "cvss_score": score,
            "description": (vuln.get("summary") or vuln.get("details") or "")[:500],
            "published": vuln.get("published", "")[:10],
        })
    return hits


def _canonical_osv_id(vuln: dict) -> tuple[str, list[str]]:
    ids = [vuln.get("id", ""), *(vuln.get("aliases") or [])]
    aliases = []
    for value in ids:
        if value and value not in aliases:
            aliases.append(value)
    for value in aliases:
        if value.startswith("CVE-"):
            return value, aliases
    return (aliases[0] if aliases else "unknown"), aliases


def _extract_osv_severity(severity_list: list[dict]) -> tuple[str, float | None]:
    for sev in severity_list:
        if sev.get("type") == "CVSS_V3":
            return _cvss_vector_to_severity(sev.get("score", "")), None
    return "UNKNOWN", None


def _cvss_vector_to_severity(vector: str) -> str:
    v = vector.upper()
    if "/C:H" in v and "/I:H" in v:
        return "CRITICAL"
    if "/C:H" in v or "/I:H" in v or "/A:H" in v:
        return "HIGH"
    if "/C:L" in v or "/I:L" in v or "/A:L" in v:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Ecosystem resolver
# ---------------------------------------------------------------------------

def _resolve_ecosystem(name: str, comp_type: str) -> str | None:
    # Named runtime (e.g. "python3.11")
    if name in _RUNTIME_TO_ECOSYSTEM:
        return _RUNTIME_TO_ECOSYSTEM[name]
    # Pip packages extracted from Lambda zip
    if comp_type == "pip_package":
        return "PyPI"
    # npm packages extracted from Lambda zip
    if comp_type == "npm_package":
        return "npm"
    return None
