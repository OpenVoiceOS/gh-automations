#!/usr/bin/env python3
"""
Read version.py, calculate the predicted next version from PR labels/title,
and output a JSON report.

Uses the same bump rules as update_version.py.

Usage:
    check_release.py --version-file version.py \
        [--pr-labels-json "[]"] \
        [--pr-title ""] \
        [--output-json /tmp/release-report.json]

Environment variables (alternative to CLI args):
    PR_LABELS_JSON   JSON array of label objects (from github.event.pull_request.labels)
    PR_TITLE         PR title string
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow importing _version_utils regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _version_utils import format_version, read_version, find_version_file  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps conventional commit prefix → bump part.  None means no semver bump
# (alpha-only increment).
CONVENTIONAL_PREFIXES: dict[str, str | None] = {
    "breaking change:": "major",
    "feat!:": "major",
    "fix!:": "major",
    "feat:": "minor",
    "feature:": "minor",
    "fix:": "build",
    "docs:": None,
    "chore:": None,
    "refactor:": None,
    "test:": None,
    "style:": None,
    "perf:": None,
    "ci:": None,
    "build:": None,
}

# Label name → bump part (case-insensitive match)
_LABEL_BUMP: dict[str, str] = {
    "breaking": "major",
    "breaking change": "major",
    "feature": "minor",
    "enhancement": "minor",
    "fix": "build",
    "bug": "build",
    "bugfix": "build",
}

# Priority order for label bumps
_BUMP_PRIORITY = {"major": 3, "minor": 2, "build": 1, "alpha": 0}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def detect_bump_part(labels: list[str], pr_title: str) -> tuple[str, str]:
    """Return (bump_part, source) from PR labels and/or title.

    Labels take precedence over title.  Priority within labels: major > minor > build.
    Source format: "label:breaking", "title:feat:", "none".
    """
    best_part: str | None = None
    best_source: str = "none"
    best_priority = -1

    for label in labels:
        mapped = _LABEL_BUMP.get(label.lower())
        if mapped and _BUMP_PRIORITY[mapped] > best_priority:
            best_part = mapped
            best_source = f"label:{label.lower()}"
            best_priority = _BUMP_PRIORITY[mapped]

    if best_part is not None:
        return best_part, best_source

    # Fall back to PR title prefix
    matched_prefix, _ = parse_pr_title(pr_title)
    if matched_prefix is not None:
        part = CONVENTIONAL_PREFIXES.get(matched_prefix)
        if part is not None:
            return part, f"title:{matched_prefix}"
        # Known prefix but no semver bump (docs, chore, …) → alpha only
        return "alpha", f"title:{matched_prefix}"

    return "alpha", "none"


def parse_pr_title(pr_title: str) -> tuple[str | None, str | None]:
    """Match the first conventional commit prefix in *pr_title*.

    Returns (matched_prefix, remainder) or (None, None) if no match.
    Comparison is case-insensitive.
    """
    lower = pr_title.strip().lower()
    for prefix in CONVENTIONAL_PREFIXES:
        if lower.startswith(prefix):
            remainder = pr_title[len(prefix):].strip()
            return prefix, remainder
    return None, None


def compute_next_version(
    major: int, minor: int, build: int, alpha: int, part: str
) -> tuple[int, int, int, int]:
    """Apply bump rules (mirrors update_version.py exactly).

    Returns (new_major, new_minor, new_build, new_alpha).
    """
    if part == "major":
        major += 1
        minor = 0
        build = 0
        alpha = 1
    elif part == "minor":
        minor += 1
        build = 0
        alpha = 1
    elif part == "build":
        build += 1
        alpha = 1
    elif part == "alpha":
        if not alpha:  # currently stable — start a new build series
            build += 1
        alpha += 1
    return major, minor, build, alpha


def validate_version_block(version_file: str) -> dict:
    """Validate that *version_file* contains proper START/END markers and is parseable.

    Returns dict with: has_start_marker, has_end_marker, parseable, error.
    """
    result = {
        "has_start_marker": False,
        "has_end_marker": False,
        "parseable": False,
        "error": None,
    }
    try:
        with open(version_file, encoding="utf-8") as fh:
            content = fh.read()
        result["has_start_marker"] = "# START_VERSION_BLOCK" in content
        result["has_end_marker"] = "# END_VERSION_BLOCK" in content
        if result["has_start_marker"] and result["has_end_marker"]:
            read_version(version_file)
            result["parseable"] = True
    except FileNotFoundError as exc:
        result["error"] = str(exc)
    except (ValueError, TypeError) as exc:
        result["error"] = str(exc)
    return result


def _extract_label_names(pr_labels_json: str) -> list[str]:
    """Parse label names from a JSON array.

    Handles both:
    - ``[{"name": "feature"}, ...]`` (GitHub API format)
    - ``["feature", ...]`` (plain string list)
    """
    try:
        raw = json.loads(pr_labels_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name")
            if name:
                names.append(str(name))
    return names


def run_checks(version_file: str, pr_labels_json: str = "[]", pr_title: str = "") -> dict:
    """Run all release checks and return the full report dict.

    Exit codes embedded in report:
      - "file_not_found" → caller may exit 0
      - "parse_error"    → caller may exit 1
    """
    report: dict = {
        "version_file": version_file,
        "file_exists": False,
        "validation": {},
        "current_version": None,
        "next_version": None,
        "bump_part": None,
        "bump_source": None,
        "pr_title": pr_title,
        "pr_labels": [],
        "has_conventional_prefix": False,
        "conventional_prefix": None,
        "status": "ok",
    }

    labels = _extract_label_names(pr_labels_json)
    report["pr_labels"] = labels

    validation = validate_version_block(version_file)
    report["validation"] = validation

    if not os.path.isfile(version_file):
        report["status"] = "file_not_found"
        return report

    report["file_exists"] = True

    if not validation["parseable"]:
        report["status"] = "parse_error"
        return report

    major, minor, build, alpha = read_version(version_file)
    report["current_version"] = format_version(major, minor, build, alpha)

    bump_part, bump_source = detect_bump_part(labels, pr_title)
    report["bump_part"] = bump_part
    report["bump_source"] = bump_source

    matched_prefix, _ = parse_pr_title(pr_title)
    report["has_conventional_prefix"] = matched_prefix is not None
    report["conventional_prefix"] = matched_prefix

    nm, ni, nb, na = compute_next_version(major, minor, build, alpha, bump_part)
    report["next_version"] = format_version(nm, ni, nb, na)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version-file", default="version.py", help="Path to the version.py file")
    parser.add_argument("--pr-labels-json", default="", help="JSON array of PR label objects")
    parser.add_argument("--pr-title", default="", help="PR title string")
    parser.add_argument("--output-json", default="/tmp/release-report.json", help="Output JSON report path")
    args = parser.parse_args()

    # Env vars override CLI args when set
    pr_labels_json = os.environ.get("PR_LABELS_JSON", args.pr_labels_json) or "[]"
    pr_title = os.environ.get("PR_TITLE", args.pr_title) or ""

    # Find the version file using auto-detection if hint fails
    version_file = find_version_file(".", args.version_file)
    checked_version_file = version_file if version_file else args.version_file
    # Convert back to relative path for report consistency if it was found
    if version_file and os.path.isabs(version_file):
        checked_version_file = os.path.relpath(version_file, os.path.abspath("."))

    report = run_checks(checked_version_file, pr_labels_json, pr_title)

    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(json.dumps(report, indent=2))

    status = report.get("status", "ok")
    if status == "parse_error":
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
