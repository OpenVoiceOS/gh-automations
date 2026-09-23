"""T-3941: the resolver's pick for pip-licenses under UV_PRERELEASE=allow
(inherited from the job-wide env block) is 6.0.0b11, whose console script
cannot import its own package:

    pip-licenses exited 1: ModuleNotFoundError: No module named 'piplicenses'

pip-licenses is a CI-only tool, never a dependency the audited closure
ships, so its own install carries no prerelease flag: 5.5.5 (stable) works.
The "Install Build Tools" step must install it on the stable line
regardless of the job-wide prerelease default, while build/wheel keep the
ambient default.

This test reads the workflow text and checks the install line, so it fails
if a future edit reintroduces a bare `uv pip install ... pip-licenses` under
the prerelease-allow default."""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Install Build Tools"


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    return script


def test_pip_licenses_install_line_carries_no_prerelease_allow():
    script = step_script()
    pip_licenses_lines = [
        line for line in script.splitlines() if "pip-licenses" in line]
    assert pip_licenses_lines, "no line installs pip-licenses at all: " + script
    for line in pip_licenses_lines:
        assert "--prerelease=allow" not in line, (
            "pip-licenses install still resolves prereleases: " + line)
        assert "--prerelease=disallow" in line, (
            "pip-licenses install does not pin the stable line: " + line)


def test_build_and_wheel_keep_the_ambient_prerelease_default():
    # Only pip-licenses is a CI tool with no shipped-dependency reason to
    # pin stable; build/wheel stay on the job's uv_prerelease default.
    script = step_script()
    build_wheel_lines = [
        line for line in script.splitlines()
        if "build" in line and "wheel" in line and "pip-licenses" not in line]
    assert build_wheel_lines, "no line installs build/wheel separately: " + script
    for line in build_wheel_lines:
        assert "--prerelease" not in line, (
            "build/wheel install should not override the ambient default: " + line)
