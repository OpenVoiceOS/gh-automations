"""spec-lint.yml's "Resolve locale path" step: an absent `locale_path` is
searched for before it is given up on.

`locale_path` defaults to the literal "locale" and no skill caller overrides
it. Twelve active public ovos-skill-* repos of 42 keep their locale tree under
the package directory instead (`<pkg>/locale`), so the path was absent, the
"Skip if locale folder is missing" step fired, and the job reported success
without linting anything. Three of the twelve carried errors nobody saw:
ovos-skill-randomness 28, ovos-skill-wordnet 6, ovos-skill-pokepedia 3
(T-4696).

The step is run under bash against scratch directory trees, with
GITHUB_OUTPUT redirected to a file, so the resolution and the outputs it
writes are what is under test."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/spec-lint.yml"
STEP = "Resolve locale path"


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["spec_lint"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    # the step must not interpolate anything into the script body: the path is
    # caller text and reaches bash through the environment
    assert "${{" not in script, script
    return script


def run(tmp_path: Path, locale_path: str = "locale") -> tuple[int, dict, str]:
    out = tmp_path / "gh-output"
    out.touch()
    proc = subprocess.run(
        ["bash", "-c", step_script()],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "LOCALE_PATH": locale_path,
             "GITHUB_OUTPUT": str(out)},
        capture_output=True, text=True,
    )
    parsed = {}
    for line in out.read_text().splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            parsed[k] = v
    return proc.returncode, parsed, proc.stdout + proc.stderr


def make_locale(base: Path, rel: str) -> None:
    d = base / rel / "en-us"
    d.mkdir(parents=True)
    (d / "x.dialog").write_text("hello\n")


# --- the defect this step exists to close -----------------------------------

def test_a_package_locale_tree_is_found_when_the_given_path_is_absent(tmp_path):
    """The twelve-repo case: <pkg>/locale is linted instead of skipped."""
    make_locale(tmp_path, "ovos_skill_wordnet/locale")
    rc, out, log = run(tmp_path)
    assert rc == 0, log
    assert out["exists"] == "true", log
    assert out["path"] == "ovos_skill_wordnet/locale", log
    assert out["source"] == "discovered", log


def test_the_discovery_is_announced(tmp_path):
    """A green must say what it read, so the fallback is not silent."""
    make_locale(tmp_path, "ovos_skill_wordnet/locale")
    _, _, log = run(tmp_path)
    assert "::notice::" in log, log
    assert "ovos_skill_wordnet/locale" in log, log


def test_a_package_name_without_the_ovos_prefix_is_found(tmp_path):
    """ovos-skill-randomness ships skill_randomness/locale, not ovos_skill_*.

    A resolver keyed on the ovos_skill_ prefix would miss the repo with the
    most hidden errors of the twelve.
    """
    make_locale(tmp_path, "skill_randomness/locale")
    rc, out, log = run(tmp_path)
    assert rc == 0, log
    assert out["path"] == "skill_randomness/locale", log


# --- controls: the 30 repos that already worked must not change -------------

def test_a_given_path_that_exists_is_used_unchanged(tmp_path):
    make_locale(tmp_path, "locale")
    rc, out, log = run(tmp_path)
    assert rc == 0, log
    assert out["path"] == "locale", log
    assert out["source"] == "input", log


def test_a_top_level_tree_wins_over_a_package_tree(tmp_path):
    """No search happens when the given path exists, so a repo holding both
    keeps linting the one the caller named."""
    make_locale(tmp_path, "locale")
    make_locale(tmp_path, "ovos_skill_thing/locale")
    rc, out, log = run(tmp_path)
    assert out["path"] == "locale", log
    assert out["source"] == "input", log


def test_an_explicit_caller_override_is_honoured(tmp_path):
    make_locale(tmp_path, "pkg/locale")
    rc, out, log = run(tmp_path)
    assert out["source"] == "discovered", log
    rc, out, log = run(tmp_path, locale_path="pkg/locale")
    assert out["source"] == "input", log
    assert out["path"] == "pkg/locale", log


# --- controls: a skip must still be possible --------------------------------

def test_no_locale_tree_anywhere_still_reports_absent(tmp_path):
    """skip_if_no_locale exists for a caller with no locale tree at all. The
    search must not turn that into a failure."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    rc, out, log = run(tmp_path)
    assert rc == 0, log
    assert out["exists"] == "false", log
    assert out["source"] == "none", log


def test_the_absent_path_is_reported_as_searched_for(tmp_path):
    (tmp_path / "src").mkdir()
    rc, out, log = run(tmp_path)
    assert "searching for" in log, log


# --- controls: nothing but the skill's own resources is picked up -----------

@pytest.mark.parametrize("where", ["test", "tests", "docs", "scripts"])
def test_a_locale_tree_under_a_non_package_directory_is_ignored(tmp_path, where):
    make_locale(tmp_path, f"{where}/locale")
    rc, out, log = run(tmp_path)
    assert out["exists"] == "false", log
    assert out["source"] == "none", log


def test_a_locale_tree_under_a_dot_directory_is_ignored(tmp_path):
    make_locale(tmp_path, ".github/locale")
    rc, out, log = run(tmp_path)
    assert out["exists"] == "false", log


def test_a_tree_deeper_than_two_is_not_searched(tmp_path):
    """The package layout is <pkg>/locale. A deeper match is somebody else's
    vendored copy, and guessing at it would lint the wrong files."""
    make_locale(tmp_path, "a/b/locale")
    rc, out, log = run(tmp_path)
    assert out["exists"] == "false", log


# --- controls: ambiguity fails rather than guesses --------------------------

def test_two_package_locale_trees_fail_instead_of_guessing(tmp_path):
    make_locale(tmp_path, "pkg_a/locale")
    make_locale(tmp_path, "pkg_b/locale")
    rc, out, log = run(tmp_path)
    assert rc == 1, log
    assert "::error::" in log, log
    assert out == {}, out


def test_the_ambiguous_failure_names_every_candidate(tmp_path):
    make_locale(tmp_path, "pkg_a/locale")
    make_locale(tmp_path, "pkg_b/locale")
    _, _, log = run(tmp_path)
    assert "pkg_a/locale" in log and "pkg_b/locale" in log, log


# --- the binding the fix turns on ------------------------------------------

def test_the_lint_step_reads_the_resolved_path_not_the_raw_input():
    """The whole fix is inert unless the steps that follow read the resolved
    path. Before T-4696 the lint step took `inputs.locale_path` directly, so
    a discovered path would have been resolved and then ignored."""
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["spec_lint"]["steps"]
    consumers = [s for s in steps
                 if s.get("name") != STEP
                 and "LOCALE_PATH" in (s.get("env") or {})]
    assert consumers, "no step consumes LOCALE_PATH"
    for s in consumers:
        assert s["env"]["LOCALE_PATH"] == "${{ steps.resolve.outputs.path }}", \
            f"{s['name']} reads {s['env']['LOCALE_PATH']}"
