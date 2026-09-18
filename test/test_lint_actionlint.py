"""lint.yml runs actionlint over .github/workflows (T-2915). The step is run
under bash against the real tool (actionlint-py) on the two shapes that
GitHub refuses at parse time and PyYAML accepts, and on a clean file."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/lint.yml"

CLEAN = """name: ok
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""
# the hivemind-test-harness docs-mirror.yml shape: an empty expression pair
# inside a shell comment of a run block
EMPTY_EXPRESSION = """name: bad
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - run: |
          # not an inline ${{ }} interpolation
          echo hi
"""
# gh-automations#126's 8f4924e shape: a key twice in one mapping
DUPLICATE_KEY = """name: dup
on: push
jobs:
  a:
    runs-on: ubuntu-latest
    steps:
      - env:
          A: 1
        run: echo hi
        env:
          B: 2
"""


def step():
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == "Run actionlint")


def run_step(tmp_path, files):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # actionlint wants a project root
    wfdir = tmp_path / ".github" / "workflows"
    wfdir.mkdir(parents=True)
    for name, text in files.items():
        (wfdir / name).write_text(text)
    script = step()["run"].replace("uv pip install actionlint-py\n", "")  # the tool is on PATH here
    assert "${{" not in script
    out = tmp_path / "out"
    out.touch()
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ, GITHUB_OUTPUT=str(out)))
    return r, dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)


pytestmark = pytest.mark.skipif(shutil.which("actionlint") is None, reason="actionlint not on PATH")


def test_clean_workflows_pass_with_the_file_count(tmp_path):
    r, out = run_step(tmp_path, {"a.yml": CLEAN, "b.yaml": CLEAN})
    assert r.returncode == 0, r.stdout
    assert out == {"files": "2", "findings": "0"}
    assert "actionlint: 2 workflow file(s), 0 finding(s), exit 0" in r.stdout


def test_an_empty_expression_in_a_run_comment_is_a_finding(tmp_path):
    r, out = run_step(tmp_path, {"docs-mirror.yml": EMPTY_EXPRESSION})
    assert r.returncode != 0
    assert out["files"] == "1" and out["findings"] == "1"
    assert "unexpected end of input" in r.stdout


def test_a_duplicate_key_is_a_finding(tmp_path):
    r, out = run_step(tmp_path, {"dup.yml": DUPLICATE_KEY})
    assert r.returncode != 0 and out["findings"] == "1"
    assert "already defined" in r.stdout or "duplicate" in r.stdout


def test_no_workflow_file_is_not_a_finding(tmp_path):
    r, out = run_step(tmp_path, {})
    assert r.returncode == 0 and out == {"files": "0", "findings": "0"}


def test_gate_step_fails_only_on_a_finding_when_asked():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    gate = next(s for s in steps if s.get("name") == "Fail the job on actionlint findings")
    assert "inputs.actionlint_fail" in gate["if"] and "steps.actionlint.outcome == 'failure'" in gate["if"]
    assert "exit 1" in gate["run"]
    inputs = wf[True]["workflow_call"]["inputs"]
    assert inputs["actionlint"]["default"] is True and inputs["actionlint_fail"]["default"] is True
