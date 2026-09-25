"""
Report test files that an explicit ``test_path`` allowlist leaves out.

``build-tests.yml`` passes ``test_path`` to pytest. A caller that names a
directory runs every test file under it. A caller that names files one by one
runs only those, and the list stops growing when a new test file is added.
``ovos-date-parser`` hid 82 of its 138 test files that way, a defect survived,
and a user found it (#347). The fleet census counted one repository of 47 with
a real gap, which is why nobody finds this by reading: the list grows one file
at a time and nobody re-reads it.

A file counts as covered when a ``test_path`` token is the file itself, or is a
directory prefix of it. A token that names a directory therefore covers
everything under it, and a directory-shaped ``test_path`` is always silent.

An uncovered file is not always a defect: a sibling workflow may run the rest
(``ovos-audio`` and ``ovos-workshop`` both do). So this is a warning by
default, and a failure only when the caller asks for one with
``test_path_strict``.

Usage:
    python check_test_path_coverage.py --test-path "test/unit test/test_x.py" \
        [--root .] [--strict] [--summary "$GITHUB_STEP_SUMMARY"]

Exit status: 0 when every file is covered, or when files are uncovered without
``--strict``. 1 when files are uncovered and ``--strict`` is set. 2 on a usage
error.
"""
import argparse
import os
import sys

TEST_DIR_SKIP = {".git", ".venv", "venv", "node_modules", "__pycache__",
                 ".tox", ".mypy_cache", ".pytest_cache", "build", "dist",
                 "_gh_automations", ".eggs"}


def is_test_file(name: str) -> bool:
    """A pytest default-discovery file name."""
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def collect_test_files(root: str) -> list:
    """Every test file under root, as paths relative to root, sorted."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in TEST_DIR_SKIP and not d.endswith(".egg-info"))
        for name in filenames:
            if is_test_file(name):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                found.append(rel.replace(os.sep, "/"))
    return sorted(found)


def normalise(token: str) -> str:
    """A token as a comparable relative path: no ./ prefix, no trailing slash."""
    token = token.strip()
    while token.startswith("./"):
        token = token[2:]
    return token.rstrip("/")


def covers(token: str, path: str) -> bool:
    """True when the token is the file, or a directory prefix of it."""
    token = normalise(token)
    if not token or token == ".":
        return True
    return path == token or path.startswith(token + "/")


def uncovered(test_path: str, files: list) -> list:
    """Files that no token names. Tokens are whitespace-separated."""
    tokens = [t for t in test_path.split() if normalise(t)]
    if not tokens:
        return []
    return [f for f in files if not any(covers(t, f) for t in tokens)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-path", required=True,
                    help="the test_path value, exactly as the caller passes it")
    ap.add_argument("--root", default=".", help="repository root to scan")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when a test file is covered by no token")
    ap.add_argument("--summary", default="",
                    help="path to write a step summary to (GITHUB_STEP_SUMMARY)")
    args = ap.parse_args()

    if not os.path.isdir(args.root):
        print(f"::error title=test_path coverage did not run::{args.root} is not a directory")
        return 2

    test_path = args.test_path
    tokens = [normalise(t) for t in test_path.split() if normalise(t)]
    if not tokens:
        print("test_path is empty: no test selection to check.")
        return 0

    files = collect_test_files(args.root)
    missing = uncovered(test_path, files)

    # Counts first: a sweep that cannot state N in and N out has not run.
    print(f"test_path tokens: {len(tokens)}")
    for t in tokens:
        print(f"  {t}")
    print(f"test files found:    {len(files)}")
    print(f"covered by a token:  {len(files) - len(missing)}")
    print(f"covered by no token: {len(missing)}")

    lines = []
    if missing:
        title = "test_path names no token for these test files"
        print(f"::warning title={title}::{len(missing)} of {len(files)} "
              f"test files run in no pytest invocation from this workflow")
        for f in missing:
            print(f"::warning file={f},title=not in test_path::"
                  f"{f} is a test file that this workflow's test_path does not name")
        lines.append(f"### test_path coverage: {len(missing)} of {len(files)} "
                     "test files are not named\n")
        lines.append("`test_path` names files explicitly, so a test file added "
                     "later runs nowhere until the list is updated. "
                     "Check whether a sibling workflow runs these; if none "
                     "does, they are not tested.\n")
        for f in missing:
            lines.append(f"- `{f}`")
        lines.append("")
    else:
        print("every test file is named by a test_path token.")
        lines.append(f"### test_path coverage: all {len(files)} test files are named\n")

    if args.summary:
        try:
            with open(args.summary, "a", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
        except OSError as e:
            print(f"::warning title=test_path coverage::could not write the summary: {e}")

    if missing and args.strict:
        print(f"::error title=test_path coverage::{len(missing)} test files are "
              "named by no test_path token, and test_path_strict is set")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
