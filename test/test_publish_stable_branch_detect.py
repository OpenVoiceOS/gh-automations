"""publish-stable.yml 'Detect branch' picks the branch the caller asked for (T-6221).

The step used to compare the request to the default branch:

    if [ "$REQUESTED" == "master" ] && [ "$DEFAULT_BRANCH" != "master" ]

so a caller passing branch: 'master' on a repository whose default is dev was
moved onto dev even when master existed. Every later job reads
steps.branch_detect.outputs.actual_branch, so the version bump, the tag, the
PyPI upload and sync_dev all spoke for the development branch, and no CI run
could catch it: the workflow only runs when a stable release is cut.

The step now asks whether the requested branch exists. These tests execute the
step's own shell, taken out of the YAML, against a stub `gh` whose branch list
and default branch come from the environment.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/publish-stable.yml"

# a gh that answers from BRANCHES and DEFAULT_BRANCH, the two facts the step reads
GH_STUB = """#!/usr/bin/env bash
if [ "$1" == "api" ]; then
  # repos/<owner>/<repo>/branches/<name>
  name="${2##*/branches/}"
  for b in $BRANCHES; do
    if [ "$b" == "$name" ]; then exit 0; fi
  done
  echo "gh: Not Found (HTTP 404)" >&2
  exit 1
fi
if [ "$1" == "repo" ] && [ "$2" == "view" ]; then
  echo "$DEFAULT_BRANCH"
  exit 0
fi
echo "gh stub: unexpected call: $*" >&2
exit 2
"""


def detect_step() -> str:
    doc = yaml.safe_load(WORKFLOW.read_text())
    steps = doc["jobs"]["bump_version"]["steps"]
    step = next(s for s in steps if s.get("name") == "Detect branch")
    return step["run"]


def run_step(tmp_path: Path, requested: str, branches: str, default: str) -> str:
    """execute the step's shell and return actual_branch"""
    script = detect_step()
    # the only expressions the step interpolates
    script = script.replace("${{ inputs.branch }}", requested)
    script = script.replace("${{ github.repository }}", "OpenVoiceOS/a-repo")
    assert "${{" not in script, f"an unsubstituted expression remains:\n{script}"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)

    out = tmp_path / "github_output"
    out.write_text("")
    env = dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        GITHUB_OUTPUT=str(out),
        BRANCHES=branches,
        DEFAULT_BRANCH=default,
    )
    proc = subprocess.run(["bash", "-e", "-c", script], env=env, cwd=tmp_path,
                          capture_output=True, text=True)
    assert proc.returncode == 0, f"the step failed:\n{proc.stdout}\n{proc.stderr}"
    written = out.read_text()
    m = re.search(r"^actual_branch=(.*)$", written, re.M)
    assert m, f"the step wrote no actual_branch: {written!r}"
    return m.group(1)


def test_master_is_honoured_when_it_exists_and_the_default_is_dev(tmp_path):
    """the defect: rover's shape, master present, default dev"""
    assert run_step(tmp_path, "master", "dev master", "dev") == "master"


def test_master_is_honoured_when_it_is_also_the_default(tmp_path):
    """the control: the old condition was already right here"""
    assert run_step(tmp_path, "master", "master", "master") == "master"


def test_an_absent_master_falls_back_to_the_default(tmp_path):
    """the fallback the input documents"""
    assert run_step(tmp_path, "master", "dev", "dev") == "dev"


def test_an_absent_branch_falls_back_even_when_it_is_not_master(tmp_path):
    """the second half of the defect: the old step only ever checked 'master'"""
    assert run_step(tmp_path, "main", "dev master", "dev") == "dev"


def test_a_requested_branch_that_exists_is_never_replaced(tmp_path):
    """a caller whose stable branch is not called master"""
    assert run_step(tmp_path, "stable", "dev stable", "dev") == "stable"


def test_the_step_never_compares_the_request_to_the_default(tmp_path):
    """the shape of the defect, so it cannot come back as a comparison"""
    script = detect_step()
    assert '"$DEFAULT_BRANCH" != "master"' not in script
    assert "branches/" in script, "the step must ask whether the branch exists"
