"""build-tests.yml says so when no test ran (T-5587).

With test_path empty the Run Tests step is skipped, the result is "success" and
the job log shows nothing. The PR comment does say "The caller set no test path,
thus no test ran", but that comment is posted only on a pull_request and only
when pr_comment is true, so a push, or a caller with the comment off, gets no
signal at all. T-5499 found 17 callers in that state, one with 47 test files.

The step is the same shape as lint.yml's ruff file count (T-2338), so these tests
are the same shape as test_lint_file_count.py: run the step's script under bash
and read what it emits.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/build-tests.yml"
STEP_NAME = "Say so when no test ran"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def build_step(name):
    steps = workflow()["jobs"]["build_tests"]["steps"]
    return next(s for s in steps if s.get("name") == name)


def test_the_step_exists_and_runs_only_when_test_path_is_empty():
    cond = build_step(STEP_NAME)["if"]
    # always(), or a failed build would swallow the warning that no test ran
    assert "always()" in cond, cond
    assert "inputs.test_path == ''" in cond, cond


def test_the_step_emits_a_github_warning_annotation(tmp_path):
    script = build_step(STEP_NAME)["run"]
    r = subprocess.run(["bash", "-e"], input=script, cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert out.startswith("::warning title="), out
    # the words that stop a reader taking it for a passing suite
    assert "ran no test" in out, out
    assert "not a passing suite" in out, out
    # and it must say what to do about it
    assert "test_path" in out, out


def test_the_step_does_not_fail_the_job():
    """A failure here would turn every caller with no test_path red at once.
    T-5499 counted 24 repositories that call this workflow and have no test
    file at all; a failure is for once that set has drained."""
    step = build_step(STEP_NAME)
    assert "exit 1" not in step["run"], step["run"]
    assert step.get("continue-on-error") is None, step


def test_run_tests_is_still_the_only_step_gated_on_a_nonempty_test_path():
    """The annotation is the negative of the Run Tests condition. If one moves
    without the other, a job could both run tests and warn that it ran none."""
    steps = workflow()["jobs"]["build_tests"]["steps"]
    run_tests = next(s for s in steps if s.get("name") == "Run Tests")
    assert run_tests["if"] == "${{ inputs.test_path != '' }}", run_tests["if"]


def test_the_result_string_the_report_parses_is_unchanged():
    """post_build_report special-cases the exact string "no pytest summary" when
    it reads a matrix job's summary file. This change must not touch it: the
    writer and the reader have to keep agreeing."""
    text = WORKFLOW.read_text()
    assert text.count("no pytest summary") == 2, text.count("no pytest summary")
    assert 'echo "${SUMMARY:-no pytest summary}"' in text


def test_the_pr_comment_still_names_the_no_test_path_case():
    """The annotation is a second signal, not a replacement: the PR comment line
    that already covers this case must stay."""
    assert "The caller set no test path, thus no test ran." in WORKFLOW.read_text()
