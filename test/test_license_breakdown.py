"""
Tests for the "Generate full license breakdown" step of license-check.yml.

The step used to pass the combined PCRE exclude to pip-licenses as
`--filter-strings $COMBINED`. `--filter-strings` takes no argument — it is the
code-page filter — so the regex arrived as an unexpected positional argument,
pip-licenses exited 2, and `|| echo "[]"` wrote an empty list. Every job summary
and PR comment the shared workflow wrote therefore said 0 packages, whatever was
installed (58 packages on TigreGotico/ovos-stt-plugin-whisper#19, run
35385266154).

These tests read the step out of the workflow rather than restating it, and run
its python body against synthetic pip-licenses output.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    pytest.skip("PyYAML not installed", allow_module_level=True)

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "license-check.yml"


def _breakdown_step() -> dict:
    data = yaml.safe_load(WORKFLOW.read_text())
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if step.get("id") == "license_breakdown":
                return step
    raise AssertionError("no step with id license_breakdown in license-check.yml")


def _python_body(run: str) -> str:
    """The heredoc body the step feeds to python3."""
    match = re.search(r"python3 - <<'PYEOF'\n(.*?)\nPYEOF", run, re.DOTALL)
    assert match, "the step no longer feeds a PYEOF heredoc to python3"
    return match.group(1)


def _run_body(tmp_path: Path, packages: list[dict], combined: str) -> tuple[int, str, dict]:
    """Run the step's python body over `packages`, reading its GITHUB_OUTPUT."""
    body = _python_body(_breakdown_step()["run"])
    # the step writes fixed /tmp paths; point them at the test's own directory
    body = body.replace("/tmp/", f"{tmp_path}/")
    (tmp_path / "pip-licenses-all.json").write_text(json.dumps(packages))
    out_file = tmp_path / "gh-output"
    out_file.write_text("")
    proc = subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        env={"COMBINED_REGEX": combined, "GITHUB_OUTPUT": str(out_file), "PATH": "/usr/bin:/bin"},
    )
    outputs = dict(
        line.split("=", 1) for line in out_file.read_text().splitlines() if "=" in line
    )
    return proc.returncode, proc.stdout + proc.stderr, outputs


PACKAGES = [
    {"Name": "ovos-utils", "Version": "0.3.0", "License": "Apache-2.0"},
    {"Name": "tqdm", "Version": "4.66.0", "License": "MPL-2.0 AND MIT"},
    {"Name": "bidict", "Version": "0.23.1", "License": "MPL-2.0"},
    {"Name": "requests", "Version": "2.32.3", "License": "Apache-2.0"},
]

CENTRAL = r"(?i:^tqdm([=<>!~ @;].*)?$)|(?i:^bidict([=<>!~ @;].*)?$)"


def _command_lines(run: str) -> str:
    """The step's shell lines with its comments removed."""
    return "\n".join(l for l in run.splitlines() if not l.lstrip().startswith("#"))


def test_the_flag_that_broke_it_is_gone():
    run = _command_lines(_breakdown_step()["run"])
    assert "--filter-strings" not in run, (
        "--filter-strings takes no argument; passing the exclude regex to it is "
        "what made every breakdown report 0 packages"
    )


def test_the_regex_reaches_the_step_as_an_env_var_not_an_interpolation():
    step = _breakdown_step()
    assert step.get("env", {}).get("COMBINED_REGEX") == "${{ steps.exclude.outputs.regex }}"
    # an unquoted ${{ }} regex in the shell line was the other half of the bug
    assert "${{ steps.exclude.outputs.regex }}" not in step["run"]


def test_a_pip_licenses_failure_is_loud_and_fails_the_step():
    run = _breakdown_step()["run"]
    assert 'echo "[]"' not in run, "the silent empty-list fallback is what hid the failure"
    assert "::error" in run
    assert "exit 1" in run


def test_every_installed_package_is_counted(tmp_path):
    code, log, outputs = _run_body(tmp_path, PACKAGES, "")
    assert code == 0, log
    assert outputs["total_packages"] == "4"


def test_the_exclude_removes_only_what_it_names(tmp_path):
    code, log, outputs = _run_body(tmp_path, PACKAGES, CENTRAL)
    assert code == 0, log
    assert outputs["total_packages"] == "2"
    kept = json.loads((tmp_path / "pip-licenses.json").read_text())
    assert sorted(p["Name"] for p in kept) == ["ovos-utils", "requests"]


def test_the_exclude_is_matched_against_name_and_version(tmp_path):
    """pilosus matches "name==version"; the breakdown must match the same string."""
    code, log, _ = _run_body(tmp_path, PACKAGES, r"(?i:^tqdm==4\.66\.0$)")
    assert code == 0, log
    kept = json.loads((tmp_path / "pip-licenses.json").read_text())
    assert "tqdm" not in [p["Name"] for p in kept]


def test_a_near_name_is_not_excluded(tmp_path):
    packages = PACKAGES + [{"Name": "tqdm-extra", "Version": "1.0", "License": "MIT"}]
    code, log, outputs = _run_body(tmp_path, packages, CENTRAL)
    assert code == 0, log
    kept = [p["Name"] for p in json.loads((tmp_path / "pip-licenses.json").read_text())]
    assert "tqdm-extra" in kept
    assert outputs["total_packages"] == "3"


def test_the_counts_are_printed_so_a_sweep_can_be_checked(tmp_path):
    code, log, _ = _run_body(tmp_path, PACKAGES, CENTRAL)
    assert code == 0, log
    assert "read 4 package(s)" in log
    assert "2 excluded" in log
    assert "2 in the breakdown" in log


def test_the_excluded_packages_are_named(tmp_path):
    """A count alone cannot be checked; the names can."""
    code, log, _ = _run_body(tmp_path, PACKAGES, CENTRAL)
    assert code == 0, log
    assert "excluded: bidict, tqdm" in log


def test_two_packages_with_the_same_contents_are_named_once_each(tmp_path):
    """The excluded names come from the match, not from a dict identity test."""
    packages = [
        {"Name": "tqdm", "Version": "4.66.0", "License": "MIT"},
        {"Name": "tqdm", "Version": "4.66.0", "License": "MIT"},
        {"Name": "requests", "Version": "2.32.3", "License": "Apache-2.0"},
    ]
    code, log, outputs = _run_body(tmp_path, packages, CENTRAL)
    assert code == 0, log
    assert "2 excluded" in log
    assert "excluded: tqdm, tqdm" in log
    assert outputs["total_packages"] == "1"


def test_an_empty_breakdown_says_so_instead_of_reporting_it_as_clean(tmp_path):
    code, log, outputs = _run_body(tmp_path, PACKAGES, r".*")
    assert code == 0, log
    assert outputs["total_packages"] == "0"
    assert "::warning" in log


def test_an_invalid_exclude_fails_instead_of_counting_nothing(tmp_path):
    code, log, outputs = _run_body(tmp_path, PACKAGES, "(?i:^unclosed")
    assert code == 1, log
    assert "::error" in log
    assert "total_packages" not in outputs
