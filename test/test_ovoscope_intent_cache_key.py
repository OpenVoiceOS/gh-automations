"""
Tests for the "Resolve the intent cache key" step of ovoscope.yml.

The step keyed each hashed file by `(str(root), relative path)`. One of the two
roots is `sysconfig.get_paths()["purelib"]`, whose path carries the interpreter
PATCH level, so the digest moved on a patch release of Python when no `.intent`
file had changed. That contradicts the contract written four lines above the
key: "The key must change when the intents change and not before."

The step now keys by a stable label per root. These tests read the step out of
the workflow rather than restating it, and run its python body over a fixture.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    pytest.skip("PyYAML not installed", allow_module_level=True)

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "ovoscope.yml"


def _intent_cache_step() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "intent_cache":
                return step
    raise AssertionError("no step with id intent_cache in ovoscope.yml")


def _python_body(run: str) -> str:
    """The heredoc body the step feeds to python3."""
    match = re.search(r"python3 - <<'PYEOF'\n(.*?)\n\s*PYEOF", run, re.DOTALL)
    assert match, "the step no longer feeds a PYEOF heredoc to python3"
    return match.group(1)


def _run_body(tmp_path: Path, purelib: Path) -> dict:
    """Run the step's body with `purelib` forced, and read its GITHUB_OUTPUT."""
    body = _python_body(_intent_cache_step()["run"])
    # sysconfig reports this venv's purelib; the fixture names its own
    shim = (
        "import sysconfig\n"
        "_real = sysconfig.get_paths\n"
        "sysconfig.get_paths = lambda *a, **k: dict(_real(*a, **k),"
        f" purelib={str(purelib)!r})\n"
    )
    out_file = tmp_path / "gh-output"
    out_file.write_text("")
    proc = subprocess.run(
        [sys.executable, "-c", shim + body],
        capture_output=True,
        text=True,
        env={
            "GITHUB_WORKSPACE": str(tmp_path / "workspace"),
            "GITHUB_OUTPUT": str(out_file),
            "PATH": "/usr/bin:/bin",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if "=" in line
    )


def _world(tmp_path: Path, patch: str) -> Path:
    """A workspace and a purelib whose path carries a Python patch level."""
    workspace = tmp_path / "workspace" / "skills"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "hello.intent").write_text("hello there\n")
    purelib = tmp_path / f"python-3.11.{patch}" / "site-packages"
    (purelib / "some_skill" / "locale" / "en-us").mkdir(parents=True, exist_ok=True)
    (purelib / "some_skill" / "locale" / "en-us" / "bye.intent").write_text("bye now\n")
    return purelib


def test_the_digest_does_not_move_when_only_the_purelib_path_moves(tmp_path):
    """A Python patch release moves purelib. No intent moved, so the key must not."""
    nine = _run_body(tmp_path / "a", _world(tmp_path / "a", "9"))
    ten = _run_body(tmp_path / "b", _world(tmp_path / "b", "10"))
    assert nine["digest"] == ten["digest"], (
        "the digest is keyed by the purelib PATH, which carries the interpreter "
        "patch level; key by a stable label per root instead"
    )
    assert nine["count"] == ten["count"] == "2"


def test_the_digest_moves_when_an_intent_moves(tmp_path):
    """The control: the key must still change when the intents change."""
    before = _run_body(tmp_path / "a", _world(tmp_path / "a", "9"))
    purelib = _world(tmp_path / "b", "9")
    (purelib / "some_skill" / "locale" / "en-us" / "bye.intent").write_text("goodbye\n")
    after = _run_body(tmp_path / "b", purelib)
    assert before["digest"] != after["digest"]


def test_an_installed_copy_does_not_shadow_a_checked_out_one(tmp_path):
    """Both roots are still counted when they share a relative path."""
    workspace = tmp_path / "workspace" / "skill" / "locale"
    workspace.mkdir(parents=True)
    (workspace / "same.intent").write_text("one\n")
    purelib = tmp_path / "site-packages"
    (purelib / "skill" / "locale").mkdir(parents=True)
    (purelib / "skill" / "locale" / "same.intent").write_text("two\n")
    outputs = _run_body(tmp_path, purelib)
    assert outputs["count"] == "2", "one root's file shadowed the other's"
