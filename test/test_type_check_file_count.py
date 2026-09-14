"""
A green Type Check must prove that mypy read a file.

mypy names the number of source files it read, in one of two lines:

    Success: no issues found in 12 source files
    Found 3 errors in 2 files (checked 12 source files)

When mypy cannot read its target it names no count:

    Found 1 error in 1 file (errors prevented further checking)

`type-check.yml` extracts that count and fails the job when there is none, so
an empty mypy output can no longer be reported as a clean type check. These
tests hold the regex in the workflow to the strings mypy really writes, in
both directions, and hold the failing step to its gate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed — skipping type check tests", allow_module_level=True)


WORKFLOWS_DIR = Path(__file__).parent.parent / ".github" / "workflows"
TYPE_CHECK = WORKFLOWS_DIR / "type-check.yml"
COVERAGE = WORKFLOWS_DIR / "coverage.yml"


def _steps(workflow: Path, job: str) -> list[dict]:
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    return data["jobs"][job]["steps"]


def _step(workflow: Path, job: str, name: str) -> dict:
    for step in _steps(workflow, job):
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in {workflow.name}")


def _count_regex() -> re.Pattern[str]:
    """The regex the workflow itself uses, read out of the workflow."""
    body = _step(TYPE_CHECK, "type_check", "Count the source files mypy read")["run"]
    match = re.search(r're\.search\(r"([^"]+)"', body)
    assert match, "the count step no longer holds a re.search pattern"
    return re.compile(match.group(1))


# Real mypy 2.3.1 output. Captured by running mypy on a clean file, on a tree
# with one type error, and on a target that does not exist.
CLEAN_ONE = "Success: no issues found in 1 source file\n"
CLEAN_MANY = "Success: no issues found in 12 source files\n"
WITH_ERRORS = (
    'pkg/bad.py:2:12: error: Incompatible return value type (got "int", expected "str")'
    "  [return-value]\nFound 1 error in 1 file (checked 2 source files)\n"
)
UNREADABLE_TARGET = (
    "mypy: error: Cannot read file 'no_such_pkg': No such file or directory\n"
    "Found 1 error in 1 file (errors prevented further checking)\n"
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (CLEAN_ONE, "1"),
        (CLEAN_MANY, "12"),
        (WITH_ERRORS, "2"),
    ],
)
def test_count_is_read_when_mypy_names_one(raw: str, expected: str) -> None:
    match = _count_regex().search(raw)
    assert match and match.group(1) == expected


@pytest.mark.parametrize("raw", [UNREADABLE_TARGET, "", "\n"])
def test_no_count_when_mypy_read_nothing(raw: str) -> None:
    """The case that used to pass as a clean check."""
    assert _count_regex().search(raw) is None


def test_the_job_fails_when_no_count_was_found() -> None:
    step = _step(TYPE_CHECK, "type_check", "Fail job if mypy checked no files")
    condition = step["if"]
    assert "steps.mypy_files.outputs.count == ''" in condition
    assert "steps.mypy_files.outputs.count == '0'" in condition
    assert "exit 1" in step["run"]


def test_that_failure_is_not_gated_on_fail_on_errors() -> None:
    """A job that read no file is a misconfiguration, not a type error."""
    step = _step(TYPE_CHECK, "type_check", "Fail job if mypy checked no files")
    assert "fail_on_errors" not in step["if"]


def test_the_human_run_keeps_the_summary_line() -> None:
    """--no-error-summary suppresses the only line that holds the count."""
    body = _step(TYPE_CHECK, "type_check", "Run mypy")["run"]
    human = [l for l in body.splitlines() if "mypy-human.txt" in l or "--show-column-numbers" in l]
    assert human, "the human-readable mypy invocation is gone"
    # The json invocation may keep it; the invocations that feed the count and
    # the exit code may not.
    assert body.count("--no-error-summary") == 1


def test_coverage_says_advisory_when_no_minimum_is_set() -> None:
    body = _step(COVERAGE, "coverage", "Format coverage section for PR comment")["run"]
    assert "advisory — no minimum set, nothing enforced" in body
    assert '"✅" if total >= 80' not in body, "a tick states a verdict no threshold reached"
