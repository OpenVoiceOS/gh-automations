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
    ("version.py", "Version file"),
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

    for filename, label in REQUIRED_FILES:
        # If a custom version_file is provided that isn't root version.py,
        # we don't require root version.py
        is_version = filename == "version.py"
        custom_version = version_file != "version.py"
        
        path = os.path.join(repo_root, filename)
        exists = os.path.isfile(path)
        
        results.append({
            "file": filename,
            "label": label,
            "exists": exists,
            "required": True if not (is_version and custom_version) else False,
        })

    # At least one setup file must exist
    has_setup = False
    for filename, label in SETUP_FILES:
        path = os.path.join(repo_root, filename)
        exists = os.path.isfile(path)
        if exists:
            has_setup = True
        results.append({
            "file": filename,
            "label": label,
            "exists": exists,
            "required": False,
            "group": "setup",
        })
    # Mark setup as required-group
    for r in results:
        if r.get("group") == "setup":
            r["group_satisfied"] = has_setup

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
    return {
        "repo_root": repo_root,
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
