"""license-check.yml reads a PEP 639 `License-Expression` from the installed
metadata (T-2467, T-3102). The checker (pilosus) does not parse the field and
reports "Error" for a package that declares its licence only there. The
"Detect combined-license packages safe by component" step excludes such a
package by name when every SPDX identifier in the expression is permissive.

The step is run under bash against a fake site-packages built from wheel
METADATA samples. The samples under test/pep639-samples/ are copied from the
real wheels (setuptools 79.0.1 and 80.9.0, packaging 26.3, urllib3 2.8.0);
the copyleft and LicenseRef samples are written here."""

from __future__ import annotations

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
SAMPLES = ROOT / "test/pep639-samples"
STEP = "Detect combined-license packages safe by component"

# pip-licenses is not on the test box; the step tolerates an empty report
FAKE_PIP_LICENSES = "#!/usr/bin/env bash\necho '[]'\n"

# The step reads importlib.metadata.distributions(), which walks the whole
# sys.path. A python3 without site-packages (-S) sees only the fake site on
# PYTHONPATH, so the real environment of the test box never leaks in.
FAKE_PYTHON = f"#!/usr/bin/env bash\nexec {sys.executable} -S \"$@\"\n"

SYNTHETIC = {
    "mutagen-1.48.1": "License-Expression: GPL-2.0-or-later\n",
    "pycountry-26.2.16": "License-Expression: LGPL-2.1-only\n",
    "orjson-3.11.0": "License-Expression: MPL-2.0 AND (Apache-2.0 OR MIT)\n",
    "vendored-thing-1.0": "License-Expression: MIT AND LicenseRef-Proprietary\n",
    "huey-3.3.4": "",
    "unidecode-1.4.0": "Classifier: License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)\n",
    # canonical-name test: the regex must match the resolved requirement line
    "pyproject_hooks-1.2.0": "License-Expression: MIT\n",
}


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def build_site(tmp_path: Path, setuptools: str = "80.9.0") -> Path:
    # one setuptools per site, as in a real environment; the exclude is by name
    site = tmp_path / "site-packages"
    site.mkdir()
    for sample in sorted(SAMPLES.glob("*.METADATA")):
        if sample.stem.startswith("setuptools-") and sample.stem != f"setuptools-{setuptools}":
            continue
        info = site / f"{sample.stem}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(sample.read_text())
    for dist, extra in SYNTHETIC.items():
        name, version = dist.rsplit("-", 1)
        info = site / f"{dist}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(
            f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{extra}")
    return site


def run_step(tmp_path: Path, fail: str = "NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error",
             exclude_licenses: str = "", setuptools: str = "80.9.0") -> str:
    site = build_site(tmp_path, setuptools)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "pip-licenses"
    fake.write_text(FAKE_PIP_LICENSES)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    py = bindir / "python3"
    py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "github_output"
    out.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", PYTHONPATH=str(site),
               GITHUB_OUTPUT=str(out), FAIL_LICENSES=fail, EXCLUDE_LICENSES=exclude_licenses)
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    line = next(l for l in out.read_text().splitlines() if l.startswith("regex="))
    return line[len("regex="):]


def matches(regex: str, requirement: str) -> bool:
    # pilosus applies the exclude with a full-string match against "name==version"
    return any(re.fullmatch(alt, requirement) for alt in regex.split("|"))


@pytest.fixture(scope="module")
def regex(tmp_path_factory) -> str:
    return run_step(tmp_path_factory.mktemp("pep639"))


@pytest.mark.parametrize("requirement", [
    "setuptools==80.9.0",          # License-Expression: MIT (80.x and later)
    "urllib3==2.8.0",              # MIT
    "packaging==26.3",             # Apache-2.0 OR BSD-2-Clause: both permissive
    "pyproject-hooks==1.2.0",      # name normalised from pyproject_hooks
    "pyproject_hooks==1.2.0",
])
def test_all_permissive_expression_is_excluded(regex, requirement):
    assert matches(regex, requirement), regex


@pytest.mark.parametrize("requirement", [
    "mutagen==1.48.1",             # GPL-2.0-or-later
    "pycountry==26.2.16",          # LGPL-2.1-only
    "orjson==3.11.0",              # MPL-2.0 AND (...): no election made here
    "vendored-thing==1.0",         # LicenseRef is not an SPDX identifier
    "huey==3.3.4",                 # no licence metadata
    "unidecode==1.4.0",            # classifier only, and GPL
    "setuptools-scm==8.0.0",       # a longer name sharing the prefix
])
def test_other_expressions_stay_with_the_checker(regex, requirement):
    assert not matches(regex, requirement), regex


def test_setuptools_79_has_no_expression_and_is_left_to_the_whitelist(tmp_path):
    # 79.x ships only License-File; 80.x added License-Expression: MIT. The
    # central whitelist in the "Build exclude regex" step carries 79.x.
    regex = run_step(tmp_path, setuptools="79.0.1")
    assert not matches(regex, "setuptools==79.0.1"), regex
    assert matches(regex, "urllib3==2.8.0"), regex


def test_a_permissive_package_is_listed_once(regex):
    names = re.findall(r"\^([a-z0-9\[\]_.-]+)\(", regex)
    assert len(names) == len(set(names)), regex
