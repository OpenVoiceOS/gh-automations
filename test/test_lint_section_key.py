"""lint.yml keys its PR comment section on section_key (T-2899). Two lint
jobs on one pull request shared the id "lint" and the second overwrote the
first. The post step runs under bash with a fake update_pr_comment.py."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/lint.yml"


def step():
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == "Post lint section to PR comment")


def test_section_key_input_exists_with_an_empty_default():
    wf = yaml.safe_load(WORKFLOW.read_text())
    inp = wf[True]["workflow_call"]["inputs"]["section_key"]
    assert inp["type"] == "string" and inp["default"] == ""


@pytest.mark.parametrize("key, section_id, title", [
    ("", "lint", "🔍 Lint"),
    ("core", "lint-core", "🔍 Lint (core)"),
    ("plugins/gui x", "lint-plugins-gui-x", "🔍 Lint (plugins/gui x)"),
])
def test_section_id_and_title_follow_the_key(tmp_path, key, section_id, title):
    script = step()["run"]
    for k, v in (("github.repository", "o/r"), ("github.event.pull_request.number", "9")):
        script = script.replace("${{ %s }}" % k, v)
    assert "${{" not in script
    fake = tmp_path / "_gh_automations" / "scripts"
    fake.mkdir(parents=True)
    (fake / "update_pr_comment.py").write_text("import sys; print(' '.join(sys.argv[1:]))")
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ, SECTION_KEY=key))
    assert r.returncode == 0, r.stderr
    assert f"--section-id {section_id} --title {title} --content-file" in r.stdout
