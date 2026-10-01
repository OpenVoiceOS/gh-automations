"""build-tests.yml pins pytest's import mode, and it defaults to importlib
(T-5380).

Running the suite through the `pytest` console script keeps the repository root
off sys.path only while pytest itself adds nothing back. pytest's default
`prepend` import mode inserts the rootdir whenever the collected tests are a
package (a `test/__init__.py`) or a `conftest.py` sits at the repository root.
A census of the callers found 104 in one of those two shapes, so for those the
T-5305 fix was undone by pytest's own default.

The first tests read the workflow. The rest are controls: they run pytest twice
over a fixture whose "installed" copy and "source" copy disagree, once in each
import mode, and assert which copy the suite imports. They need no network and
build no wheel. The mechanism under test is sys.path, so a directory on
PYTHONPATH stands in for site-packages.

The controls also pin the cost of the default: under importlib a test that
imports a sibling module by a bare name stops resolving. That is the breaking
set the campaign has to rewrite, and a test that asserts it here is what keeps
the `prepend` escape hatch honest.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/build-tests.yml"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def run_tests_step():
    steps = workflow()["jobs"]["build_tests"]["steps"]
    return next(s for s in steps if s.get("name") == "Run Tests")


# --- the workflow ---------------------------------------------------------


def test_the_input_exists_and_is_a_string():
    # `on` is the YAML 1.1 true, so the key is True after a safe_load.
    inputs = workflow()[True]["workflow_call"]["inputs"]
    assert "import_mode" in inputs
    assert inputs["import_mode"]["type"] == "string"


def test_the_default_is_importlib_and_not_pytest_s_own_default():
    inputs = workflow()[True]["workflow_call"]["inputs"]
    assert inputs["import_mode"]["default"] == "importlib"


def test_the_pytest_invocation_passes_the_input():
    run = run_tests_step()["run"]
    command = [
        line.strip()
        for line in run.splitlines()
        if line.strip().startswith(("pytest ", "python -m pytest"))
    ]
    assert command == [
        "pytest ${{ inputs.test_path }} -v "
        "--import-mode=${{ inputs.import_mode }} ${{ inputs.pytest_args }} "
        "| tee pytest.log"
    ], command


def test_the_import_mode_is_not_hard_coded():
    # A literal --import-mode=importlib would take the escape hatch away from
    # the callers that need `prepend` while their imports are rewritten.
    run = run_tests_step()["run"]
    assert "--import-mode=importlib" not in run
    assert "--import-mode=prepend" not in run


def test_pytest_args_still_comes_last():
    # A caller that passes its own --import-mode through pytest_args must still
    # win, because pytest takes the last occurrence of the option.
    run = run_tests_step()["run"]
    line = next(l for l in run.splitlines() if l.strip().startswith("pytest "))
    assert line.index("inputs.import_mode") < line.index("inputs.pytest_args")


# --- controls -------------------------------------------------------------

# "installed" says installed, "source" says source. Whichever copy the suite
# imports names itself, so the assertion cannot pass by accident.
INSTALLED = "WHERE = 'installed'\n"
SOURCE = "WHERE = 'source'\n"

IMPORTS_THE_PACKAGE = """
import shadowed


def test_which_copy():
    print("WHERE=" + shadowed.WHERE)
"""

IMPORTS_A_BARE_SIBLING = """
import helper


def test_which_copy():
    print("WHERE=" + helper.WHERE)
"""


def build_tree(tmp_path, test_body, *, tests_are_a_package):
    """A repository root that shadows an installed package, as a caller does."""
    site = tmp_path / "site"
    (site / "shadowed").mkdir(parents=True)
    (site / "shadowed" / "__init__.py").write_text(INSTALLED)

    root = tmp_path / "root"
    (root / "shadowed").mkdir(parents=True)
    (root / "shadowed" / "__init__.py").write_text(SOURCE)

    tests = root / "test"
    tests.mkdir()
    if tests_are_a_package:
        (tests / "__init__.py").write_text("")
    (tests / "helper.py").write_text(SOURCE)
    (tests / "test_which.py").write_text(textwrap.dedent(test_body))
    return site, root


PYTEST = Path(sys.executable).parent / "pytest"


def run_pytest(site, root, import_mode):
    # The console script, never `python -m pytest`: the -m form puts the
    # working directory first on sys.path by itself, which is the T-5305
    # defect and would mask the one under test here. The workflow runs the
    # console script for the same reason.
    if not PYTEST.exists():
        pytest.skip("the pytest console script is not beside this interpreter")
    return subprocess.run(
        [str(PYTEST), "test", "-v", "-s", f"--import-mode={import_mode}"],
        cwd=root,
        env={"PYTHONPATH": str(site), "PATH": str(PYTEST.parent) + ":/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("tests_are_a_package", [True, False])
def test_prepend_imports_the_source_tree_when_the_tests_are_a_package(
    tmp_path, tests_are_a_package
):
    # The control that proves the defect is real: with a test package, prepend
    # puts the repository root back and the source copy wins.
    site, root = build_tree(
        tmp_path, IMPORTS_THE_PACKAGE, tests_are_a_package=tests_are_a_package
    )
    result = run_pytest(site, root, "prepend")
    assert result.returncode == 0, result.stdout + result.stderr
    if tests_are_a_package:
        assert "WHERE=source" in result.stdout, result.stdout
    else:
        assert "WHERE=installed" in result.stdout, result.stdout


@pytest.mark.parametrize("tests_are_a_package", [True, False])
def test_importlib_imports_the_installed_copy_in_both_shapes(
    tmp_path, tests_are_a_package
):
    # The fix: importlib inserts nothing, so the installed copy wins whatever
    # shape the test directory has.
    site, root = build_tree(
        tmp_path, IMPORTS_THE_PACKAGE, tests_are_a_package=tests_are_a_package
    )
    result = run_pytest(site, root, "importlib")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WHERE=installed" in result.stdout, result.stdout


def test_importlib_breaks_a_bare_sibling_import_and_prepend_does_not(tmp_path):
    # The cost of the default, pinned. This is why the input exists and why a
    # caller may set "prepend" while its imports are rewritten. A change that
    # made this pass under importlib would mean the escape hatch is no longer
    # needed; that is a result to read, not a test to delete.
    site, root = build_tree(
        tmp_path, IMPORTS_A_BARE_SIBLING, tests_are_a_package=False
    )

    broken = run_pytest(site, root, "importlib")
    assert broken.returncode != 0, broken.stdout + broken.stderr
    assert "helper" in broken.stdout + broken.stderr

    works = run_pytest(site, root, "prepend")
    assert works.returncode == 0, works.stdout + works.stderr
