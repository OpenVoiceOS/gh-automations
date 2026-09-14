"""
resolve_codename.py - Resolve the active OVOS release codename.

Reads codenames/CURRENT (pointer) and validates it exists in codenames/CODENAMES.
Exits with code 0 on success, 1 on error.

Usage:
    python resolve_codename.py [--codenames-dir PATH]

Output (stdout):
    The codename string (e.g. "Achernar"), with a trailing newline.

Options:
    --codenames-dir PATH   Path to the directory containing CODENAMES and CURRENT.
                           Defaults to the codenames/ sibling of scripts/.
"""

from __future__ import annotations

import argparse
import os
import sys


def resolve_codename(codenames_dir: str) -> str:
    """Return the currently active codename.

    Args:
        codenames_dir: Path to the directory that holds CODENAMES and CURRENT.

    Returns:
        The active codename string (stripped).

    Raises:
        FileNotFoundError: If CODENAMES or CURRENT is missing.
        ValueError: If CURRENT points to a name not present in CODENAMES.
    """
    registry_path = os.path.join(codenames_dir, "CODENAMES")
    pointer_path = os.path.join(codenames_dir, "CURRENT")

    if not os.path.isfile(registry_path):
        raise FileNotFoundError(f"CODENAMES registry not found at {registry_path}")
    if not os.path.isfile(pointer_path):
        raise FileNotFoundError(f"CURRENT pointer not found at {pointer_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registered = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    with open(pointer_path, "r", encoding="utf-8") as f:
        current = f.read().strip()

    if not current:
        raise ValueError("CURRENT pointer file is empty")

    if current not in registered:
        raise ValueError(
            f"Codename '{current}' in CURRENT is not listed in CODENAMES registry. "
            f"Available names: {registered}"
        )

    return current


def advance_codename(codenames_dir: str) -> tuple[str, str]:
    """Advance the CURRENT pointer to the next name in the registry.

    Args:
        codenames_dir: Path to the directory that holds CODENAMES and CURRENT.

    Returns:
        (old_codename, new_codename) tuple.

    Raises:
        FileNotFoundError: If CODENAMES or CURRENT is missing.
        ValueError: If CURRENT is the last entry (no next name).
    """
    registry_path = os.path.join(codenames_dir, "CODENAMES")
    pointer_path = os.path.join(codenames_dir, "CURRENT")

    if not os.path.isfile(registry_path):
        raise FileNotFoundError(f"CODENAMES registry not found at {registry_path}")
    if not os.path.isfile(pointer_path):
        raise FileNotFoundError(f"CURRENT pointer not found at {pointer_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registered = [
            line.strip()
            for line in f
            if line.strip() and not line.strip().startswith("#")
        ]

    with open(pointer_path, "r", encoding="utf-8") as f:
        current = f.read().strip()

    if current not in registered:
        raise ValueError(
            f"Codename '{current}' in CURRENT is not listed in CODENAMES registry."
        )

    idx = registered.index(current)
    if idx + 1 >= len(registered):
        raise ValueError(
            f"'{current}' is the last codename in the registry. "
            "Append more names to codenames/CODENAMES before advancing."
        )

    next_name = registered[idx + 1]

    with open(pointer_path, "w", encoding="utf-8") as f:
        f.write(next_name + "\n")

    return current, next_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve (or advance) the active OVOS release codename."
    )
    default_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "codenames"
    )
    parser.add_argument(
        "--codenames-dir",
        default=default_dir,
        help="Path to the codenames/ directory (default: ../codenames relative to this script).",
    )
    parser.add_argument(
        "--advance",
        action="store_true",
        help="Advance the CURRENT pointer to the next codename (used by propose-codename workflow).",
    )
    args = parser.parse_args(argv)

    codenames_dir = os.path.abspath(args.codenames_dir)

    try:
        if args.advance:
            old, new = advance_codename(codenames_dir)
            print(f"Advanced codename: {old} -> {new}")
            print(f"new_codename={new}")
        else:
            name = resolve_codename(codenames_dir)
            print(name)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
