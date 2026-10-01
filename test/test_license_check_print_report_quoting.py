"""gh-automations#151 added `report-format: 'json'` to the pilosus step, so
the "Print report" step's `run: echo "${{ steps.license_check_report.outputs.report
}}"` now echoes a JSON string carrying licence names with parentheses (e.g.
"GNU General Public License (GPL)") straight onto the run line. GitHub Actions
substitutes `${{ ... }}` textually before bash ever sees the line, so an
unescaped "(" in that text is a bash syntax error
("syntax error near unexpected token '('"), failing the step regardless of
the licence verdict (ovos-skill-alerts run 35880382478, step 17). The recheck
step had already cleared the row (caldav, recurring-ical-events,
x-wr-timezone are in exclude_packages); the print step still broke on the raw
text.

The fix passes the report through an `env:` block and prints it with a
double-quoted shell variable (`printf '%s\\n' "$REPORT"`), so its content is
inert to the shell no matter what it contains.

This test drives the step exactly as GitHub would: it renders the step's
`run:` template the same way the Actions runner does (a literal textual
substitution of `${{ steps.license_check_report.outputs.report }}`, if the
template still contains one) before handing the result to bash. Run against
the workflow as shipped before this fix, it reproduces the syntax error;
after the fix, the step has no bare `${{ }}` left in its `run:` text (the
value only ever reaches the shell through env) and the report line prints
unharmed."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Print report"

GPL_REPORT = '{"items": [{"dependency": {"name": "caldav", "version": "1.0"}, ' \
             '"license": {"name": "GNU General Public License (GPL)", "type": "StrongCopyleft"}}]}'


def _step():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    return next(s for s in steps if s.get("name") == STEP)


def _run_as_github_would(step: dict, report: str) -> subprocess.CompletedProcess:
    """Simulate the Actions runner: substitute any `${{ steps.*.outputs.report }}`
    expression textually into the run script (GitHub's own behaviour, done
    before bash is invoked), and set the value as $REPORT for any env-based
    step. Then hand the resulting script to bash exactly as the runner would."""
    script = step["run"]
    script = re.sub(r"\$\{\{\s*steps\.license_check_report\.outputs\.report\s*\}\}",
                     report, script)
    env = dict(**{"REPORT": report}) if "env" in step else None
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           timeout=10, env=full_env)


def test_print_report_step_has_no_bare_interpolation():
    # The whole bug class: a `${{ steps.*.outputs.* }}` expression expanded
    # directly onto the run line, instead of passed through env and quoted.
    step = _step()
    assert "${{" not in step["run"], step["run"]


def test_print_report_survives_a_licence_name_with_parentheses():
    step = _step()
    result = _run_as_github_would(step, GPL_REPORT)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "GNU General Public License (GPL)" in result.stdout, result.stdout


# --- bare expression interpolation inside any run block -------------------
#
# Same defect class as "Print report" above, for every other run block of
# the workflow. GitHub Actions substitutes `${{ ... }}` into the script as
# text before bash reads it, so a caller value holding a quote or a
# parenthesis is a bash syntax error and the step dies before it does any
# work. The values reach the shell through `env:` instead.

RUN_EXPRESSION = re.compile(
    r"\$\{\{\s*(steps\.[\w.-]+\.outputs\.[\w-]+|inputs\.[\w-]+)\s*\}\}")

HOSTILE = 'libfoo-dev (GPL) "x\' y'

# The steps that read a caller input or a step output in their script, and
# the expression each one must receive through env.
ENV_ROUTED_STEPS = {
    "Install System Dependencies": "${{ inputs.system_deps }}",
    "Install package": "${{ inputs.install_extras }}",
    "Generate full license breakdown": "${{ steps.exclude.outputs.regex }}",
    "Print report": "${{ steps.license_check_report.outputs.report }}",
}


def _steps():
    wf = yaml.safe_load(WORKFLOW.read_text())
    return [s for j in wf["jobs"].values() for s in j["steps"]]


def test_no_run_block_interpolates_a_step_output_or_an_input():
    found = {s.get("name"): RUN_EXPRESSION.findall(s.get("run") or "")
             for s in _steps()}
    assert {k: v for k, v in found.items() if v} == {}


@pytest.mark.parametrize("name", sorted(ENV_ROUTED_STEPS))
def test_step_takes_the_value_from_env(name):
    step = next(s for s in _steps() if s.get("name") == name)
    assert ENV_ROUTED_STEPS[name] in step.get("env", {}).values()


@pytest.mark.parametrize("name", sorted(ENV_ROUTED_STEPS))
def test_step_script_parses_with_a_hostile_value(name):
    """Render the step the way the runner does, then let bash parse it.

    A parse check reaches only two of these four steps. "Install System
    Dependencies" and "Generate full license breakdown" put the value where
    the parenthesis is bare shell text, so bash rejects the unfixed script.
    "Install package" wraps it in `RAW="..."`, where the parenthesis is
    inert and the stray single quote pairs with one in a later comment, so
    the unfixed script parses and corrupts the value instead; the value is
    asserted by test_install_package_computes_the_callers_extras below.
    "Print report" was fixed in #152 and parses either way.
    """
    step = next(s for s in _steps() if s.get("name") == name)
    script = RUN_EXPRESSION.sub(HOSTILE, step["run"])
    result = subprocess.run(["bash", "-n"], input=script, capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr


# --- the value the Install package step derives ----------------------------
#
# The "Install package" defect is a silent value corruption, not a syntax
# error, so only an assertion on the computed value can see it. The expected
# value comes from the step's documented contract, restated here, rather than
# from the step itself.
#
# The two values carrying a stray single quote are the controls: against the
# unfixed step the quote pairs with one in a later comment, the assignment
# swallows the rest of the line, and NORMALIZED comes out empty. The other
# values, parentheses included, survive the unfixed step because a double
# quoted assignment makes them inert; they hold the normalisation itself.

INSTALL_EXTRAS_VALUES = [
    "",
    "dev",
    "[dev]",
    ".[dev]",
    "-r requirements/test.txt",
    "docs/extra",
    "libfoo (GPL)",
    'test] "x\' y',
    '.[dev] "x\' y',
]

STUB_UV = 'uv() { : "the test does not install anything"; }\n'
PRINT_NORMALIZED = '\nprintf "NORMALIZED=%s\\n" "$NORMALIZED"\n'


def _normalized(raw: str) -> str:
    """What install_extras must become, by the contract the step documents.

    An empty value installs the project itself. A pip argument, a path, or an
    already dot-prefixed value passes through untouched. A bracketed value
    takes the project prefix, and a bare extra name is wrapped in brackets.
    """
    if not raw:
        return "."
    if raw.startswith("-") or "/" in raw or raw.startswith("."):
        return raw
    if raw.startswith("["):
        return f".{raw}"
    return f".[{raw}]"


def _render(step: dict, value: str) -> tuple[str, dict]:
    """Do what the runner does with one caller value: substitute every
    expression in the run text, and resolve the step's own env entries."""
    script = RUN_EXPRESSION.sub(lambda _: value, step["run"])
    env = dict(os.environ)
    env.update({key: RUN_EXPRESSION.sub(lambda _: value, str(expression))
                for key, expression in (step.get("env") or {}).items()})
    return script, env


@pytest.mark.parametrize("value", INSTALL_EXTRAS_VALUES)
def test_install_package_computes_the_callers_extras(value):
    step = next(s for s in _steps() if s.get("name") == "Install package")
    script, env = _render(step, value)
    result = subprocess.run(["bash", "-c", STUB_UV + script + PRINT_NORMALIZED],
                            capture_output=True, text=True, timeout=30,
                            env=env)
    reported = [line[len("NORMALIZED="):] for line in result.stdout.splitlines()
                if line.startswith("NORMALIZED=")]
    assert reported == [_normalized(value)], result.stdout + result.stderr
