"""
On merge to the stable branch (e.g. master or main): declare stable by setting VERSION_ALPHA = 0.

Called by publish-stable.yml after the release PR is merged.
Uses the shared write_version_block utility to rewrite only the version block,
safely scoped within START_VERSION_BLOCK / END_VERSION_BLOCK markers.
"""

from __future__ import annotations

import argparse
import sys
from os.path import abspath

from _version_utils import read_version, write_version_block, find_version_file


def update_alpha(version_file: str) -> None:
    """Set VERSION_ALPHA = 0 in *version_file* (declare stable).

    Reads current version components, then rewrites the block with alpha = 0.
    All content outside the version block is preserved unchanged.

    Args:
        version_file: Absolute path to the version.py file.
    """
    major, minor, build, _alpha = read_version(version_file)
    write_version_block(version_file, major, minor, build, 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Declare stable: set VERSION_ALPHA = 0 in version.py"
    )
    parser.add_argument("--version-file", default="version.py", help="Path to the version.py file")

    args = parser.parse_args()
    
    version_file = find_version_file(".", args.version_file)
    if not version_file:
        print(f"Could not find version file '{args.version_file}'", file=sys.stderr)
        sys.exit(1)
        
    update_alpha(version_file)
