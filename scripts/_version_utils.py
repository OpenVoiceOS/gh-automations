"""
Shared version.py parsing utilities used by update_version.py, remove_alpha.py, and get_version.py.

All three scripts operate on the START_VERSION_BLOCK / END_VERSION_BLOCK format:

    # START_VERSION_BLOCK
    VERSION_MAJOR = 1
    VERSION_MINOR = 2
    VERSION_BUILD = 3
    VERSION_ALPHA = 4   # 0 = stable
    # END_VERSION_BLOCK
"""

from __future__ import annotations


def read_version(version_file: str) -> tuple[int, int, int, int]:
    """Parse VERSION_MAJOR, VERSION_MINOR, VERSION_BUILD, VERSION_ALPHA from a version.py file.

    Reads only the lines between START_VERSION_BLOCK and END_VERSION_BLOCK markers.
    Returns (major, minor, build, alpha). Returns 0 for any component not found.

    Args:
        version_file: Absolute or relative path to the version.py file.

    Returns:
        Tuple of (VERSION_MAJOR, VERSION_MINOR, VERSION_BUILD, VERSION_ALPHA).
    """
    major = minor = build = alpha = 0

    with open(version_file, "r") as f:
        in_block = False
        for line in f:
            stripped = line.strip()
            if stripped.startswith("# START_VERSION_BLOCK"):
                in_block = True
                continue
            if stripped.startswith("# END_VERSION_BLOCK"):
                break
            if not in_block:
                continue
            if stripped.startswith("VERSION_MAJOR"):
                major = int(stripped.split("=")[-1].strip().split("#")[0].strip())
            elif stripped.startswith("VERSION_MINOR"):
                minor = int(stripped.split("=")[-1].strip().split("#")[0].strip())
            elif stripped.startswith("VERSION_BUILD"):
                build = int(stripped.split("=")[-1].strip().split("#")[0].strip())
            elif stripped.startswith("VERSION_ALPHA"):
                alpha = int(stripped.split("=")[-1].strip().split("#")[0].strip())

    return major, minor, build, alpha


def format_version(major: int, minor: int, build: int, alpha: int) -> str:
    """Format version components into a PEP 440 version string.

    Args:
        major: Major version component.
        minor: Minor version component.
        build: Build/patch version component.
        alpha: Alpha counter. 0 means stable (no alpha suffix).

    Returns:
        Version string, e.g. "1.2.3a4" or "1.2.3".
    """
    version = f"{major}.{minor}.{build}"
    if alpha:
        version += f"a{alpha}"
    return version


def write_version_block(version_file: str, major: int, minor: int, build: int, alpha: int) -> None:
    """Rewrite the START_VERSION_BLOCK section of a version.py file with new values.

    Preserves all content outside the version block unchanged.

    Args:
        version_file: Absolute or relative path to the version.py file.
        major: New VERSION_MAJOR value.
        minor: New VERSION_MINOR value.
        build: New VERSION_BUILD value.
        alpha: New VERSION_ALPHA value.
    """
    with open(version_file, "r") as f:
        content = f.read()

    # Split on END_VERSION_BLOCK to preserve everything after the block
    after_block = content.split("# END_VERSION_BLOCK")[-1]

    new_block = (
        f"# START_VERSION_BLOCK\n"
        f"VERSION_MAJOR = {major}\n"
        f"VERSION_MINOR = {minor}\n"
        f"VERSION_BUILD = {build}\n"
        f"VERSION_ALPHA = {alpha}\n"
        f"# END_VERSION_BLOCK"
    )

    with open(version_file, "w") as f:
        f.write(new_block + after_block)
