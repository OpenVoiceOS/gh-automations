"""golden-utterances.yml reads the skill id from the checkout's entry point:
the key under [project.entry-points."ovos.plugin.skill"] in pyproject.toml,
or the left side of PLUGIN_ENTRY_POINT in setup.py resolved from module
constants. The repository name is never the id (ovos-skill-easter-eggs
declares skill-easter-eggs.openvoiceos). The step runs under bash in a
scratch checkout."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/golden-utterances.yml"
STEP = "Read the skill id from the entry point"

PYPROJECT = """\
[project]
name = "skill-easter-eggs"

[project.entry-points."ovos.plugin.skill"]
"skill-easter-eggs.openvoiceos" = "skill_easter_eggs:EasterEggsSkill"
"""

SETUP_PY = """\
from setuptools import setup

SKILL_NAME = "skill-easter-eggs"
SKILL_PKG = SKILL_NAME.replace("-", "_")
PLUGIN_ENTRY_POINT = f"{SKILL_NAME}.openvoiceos={SKILL_PKG}:EasterEggsSkill"

setup(name=f"{SKILL_NAME}", entry_points={"ovos.plugin.skill": PLUGIN_ENTRY_POINT})
"""


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["golden"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def run_step(tmp_path: Path, files: dict) -> tuple[int, str, str]:
    repo = tmp_path / "ovos-skill-easter-eggs"
    repo.mkdir()
    for name, text in files.items():
        (repo / name).write_text(text)
    out = tmp_path / "github_output"
    out.touch()
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=repo, capture_output=True, text=True,
                       env=dict(os.environ, GITHUB_OUTPUT=str(out)))
    return r.returncode, out.read_text(), r.stderr


def test_pyproject_entry_point_is_the_id(tmp_path):
    rc, out, _ = run_step(tmp_path, {"pyproject.toml": PYPROJECT})
    assert rc == 0 and out.strip() == "id=skill-easter-eggs.openvoiceos", out


def test_setup_py_entry_point_is_the_id(tmp_path):
    rc, out, _ = run_step(tmp_path, {"setup.py": SETUP_PY})
    assert rc == 0 and out.strip() == "id=skill-easter-eggs.openvoiceos", out


def test_no_entry_point_fails_the_step_and_names_nothing_after_the_directory(tmp_path):
    rc, out, err = run_step(tmp_path, {"README.md": "no packaging\n"})
    assert rc != 0 and out.strip() == "", (out, err)
    assert "no skill entry point" in err
