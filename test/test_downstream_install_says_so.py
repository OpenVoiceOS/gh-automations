"""downstream-check.yml no longer describes an environment it did not build
(T-2338). The ecosystem install may be partial and says so; the target
package install is a hard requirement; the report ends with an
Environment line naming the target version and the package count."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/downstream-check.yml"

FAKE_UV = """#!/usr/bin/env bash
# pip install -r ...: exit $ECO_RC; pip install -c ... <pkg>: exit $PKG_RC
# pip show <pkg>: a Version line; pip list: two header lines and $N_PKGS rows
case "$2" in
  install)
    if [[ " $* " == *" -r "* ]]; then exit ${ECO_RC:-0}; fi
    exit ${PKG_RC:-0} ;;
  show) echo "Name: ${@: -1}"; echo "Version: 1.2.3a1"; exit 0 ;;
  list) echo "Package Version"; echo "------- -------"; for i in $(seq ${N_PKGS:-5}); do echo "p$i 1.0"; done ;;
esac
exit 0
"""


def step(name):
    wf = yaml.safe_load(WORKFLOW.read_text())
    return next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == name)


def run_install(tmp_path, **env):
    script = step("Install OVOS ecosystem and pipdeptree")["run"]
    script = script.replace("${{ inputs.constraints_url }}", "file:///dev/null").replace("${{ inputs.package_name }}", "ovos-thing")
    script = script.replace('curl -fsSL -o constraints.txt "file:///dev/null"', ": > constraints.txt")
    assert "${{" not in script
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    uv = bindir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "out"
    out.touch()
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                       env=dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", GITHUB_OUTPUT=str(out), **env))
    return r, dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)


def test_complete_install_records_the_environment(tmp_path):
    r, out = run_install(tmp_path, N_PKGS="42")
    assert r.returncode == 0, r.stderr
    assert out == {"ecosystem": "complete", "target": "1.2.3a1", "installed": "42"}
    assert "::warning" not in r.stdout


def test_partial_ecosystem_install_warns_and_continues(tmp_path):
    r, out = run_install(tmp_path, ECO_RC="1")
    assert r.returncode == 0
    assert out["ecosystem"] == "partial" and out["target"] == "1.2.3a1"
    assert "::warning title=downstream-check ecosystem install incomplete::" in r.stdout


def test_target_install_failure_fails_the_step(tmp_path):
    r, out = run_install(tmp_path, PKG_RC="1")
    assert r.returncode != 0
    assert "target" not in out


def test_report_step_appends_the_environment_line():
    run = step("Generate downstream report")["run"]
    assert "Environment: ${{ inputs.package_name }} ${{ steps.install.outputs.target }} installed" in run
    assert "${{ steps.install.outputs.installed }} packages in the environment" in run
    assert "ecosystem install ${{ steps.install.outputs.ecosystem }}" in run
