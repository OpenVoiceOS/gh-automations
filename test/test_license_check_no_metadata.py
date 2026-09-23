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
lookup for the "inherited licence" note reports a status of "found", "none"
or "unavailable": "unavailable" covers a network or parse failure, and
"none" is reserved for every inspected release genuinely lacking licence
metadata. The test routes the lookup at an unreachable local port, so it
always sees "unavailable" here; a second test stubs the lookup with a
fake `pip` cache entry to cover the "found" path without touching the
network."""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
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
    # The step runs under a fake python3 with the site module disabled
    # (see FAKE_PYTHON), so packaging.version has to be reachable via
    # PYTHONPATH rather than the ambient interpreter's own site-packages.
    packaging_src = Path(importlib.import_module("packaging").__file__).parent
    shutil.copytree(packaging_src, site / "packaging")
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
               # route the PyPI lookup at an unreachable local port so it
               # fails fast instead of hitting the real network (NO_PROXY
               # does not disable a direct connection, so unset it too).
               HTTPS_PROXY="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1",
               NO_PROXY="", no_proxy="")
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

# Only `request` is stubbed below; extend the search path so every other
# submodule (`parse`, used by the stdlib's own `email` package) still
# resolves to the real standard library.
__path__.append(_os.path.join(_sysconfig.get_paths()["stdlib"], "urllib"))
"""


def install_fake_urllib(site: Path, responses: dict) -> None:
    # Shadows only urllib.request with a stub that answers the exact PyPI
    # URLs given, so the "found" path is covered without a real network
    # call. PYTHONPATH is searched ahead of the standard library, so a
    # package of this name placed in the fake site-packages dir wins.
    pkg = site / "urllib"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FAKE_URLLIB_INIT)
    (pkg / "request.py").write_text(FAKE_URLLIB_REQUEST.format(responses=responses))


def test_package_with_no_licence_metadata_is_excluded_and_warned(tmp_path):
    # tokenizers 1.0.0rc2 (T-2477): PyPI carries no licence metadata for the
    # release candidate at all, so the row must be a WARN, never a hard
    # failure. The lookup for a release that DOES carry metadata is routed
    # at an unreachable local port here, so it always reports "unavailable"
    # rather than silently reading as "no released version carries licence
    # metadata" — a network failure must never be mistaken for a confirmed
    # absence of licence metadata.
    packages = [{"Name": "tokenizers", "Version": "1.0.0rc2", "License": "UNKNOWN"}]
    dists = {"tokenizers-1.0.0rc2": ""}  # no License, no Expression, no classifier
    regex, warnings = run_step(tmp_path, packages, dists)
    assert matches(regex, "tokenizers==1.0.0rc2"), regex
    assert len(warnings) == 1, warnings
    warning = warnings[0]
    assert warning["name"] == "tokenizers", warning
    assert warning["version"] == "1.0.0rc2", warning
    assert warning["inherited"]["status"] == "unavailable", warning


def test_inherited_licence_found_from_a_later_release(tmp_path):
    # A stubbed PyPI answers with two releases: the installed 1.0.0rc2
    # (no licence metadata, same as above) and a newer 1.0.1 that carries
    # Apache-2.0. The step must pick the newest release that carries
    # licence metadata, not merely the newest release overall.
    packages = [{"Name": "tokenizers", "Version": "1.0.0rc2", "License": "UNKNOWN"}]
    dists = {"tokenizers-1.0.0rc2": ""}
    site = build_site(tmp_path, dists)
    install_fake_urllib(site, {
        "https://pypi.org/pypi/tokenizers/json": {
            "releases": {
                "1.0.0rc2": [{"filename": "tokenizers-1.0.0rc2.tar.gz"}],
                "1.0.1": [{"filename": "tokenizers-1.0.1.tar.gz"}],
            },
        },
        "https://pypi.org/pypi/tokenizers/1.0.1/json": {
            "info": {"license": "Apache-2.0", "classifiers": []},
        },
        "https://pypi.org/pypi/tokenizers/1.0.0rc2/json": {
            "info": {"license": "", "classifiers": []},
        },
    })
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
    warnings = json.loads(next(l for l in lines if l.startswith("warnings="))[len("warnings="):])
    assert len(warnings) == 1, warnings
    inherited = warnings[0]["inherited"]
    assert inherited["status"] == "found", inherited
    assert inherited["version"] == "1.0.1", inherited
    assert inherited["license"] == "Apache-2.0", inherited


def test_gpl_package_still_fails(tmp_path):
    packages = [{"Name": "some-gpl-pkg", "Version": "2.0.0", "License": "GNU General Public License v3"}]
    dists = {"some-gpl-pkg-2.0.0": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert not matches(regex, "some-gpl-pkg==2.0.0"), regex
    assert warnings == [], warnings
