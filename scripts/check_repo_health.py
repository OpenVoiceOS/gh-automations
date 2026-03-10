#!/usr/bin/env python3
"""
Check repository health: required files, contributor status, breaking changes.

Outputs a JSON report used by repo-health.yml to post PR comment sections.

Usage:
    check_repo_health.py --repo-root . --output-json /tmp/health-report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from _version_utils import find_version_file


REQUIRED_FILES = [
    ("README.md", "README"),
    ("LICENSE", "License file"),
]

SETUP_FILES = [
    ("pyproject.toml", "pyproject.toml"),
    ("setup.py", "setup.py"),
]

OPTIONAL_FILES = [
    ("CHANGELOG.md", "Changelog"),
    ("requirements.txt", "Requirements"),
]


def check_required_files(repo_root: str, version_file: str = "version.py") -> list[dict]:
    """Check for required and optional files in the repo root."""
    results: list[dict] = []

    # Handle version.py separately to avoid root-only confusion
    v_path = os.path.join(repo_root, version_file)
    results.append({
        "file": version_file,
        "label": "Version file",
        "exists": os.path.isfile(v_path),
        "required": True
    })

    for filename, label in REQUIRED_FILES:
        path = os.path.join(repo_root, filename)
        exists = os.path.isfile(path)
        results.append({
            "file": filename,
            "label": label,
            "exists": exists,
            "required": True,
        })

    # At least one setup file must exist
    has_pyproject = os.path.isfile(os.path.join(repo_root, "pyproject.toml"))
    has_setup_py = os.path.isfile(os.path.join(repo_root, "setup.py"))
    
    for filename, label in SETUP_FILES:
        exists = os.path.isfile(os.path.join(repo_root, filename))
        is_required = False
        
        # If neither exists, they are BOTH required (group failure)
        # If pyproject exists, setup.py is truly optional (no warning)
        # If ONLY setup.py exists, it's satisfied but we might suggest pyproject later
        if filename == "pyproject.toml" and not has_setup_py:
            is_required = True
        
        results.append({
            "file": filename,
            "label": label,
            "exists": exists,
            "required": is_required,
            "group": "setup",
            "group_satisfied": (has_pyproject or has_setup_py)
        })

    for filename, label in OPTIONAL_FILES:
        path = os.path.join(repo_root, filename)
        exists = os.path.isfile(path)
        results.append({
            "file": filename,
            "label": label,
            "exists": exists,
            "required": False,
        })

    return results


def check_version_file(repo_root: str, version_file: str = "version.py") -> dict:
    """Check if version.py exists and has proper markers."""
    path = os.path.join(repo_root, version_file)
    result = {
        "path": version_file,
        "exists": False,
        "has_start_marker": False,
        "has_end_marker": False,
    }
    if not os.path.isfile(path):
        return result
    result["exists"] = True
    try:
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        result["has_start_marker"] = "# START_VERSION_BLOCK" in content
        result["has_end_marker"] = "# END_VERSION_BLOCK" in content
    except OSError:
        pass
    return result


def run_checks(repo_root: str, version_file: str = "version.py") -> dict:
    """Run all repo health checks and return the full report."""
    repo_root = os.path.abspath(repo_root)

    # Get current version for the report if possible
    version_str = "Unknown"
    v_abs_path = os.path.join(repo_root, version_file)
    if os.path.isfile(v_abs_path):
        try:
            from _version_utils import read_version, format_version
            major, minor, build, alpha = read_version(v_abs_path)
            version_str = format_version(major, minor, build, alpha)
        except Exception:
            pass

    return {
        "repo_root": repo_root,
        "version_str": version_str,
        "files": check_required_files(repo_root, version_file),
        "version": check_version_file(repo_root, version_file),
    }



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=".", help="Root of the repository")
    parser.add_argument("--version-file", default="version.py", help="Path to version.py")
    parser.add_argument("--output-json", default="/tmp/health-report.json",
                        help="Output JSON report path")
    args = parser.parse_args()

    # Find the version file using auto-detection if hint fails
    version_file = find_version_file(args.repo_root, args.version_file)
    # Even if not found, we want to know what it TRIED to check for the report
    checked_version_file = version_file if version_file else args.version_file
    # Convert back to relative path for report consistency if it was found
    if version_file and os.path.isabs(version_file):
        checked_version_file = os.path.relpath(version_file, os.path.abspath(args.repo_root))

    report = run_checks(args.repo_root, checked_version_file)

    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
