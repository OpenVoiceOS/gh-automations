"""A test_path that names files one by one stops covering the suite when a test
file is added, and nobody re-reads the list: ovos-date-parser hid 82 of its 138
test files that way and a defect reached a user (#347). build-tests.yml now
reports a test file that no test_path token names.

The cases run the real script against fixture trees, and check the wiring of the
job that calls it: the guard, the environment, and the strict input. The step's
own run block is executed under bash, so the test covers the argument assembly
and not only the script.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/check_test_path_coverage.py"
WORKFLOW = ROOT / ".github/workflows/build-tests.yml"
JOB = "test_path_coverage"


def make_tree(base: Path) -> None:
    """A repository with test files in two directories and at the top level."""
    (base / "test/unit").mkdir(parents=True)
    (base / "test/end2end").mkdir(parents=True)
    (base / "src/pkg").mkdir(parents=True)
    for rel in ("test/unit/test_a.py", "test/unit/test_b.py",
                "test/end2end/test_slow.py", "test/test_top.py",
                "test/legacy_test.py"):
        (base / rel).write_text("def test_x():\n    assert True\n", encoding="utf-8")
    # not test files: must not be counted
    (base / "test/helpers.py").write_text("X = 1\n", encoding="utf-8")
    (base / "src/pkg/__init__.py").write_text("", encoding="utf-8")
    (base / "src/pkg/testing.py").write_text("X = 1\n", encoding="utf-8")
    # a directory the walk must skip, holding a file that looks like a test
    (base / ".venv/lib").mkdir(parents=True)
    (base / ".venv/lib/test_vendored.py").write_text("", encoding="utf-8")


def run_script(root: Path, test_path: str, *extra: str):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--test-path", test_path, "--root", str(root), *extra],
        capture_output=True, text=True, check=False)


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    make_tree(tmp_path)
    return tmp_path


def test_every_test_file_is_found_and_none_else(tree: Path):
    """Five test files, by both naming conventions; helpers and vendored are not."""
    res = run_script(tree, "test")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "test files found:    5" in res.stdout, res.stdout
    assert "covered by no token: 0" in res.stdout, res.stdout
    assert "test_vendored" not in res.stdout
    assert "helpers.py" not in res.stdout


def test_a_directory_token_is_silent(tree: Path):
    """The control: a directory-shaped test_path warns about nothing."""
    res = run_script(tree, "test")
    assert res.returncode == 0
    assert "::warning" not in res.stdout, res.stdout
    assert "every test file is named" in res.stdout


@pytest.mark.parametrize("token", ["test", "test/", "./test", "./test/"])
def test_a_directory_token_is_silent_however_it_is_written(tree: Path, token: str):
    res = run_script(tree, token)
    assert res.returncode == 0
    assert "::warning" not in res.stdout, f"{token}: {res.stdout}"


def test_an_allowlist_names_the_files_it_leaves_out(tree: Path):
    """The canary: an allowlist that misses two files reports exactly those."""
    res = run_script(tree, "test/unit test/test_top.py")
    assert res.returncode == 0, "a warning must not fail the job by default"
    assert "covered by no token: 2" in res.stdout, res.stdout
    assert "test/end2end/test_slow.py" in res.stdout
    assert "test/legacy_test.py" in res.stdout
    assert "::warning" in res.stdout
    # the covered ones are not reported
    assert "not in test_path::test/unit/test_a.py" not in res.stdout


def test_strict_turns_the_warning_into_a_failure(tree: Path):
    res = run_script(tree, "test/unit test/test_top.py", "--strict")
    assert res.returncode == 1
    assert "::error" in res.stdout


def test_strict_does_not_fail_a_caller_that_covers_everything(tree: Path):
    """A correct caller never reddens, whatever the input is set to."""
    res = run_script(tree, "test", "--strict")
    assert res.returncode == 0, res.stdout


def test_an_empty_test_path_checks_nothing(tree: Path):
    res = run_script(tree, "")
    assert res.returncode == 0
    assert "no test selection" in res.stdout


def test_a_token_does_not_cover_a_directory_whose_name_it_prefixes(tmp_path: Path):
    """`test/unit` must not cover `test/unit_extra/test_x.py`. The match is a
    path boundary, not a string prefix: a string prefix silently covers every
    directory whose name begins with the token, and the file runs nowhere while
    the check reports it as covered."""
    (tmp_path / "test/unit").mkdir(parents=True)
    (tmp_path / "test/unit_extra").mkdir(parents=True)
    (tmp_path / "test/unit/test_in.py").write_text("", encoding="utf-8")
    (tmp_path / "test/unit_extra/test_out.py").write_text("", encoding="utf-8")
    res = run_script(tmp_path, "test/unit")
    assert "test files found:    2" in res.stdout, res.stdout
    assert "covered by no token: 1" in res.stdout, res.stdout
    assert "test/unit_extra/test_out.py" in res.stdout


def test_a_file_token_does_not_cover_a_sibling_by_prefix(tmp_path: Path):
    """test/test_a.py must not cover test/test_ab.py."""
    (tmp_path / "test").mkdir()
    for name in ("test_a.py", "test_ab.py"):
        (tmp_path / "test" / name).write_text("", encoding="utf-8")
    res = run_script(tmp_path, "test/test_a.py")
    assert "covered by no token: 1" in res.stdout, res.stdout
    assert "test/test_ab.py" in res.stdout


def test_the_summary_lists_the_uncovered_files(tree: Path, tmp_path: Path):
    summary = tmp_path / "summary.md"
    res = run_script(tree, "test/unit test/test_top.py", "--summary", str(summary))
    assert res.returncode == 0
    written = summary.read_text(encoding="utf-8")
    assert "test/end2end/test_slow.py" in written
    assert "2 of 5 test files are not named" in written


# ---------------------------------------------------------------- the wiring --


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def workflow_inputs():
    wf = workflow()
    key = [k for k in wf if k in (True, "on")][0]
    return wf[key]["workflow_call"]["inputs"]


def coverage_step():
    steps = workflow()["jobs"][JOB]["steps"]
    return [s for s in steps if s.get("name") == "Check test_path coverage"][0]


def test_the_job_runs_only_when_a_test_path_is_set():
    assert workflow()["jobs"][JOB]["if"].strip() == "${{ inputs.test_path != '' }}"


def test_the_job_is_not_in_the_python_matrix():
    """One annotation, not one per interpreter."""
    assert "strategy" not in workflow()["jobs"][JOB]


def test_the_strict_input_defaults_to_a_warning():
    spec = workflow_inputs()["test_path_strict"]
    assert spec["type"] == "boolean"
    assert spec["default"] is False


def test_test_path_reaches_the_script_through_the_environment():
    """Caller text on a command line would be read as shell syntax."""
    step = coverage_step()
    assert step["env"]["TEST_PATH"] == "${{ inputs.test_path }}"
    assert "${{ inputs.test_path }}" not in step["run"]
    assert '"$TEST_PATH"' in step["run"]


def test_the_step_runs_the_shipped_script():
    step = coverage_step()
    assert "_gh_automations/scripts/check_test_path_coverage.py" in step["run"]


@pytest.mark.parametrize(("strict", "want_rc"), [("false", 0), ("true", 1)])
def test_the_step_run_block_assembles_the_strict_flag(tree: Path, tmp_path: Path,
                                                      strict: str, want_rc: int):
    """The run block itself, under bash, with the real script."""
    run = coverage_step()["run"].replace(
        "python _gh_automations/scripts/check_test_path_coverage.py",
        f"{sys.executable} {SCRIPT}")
    env = dict(os.environ,
               TEST_PATH="test/unit test/test_top.py",
               STRICT=strict,
               GITHUB_STEP_SUMMARY=str(tmp_path / "summary.md"))
    res = subprocess.run(["bash", "-euo", "pipefail", "-c", run],
                         cwd=tree, env=env, capture_output=True, text=True, check=False)
    assert res.returncode == want_rc, res.stdout + res.stderr
