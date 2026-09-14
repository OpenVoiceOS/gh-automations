"""
Tests for scripts/pip_audit_sarif.py — the pip-audit JSON to SARIF converter.

Covers: load_dependencies (both report shapes, and a corrupt or missing
file), find_manifest, and build_sarif (rule dedup, alert count, location,
and the empty case).

Runs without any external dependencies beyond the Python standard library.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from pip_audit_sarif import (  # noqa: E402
    build_sarif,
    find_manifest,
    load_dependencies,
)

VULN_REPORT = {
    "dependencies": [
        {"name": "certifi", "version": "2026.7.22", "vulns": []},
        {
            "name": "urllib3",
            "version": "1.26.5",
            "vulns": [
                {
                    "id": "PYSEC-2026-1995",
                    "description": "Proxy-Authorization leak.",
                    "fix_versions": ["1.26.19", "2.2.2"],
                    "aliases": ["CVE-2024-37891", "GHSA-34jh-p97f-mpxf"],
                },
                {
                    "id": "PYSEC-2026-1999",
                    "description": "Redirect handling.",
                    "fix_versions": [],
                    "aliases": [],
                },
            ],
        },
        {
            "name": "requests",
            "version": "2.20.0",
            "vulns": [
                {
                    "id": "PYSEC-2026-1995",
                    "description": "Proxy-Authorization leak.",
                    "fix_versions": ["2.34.2"],
                    "aliases": ["CVE-2024-37891"],
                }
            ],
        },
    ]
}


def write(tmp_path: Path, name: str, data) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return path


# --- load_dependencies ------------------------------------------------------


def test_load_dependencies_dict_shape(tmp_path):
    path = write(tmp_path, "r.json", VULN_REPORT)
    assert len(load_dependencies(path)) == 3


def test_load_dependencies_list_shape(tmp_path):
    path = write(tmp_path, "r.json", VULN_REPORT["dependencies"])
    assert len(load_dependencies(path)) == 3


def test_load_dependencies_corrupt_file(tmp_path):
    path = write(tmp_path, "r.json", "not json at all")
    assert load_dependencies(path) == []


def test_load_dependencies_missing_file(tmp_path):
    assert load_dependencies(tmp_path / "absent.json") == []


def test_load_dependencies_unexpected_shape(tmp_path):
    path = write(tmp_path, "r.json", 42)
    assert load_dependencies(path) == []


# --- find_manifest ----------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"]
)
def test_find_manifest_finds_each(tmp_path, name):
    (tmp_path / name).write_text("")
    assert find_manifest(tmp_path) == name


def test_find_manifest_prefers_pyproject(tmp_path):
    (tmp_path / "setup.py").write_text("")
    (tmp_path / "pyproject.toml").write_text("")
    assert find_manifest(tmp_path) == "pyproject.toml"


def test_find_manifest_default_when_none(tmp_path):
    assert find_manifest(tmp_path) == "pyproject.toml"


# --- build_sarif ------------------------------------------------------------


def test_build_sarif_counts_results_and_dedups_rules():
    sarif = build_sarif(VULN_REPORT["dependencies"], "pyproject.toml")
    run = sarif["runs"][0]
    # 3 vulnerability records, over 2 distinct ids
    assert len(run["results"]) == 3
    assert len(run["tool"]["driver"]["rules"]) == 2


def test_build_sarif_envelope():
    sarif = build_sarif(VULN_REPORT["dependencies"], "pyproject.toml")
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].endswith("sarif-2.1.0.json")
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "pip-audit"


def test_build_sarif_every_result_has_a_location():
    # Code scanning shows an alert only when the result carries a location.
    sarif = build_sarif(VULN_REPORT["dependencies"], "requirements.txt")
    for result in sarif["runs"][0]["results"]:
        location = result["locations"][0]["physicalLocation"]
        assert location["artifactLocation"]["uri"] == "requirements.txt"
        assert location["region"]["startLine"] == 1
        assert result["level"] == "error"


def test_build_sarif_message_names_package_version_and_fix():
    sarif = build_sarif(VULN_REPORT["dependencies"], "pyproject.toml")
    messages = [r["message"]["text"] for r in sarif["runs"][0]["results"]]
    assert "urllib3 1.26.5 is affected by PYSEC-2026-1995" in messages[0]
    assert "CVE-2024-37891" in messages[0]
    assert "Fix: 1.26.19, 2.2.2." in messages[0]
    assert "no fix available" in messages[1]


def test_build_sarif_fingerprints_are_unique_per_package():
    sarif = build_sarif(VULN_REPORT["dependencies"], "pyproject.toml")
    prints = [
        r["partialFingerprints"]["pipAuditVuln"] for r in sarif["runs"][0]["results"]
    ]
    assert len(set(prints)) == 3
    assert "requests:2.20.0:PYSEC-2026-1995" in prints


def test_build_sarif_clean_report_is_an_empty_run():
    sarif = build_sarif([{"name": "certifi", "version": "1", "vulns": []}], "x.txt")
    run = sarif["runs"][0]
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"] == []


def test_build_sarif_missing_fields_do_not_raise():
    sarif = build_sarif([{"vulns": [{}]}], "pyproject.toml")
    result = sarif["runs"][0]["results"][0]
    assert result["ruleId"] == "UNKNOWN"
    assert "unknown unknown is affected by UNKNOWN" in result["message"]["text"]
