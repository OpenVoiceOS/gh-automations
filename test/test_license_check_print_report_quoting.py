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
    import os
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
