"""redistribution-guard.yml fails when a built artifact carries a guarded library.

The tests execute the scan step's own shell, taken out of the YAML, against
fixture trees and wheels.
"""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/redistribution-guard.yml"


def scan(tmp_path: Path, files: list[str], wheel: bool = False) -> subprocess.CompletedProcess:
    doc = yaml.safe_load(WORKFLOW.read_text())
    inputs = doc[True]["workflow_call"]["inputs"]
    step = next(s for s in doc["jobs"]["redistribution_guard"]["steps"]
                if s.get("name") == "Scan for redistributed libraries")
    assert "${{" not in step["run"]
    dist = tmp_path / "dist"
    dist.mkdir()
    if wheel:
        with zipfile.ZipFile(dist / "bundle-1.0-py3-none-any.whl", "w") as zf:
            for name in files:
                zf.writestr(name, b"")
    else:
        for name in files:
            target = dist / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"")
    env = dict(
        os.environ,
        SCAN_PATHS="dist",
        GUARDED_LIBRARIES=inputs["guarded_libraries"]["default"],
        GUARDED_PACKAGES=inputs["guarded_packages"]["default"],
    )
    return subprocess.run(["bash", "-c", step["run"]], env=env, cwd=tmp_path,
                          capture_output=True, text=True)


# the file list of the PyPI soxr 0.5.0 manylinux wheel: libsoxr is linked
# statically into soxr_ext, so no libsoxr file exists
SOXR_WHEEL = [
    "soxr/__init__.py",
    "soxr/_version.py",
    "soxr/soxr_ext.cpython-311-x86_64-linux-gnu.so",
    "soxr-0.5.0.dist-info/METADATA",
]


@pytest.mark.parametrize("wheel", [False, True])
def test_the_soxr_package_is_caught(tmp_path, wheel):
    proc = scan(tmp_path, SOXR_WHEEL, wheel=wheel)
    assert proc.returncode == 1
    assert "soxr: " in proc.stdout + proc.stderr


@pytest.mark.parametrize("name", [
    "site-packages/soxr-0.5.0.dist-info/RECORD",
    "lib/soxr_ext.cpython-312-darwin.so",
])
def test_each_soxr_marker_alone_is_caught(tmp_path, name):
    assert scan(tmp_path, [name]).returncode == 1


def test_a_shared_libsoxr_is_caught(tmp_path):
    assert scan(tmp_path, ["usr/lib/libsoxr.so.0"]).returncode == 1


def test_an_artifact_without_soxr_passes(tmp_path):
    proc = scan(tmp_path, ["mypkg/__init__.py", "mypkg-1.0.dist-info/METADATA",
                           "mypkg/resample_soxr_notes.txt"])
    assert proc.returncode == 0, proc.stderr
