"""Read version string from version.py file (START_VERSION_BLOCK/END_VERSION_BLOCK format).

Used by publish-alpha.yml and publish-stable.yml to capture the new version after
update_version.py or remove_alpha.py has run.
"""

from __future__ import annotations

import argparse
import sys
from os.path import abspath

from _version_utils import format_version, read_version, find_version_file


def get_version(version_file: str) -> str:
    """Read and format the version string from *version_file*.

    Args:
        version_file: Absolute or relative path to the version.py file.

    Returns:
        Version string, e.g. "1.2.3a4" (alpha) or "1.2.3" (stable).
    """
    major, minor, build, alpha = read_version(version_file)
    return format_version(major, minor, build, alpha)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get version string from version.py file")
    parser.add_argument("--version-file", default="version.py", help="Path to version.py file")
    args = parser.parse_args()
    
    version_file = find_version_file(".", args.version_file)
    if not version_file:
        print(f"Could not find version file '{args.version_file}'", file=sys.stderr)
        sys.exit(1)
        
    print(get_version(version_file))
