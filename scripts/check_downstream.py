"""
Find and report packages that depend on a given package,
using pipdeptree against an installed environment.

Output is sorted deterministically so repeated runs only generate
a git commit when the actual dependency tree changes.

Usage:
    pip install pipdeptree
    python check_downstream.py --package ovos-bus-client --output downstream_report.txt
"""
import argparse
import subprocess
import sys


def _pkg_sort_key(line: str) -> str:
    """Extract lowercase package name from a pipdeptree line (strips indent and version)."""
    return line.strip().split("==")[0].lower()


def _sort_block(lines: list) -> list:
    """Recursively sort a pipdeptree tree block preserving parent→child structure."""
    if not lines:
        return []
    base_indent = len(lines[0]) - len(lines[0].lstrip())
    groups = []
    i = 0
    while i < len(lines):
        line = lines[i]
        indent = len(line) - len(line.lstrip())
        if indent == base_indent:
            children = []
            i += 1
            while i < len(lines):
                child_indent = len(lines[i]) - len(lines[i].lstrip())
                if child_indent > base_indent:
                    children.append(lines[i])
                    i += 1
                else:
                    break
            groups.append((line, children))
        else:
            i += 1
    groups.sort(key=lambda g: _pkg_sort_key(g[0]))
    result = []
    for header, children in groups:
        result.append(header)
        result.extend(_sort_block(children))
    return result


def sort_pipdeptree_output(text: str) -> str:
    """Sort pipdeptree output for stable diffs between runs."""
    if not text.strip():
        return text
    lines = text.rstrip("\n").split("\n")
    return "\n".join(_sort_block(lines)) + "\n"


def get_downstream(package_name: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pipdeptree", "-r", "-p", package_name],
        capture_output=True, text=True
    )
    raw = result.stdout or f"No dependents found for {package_name}\n"
    return sort_pipdeptree_output(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find downstream dependents of a package")
    parser.add_argument("--package", required=True, help="Package name to check")
    parser.add_argument("--output", default="downstream_report.txt", help="Output file path")
    args = parser.parse_args()

    report = get_downstream(args.package)
    with open(args.output, "w") as f:
        f.write(report)
    print(report)
