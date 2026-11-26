"""build-tests.yml ran the suite against the source tree, not the wheel it had
just built and installed (T-5305).

`python -m pytest` puts the working directory first on sys.path, and the
working directory is the repository root. For a flat-layout package the root
holds the package directory, so `import mypkg` resolved to the source tree and
never to site-packages. A packaging defect -- a module left out of the wheel, a
dependency not declared, package data not shipped -- passed in every caller
whose package directory sits at the repository root.

The first test reads the workflow. The rest are controls that run pytest twice
over a fixture whose "installed" copy and "source" copy disagree, and assert
which copy each command form imports. They need no network and build no wheel:
the mechanism under test is sys.path, so a directory on PYTHONPATH stands in
for site-packages.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/build-tests.yml"


def run_tests_step():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["build_tests"]["steps"]
    return next(s for s in steps if s.get("name") == "Run Tests")


def test_the_workflow_does_not_invoke_pytest_through_dash_m():
    run = run_tests_step()["run"]
    command = [
        line.strip()
        for line in run.splitlines()
        if line.strip().startswith(("pytest ", "python -m pytest"))
    ]
    assert command == ["pytest ${{ inputs.test_path }} -v ${{ inputs.pytest_args }} | tee pytest.log"], command


def test_the_working_directory_is_not_changed_away_from_the_repository_root():
    # A suite that reads a repo-relative fixture path must keep working, so the
    # fix must not be "cd somewhere neutral".
    step = run_tests_step()
    assert "working-directory" not in step
    assert "cd " not in step["run"]


# --- controls -------------------------------------------------------------

FIXTURE_TEST = """
import shadowed


def test_which_copy():
    assert shadowed.ORIGIN == "installed", shadowed.ORIGIN
"""


@pytest.fixture
def two_copies(tmp_path):
    """A repository root whose flat-layout package disagrees with the installed one."""
    repo = tmp_path / "repo"
    (repo / "shadowed").mkdir(parents=True)
    (repo / "shadowed" / "__init__.py").write_text('ORIGIN = "source"\n')
    (repo / "tests").mkdir()
    (repo / "tests" / "test_origin.py").write_text(FIXTURE_TEST)

    site = tmp_path / "site"
    (site / "shadowed").mkdir(parents=True)
    (site / "shadowed" / "__init__.py").write_text('ORIGIN = "installed"\n')
    return repo, site


PYTEST_SCRIPT = Path(sys.executable).parent / "pytest"


def run(argv, cwd, site):
    return subprocess.run(
        argv,
        cwd=cwd,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(site)},
        capture_output=True,
        text=True,
    )


def test_control_the_old_command_imported_the_source_tree(two_copies):
    """`python -m pytest tests` from the repository root imports the source."""
    repo, site = two_copies
    result = run([sys.executable, "-m", "pytest", "tests", "-v"], repo, site)
    assert result.returncode != 0, "the source copy must have been imported:\n" + result.stdout
    assert "ORIGIN == \"installed\"" in result.stdout or "assert 'source'" in result.stdout, result.stdout


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
def test_control_the_new_command_imports_the_installed_copy(two_copies):
    """The console script does not put the working directory on sys.path.

    `python -c` prepends the working directory exactly as `-m` does, so this
    control has to run the real script and cannot stand in for it.
    """
    repo, site = two_copies
    result = run([str(PYTEST_SCRIPT), "tests", "-v"], repo, site)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
def test_control_a_tests_local_helper_import_still_resolves(two_copies):
    """Prepend import mode still puts the tests directory on sys.path, so a
    suite that imports a helper module beside its tests keeps working."""
    repo, site = two_copies
    (repo / "tests" / "helper.py").write_text("VALUE = 1\n")
    (repo / "tests" / "test_helper.py").write_text(
        "from helper import VALUE\n\n\ndef test_value():\n    assert VALUE == 1\n"
    )
    result = run([str(PYTEST_SCRIPT), "tests/test_helper.py", "-v"], repo, site)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
def test_control_a_repo_relative_fixture_path_still_resolves(two_copies):
    """The working directory is still the repository root under the new command."""
    repo, site = two_copies
    (repo / "fixture.txt").write_text("data\n")
    (repo / "tests" / "test_cwd.py").write_text(
        "import os\n\n\ndef test_fixture():\n    assert os.path.exists(\"fixture.txt\")\n"
    )
    result = run([str(PYTEST_SCRIPT), "tests/test_cwd.py", "-v"], repo, site)
    assert result.returncode == 0, result.stdout + result.stderr


# --- the console script is necessary and not sufficient -------------------
# Prepend import mode puts the rootdir back on sys.path in two shapes, and the
# shadowing returns with it. These controls pin the qualification the comment
# above the command now carries.


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
def test_control_a_test_package_puts_the_rootdir_back(two_copies):
    """With an __init__.py beside the tests, the console script imports the source."""
    repo, site = two_copies
    (repo / "tests" / "__init__.py").write_text("")
    result = run([str(PYTEST_SCRIPT), "tests", "-v"], repo, site)
    assert result.returncode != 0, "the source copy must have been imported:\n" + result.stdout
    assert "AssertionError: source" in result.stdout, result.stdout


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
def test_control_a_root_conftest_puts_the_rootdir_back(two_copies):
    """A conftest.py at the repository root does the same, with no test package."""
    repo, site = two_copies
    (repo / "conftest.py").write_text("")
    result = run([str(PYTEST_SCRIPT), "tests", "-v"], repo, site)
    assert result.returncode != 0, "the source copy must have been imported:\n" + result.stdout
    assert "AssertionError: source" in result.stdout, result.stdout


@pytest.mark.skipif(not PYTEST_SCRIPT.exists(), reason="no pytest console script beside this interpreter")
@pytest.mark.parametrize("shape", ["test_package", "root_conftest"])
def test_import_mode_importlib_holds_in_both_shapes(two_copies, shape):
    """--import-mode=importlib inserts nothing, so neither shape shadows."""
    repo, site = two_copies
    if shape == "test_package":
        (repo / "tests" / "__init__.py").write_text("")
    else:
        (repo / "conftest.py").write_text("")
    result = run([str(PYTEST_SCRIPT), "tests", "-v", "--import-mode=importlib"], repo, site)
    assert result.returncode == 0, result.stdout + result.stderr
