"""lint.yml counts the files ruff checked (T-2338). ruff exits 0 for a clean
tree and for a ruff_args that matched no file, and the comment read "no
issues" for both. The count step and the comment step run under bash with a
fake ruff."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/lint.yml"

FAKE_RUFF = """#!/usr/bin/env bash
# `ruff check <args> --show-files` lists $RUFF_FILES lines
if [[ " $* " == *" --show-files "* ]]; then
  for f in $RUFF_FILES; do echo "$f"; done
fi
exit 0
"""


def step(name):
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == name)


def run(tmp_path, name, files, outcome="success", ruff_args="."):
    script = step(name)["run"]
    known = {"inputs.ruff_args": ruff_args, "inputs.ruff": "true", "steps.ruff.outcome": outcome,
             "steps.ruff_files.outputs.count": str(len(files.split()))}

    def value(m):
        # Every other lint (pre_commit, actionlint, whatever lint.yml gains
        # next) is off, and its step outputs are skipped or empty.
        k = m.group(1)
        if k in known:
            return known[k]
        if k.startswith("inputs."):
            return "false"
        return "skipped" if k.endswith(".outcome") else ""

    script = re.sub(r"\$\{\{\s*([A-Za-z0-9_.]+)\s*\}\}", value, script)
    assert "${{" not in script, script
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    ruff = bindir / "ruff"
    ruff.write_text(FAKE_RUFF)
    ruff.chmod(ruff.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "out"
    out.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", GITHUB_OUTPUT=str(out), RUFF_FILES=files)
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    section = Path("/tmp/lint-section.md")
    return r.stdout, out.read_text(), section.read_text() if section.exists() else ""


def test_count_step_reports_the_files_and_warns_on_zero(tmp_path):
    out, gh_out, _ = run(tmp_path, "Count the files ruff checked", "a.py b.py c.py")
    assert "ruff matched 3 file(s)" in out and "count=3" in gh_out and "::warning" not in out
    out, gh_out, _ = run(tmp_path, "Count the files ruff checked", "", ruff_args="nosuch")
    assert "count=0" in gh_out
    assert "::warning title=ruff checked nothing::ruff_args 'nosuch' matched no file" in out


@pytest.mark.parametrize("files, outcome, expected", [
    ("a.py b.py", "success", "✅ **ruff**: no issues in 2 file(s)"),
    ("a.py b.py", "failure", "❌ **ruff**: issues found in 2 file(s) — see job log"),
    ("", "success", "⚠️ **ruff**: checked no file (ruff_args matched nothing) — not a clean result"),
])
def test_comment_names_the_count_and_never_calls_nothing_clean(tmp_path, files, outcome, expected):
    _, _, section = run(tmp_path, "Format lint section for PR comment", files, outcome)
    assert section.strip() == expected
