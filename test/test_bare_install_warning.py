"""The install step of coverage.yml and type-check.yml says, in the job
summary and as an annotation, when a caller declares neither test extra and
sets no install_extras (T-2191). The step's run block is executed under bash
with a fake `uv` on PATH that answers like the real one: exit 0 with the
"does not have an extra named" warning for an extra the package lacks."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = {
    "coverage": (ROOT / ".github/workflows/coverage.yml", "Install Package", "test"),
    "type-check": (ROOT / ".github/workflows/type-check.yml", "Install Dependencies", "typing"),
}

FAKE_UV = """#!/usr/bin/env bash
# `uv pip install -e .[extra]`: declared extras come from $DECLARED_EXTRAS.
# A missing package ($NO_PACKAGE=1) fails every editable install.
set -e
[ "$1" = pip ] && [ "$2" = install ] || exit 0
echo "uv $*" >> "$UV_LOG"
target="${@: -1}"
case "$target" in
  -e) exit 0 ;;
esac
if [ "$3" = -e ]; then
  [ -n "$NO_PACKAGE" ] && { echo "error: no pyproject.toml" >&2; exit 2; }
  case "$target" in
    .\\[*\\])
      extra="${target#.[}"; extra="${extra%]}"
      case ",$DECLARED_EXTRAS," in
        *",$extra,"*) ;;
        *) echo "warning: The package \\`pkg\\` does not have an extra named \\`$extra\\`" ;;
      esac ;;
  esac
fi
exit 0
"""


def run_block(name: str) -> str:
    path, step_name, _ = WORKFLOWS[name]
    wf = yaml.safe_load(path.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    step = next(s for s in steps if s.get("name") == step_name)
    return step["run"]


def run_step(tmp_path: Path, name: str, *, test_extras="dev", fallback="test",
             install_extras="", declared="", no_package=False) -> tuple[str, str, str]:
    script = run_block(name)
    for key, val in (("test_extras", test_extras), ("test_extras_fallback", fallback),
                     ("install_extras", install_extras)):
        script = script.replace("${{ inputs.%s }}" % key, val)
    assert "${{" not in script, "an input is not substituted: " + script
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    summary = tmp_path / "summary.md"
    summary.touch()
    log = tmp_path / "uv.log"
    log.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", GITHUB_STEP_SUMMARY=str(summary),
               UV_LOG=str(log), DECLARED_EXTRAS=declared, NO_PACKAGE="1" if no_package else "")
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout, summary.read_text(), log.read_text()


@pytest.mark.parametrize("name", list(WORKFLOWS))
class TestBareInstall:
    def test_neither_extra_warns(self, tmp_path, name):
        kind = WORKFLOWS[name][2]
        out, summary, _ = run_step(tmp_path, name, declared="")
        assert "Installed package (no test extras found)" in out
        assert f"::warning title=No {kind} extra installed::" in out
        assert "declares neither [dev] nor [test]" in summary
        assert summary.startswith(f"> ⚠️ **No {kind} extra installed.**")

    def test_no_package_warns(self, tmp_path, name):
        out, summary, _ = run_step(tmp_path, name, no_package=True)
        assert "No installable package found" in out
        assert "::warning" in out
        assert "install_extras is empty" in summary

    def test_declared_fallback_is_silent(self, tmp_path, name):
        out, summary, _ = run_step(tmp_path, name, declared="test")
        assert "Installed package with [test] extras" in out
        assert "::warning" not in out
        assert summary == ""

    def test_declared_primary_is_silent(self, tmp_path, name):
        out, summary, _ = run_step(tmp_path, name, declared="dev,test")
        assert "Installed package with [dev] extras" in out
        assert summary == ""

    def test_install_extras_is_silent(self, tmp_path, name):
        out, summary, log = run_step(tmp_path, name, declared="", install_extras="dev")
        assert "Installed package (no test extras found)" in out
        assert "uv pip install .[dev]" in log
        assert "::warning" not in out
        assert summary == ""

    def test_no_extras_asked_warns(self, tmp_path, name):
        out, summary, _ = run_step(tmp_path, name, test_extras="", fallback="", declared="test")
        assert "declares neither [] nor []" in summary
