#!/usr/bin/env python3
"""
Check if a predicted version is compatible with current ovos-releases channels.

Reads constraints-stable.txt, constraints-testing.txt, constraints-alpha.txt
from a checked-out ovos-releases repo and compares against the predicted next version.

Usage:
    python check_release_channels.py \
        --releases-dir ./ovos-releases \
        --package ovos-core \
        --version 1.3.2a1 \
        --output /tmp/channel-report.md
"""
import argparse
import os
import re
import sys

def parse_constraints(content):
    """Parse constraints file into a dict of {package: requirement_string}."""
    constraints = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split on first occurrence of <, >, =, !
        match = re.split(r'([<>=!])', line, 1)
        if len(match) >= 3:
            name = match[0].strip()
            constraints[name] = line
        else:
            # Bare package name
            constraints[line] = line
    return constraints

def check_version_against_constraint(version, constraint_line):
    """
    Check if 'version' satisfies the 'constraint_line'.
    This is a simplified check for the specific patterns used in ovos-releases:
    - name>=X.Y.Z,<A.B.C
    - name<X.Y.Z
    - name
    """
    if not constraint_line:
        return "unknown", "No constraint found"

    # Extract the requirement part (everything after the package name)
    # ovos-core>=1.3.1,<1.4.0 -> >=1.3.1,<1.4.0
    match = re.search(r'([<>=!].*)', constraint_line)
    if not match:
        return "✅", "Unconstrained"

    req = match.group(1)
    
    # We'll use packaging.version if available, but since we are in a script 
    # intended for environments that might only have stdlib, let's use a 
    # slightly more robust regex/logic for the specific OVOS patterns.
    
    from _version_utils import read_version, format_version
    # We can't use read_version here as it's for version.py, but we can 
    # reuse the logic to parse a version string.
    
    def parse_ver(v_str):
        # 1.3.2a1 -> (1, 3, 2, 1)
        v_match = re.match(r'(\d+)\.(\d+)\.(\d+)(a\d+)?', v_str)
        if not v_match:
            return None
        major, minor, build, alpha = v_match.groups()
        alpha_val = int(alpha[1:]) if alpha else 0
        return (int(major), int(minor), int(build), alpha_val)

    target_v = parse_ver(version)
    if not target_v:
        return "❓", f"Malformed version: {version}"

    # Split requirements by comma: >=1.3.1,<1.4.0 -> ['>=1.3.1', '<1.4.0']
    for part in req.split(','):
        part = part.strip()
        op_match = re.match(r'([<>!=]+)(.*)', part)
        if not op_match:
            continue
        op, ver_str = op_match.groups()
        check_v = parse_ver(ver_str)
        if not check_v:
            continue
            
        if op == ">=":
            if target_v < check_v:
                return "❌", f"Too old (needs {ver_str})"
        elif op == "<":
            if target_v >= check_v:
                return "❌", f"Too new (must be <{ver_str})"
        elif op == "==":
            if target_v != check_v:
                return "❌", f"Exact match required: {ver_str}"
        elif op == "<=":
            if target_v > check_v:
                return "❌", f"Must be <={ver_str}"

    return "✅", "Compatible"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--releases-dir", required=True, help="Path to ovos-releases repo")
    parser.add_argument("--package", required=True, help="Package name to check")
    parser.add_argument("--version", required=True, help="Predicted next version")
    parser.add_argument("--output", required=True, help="Path to write the Markdown report")
    args = parser.parse_args()

    channels = {
        "Stable": "constraints-stable.txt",
        "Testing": "constraints-testing.txt",
        "Alpha": "constraints-alpha.txt"
    }

    report_lines = []
    report_lines.append("🚀 **Release Channel Compatibility**")
    report_lines.append("")
    report_lines.append(f"Predicted next version: `{args.version}`")
    report_lines.append("")
    report_lines.append("| Channel | Status | Note | Current Constraint |")
    report_lines.append("|---------|--------|------|--------------------|")

    for name, filename in channels.items():
        path = os.path.join(args.releases_dir, filename)
        if not os.path.exists(path):
            report_lines.append(f"| {name} | ❓ | {filename} not found | - |")
            continue

        with open(path, "r") as f:
            constraints = parse_constraints(f.read())
        
        constraint = constraints.get(args.package)
        if not constraint:
            report_lines.append(f"| {name} | ⚪ | Not in channel | - |")
        else:
            icon, note = check_version_against_constraint(args.version, constraint)
            report_lines.append(f"| {name} | {icon} | {note} | `{constraint}` |")

    with open(args.output, "w") as f:
        f.write("\n".join(report_lines))

if __name__ == "__main__":
    # Add parent dir to sys.path to import _version_utils if needed
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
