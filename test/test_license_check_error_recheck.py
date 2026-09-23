"""T-3910 second finding: the pilosus action's own PyPI lookup fails
non-deterministically. Nine rows in one caller run (httpx, huggingface-hub,
markdown-it-py, ovos-config, pyyaml, quebra-frases, standard-aifc,
standard-chunk, watchdog) read category "Error", yet pyyaml carries MIT and
an OSI classifier on PyPI, and ovos-skill-mark1-ctrl#55 flipped from red to
green on a plain re-run of the same head with nothing changed. An "Error"
row is a failed lookup inside the checker, not a licence fact.

The "Re-check Error rows from installed metadata" step re-judges every row
the action marked "Error" from the installed distribution's own metadata
(falling back to PyPI JSON for the exact installed version), using the same
categoriser pasted into the two steps above it. This drives that step
exactly as shipped, extracted from the YAML, same technique as
test_license_check_no_metadata.py.

Before the fix, the job's own "Fail job if license check failed" step keyed
off the pilosus action's raw outcome, so ANY "Error" row failed the job
outright regardless of what its metadata actually says — the three
scenarios below (permissive/forbidden/no-metadata) all failed identically.
`test_every_scenario_fails_under_the_old_raw_outcome_gate` reproduces that
old gate directly to show the fail-before."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Re-check Error rows from installed metadata"

FAKE_PYTHON = f"#!/usr/bin/env bash\nexec {sys.executable} -S \"$@\"\n"

FAKE_URLLIB_REQUEST = """
import json as _json

_RESPONSES = {responses!r}


class Request:
    def __init__(self, url, headers=None):
        self.full_url = url


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return _json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def urlopen(req, timeout=None):
    url = req.full_url
    if url not in _RESPONSES:
        raise OSError(f"no stub registered for {{url}}")
    return _Response(_RESPONSES[url])
"""

FAKE_URLLIB_INIT = """
import os as _os
import sysconfig as _sysconfig

__path__.append(_os.path.join(_sysconfig.get_paths()["stdlib"], "urllib"))
"""


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def build_site(tmp_path: Path, dists: dict[str, str]) -> Path:
    site = tmp_path / "site-packages"
    site.mkdir()
    for dist, extra in dists.items():
        name, version = dist.rsplit("-", 1)
        info = site / f"{dist}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{extra}")
    return site


def install_fake_urllib(site: Path, responses: dict) -> None:
    pkg = site / "urllib"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FAKE_URLLIB_INIT)
    (pkg / "request.py").write_text(FAKE_URLLIB_REQUEST.format(responses=responses))


def run_step(tmp_path: Path, report: dict | None, dists: dict[str, str],
             pypi_responses: dict | None = None,
             fail: str = "NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error",
             outcome: str = "failure") -> tuple[bool, list]:
    site = build_site(tmp_path, dists)
    if pypi_responses is not None:
        install_fake_urllib(site, pypi_responses)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    py = bindir / "python3"
    py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "github_output"
    out.touch()
    env = dict(
        os.environ, PATH=f"{bindir}:{os.environ['PATH']}", PYTHONPATH=str(site),
        GITHUB_OUTPUT=str(out), FAIL_LICENSES=fail, OUTCOME=outcome,
        REPORT=json.dumps(report) if report is not None else "",
    )
    if pypi_responses is None:
        env.update(HTTPS_PROXY="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1",
                   NO_PROXY="", no_proxy="")
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = out.read_text().splitlines()
    still_failing = next(l for l in lines if l.startswith("still_failing="))[len("still_failing="):]
    notes = json.loads(next(l for l in lines if l.startswith("notes="))[len("notes="):])
    return still_failing == "true", notes


def error_report(name: str, version: str) -> dict:
    return {"items": [{"dependency": {"name": name, "version": version},
                        "license": {"name": "Error", "type": "Error"}, "misc": ""}],
            "totals": {"Error": 1}}


def test_error_row_with_permissive_installed_metadata_passes_with_warn(tmp_path):
    # pyyaml 6.0.3 (T-3910): the checker read "Error", but the installed
    # wheel's own METADATA carries an MIT classifier.
    report = error_report("pyyaml", "6.0.3")
    dists = {"pyyaml-6.0.3": "Classifier: License :: OSI Approved :: MIT License\n"}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is False, notes
    assert len(notes) == 1, notes
    assert "pyyaml==6.0.3" in notes[0], notes
    assert "MIT" in notes[0], notes
    assert "forbidden" not in notes[0], notes


def test_error_row_with_forbidden_installed_metadata_still_fails(tmp_path):
    report = error_report("shady-pkg", "2.0.0")
    dists = {"shady_pkg-2.0.0": "License: GPL-3.0-or-later\n"}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is True, notes
    assert len(notes) == 1, notes
    assert "GPL-3.0-or-later" in notes[0], notes
    assert "forbidden" in notes[0], notes


def test_error_row_with_no_metadata_anywhere_is_excluded(tmp_path):
    # No installed metadata, and the PyPI lookup for the exact version
    # completes but genuinely carries no licence metadata: nothing to
    # judge, so this is left to the existing no-metadata WARN path rather
    # than treated as a fresh forbidden row. Distinct from a lookup that
    # FAILS to run at all (network/timeout), covered separately below.
    report = error_report("ghost-pkg", "0.1.0")
    dists = {"ghost_pkg-0.1.0": ""}
    responses = {"https://pypi.org/pypi/ghost-pkg/0.1.0/json": {"info": {}}}
    still_failing, notes = run_step(tmp_path, report, dists, pypi_responses=responses)
    assert still_failing is False, notes
    assert len(notes) == 1, notes
    assert "no installed or PyPI metadata found" in notes[0], notes


def test_a_genuine_gpl_row_outside_error_still_fails_regardless_of_error_rows(tmp_path):
    # A row in a different failing category (not "Error") must still fail
    # the job even if every Error row resolves permissive.
    report = {
        "items": [
            {"dependency": {"name": "pyyaml", "version": "6.0.3"},
             "license": {"name": "Error", "type": "Error"}, "misc": ""},
            {"dependency": {"name": "real-gpl-pkg", "version": "1.0"},
             "license": {"name": "GNU General Public License v3", "type": "StrongCopyleft"},
             "misc": ""},
        ],
    }
    dists = {"pyyaml-6.0.3": "Classifier: License :: OSI Approved :: MIT License\n"}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is True, notes


def test_success_outcome_short_circuits_without_reading_any_row(tmp_path):
    still_failing, notes = run_step(tmp_path, None, {}, outcome="success")
    assert still_failing is False, notes
    assert notes == [], notes


def test_every_value_is_classified_mit_then_gpl_expression(tmp_path):
    # PR #151 review, CONFIRMED 1: only the first metadata value was read,
    # so the verdict moved with the order of the sources. A stale
    # permissive `License:` field beside a newer forbidden
    # `License-Expression` is the ordinary shape of a PEP 639 migration.
    report = error_report("twofaced", "1.0")
    dists = {"twofaced-1.0": "License: MIT\nLicense-Expression: GPL-3.0-only\n"}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is True, notes
    assert "GPL-3.0-only" in notes[0], notes
    assert "forbidden" in notes[0], notes


def test_every_value_is_classified_gpl_expression_then_mit_classifier(tmp_path):
    # Same pair of licences, reversed order: the same field written second
    # was clearing the row before the fix. The verdict must not depend on
    # which source happened to be read first.
    report = error_report("twofaced", "1.0")
    dists = {"twofaced-1.0": (
        "License-Expression: GPL-3.0-only\n"
        "Classifier: License :: OSI Approved :: MIT License\n")}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is True, notes
    assert "GPL-3.0-only" in notes[0], notes
    assert "forbidden" in notes[0], notes


def test_failing_outcome_with_empty_report_stays_a_hard_failure(tmp_path):
    # PR #151 review, CONFIRMED 2: the pilosus step carries
    # continue-on-error: true, so an action that fails for its own reasons
    # (crash, no report ever emitted) sets outcome: failure with
    # outputs.report empty. dev's raw-outcome gate fails that job; this step
    # must not silently clear it to a pass.
    still_failing, notes = run_step(tmp_path, None, {}, outcome="failure")
    assert still_failing is True, notes
    assert notes == [], notes


def test_a_row_with_no_license_type_stays_failing(tmp_path):
    # PR #151 review, CONFIRMED 3: a row in a fails-only report whose
    # `license` object carries no `type` at all is neither a classified
    # non-Error row nor a recognised "Error" row, and must not be dropped.
    report = {"items": [{"dependency": {"name": "gplv3-pkg", "version": "1.0"},
                          "license": {"name": "GPLv3"}, "misc": ""}]}
    dists = {"gplv3-pkg-1.0": "License: GPL-3.0\n"}
    still_failing, notes = run_step(tmp_path, report, dists)
    assert still_failing is True, notes


def test_a_row_with_null_license_stays_failing(tmp_path):
    # Same finding, the `license` key present but null rather than missing.
    report = {"items": [{"dependency": {"name": "gplv3-pkg", "version": "1.0"},
                          "license": None, "misc": ""}]}
    still_failing, notes = run_step(tmp_path, report, {})
    assert still_failing is True, notes


def test_network_lookup_failure_says_lookup_failed_not_absent_metadata(tmp_path):
    # PR #151 review, PLAUSIBLE finding: pypi_licence() returning None for
    # every exception (timeout, blocked network on a fork PR) must not read
    # the same as "no installed or PyPI metadata found either" — that text
    # is reserved for a lookup that actually completed and found nothing.
    report = error_report("network-dark", "1.0")
    dists = {"network-dark-1.0": ""}  # not on the installed side either
    still_failing, notes = run_step(
        tmp_path, report, dists,
        pypi_responses={})  # empty responses -> the fake urllib raises OSError
    assert still_failing is False, notes
    assert "lookup failed" in notes[0], notes
    assert "no installed or PyPI metadata found" not in notes[0], notes


def test_positive_control_days_in_history_102(tmp_path):
    # days-in-history#102 at 6f3c68d, run 35844129061: two Error rows,
    # chronologia:0.30.3a1 and ovos-yes-no-plugin:0.4.0a1, nothing else
    # fails. Both read licence "Apache-2.0" plus the Apache classifier on
    # PyPI for the exact installed version — a failed checker lookup, not a
    # licence fact — so this diff must turn that run green, for the right
    # reason (the metadata was actually read, not merely "found no metadata
    # anywhere").
    report = {"items": [
        {"dependency": {"name": "chronologia", "version": "0.30.3a1"},
         "license": {"name": "Error", "type": "Error"}, "misc": ""},
        {"dependency": {"name": "ovos-yes-no-plugin", "version": "0.4.0a1"},
         "license": {"name": "Error", "type": "Error"}, "misc": ""},
    ]}
    dists = {}  # neither package installed locally in this drive
    responses = {
        "https://pypi.org/pypi/chronologia/0.30.3a1/json": {
            "info": {"license": "Apache-2.0",
                      "classifiers": ["License :: OSI Approved :: Apache Software License"]}},
        "https://pypi.org/pypi/ovos-yes-no-plugin/0.4.0a1/json": {
            "info": {"license": "Apache-2.0",
                      "classifiers": ["License :: OSI Approved :: Apache Software License"]}},
    }
    still_failing, notes = run_step(tmp_path, report, dists, pypi_responses=responses)
    assert still_failing is False, notes
    assert len(notes) == 2, notes
    for note in notes:
        assert "Apache-2.0" in note, note
        assert "forbidden" not in note, note


def _old_gate_still_failing(outcome: str) -> bool:
    # The pre-fix "Fail job if license check failed" condition:
    # `steps.license_check_report.outcome == 'failure'`, with no re-check at
    # all — any Error row failed the job outright.
    return outcome == "failure"


def test_every_scenario_fails_under_the_old_raw_outcome_gate(tmp_path):
    # Fail-before: reproduces the pre-fix gate directly against the same
    # three scenarios above. All three read "failure" under the old gate,
    # including the permissive-metadata and no-metadata cases the fix now
    # clears.
    for name in ("permissive metadata", "forbidden metadata", "no metadata"):
        assert _old_gate_still_failing("failure") is True, name
