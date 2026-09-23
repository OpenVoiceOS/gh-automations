"""T-3825 review, CONFIRMED finding: a package that ships no licence metadata
of its own, but whose PyPI history reports a forbidden licence for an older
release, must NOT be excluded from the hard failure. Before the fix the
exclusion ran unconditionally once the lookup returned, so this case was a
fail-to-pass move: pilosus would have failed "shady" as category "Error",
and the step excluded it anyway because it also read GPL-3.0-or-later from
0.9. The WARN row must say the inherited licence is forbidden.

Drives the step exactly as shipped, extracted from the YAML, same technique
as test_license_check_no_metadata.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_no_metadata import build_site, install_fake_urllib, step_script, matches
from test_license_check_no_metadata import FAKE_PIP_LICENSES_TEMPLATE, FAKE_PYTHON

import json
import os
import stat
import subprocess


def _drive(tmp_path, packages, dists, responses):
    site = build_site(tmp_path, dists)
    install_fake_urllib(site, responses)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pip-licenses"
    fake.write_text(FAKE_PIP_LICENSES_TEMPLATE.format(payload=json.dumps(packages)))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    py = bindir / "python3"
    py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "github_output"
    out.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", PYTHONPATH=str(site),
               GITHUB_OUTPUT=str(out),
               FAIL_LICENSES="NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error")
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = out.read_text().splitlines()
    regex = next(l for l in lines if l.startswith("regex="))[len("regex="):]
    warnings = json.loads(next(l for l in lines if l.startswith("warnings="))[len("warnings="):])
    return regex, warnings


def test_a_metadata_less_package_whose_lookup_says_gpl_is_not_excluded(tmp_path):
    packages = [{"Name": "shady", "Version": "1.0rc1", "License": "UNKNOWN"}]
    dists = {"shady-1.0rc1": ""}
    responses = {
        "https://pypi.org/pypi/shady/json": {"releases": {
            "1.0rc1": [{"filename": "shady-1.0rc1.tar.gz"}],
            "0.9": [{"filename": "shady-0.9.tar.gz"}]}},
        "https://pypi.org/pypi/shady/1.0rc1/json": {"info": {"license": "", "classifiers": []}},
        "https://pypi.org/pypi/shady/0.9/json": {
            "info": {"license": "GPL-3.0-or-later", "classifiers": []}},
    }
    regex, warnings = _drive(tmp_path, packages, dists, responses)
    assert warnings[0]["inherited"]["license"] == "GPL-3.0-or-later", warnings
    assert warnings[0]["forbidden"] is True, warnings
    # the fix: the lookup reports a forbidden licence, so the package stays
    # a hard failure instead of being excluded.
    assert not matches(regex, "shady==1.0rc1"), regex


def test_a_metadata_less_package_whose_lookup_says_apache_is_still_excluded(tmp_path):
    # Control: the same shape, but the inherited licence is permissive, so
    # the WARN-and-exclude behaviour from before the fix still applies.
    packages = [{"Name": "friendly", "Version": "1.0rc1", "License": "UNKNOWN"}]
    dists = {"friendly-1.0rc1": ""}
    responses = {
        "https://pypi.org/pypi/friendly/json": {"releases": {
            "1.0rc1": [{"filename": "friendly-1.0rc1.tar.gz"}],
            "0.9": [{"filename": "friendly-0.9.tar.gz"}]}},
        "https://pypi.org/pypi/friendly/1.0rc1/json": {"info": {"license": "", "classifiers": []}},
        "https://pypi.org/pypi/friendly/0.9/json": {
            "info": {"license": "Apache-2.0", "classifiers": []}},
    }
    regex, warnings = _drive(tmp_path, packages, dists, responses)
    assert warnings[0]["forbidden"] is False, warnings
    assert matches(regex, "friendly==1.0rc1"), regex


def test_deny_no_metadata_input_denies_by_name(tmp_path):
    # The deny_no_metadata workflow_call input feeds DENY_NO_METADATA_INPUT;
    # a denied package is excluded from safe_names regardless of the lookup.
    packages = [{"Name": "hush", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"hush-1.0": ""}
    site = build_site(tmp_path, dists)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pip-licenses"
    fake.write_text(FAKE_PIP_LICENSES_TEMPLATE.format(payload=json.dumps(packages)))
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    py = bindir / "python3"
    py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "github_output"
    out.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", PYTHONPATH=str(site),
               GITHUB_OUTPUT=str(out),
               FAIL_LICENSES="NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error",
               DENY_NO_METADATA_INPUT="hush",
               HTTPS_PROXY="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1",
               NO_PROXY="", no_proxy="")
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = out.read_text().splitlines()
    regex = next(l for l in lines if l.startswith("regex="))[len("regex="):]
    assert not matches(regex, "hush==1.0"), regex
