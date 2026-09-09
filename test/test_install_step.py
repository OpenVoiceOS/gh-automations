"""Run the package-install shell step of coverage.yml and type-check.yml
against a fake `uv` and assert which extra it installs.

`uv pip install -e ".[x]"` exits 0 when the package does not declare `x`; it
only prints a warning. The fake reproduces that, so the step is judged by the
extra it actually asks for, not by an exit code.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS_DIR = Path(__file__).parent.parent / ".github" / "workflows"

STEPS = {
    "coverage.yml": "Install Package",
    "type-check.yml": "Install Dependencies",
}

INPUTS = {
    "test_extras": "dev",
    "test_extras_fallback": "test",
    "install_extras": "",
}

FAKE_UV = """#!/usr/bin/env bash
# Fake uv: logs its arguments; on `pip install -e .[x]` warns (exit 0) when
# x is not in $DECLARED_EXTRAS, exactly as uv does for an undeclared extra.
printf '%s\\n' "$*" >> "$UV_LOG"
if [ "$1" = pip ] && [ "$2" = install ]; then
  for arg in "$@"; do
    case "$arg" in
      .\\[*\\])
        extra="${arg#.[}"; extra="${extra%]}"
        if ! grep -qw -- "$extra" <<<"${DECLARED_EXTRAS:-}"; then
          echo "warning: The package does not have an extra named \\`$extra\\`" >&2
        fi ;;
    esac
  done
fi
exit 0
"""

PYPROJECT = """[project]
name = "fixture-pkg"
version = "0.0.1"

[project.optional-dependencies]
{extras}
"""


def install_script(workflow: str) -> str:
    with open(WORKFLOWS_DIR / workflow) as f:
        data = yaml.safe_load(f)
    (job,) = data["jobs"].values()
    step = next(s for s in job["steps"] if s.get("name") == STEPS[workflow])
    script = step["run"]
    for key, value in INPUTS.items():
        script = script.replace("${{ inputs.%s }}" % key, value)
    assert "${{" not in script, "unsubstituted workflow expression in step"
    return script


def run_step(tmp_path: Path, workflow: str, extras: dict[str, list[str]] | None) -> tuple[list[str], str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    if extras is not None:
        body = "\n".join(f'{k} = {v!r}' for k, v in extras.items())
        (pkg / "pyproject.toml").write_text(PYPROJECT.format(extras=body))
    log = tmp_path / "uv.log"
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", UV_LOG=str(log),
               DECLARED_EXTRAS=" ".join(extras or {}))
    proc = subprocess.run(["bash", "-euo", "pipefail", "-c", install_script(workflow)],
                          cwd=pkg, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    calls = log.read_text().splitlines() if log.exists() else []
    return [c for c in calls if c.startswith("pip install -e")], proc.stdout


@pytest.mark.parametrize("workflow", sorted(STEPS))
def test_installs_declared_fallback_when_primary_is_undeclared(tmp_path, workflow):
    installs, _ = run_step(tmp_path, workflow, {"test": ["pytest"]})
    assert installs == ["pip install -e .[test]"]


@pytest.mark.parametrize("workflow", sorted(STEPS))
def test_installs_primary_when_declared(tmp_path, workflow):
    installs, _ = run_step(tmp_path, workflow, {"dev": ["pytest"], "test": ["pytest"]})
    assert installs == ["pip install -e .[dev]"]


@pytest.mark.parametrize("workflow", sorted(STEPS))
def test_neither_declared_installs_bare_package_and_warns(tmp_path, workflow):
    installs, out = run_step(tmp_path, workflow, {"docs": ["mkdocs"]})
    assert installs == ["pip install -e ."]
    assert "::warning::" in out


@pytest.mark.parametrize("workflow", sorted(STEPS))
def test_no_package_at_root_installs_nothing(tmp_path, workflow):
    installs, out = run_step(tmp_path, workflow, None)
    assert installs == []
    assert "No installable package found" in out
