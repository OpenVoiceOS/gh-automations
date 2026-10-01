"""The packaging control, and the two questions it has to keep apart (T-6960).

``build-tests.yml`` installs the built wheel non-editable and runs the ``pytest``
console script. Its own comment already said that is "necessary and not
sufficient", and nothing checked. ``coverage.yml`` cannot see a packaging defect
at all: it installs editable and runs ``python -m pytest``, so the tree is the
package in every configuration.

Measured on ``hivemind-websocket-client`` at 7c1c5f6, wheel installed
non-editable in both arms:

  ``test,e2e`` extras   the package resolved to site-packages, 1103 collected
  ``test`` extra        the package resolved to the SOURCE TREE, 1083 collected

The only difference is ``hivescope``, which the ``e2e`` extra installs and which
imports the package at plugin load. The first arm is green by luck.

The control therefore has two arms, and the tests below pin why one is not
enough: hiding the tree lets the import fall back to a complete wheel, so
collection succeeds either way and a tree read passes unseen. Only the
resolution arm catches it, and only the completeness arm catches the incomplete
wheel the tree read conceals.

The fixtures need no network and build no real wheel. The mechanism under test
is ``sys.path``, so a directory on ``PYTHONPATH`` stands in for site-packages,
exactly as ``test_build_tests_runs_the_wheel.py`` does it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/packaging_control.py"
BUILD_TESTS = ROOT / ".github/workflows/build-tests.yml"
COVERAGE = ROOT / ".github/workflows/coverage.yml"
PYTEST_DIR = Path(sys.executable).parent

sys.path.insert(0, str(ROOT / "scripts"))
import packaging_control  # noqa: E402

needs_console_script = pytest.mark.skipif(
    not (PYTEST_DIR / "pytest").exists(),
    reason="no pytest console script beside this interpreter",
)


# --- the workflows say what they do ---------------------------------------


def test_build_tests_runs_the_packaging_control_after_the_suite():
    wf = yaml.safe_load(BUILD_TESTS.read_text())
    steps = wf["jobs"]["build_tests"]["steps"]
    names = [s.get("name") for s in steps]
    assert "Packaging control" in names, names
    assert names.index("Packaging control") > names.index("Run Tests"), names
    step = steps[names.index("Packaging control")]
    assert "packaging_control.py" in step["run"]


def test_build_tests_declares_packaging_strict_and_warns_by_default():
    wf = yaml.safe_load(BUILD_TESTS.read_text())
    on = wf.get("on") or wf.get(True)  # YAML `on` may parse as bool True
    spec = on["workflow_call"]["inputs"]["packaging_strict"]
    assert spec["type"] == "boolean"
    assert spec["default"] is False


def test_coverage_still_installs_editable_and_runs_dash_m():
    """The header calls coverage.yml a tree job. That has to stay true, or the
    documentation becomes the lie instead of the code."""
    text = COVERAGE.read_text()
    assert "python -m pytest" in text
    assert 'uv pip install -e ".[$1]"' in text or "uv pip install -e ." in text


def test_coverage_says_it_never_certifies_packaging():
    head = "\n".join(COVERAGE.read_text().splitlines()[:30])
    assert "never certifies packaging" in head
    assert "build-tests.yml" in head


# --- reading the wheel ----------------------------------------------------


def make_wheel(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in entries.items():
            zf.writestr(name, body)
    return path


def test_top_level_names_reads_packages_and_modules(tmp_path):
    wheel = make_wheel(tmp_path / "w-1.0-py3-none-any.whl", {
        "mypkg/__init__.py": "",
        "mypkg/sub/mod.py": "",
        "single.py": "",
        "w-1.0.dist-info/METADATA": "",
        "w-1.0.data/scripts/thing": "",
    })
    assert packaging_control.top_level_names(wheel) == ["mypkg", "single"]


def test_tree_paths_finds_a_package_a_module_and_skips_what_is_absent(tmp_path):
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "single.py").write_text("")
    found = packaging_control.tree_paths(tmp_path, ["mypkg", "single", "absent"])
    assert [os.path.basename(p) for p in found] == ["mypkg", "single.py"]


# --- the fixture ----------------------------------------------------------

ORIGIN_TEST = """
import shadowed


def test_origin():
    assert shadowed.ORIGIN in ("installed", "source")
"""


@pytest.fixture
def repo(tmp_path):
    """A flat-layout repo whose tree copy and "installed" copy disagree.

    `site` stands in for site-packages and sits OUTSIDE the repo root, which is
    what the resolution arm keys on.
    """
    root = tmp_path / "repo"
    (root / "shadowed").mkdir(parents=True)
    (root / "shadowed" / "__init__.py").write_text('ORIGIN = "source"\n')
    (root / "shadowed" / "extra.py").write_text("VALUE = 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_origin.py").write_text(ORIGIN_TEST)

    site = tmp_path / "site"
    (site / "shadowed").mkdir(parents=True)
    (site / "shadowed" / "__init__.py").write_text('ORIGIN = "installed"\n')
    (site / "shadowed" / "extra.py").write_text("VALUE = 1\n")

    dist = root / "dist"
    dist.mkdir()
    make_wheel(dist / "shadowed-1.0-py3-none-any.whl", {
        "shadowed/__init__.py": "", "shadowed/extra.py": "",
        "shadowed-1.0.dist-info/METADATA": "",
    })
    return root, site


def run_control(root, site, *extra, env_extra=None):
    env = {
        "PATH": f"{PYTEST_DIR}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "PYTHONPATH": str(site),
    }
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--test-path", "tests", "--root", str(root),
         *extra],
        cwd=root, env=env, capture_output=True, text=True,
    )


# --- resolution -----------------------------------------------------------


@needs_console_script
def test_a_root_conftest_makes_the_suite_read_the_tree_and_the_control_says_so(repo):
    root, site = repo
    (root / "conftest.py").write_text("")
    result = run_control(root, site, "--strict")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "SOURCE TREE" in result.stderr, result.stderr
    assert "the source tree copy" in result.stdout, result.stdout


@needs_console_script
def test_the_same_tree_only_warns_without_strict(repo):
    root, site = repo
    (root / "conftest.py").write_text("")
    result = run_control(root, site)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning" in result.stderr, result.stderr


@needs_console_script
def test_a_clean_shape_passes_both_arms(repo):
    """No test package and no root conftest: the console script reaches the
    installed copy, and the wheel is complete."""
    root, site = repo
    result = run_control(root, site, "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "control passed" in result.stdout, result.stdout


@needs_console_script
def test_import_mode_importlib_rescues_a_root_conftest(repo):
    root, site = repo
    (root / "conftest.py").write_text("")
    result = run_control(root, site, "--strict",
                         "--pytest-args=--import-mode=importlib")
    assert result.returncode == 0, result.stdout + result.stderr


# --- completeness ---------------------------------------------------------


@needs_console_script
def test_a_tree_read_conceals_an_incomplete_wheel_and_both_arms_fire(repo):
    """The defect the two arms exist for.

    The installed copy is missing a module the tree has. With a root conftest
    the suite reads the tree, so it collects and build-tests would be green.
    Resolution names the tree read; completeness names the missing module.
    """
    root, site = repo
    (root / "conftest.py").write_text("")
    (root / "tests" / "test_extra.py").write_text(
        "from shadowed.extra import VALUE\n\n\ndef test_v():\n    assert VALUE == 1\n")
    os.rename(site / "shadowed" / "extra.py", site / "shadowed" / "extra.hidden")

    result = run_control(root, site, "--strict")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "SOURCE TREE" in result.stderr, result.stderr
    assert "missing something the tree supplies" in result.stderr, result.stderr


@needs_console_script
def test_the_baseline_is_reported_inconclusive_and_never_as_a_pass(repo):
    """A suite that does not collect with the tree present says nothing about
    packaging, so it must not read as a pass."""
    root, site = repo
    (root / "tests" / "test_broken.py").write_text("import a_module_that_is_absent\n")
    result = run_control(root, site, "--strict")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "inconclusive" in result.stderr.lower(), result.stderr


# --- the instrument must not manufacture the defect ----------------------


@needs_console_script
def test_the_tree_is_restored_even_when_an_arm_fails(repo):
    root, site = repo
    (root / "conftest.py").write_text("")
    run_control(root, site, "--strict")
    assert (root / "shadowed" / "__init__.py").exists()
    leftover = list(root.glob("*" + packaging_control.HIDDEN_SUFFIX))
    assert leftover == [], leftover


def test_pythonpath_never_carries_an_empty_entry(tmp_path, monkeypatch):
    """An empty PYTHONPATH entry is the current directory, which is the repo
    root, so it puts the tree back on sys.path and the probe reports a tree read
    for a suite that read the wheel. Measured: a trailing os.pathsep alone
    flipped the hivemind-websocket-client e2e arm from site-packages to the
    tree, which is the instrument manufacturing the defect it measures.
    """
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs["env"]
        return subprocess.CompletedProcess(cmd, 0, "1 test collected", "")

    monkeypatch.setattr(packaging_control.subprocess, "run", fake_run)
    for inherited in ("", "/somewhere"):
        monkeypatch.setenv("PYTHONPATH", inherited)
        packaging_control.collect("tests", "", str(tmp_path),
                                  names=["x"], probe_dir=str(tmp_path))
        parts = seen["env"]["PYTHONPATH"].split(os.pathsep)
        assert "" not in parts, (inherited, parts)


def test_the_probe_rescues_a_virtualenv_that_lives_inside_the_repo(tmp_path):
    """`.venv` in the repo puts site-packages UNDER the repo root, so "under the
    repo root" alone would call every installed import a tree read. Measured on
    the hivemind-websocket-client worktree, whose venv is inside it."""
    probe = tmp_path / "probe.py"
    probe.write_text(packaging_control.PROBE)
    repo = tmp_path / "repo"
    site = repo / ".venv/lib/python3.11/site-packages"
    site.mkdir(parents=True)
    pkg = site / "shadowed"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")

    out = tmp_path / "probe.json"
    script = (
        "import json, os, sys, sysconfig, types\n"
        f"sys.path.insert(0, {str(tmp_path)!r})\n"
        "import probe\n"
        "m = types.ModuleType('shadowed')\n"
        f"m.__file__ = {str(pkg / '__init__.py')!r}\n"
        "sys.modules['shadowed'] = m\n"
        f"sysconfig.get_paths = lambda: {{'purelib': {str(site)!r}, 'platlib': {str(site)!r}}}\n"
        "probe.pytest_sessionfinish(None, 0)\n"
    )
    env = dict(os.environ)
    env.update({
        "PACKAGING_CONTROL_NAMES": json.dumps(["shadowed"]),
        "PACKAGING_CONTROL_OUT": str(out),
        "PACKAGING_CONTROL_REPO": str(repo),
    })
    done = subprocess.run([sys.executable, "-c", script], env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    data = json.loads(out.read_text())
    assert data["modules"]["shadowed"]["in_tree"] is False, data
