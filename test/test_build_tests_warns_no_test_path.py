"""build-tests.yml says so when no test ran (T-5587).

With test_path empty the Run Tests step is skipped, the result is "success" and
the job log shows nothing. The PR comment does say "The caller set no test path,
thus no test ran", but that comment is posted only on a pull_request and only
when pr_comment is true, so a push, or a caller with the comment off, gets no
signal at all. T-5499 found 17 callers in that state, one with 47 test files.

The step is the same shape as lint.yml's ruff file count (T-2338), so these tests
are the same shape as test_lint_file_count.py: run the step's script under bash
and read what it emits.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/build-tests.yml"
STEP_NAME = "Say so when no test ran"


def workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def build_step(name):
    steps = workflow()["jobs"]["build_tests"]["steps"]
    return next(s for s in steps if s.get("name") == name)


def run_say_so(tmp_path, require):
    script = build_step(STEP_NAME)["run"].replace(
        "${{ inputs.require_test_path }}", require)
    return subprocess.run(["bash"], input=script, cwd=tmp_path,
                          capture_output=True, text=True)


def test_the_step_exists_and_runs_only_when_test_path_is_empty():
    cond = build_step(STEP_NAME)["if"]
    # always(), or a failed build would swallow the warning that no test ran
    assert "always()" in cond, cond
    assert "inputs.test_path == ''" in cond, cond


def test_the_step_emits_a_github_warning_annotation(tmp_path):
    # require_test_path substituted to its default: the runner expands the
    # expression before bash sees it, and `${{` is not valid bash.
    out = run_say_so(tmp_path, "false").stdout
    assert out.startswith("::warning title="), out
    # the words that stop a reader taking it for a passing suite
    assert "ran no test" in out, out
    assert "not a passing suite" in out, out
    # and it must say what to do about it
    assert "test_path" in out, out


def test_the_step_does_not_fail_the_job_by_default(tmp_path):
    """A failure by default would turn every caller with no test_path red at
    once. T-5499 counted 24 repositories that call this workflow and have no
    test file at all, and the re-measure found 14 of 27 with no test file, so
    the fleet never fully drains. Failing is opt-in per repository
    (require_test_path) and never the default."""
    step = build_step(STEP_NAME)
    assert step.get("continue-on-error") is None, step
    assert run_say_so(tmp_path, "false").returncode == 0


def test_run_tests_is_still_the_only_step_gated_on_a_nonempty_test_path():
    """The annotation is the negative of the Run Tests condition. If one moves
    without the other, a job could both run tests and warn that it ran none."""
    steps = workflow()["jobs"]["build_tests"]["steps"]
    run_tests = next(s for s in steps if s.get("name") == "Run Tests")
    assert run_tests["if"] == "${{ inputs.test_path != '' }}", run_tests["if"]


def test_the_result_string_the_report_parses_is_unchanged():
    """post_build_report special-cases the exact string "no pytest summary" when
    it reads a matrix job's summary file. This change must not touch it: the
    writer and the reader have to keep agreeing."""
    text = WORKFLOW.read_text()
    assert text.count("no pytest summary") == 2, text.count("no pytest summary")
    assert 'echo "${SUMMARY:-no pytest summary}"' in text


def test_the_pr_comment_still_names_the_no_test_path_case():
    """The annotation is a second signal, not a replacement: the PR comment line
    that already covers this case must stay."""
    assert NO_TEST_PATH_LINE in report_line().lower()


# --- the report icon ------------------------------------------------------
# The sentence in the PR comment was already right and the icon contradicted
# it. A reader scanning the comment sees the icon first, so a green tick on
# "no test ran" is the defect this task names, not a cosmetic point.

NO_TEST_PATH_LINE = "the caller set no test path, thus no test ran"


def report_line():
    """The lines.append(...) call that builds the headline, not a comment that
    quotes the same sentence: the prior commit's comment block does."""
    return next(l for l in WORKFLOW.read_text().splitlines()
                if NO_TEST_PATH_LINE in l.lower() and "lines.append(" in l)


def test_the_pr_comment_does_not_put_a_tick_on_no_test_ran():
    line = report_line()
    assert "⚠" in line, line
    assert "✅" not in line, line


def test_the_pr_comment_says_it_is_not_a_passing_suite():
    line = report_line()
    assert "not a passing suite" in line.lower(), line


def test_the_fully_skipped_sibling_still_warns_the_same_way():
    """The two cases are the same reading and must not drift apart: a suite
    that ran and was fully skipped already used the warning sign, which is why
    the no-test-path line now does too."""
    text = WORKFLOW.read_text()
    line = next(l for l in text.splitlines()
                if "no test ran. The full suite was skipped" in l)
    assert "⚠" in line, line


# --- the test extras warning ---------------------------------------------
# The other half of the silence: with test_path set and install_extras empty
# the suite runs against the bare wheel, so a package that declares its test
# dependencies under an extra fails collection on an import and reads as a
# code defect. Two HiveMind repositories failed exactly that way once
# test_path was set (T-5499 census, second half).

EXTRAS_STEP = "Check test extras"


def extras_script():
    """The python body of the step, as the runner would execute it.

    yaml already strips the block scalar's indentation, so the heredoc body is
    taken from the parsed value and never re-dedented.
    """
    run = build_step(EXTRAS_STEP)["run"]
    return run.split("<<'PY'\n", 1)[1].rsplit("PY", 1)[0]


def make_wheel(path, extras):
    import zipfile
    meta = ["Metadata-Version: 2.1", "Name: w", "Version: 1.0"]
    meta += [f"Provides-Extra: {e}" for e in extras]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("w/__init__.py", "")
        zf.writestr("w-1.0.dist-info/METADATA", "\n".join(meta) + "\n")


def run_extras(tmp_path, extras, summary=None):
    (tmp_path / "dist").mkdir(exist_ok=True)
    make_wheel(tmp_path / "dist" / "w-1.0-py3-none-any.whl", extras)
    env = {"PATH": os.environ["PATH"]}
    if summary:
        env["GITHUB_STEP_SUMMARY"] = str(summary)
    return subprocess.run([sys.executable, "-"], input=extras_script(),
                          cwd=tmp_path, env=env, capture_output=True, text=True)


def test_the_extras_step_runs_only_when_tests_run_and_no_extra_is_installed():
    cond = build_step(EXTRAS_STEP)["if"]
    assert "inputs.test_path != ''" in cond, cond
    assert "inputs.install_extras == ''" in cond, cond


def test_the_extras_step_runs_before_the_suite():
    """A warning after the collection error it explains is no use."""
    names = [s.get("name") for s in workflow()["jobs"]["build_tests"]["steps"]]
    assert names.index(EXTRAS_STEP) < names.index("Run Tests"), names


def test_a_declared_test_extra_is_named_in_a_warning(tmp_path):
    r = run_extras(tmp_path, ["test", "docs"])
    assert r.returncode == 0, r.stderr
    assert "::warning title=No test extra installed::" in r.stdout, r.stdout
    assert "[test]" in r.stdout, r.stdout
    assert "Set install_extras to test." in r.stdout, r.stdout


def test_a_package_with_no_test_extra_is_not_warned_about(tmp_path):
    r = run_extras(tmp_path, ["docs", "async"])
    assert r.returncode == 0, r.stderr
    assert "::warning" not in r.stdout, r.stdout


def test_the_step_reports_how_many_it_read_and_how_many_matched(tmp_path):
    """A step that processes a set says how many went in and how many came
    out, so a silent run cannot be mistaken for a clean one."""
    r = run_extras(tmp_path, ["docs", "async"])
    assert "declares 2 extra(s)" in r.stdout, r.stdout
    assert "0 of them look like a test extra" in r.stdout, r.stdout


def test_the_named_extra_follows_preference_order_not_wheel_order(tmp_path):
    """A package declaring both must be told to set test, not dev, whichever
    order the wheel lists them in. Measured on hivemind-websocket-client,
    whose wheel declares async, dev, test, e2e, benchmark in that order."""
    r = run_extras(tmp_path, ["dev", "test"])
    assert "Set install_extras to test." in r.stdout, r.stdout
    r = run_extras(tmp_path, ["test", "dev"])
    assert "Set install_extras to test." in r.stdout, r.stdout


def test_the_extras_step_writes_the_job_summary(tmp_path):
    summary = tmp_path / "summary.md"
    summary.write_text("")
    r = run_extras(tmp_path, ["test"], summary=summary)
    assert r.returncode == 0, r.stderr
    assert "No test extra installed" in summary.read_text()


def test_the_extras_step_is_silent_and_green_with_no_wheel(tmp_path):
    """A caller whose build produced no wheel has a different problem, and
    this step must not add noise to it or fail the job."""
    env = {"PATH": os.environ["PATH"]}
    r = subprocess.run([sys.executable, "-"], input=extras_script(),
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", r.stdout


def test_the_extras_step_does_not_fail_the_job(tmp_path):
    """Like its sibling: a failure would turn every caller with a test extra
    and no install_extras red at once."""
    r = run_extras(tmp_path, ["test"])
    assert r.returncode == 0, r.stderr + r.stdout


# --- the escalation path --------------------------------------------------
# The task asked for a ruling on warning versus failure. It is a warning by
# default and a failure per repository, not a fleet default: T-5499 measured 27
# callers in this state and 14 of them have no test file at all, so the fleet
# never fully drains and a global failure would never become correct. The
# escalation has to be a repository opting in.


def test_require_test_path_is_declared_and_defaults_to_warning():
    on = workflow().get("on") or workflow().get(True)
    spec = on["workflow_call"]["inputs"]["require_test_path"]
    assert spec["type"] == "boolean"
    assert spec["default"] is False


def test_by_default_it_warns_and_the_job_stays_green(tmp_path):
    r = run_say_so(tmp_path, "false")
    assert r.returncode == 0, r.stderr
    assert "::warning title=no test ran::" in r.stdout, r.stdout
    assert "::error" not in r.stdout, r.stdout


def test_with_require_test_path_it_fails_the_job(tmp_path):
    r = run_say_so(tmp_path, "true")
    assert r.returncode != 0, r.stdout
    assert "::error title=no test ran::" in r.stdout, r.stdout
    assert "::warning" not in r.stdout, r.stdout


def test_both_paths_say_the_same_thing(tmp_path):
    """The message is one string, so the warning and the failure cannot drift
    apart and leave the honest wording on only one of them."""
    warn = run_say_so(tmp_path, "false").stdout
    fail = run_say_so(tmp_path, "true").stdout
    body = "test_path is empty, so the Run Tests step was skipped."
    assert body in warn and body in fail
    assert "not a passing suite" in warn and "not a passing suite" in fail
