"""docs-check.yml: a crashed markdownlint no longer reads as clean (T-2338).
The lint step is run under bash with a fake npm and a fake markdownlint-cli2;
the report step is run with the status file the lint step writes."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/docs-check.yml"

FAKE_NPM = """#!/usr/bin/env bash
exit ${NPM_RC:-0}
"""
# prints what markdownlint-cli2 prints: Linting/Summary lines, then findings
FAKE_ML = """#!/usr/bin/env bash
echo "markdownlint-cli2 v0.23.2 (markdownlint v0.41.1)"
echo "Finding: $*"
echo "Linting: ${ML_FILES:-2} files"
echo "Summary: ${ML_ISSUES:-0} issues in 1 file"
[ "${ML_ISSUES:-0}" != "0" ] && echo "b.md:1 error MD022/blanks-around-headings Headings should be surrounded by blank lines"
exit ${ML_RC:-0}
"""


def step(name):
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == name)


def bash(tmp_path, script, env):
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    for name, body in (("npm", FAKE_NPM), ("markdownlint-cli2", FAKE_ML)):
        f = bindir / name
        f.write_text(body)
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    full = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", **env)
    return subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=full, capture_output=True, text=True)


def lint(tmp_path, **env):
    script = step("Run markdownlint")["run"].replace("${{ inputs.markdownlint_config }}", "")
    assert "${{" not in script
    r = bash(tmp_path, script, env)
    status = Path("/tmp/markdownlint-status.txt").read_text().strip() if Path("/tmp/markdownlint-status.txt").exists() else ""
    return r, status


def report(tmp_path, outcome):
    script = step("Format docs check section for PR comment")["run"]
    r = bash(tmp_path, script, {"FILE_CHECK_OUTCOME": "success", "MARKDOWNLINT_OUTCOME": outcome, "RUN_MARKDOWNLINT": "true"})
    assert r.returncode == 0, r.stderr
    return Path("/tmp/docs-check-section.md").read_text()


def test_install_failure_is_a_failed_step_and_says_so(tmp_path):
    r, status = lint(tmp_path, NPM_RC="1")
    assert r.returncode == 1
    assert "::warning title=markdownlint did not install::" in r.stdout
    assert status == "status=install-failed"
    assert "did not install — the documents were not linted" in report(tmp_path, "failure")


def test_clean_lint_reports_the_file_count(tmp_path):
    r, status = lint(tmp_path, ML_FILES="7", ML_ISSUES="0")
    assert r.returncode == 0 and status == "status=ran rc=0 files=7 issues=0"
    assert "✅ **markdownlint**: no issues in 7 file(s)" in report(tmp_path, "success")


def test_findings_fail_the_step_and_the_report_counts_them(tmp_path):
    r, status = lint(tmp_path, ML_FILES="3", ML_ISSUES="4", ML_RC="1")
    assert r.returncode == 1, "the step must end with the linter's exit code, not tee's"
    assert status == "status=ran rc=1 files=3 issues=4"
    assert "⚠️ **markdownlint**: 4 issue(s) in 3 file(s)" in report(tmp_path, "failure")


def test_no_markdown_file_is_not_clean(tmp_path):
    r, status = lint(tmp_path, ML_FILES="0")
    assert "::warning title=markdownlint linted nothing::" in r.stdout
    assert "no *.md file matched — nothing was linted" in report(tmp_path, "success")


def test_no_status_file_is_not_clean(tmp_path):
    for f in ("/tmp/markdownlint-status.txt",):
        if Path(f).exists():
            Path(f).unlink()
    assert "did not run" in report(tmp_path, "success")
