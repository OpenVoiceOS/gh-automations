"""license-check.yml installs the package with the PyTorch CPU index as an
extra index (T-2791). The torch wheel PyPI serves on Linux x86_64 pins the
NVIDIA CUDA runtime wheels, which are proprietary and carry no licence
metadata; the CPU index carries the torch family only, so the audit sees the
platform-neutral closure. The install step is run under bash with a fake `uv`
that records its arguments."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"

FAKE_UV = """#!/usr/bin/env bash
echo "uv $*" >> "$UV_LOG"
if [ "$1 $2" = "pip freeze" ]; then
  printf '%s\\n' $FREEZE_LINES
fi
exit 0
"""


def step(name: str) -> dict:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    return next(s for s in steps if s.get("name") == name)


def run_step(tmp_path: Path, name: str, install_extras: str = "", freeze: str = "") -> tuple[str, str, str]:
    script = step(name)["run"].replace("${{ inputs.install_extras }}", install_extras)
    assert "${{" not in script, script
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    uv = bindir / "uv"
    uv.write_text(FAKE_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "uv.log"
    log.touch()
    summary = tmp_path / "summary.md"
    summary.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", UV_LOG=str(log),
               GITHUB_STEP_SUMMARY=str(summary), FREEZE_LINES=freeze)
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout, log.read_text(), summary.read_text()


@pytest.mark.parametrize("install_extras, target", [
    ("", "."), ("dev", ".[dev]"), ("[dev,linux]", ".[dev,linux]"),
    (".[test]", ".[test]"), ("-r requirements/test.txt", "-r requirements/test.txt"),
])
def test_install_uses_the_cpu_index_for_every_spelling(tmp_path, install_extras, target):
    _, log, _ = run_step(tmp_path, "Install package", install_extras)
    assert log.strip() == f"uv pip install {target} --extra-index-url {CPU_INDEX} --index-strategy unsafe-best-match"


def test_freeze_names_the_cpu_torch_in_the_summary(tmp_path):
    out, log, summary = run_step(tmp_path, "Collect transitive dependencies",
                                 freeze="numpy==2.0.0 torch==2.14.0+cpu torchaudio==2.11.0+cpu")
    assert "torch resolved from the CPU index" in out
    assert "NVIDIA CUDA runtime wheels are not part of this audit" in summary
    # the local version label is dropped for the PyPI lookup: 2.14.0+cpu is
    # not a version PyPI lists, and the checker read it as Error
    assert (tmp_path / "requirements-all.txt").read_text().splitlines() == [
        "numpy==2.0.0", "torch==2.14.0", "torchaudio==2.11.0"]


def test_local_labels_are_dropped_only_after_the_version(tmp_path):
    _, _, _ = run_step(tmp_path, "Collect transitive dependencies",
                       freeze="a==1.0+local.1 b==2.0 c==3.0rc1+cpu git+https://x/y@z#egg=d")
    assert (tmp_path / "requirements-all.txt").read_text().splitlines() == [
        "a==1.0", "b==2.0", "c==3.0rc1", "git+https://x/y@z#egg=d"]


def test_freeze_without_torch_writes_no_summary(tmp_path):
    out, _, summary = run_step(tmp_path, "Collect transitive dependencies", freeze="numpy==2.0.0")
    assert "CPU index" not in out
    assert summary == ""


def test_a_pypi_torch_is_not_called_cpu(tmp_path):
    """A caller that pins a torch the CPU index lacks gets the PyPI wheel; the
    summary must not then claim the CUDA wheels are absent."""
    out, _, summary = run_step(tmp_path, "Collect transitive dependencies",
                               freeze="torch==2.14.0 nvidia-cublas==13.1.1.3")
    assert "CPU index" not in out
    assert summary == ""
