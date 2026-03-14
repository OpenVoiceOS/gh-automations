#!/usr/bin/env python3
"""
Verify that locale folders are correctly included in the package build.

Checks:
1. Locale folder exists in the source tree
2. Locale files are included in pyproject.toml [tool.setuptools.package-data]
3. Build actually includes locale files (validates via SOURCES.txt)

Outputs a JSON report used by locale-check.yml to post PR comment sections.

Usage:
    python check_locale_build.py --repo-root . --locale-path "" --output-json /tmp/locale-report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


def find_locale_dirs(repo_root: str) -> List[str]:
    """
    Find all locale directories in the repository.
    
    Returns list of absolute paths to locale directories found.
    Searches for:
    - <package>/locale/ (most common pattern)
    - locale/ at repo root
    """
    locale_dirs = []
    repo_path = Path(repo_root)
    
    # Search for locale directories
    for locale_dir in repo_path.rglob("locale"):
        if not locale_dir.is_dir():
            continue
        # Skip hidden directories and venvs
        if any(part.startswith(".") for part in locale_dir.parts):
            continue
        if "venv" in str(locale_dir) or "__pycache__" in str(locale_dir):
            continue
        
        # Check if it contains language subdirectories
        has_lang_dirs = any(
            sub.is_dir() and len(sub.name.split("-")) >= 1
            for sub in locale_dir.iterdir()
        )
        if has_lang_dirs:
            locale_dirs.append(str(locale_dir))
    
    return sorted(locale_dirs)


def count_locale_files(locale_dir: str) -> Dict[str, int]:
    """
    Count locale files by extension and language.
    
    Returns dict with:
    - total_files: total count
    - by_extension: {".voc": count, ".dialog": count, ...}
    - by_language: {"en-us": count, "pt-br": count, ...}
    """
    result = {
        "total_files": 0,
        "by_extension": {},
        "by_language": {},
    }
    
    locale_path = Path(locale_dir)
    if not locale_path.is_dir():
        return result
    
    for lang_dir in locale_path.iterdir():
        if not lang_dir.is_dir():
            continue
        
        lang = lang_dir.name
        lang_count = 0
        
        for file in lang_dir.rglob("*"):
            if not file.is_file():
                continue
            
            ext = file.suffix.lower()
            result["by_extension"][ext] = result["by_extension"].get(ext, 0) + 1
            lang_count += 1
        
        if lang_count > 0:
            result["by_language"][lang] = lang_count
            result["total_files"] += lang_count
    
    return result


def check_pyproject_includes_locale(repo_root: str) -> Tuple[bool, Optional[str], List[str]]:
    """
    Check if pyproject.toml includes locale files in package-data.
    
    Returns (has_locale_data, package_name, patterns):
    - has_locale_data: True if locale patterns found in package-data
    - package_name: the package name from [tool.setuptools.package-data]
    - patterns: list of glob patterns that match locale
    """
    pyproject = Path(repo_root) / "pyproject.toml"
    if not pyproject.exists():
        return (False, None, [])
    
    try:
        with open(pyproject, "rb") as f:
            config = tomllib.load(f)
        
        package_data = config.get("tool", {}).get("setuptools", {}).get("package-data", {})
        
        patterns_found = []
        package_name = None
        
        for pkg_name, patterns in package_data.items():
            if isinstance(patterns, list):
                for pattern in patterns:
                    if "locale" in pattern.lower():
                        patterns_found.append(pattern)
                        package_name = pkg_name
        
        if patterns_found:
            return (True, package_name, patterns_found)
        
        # Check for wildcard that might include locale implicitly
        for pkg_name, patterns in package_data.items():
            if isinstance(patterns, list):
                if "*" in patterns or "**/*" in patterns:
                    return (True, pkg_name, ["* (wildcard)"])
        
        return (False, None, [])
    
    except Exception as e:
        print(f"Warning: Could not parse pyproject.toml: {e}", file=sys.stderr)
        return (False, None, [])


def check_build_includes_locale(repo_root: str) -> Tuple[bool, List[str]]:
    """
    Check if locale files are included in the build manifest.
    
    Reads SOURCES.txt from egg-info directory (created during build).
    
    Returns (has_locale_in_build, locale_files_in_build):
    - has_locale_in_build: True if locale files found in SOURCES.txt
    - locale_files_in_build: list of locale file paths found
    """
    egg_info_dirs = []
    repo_path = Path(repo_root)
    
    # Find egg-info directories
    for egg_info in repo_path.rglob("*.egg-info"):
        if egg_info.is_dir() and "venv" not in str(egg_info):
            egg_info_dirs.append(egg_info)
    
    if not egg_info_dirs:
        # No build has been run yet
        return (False, [])
    
    # Use the most recently modified egg-info
    egg_info_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    sources_txt = egg_info_dirs[0] / "SOURCES.txt"
    
    if not sources_txt.exists():
        return (False, [])
    
    locale_files = []
    try:
        with open(sources_txt) as f:
            for line in f:
                line = line.strip()
                if "locale" in line.lower() and not line.startswith("#"):
                    locale_files.append(line)
    except Exception:
        pass
    
    return (len(locale_files) > 0, locale_files)


def run_checks(repo_root: str, locale_path_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Run all locale build checks and return the full report.
    """
    repo_root = os.path.abspath(repo_root)
    
    report: Dict[str, Any] = {
        "repo_root": repo_root,
        "locale_dirs_found": [],
        "locale_dirs_details": [],
        "pyproject_config": {
            "has_locale_data": False,
            "package_name": None,
            "patterns": [],
        },
        "build_manifest": {
            "includes_locale": False,
            "files": [],
        },
        "issues": [],
        "status": "pass",
        "summary": "",
    }
    
    # Step 1: Find locale directories
    locale_dirs = find_locale_dirs(repo_root)
    report["locale_dirs_found"] = locale_dirs
    
    if locale_path_override:
        override_path = os.path.join(repo_root, locale_path_override)
        if os.path.isdir(override_path):
            locale_dirs = [override_path]
        else:
            report["issues"].append({
                "severity": "warning",
                "message": f"Override locale path not found: {locale_path_override}",
                "check": "locale_override"
            })
    
    # Step 2: Analyze each locale directory
    for locale_dir in locale_dirs:
        rel_path = os.path.relpath(locale_dir, repo_root)
        file_counts = count_locale_files(locale_dir)
        
        report["locale_dirs_details"].append({
            "path": rel_path,
            "file_counts": file_counts,
            "languages": list(file_counts["by_language"].keys()),
            "extensions": list(file_counts["by_extension"].keys()),
        })
    
    # Step 3: Check pyproject.toml configuration
    has_config, pkg_name, patterns = check_pyproject_includes_locale(repo_root)
    report["pyproject_config"] = {
        "has_locale_data": has_config,
        "package_name": pkg_name,
        "patterns": patterns,
    }
    
    # Step 4: Check build manifest
    has_in_build, build_files = check_build_includes_locale(repo_root)
    report["build_manifest"] = {
        "includes_locale": has_in_build,
        "files": build_files,
    }
    
    # Step 5: Collect issues
    if locale_dirs and not has_config:
        report["issues"].append({
            "severity": "error",
            "message": "Locale folder found but not included in [tool.setuptools.package-data]",
            "check": "pyproject_config"
        })
    
    if locale_dirs and has_config and not has_in_build:
        report["issues"].append({
            "severity": "warning",
            "message": "Locale configured in pyproject.toml but not found in build (run build first)",
            "check": "build_manifest"
        })
    
    if not locale_dirs:
        report["issues"].append({
            "severity": "info",
            "message": "No locale folder found in repository",
            "check": "locale_detection"
        })
    
    # Step 6: Compute status
    has_errors = any(i["severity"] == "error" for i in report["issues"])
    has_warnings = any(i["severity"] == "warning" for i in report["issues"])
    
    if has_errors:
        report["status"] = "fail"
    elif has_warnings:
        report["status"] = "warning"
    else:
        report["status"] = "pass"
    
    # Step 7: Generate summary
    if not locale_dirs:
        report["summary"] = "ℹ️ No locale folder found — localization not used"
    elif has_errors:
        report["summary"] = "❌ Locale folder not properly configured for packaging"
    elif has_warnings:
        report["summary"] = "⚠️ Locale configured but build verification pending"
    else:
        total_files = sum(d["file_counts"]["total_files"] for d in report["locale_dirs_details"])
        total_langs = len(set(lang for d in report["locale_dirs_details"] for lang in d["languages"]))
        report["summary"] = f"✅ Locale properly configured ({total_files} files, {total_langs} languages)"
    
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Root of the repository"
    )
    parser.add_argument(
        "--locale-path",
        default="",
        help="Override locale path (relative to repo root)"
    )
    parser.add_argument(
        "--output-json",
        default="/tmp/locale-report.json",
        help="Output JSON report path"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed report to stdout"
    )
    
    args = parser.parse_args()
    
    report = run_checks(args.repo_root, args.locale_path or None)
    
    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    
    if args.verbose:
        print(json.dumps(report, indent=2))
    else:
        print(report["summary"])
    
    # Always exit 0 - caller decides if status is acceptable
    sys.exit(0)


if __name__ == "__main__":
    main()
