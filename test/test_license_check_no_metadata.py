"""license-check.yml reads a hard "Error" from pilosus for any distribution
that carries no licence metadata at all: no `License` field, no PEP 639
`License-Expression`, no `License ::` classifier (T-2477). FAIL_LICENSES
includes "Error" by default, so a prerelease resolved before its licence
metadata landed on PyPI (tokenizers 1.0.0rc2) failed the job for every
downstream repo, even though nothing about the metadata says the licence is
forbidden — there is simply nothing to read.

The "Detect packages with no licence metadata" step excludes such a package
from the hard failure by name (reported instead as a WARN in the PR comment)
unless it is named in the step's DENY_NO_METADATA set. A package that DOES
carry licence metadata, forbidden or not, is left untouched and still fails
through the existing pilosus check.

The step is run under bash against a fake site-packages built from wheel
METADATA samples, same technique as test_license_check_pep639.py. The PyPI
lookup for the "inherited licence" note is wrapped in a bare try/except in
the step, so it degrades to "no released version carries licence metadata
either" when the test box has no network."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Detect packages with no licence metadata"

FAKE_PIP_LICENSES_TEMPLATE = "#!/usr/bin/env bash\ncat <<'JSON'\n{payload}\nJSON\n"

FAKE_PYTHON = f"#!/usr/bin/env bash\nexec {sys.executable} -S \"$@\"\n"


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def build_site(tmp_path: Path, dists: dict[str, str]) -> Path:
    # dists maps "name-version" -> extra METADATA lines (License, classifier, etc).
    site = tmp_path / "site-packages"
    site.mkdir()
    for dist, extra in dists.items():
        name, version = dist.rsplit("-", 1)
        info = site / f"{dist}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{extra}")
    return site


def run_step(tmp_path: Path, packages: list[dict], dists: dict[str, str],
             fail: str = "NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error") -> tuple[str, list]:
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
               GITHUB_OUTPUT=str(out), FAIL_LICENSES=fail,
               NO_PROXY="*")  # block the PyPI lookup rather than let it hang in CI
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = out.read_text().splitlines()
    regex_line = next(l for l in lines if l.startswith("regex="))
    warnings_line = next(l for l in lines if l.startswith("warnings="))
    regex = regex_line[len("regex="):]
    warnings = json.loads(warnings_line[len("warnings="):])
    return regex, warnings


def matches(regex: str, requirement: str) -> bool:
    if not regex:
        return False
    return any(re.fullmatch(alt, requirement) for alt in regex.split("|"))


def test_package_with_no_licence_metadata_is_excluded_and_warned(tmp_path):
    # tokenizers 1.0.0rc2 (T-2477): PyPI carries no licence metadata for the
    # release candidate at all, so the row must be a WARN, never a hard
    # failure. The step best-effort looks up the newest release that DOES
    # carry metadata (Apache-2.0, from 0.23.2) to label the WARN row; a test
    # box with no network still passes, because that lookup is optional.
    packages = [{"Name": "tokenizers", "Version": "1.0.0rc2", "License": "UNKNOWN"}]
    dists = {"tokenizers-1.0.0rc2": ""}  # no License, no Expression, no classifier
    regex, warnings = run_step(tmp_path, packages, dists)
    assert matches(regex, "tokenizers==1.0.0rc2"), regex
    assert len(warnings) == 1, warnings
    warning = warnings[0]
    assert warning["name"] == "tokenizers", warning
    assert warning["version"] == "1.0.0rc2", warning
    # inherited is either None (no network in this environment) or names an
    # Apache licence from a later release; it must never be a copyleft one.
    inherited = warning["inherited"]
    if inherited is not None:
        assert "apache" in inherited["license"].lower(), inherited


def test_gpl_package_still_fails(tmp_path):
    packages = [{"Name": "some-gpl-pkg", "Version": "2.0.0", "License": "GNU General Public License v3"}]
    dists = {"some-gpl-pkg-2.0.0": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert not matches(regex, "some-gpl-pkg==2.0.0"), regex
    assert warnings == [], warnings
