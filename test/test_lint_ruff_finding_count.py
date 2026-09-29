"""lint.yml names the findings and the files that hold them (T-6482).

The comment used to read "issues found in $N file(s)", where $N is the count
of files ruff READ. On OpenVoiceOS/ovos-gui#133 that said 21 when the 19
findings sat in 9 files, so 12 clean files were reported as broken, and
`bin/gate ci` copies the sentence into the ci row, so the wrong number
travels. Three lanes misread it before it was fixed.

The Run ruff step and the comment step run under bash with a fake ruff.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/lint.yml"

# `ruff check <args> --output-format=github` writes one ::error line per
# finding, each carrying file=. $RUFF_ROWS is "<file>:<code>" per finding.
FAKE_RUFF = """#!/usr/bin/env bash
if [[ " $* " == *" --show-files "* ]]; then
  for f in $RUFF_FILES; do echo "$f"; done
  exit 0
fi
rc=0
for row in $RUFF_ROWS; do
  f="${row%%:*}"; code="${row##*:}"
  echo "::error title=ruff ($code),file=/src/$f,line=1,col=8,endLine=1,endColumn=12::$f:1:8: $code something"
  rc=1
done
exit $rc
"""


def step(name):
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == name)


def run(tmp_path, name, *, files="", rows="", outcome="success",
        findings="", dirty="", ruff_args="."):
    script = step(name)["run"]
    known = {
        "inputs.ruff_args": ruff_args,
        "inputs.ruff": "true",
        "steps.ruff.outcome": outcome,
        "steps.ruff.outputs.findings": findings,
        "steps.ruff.outputs.dirty_files": dirty,
        "steps.ruff_files.outputs.count": str(len(files.split())),
    }

    def value(m):
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
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}",
               GITHUB_OUTPUT=str(out), RUFF_FILES=files, RUFF_ROWS=rows)
    r = subprocess.run(["bash", "-c", script], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    section = Path("/tmp/lint-section.md")
    return r, out.read_text(), section.read_text() if section.exists() else ""


def test_the_step_counts_the_findings_and_the_files_that_hold_them(tmp_path):
    """Four findings in two files. The old sentence could say neither number."""
    r, gh_out, _ = run(tmp_path, "Run ruff",
                       rows="a.py:F401 a.py:F401 b.py:F401 b.py:E731")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "findings=4" in gh_out
    assert "dirty_files=2" in gh_out


def test_a_clean_tree_counts_nothing_and_passes(tmp_path):
    r, gh_out, _ = run(tmp_path, "Run ruff", rows="")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "findings=0" in gh_out
    assert "dirty_files=0" in gh_out


def test_the_comment_names_the_files_with_issues_not_the_files_checked(tmp_path):
    """The defect: 2 files hold the findings, 5 were read. It said 5."""
    _, _, section = run(tmp_path, "Format lint section for PR comment",
                        files="a.py b.py c.py d.py e.py", outcome="failure",
                        findings="4", dirty="2")
    assert section.strip() == "❌ **ruff**: issues found in 2 file(s) — see job log"
    # the checked count is not the with-issues count
    assert "in 5 file(s)" not in section


def test_a_failure_with_no_finding_invents_no_file_count(tmp_path):
    """ruff died or ruff_args was bad: naming a with-issues count would lie."""
    _, _, section = run(tmp_path, "Format lint section for PR comment",
                        files="a.py b.py c.py", outcome="failure",
                        findings="0", dirty="0")
    assert section.strip() == (
        "❌ **ruff**: failed over 3 checked file(s), no finding parsed — see job log"
    )


# bin/gate REPO_WIDE_FINDING_RES, copied. The gate matches the lint line to
# class the finding as repository-wide and measure it against the merge base.
# A sentence that stops matching stalls every pull request carrying a ruff
# finding at NEXT: ci, which is the stall T-6174 removed, so the shape of the
# sentence is a contract between this workflow and the gate.
GATE_RUFF_RE = re.compile(
    r"^lint: \*\*ruff\*\*: issues found in \d+ file\(s\)(?: [-—] see job log)?$"
)


def test_the_failure_sentence_still_matches_the_gate_pattern(tmp_path):
    _, _, section = run(tmp_path, "Format lint section for PR comment",
                        files="a.py b.py c.py d.py e.py", outcome="failure",
                        findings="4", dirty="2")
    # the bot prefixes the section key; the gate matches the line that follows
    line = section.strip().replace("❌ ", "lint: ", 1)
    assert GATE_RUFF_RE.match(line), line


def test_the_no_finding_sentence_deliberately_does_not_match_the_gate(tmp_path):
    """ruff died: there is nothing to measure, so a person reads it."""
    _, _, section = run(tmp_path, "Format lint section for PR comment",
                        files="a.py b.py c.py", outcome="failure",
                        findings="0", dirty="0")
    line = section.strip().replace("❌ ", "lint: ", 1)
    assert not GATE_RUFF_RE.match(line), line

# --------------------------------------------------------------------------
# The canary. A unit test can only prove the shell arithmetic; the self-check
# runs the real workflow over a real tree and is the canary run this change is
# gated on.
# --------------------------------------------------------------------------

SELF_CHECK = (Path(__file__).resolve().parent.parent
              / ".github/workflows/self-check-lint.yml")
CANARY = Path(__file__).resolve().parent / "canary" / "lint-count"


def test_the_canary_has_three_files_and_only_two_hold_findings():
    """A fixture where every checked file is dirty cannot tell the old
    sentence from the new one, so the three counts must differ."""
    files = sorted(p.name for p in CANARY.glob("*.py"))
    assert files == ["a.py", "b.py", "clean.py"]
    assert "import json" in (CANARY / "a.py").read_text()
    assert "lambda" in (CANARY / "b.py").read_text()
    clean = (CANARY / "clean.py").read_text()
    assert "import" not in clean, "the clean file must hold no finding"


def test_the_self_check_runs_the_branch_over_the_canary():
    wf = yaml.safe_load(SELF_CHECK.read_text())
    job = wf["jobs"]["counts_the_files_that_hold_the_findings"]
    assert job["uses"] == "./.github/workflows/lint.yml"
    with_ = job["with"]
    # the branch under test, not the lint.yml already on dev
    assert with_["gh_automations_ref"] == "${{ github.head_ref || github.ref_name }}"
    assert "test/canary/lint-count" in with_["ruff_args"]
    # every input it passes must exist on lint.yml
    lint = yaml.safe_load(
        (Path(__file__).resolve().parent.parent / ".github/workflows/lint.yml").read_text())
    key = "on" if "on" in lint else True
    declared = lint[key]["workflow_call"]["inputs"]
    assert not set(with_) - set(declared), set(with_) - set(declared)
