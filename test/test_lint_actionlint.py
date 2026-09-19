"""lint.yml runs actionlint over .github/workflows (T-2915). The step is run
under bash against the real tool (actionlint-py) on the two shapes that
GitHub refuses at parse time and PyYAML accepts, and on a clean file."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
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
    script = step()["run"].replace('uv pip install "$ACTIONLINT_PY"\n', "")  # the tool is on PATH here
    assert "${{" not in script
    out = tmp_path / "out"
    out.touch()
    assert Path(ACTIONLINT).exists(), f"actionlint not installed at {ACTIONLINT}"
    env = dict(os.environ, GITHUB_OUTPUT=str(out), PATH=f"{Path(ACTIONLINT).parent}:{os.environ['PATH']}")
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True, env=env)
    return r, dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)


# actionlint-py puts the binary beside the interpreter; the Test workflow
# installs it, so a missing binary is a failure here, not a skip.
ACTIONLINT = shutil.which("actionlint") or str(Path(sys.executable).parent / "actionlint")


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


# T-3335: one exact actionlint release for the fleet. lint.yml pins it in
# its env, test.yml installs the same one for these tests, and Renovate's
# regex manager moves both. A drift between the two means the tests ran a
# different linter than the fleet.
ACTIONLINT_PIN = re.compile(r"actionlint-py==([0-9][0-9.]*)")


def test_the_actionlint_pin_is_exact_and_the_same_in_both_workflows():
    lint_env = yaml.safe_load(WORKFLOW.read_text())["env"]["ACTIONLINT_PY"]
    m = ACTIONLINT_PIN.fullmatch(lint_env)
    assert m, f"lint.yml env ACTIONLINT_PY is not an exact pin: {lint_env!r}"
    test_wf = (ROOT / ".github/workflows/test.yml").read_text()
    pins = set(ACTIONLINT_PIN.findall(test_wf))
    assert pins == {m.group(1)}, f"test.yml installs {pins or 'no pin'}, lint.yml pins {m.group(1)}"


def test_renovate_moves_the_actionlint_pin():
    cfg = json.loads((ROOT / "renovate.json").read_text())
    managers = [c for c in cfg.get("customManagers", []) if c.get("depNameTemplate") == "actionlint-py"]
    assert managers, "renovate.json has no custom manager for actionlint-py"
    # Renovate writes RE2 named groups, (?<name>); Python spells them (?P<name>)
    pattern = re.compile(managers[0]["matchStrings"][0].replace("(?<", "(?P<"))
    lint_env = yaml.safe_load(WORKFLOW.read_text())["env"]["ACTIONLINT_PY"]
    assert pattern.search(lint_env), "the Renovate matchString does not match lint.yml's pin"
    assert pattern.search((ROOT / ".github/workflows/test.yml").read_text()), \
        "the Renovate matchString does not match test.yml's pin"
