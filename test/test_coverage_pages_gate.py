"""coverage-pages.yml fails the job when the test suite failed (T-2338). The
test step keeps continue-on-error so the report still deploys, and a last
step reads its outcome; before it nothing did, and a failing suite was a
green job."""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/coverage-pages.yml"


def steps():
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(iter(wf["jobs"].values()))["steps"]


def test_the_test_step_has_an_id_and_continue_on_error():
    s = next(s for s in steps() if s.get("name") == "Run Tests with Coverage")
    assert s["id"] == "tests" and s["continue-on-error"] is True


def test_the_last_step_fails_on_the_test_outcome():
    last = steps()[-1]
    assert "steps.tests.outcome != 'success'" in last["if"]
    assert "exit 1" in last["run"] and "::error::" in last["run"]


def test_the_deploy_step_runs_before_the_gate():
    names = [s.get("name") for s in steps()]
    assert names.index("Deploy to gh-pages branch") < names.index("Fail the job when the tests failed")
