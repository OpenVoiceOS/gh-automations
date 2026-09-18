"""channel-compat.yml under soft_fail says so on every run (T-2338). The
install and test steps carry continue-on-error and the job is green; the
PR comment stated the failure only on a pull_request run. A warning
annotation and a job summary line now carry it on every run."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/channel-compat.yml"


def step():
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == "Say so when soft_fail swallowed a failure")


def test_step_runs_only_under_soft_fail_with_a_failure():
    cond = step()["if"]
    assert "always()" in cond and "inputs.soft_fail" in cond
    assert "steps.install.outcome == 'failure'" in cond and "steps.tests.outcome == 'failure'" in cond


@pytest.mark.parametrize("install, tests, expected", [
    ("failure", "skipped", "the repo does not resolve against the channel constraints"),
    ("success", "failure", "the test suite failed"),
])
def test_warning_and_summary_name_the_failure(tmp_path, install, tests, expected):
    script = step()["run"]
    for k, v in (("steps.channel.outputs.name", "stable"), ("steps.install.outcome", install), ("steps.tests.outcome", tests)):
        script = script.replace("${{ %s }}" % k, v)
    assert "${{" not in script
    summary = tmp_path / "summary.md"
    summary.touch()
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)))
    assert r.returncode == 0, r.stderr
    assert f"::warning title=channel-compat soft failure::channel stable: {expected} (soft_fail held the job green)" in r.stdout
    assert expected in summary.read_text() and "channel-compat-stable artifact" in summary.read_text()
