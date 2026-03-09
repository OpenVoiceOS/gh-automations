"""
On merge to dev: bump version in version.py according to PR label.

Called by publish-alpha.yml with one of: major | minor | build | alpha

Bump rules:
  major  — MAJOR += 1, MINOR = 0, BUILD = 0, ALPHA = 1
  minor  — MINOR += 1, BUILD = 0, ALPHA = 1
  build  — BUILD += 1, ALPHA = 1
  alpha  — ALPHA += 1 (if currently stable: BUILD += 1 first)
"""

from __future__ import annotations

import argparse
import sys
from os.path import abspath

from _version_utils import format_version, read_version, write_version_block


def update_version(part: str, version_file: str) -> str:
    """Bump the version in *version_file* according to *part* and return the new version string.

    Args:
        part: One of "major", "minor", "build", or "alpha".
        version_file: Absolute path to the version.py file.

    Returns:
        The new version string (e.g. "1.2.3a4").

    Raises:
        ValueError: If *part* is not one of the accepted values.
    """
    major, minor, build, alpha = read_version(version_file)

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
    else:
        raise ValueError(f"Unknown version part: {part!r}. Expected one of: major, minor, build, alpha")

    write_version_block(version_file, major, minor, build, alpha)
    return format_version(major, minor, build, alpha)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update the version based on the specified part (major, minor, build, alpha)"
    )
    parser.add_argument(
        "part",
        choices=["major", "minor", "build", "alpha"],
        help="Part of the version to update",
    )
    parser.add_argument("--version-file", required=True, help="Path to the version.py file")

    args = parser.parse_args()
    update_version(args.part, abspath(args.version_file))
