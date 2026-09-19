"""golden-utterances.yml reads the skill id from the installed metadata, not
from pyproject.toml or setup.py: the step before installs the checkout
editable, and the entry point in group ovos.plugin.skill or opm.skill of the
distribution that came from this checkout is the id. The skill template
derives SKILL_NAME and SKILL_AUTHOR from URL.split(), which no parser of
setup.py reads (hello-world, fallback-unknown, fallback-chatgpt, T-3545).
The repository name is never the id (ovos-skill-easter-eggs declares
skill-easter-eggs.openvoiceos). The step runs under bash in a scratch
checkout with a fabricated site directory on PYTHONPATH."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/golden-utterances.yml"
STEP = "Read the skill id from the entry point"


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["golden"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    assert "importlib.metadata" in script and "PLUGIN_ENTRY_POINT" not in script, "the step parses files again"
    return script


def write_dist(site: Path, name: str, group: str, sid: str, editable_from: Path | None = None,
               suffix: str = "dist-info") -> Path:
    """A distribution's metadata directory, as an editable install writes it."""
    info = site / f"{name.replace('-', '_')}-1.0.0.{suffix}"
    info.mkdir(parents=True)
    (info / "METADATA" if suffix == "dist-info" else info / "PKG-INFO").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0.0\n")
    (info / "entry_points.txt").write_text(f"[{group}]\n{sid} = {name.replace('-', '_')}:Skill\n")
    if editable_from is not None:
        (info / "direct_url.json").write_text(json.dumps(
            {"url": editable_from.resolve().as_uri(), "dir_info": {"editable": True}}))
    return info


def run_step(repo: Path, site: Path) -> tuple[int, str, str]:
    out = repo.parent / "github_output"
    out.write_text("")
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=repo, capture_output=True, text=True,
                       env=dict(os.environ, GITHUB_OUTPUT=str(out), PYTHONPATH=str(site)))
    return r.returncode, out.read_text(), r.stderr


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "ovos-skill-easter-eggs"
    repo.mkdir()
    return repo


def test_editable_dist_info_from_the_checkout_is_the_id(checkout, tmp_path):
    site = tmp_path / "site"
    write_dist(site, "ovos-skill-easter-eggs", "ovos.plugin.skill", "skill-easter-eggs.openvoiceos",
               editable_from=checkout)
    rc, out, err = run_step(checkout, site)
    assert rc == 0 and out.strip() == "id=skill-easter-eggs.openvoiceos", (out, err)


def test_egg_info_inside_the_checkout_is_the_id_for_a_template_setup_py(checkout, tmp_path):
    # The skill template's setup.py derives the id from URL.split(); a
    # setuptools editable build leaves <pkg>.egg-info in the checkout.
    (checkout / "setup.py").write_text(
        'URL = "https://github.com/OpenVoiceOS/ovos-skill-hello-world"\n'
        'SKILL_AUTHOR, SKILL_NAME = URL.split(".com/")[-1].split("/")\n')
    write_dist(checkout, "ovos-skill-hello-world", "opm.skill", "ovos-skill-hello-world.openvoiceos",
               suffix="egg-info")
    rc, out, err = run_step(checkout, tmp_path / "empty-site")
    assert rc == 0 and out.strip() == "id=ovos-skill-hello-world.openvoiceos", (out, err)


def test_the_local_skill_wins_over_another_installed_skill(checkout, tmp_path):
    site = tmp_path / "site"
    write_dist(site, "ovos-skill-parrot", "ovos.plugin.skill", "ovos-skill-parrot.openvoiceos",
               editable_from=tmp_path / "elsewhere")
    write_dist(site, "ovos-skill-easter-eggs", "ovos.plugin.skill", "skill-easter-eggs.openvoiceos",
               editable_from=checkout)
    rc, out, err = run_step(checkout, site)
    assert rc == 0 and out.strip() == "id=skill-easter-eggs.openvoiceos", (out, err)


def test_no_skill_from_this_checkout_fails_the_step_and_names_what_is_installed(checkout, tmp_path):
    site = tmp_path / "site"
    write_dist(site, "ovos-skill-parrot", "ovos.plugin.skill", "ovos-skill-parrot.openvoiceos",
               editable_from=tmp_path / "elsewhere")
    rc, out, err = run_step(checkout, site)
    assert rc != 0 and out.strip() == "", (out, err)
    assert "no single skill entry point installed from" in err
    assert "ovos-skill-parrot.openvoiceos (ovos-skill-parrot)" in err


def test_nothing_installed_fails_the_step(checkout, tmp_path):
    rc, out, err = run_step(checkout, tmp_path / "empty-site")
    assert rc != 0 and out.strip() == "", (out, err)
    assert "installed: none" in err
