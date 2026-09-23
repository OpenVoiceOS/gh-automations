"""End to end: the REAL payload the detect step emits, fed to the REAL renderer.

The committed test_license_check_warn_row_names_blocking_value.py hands the
renderer a payload with `values` and no `offending`, so it exercises the
fallback and would pass even if the detect step never set `offending`. This
drives both steps in sequence, so the wiring itself is under test.
"""
import json, os, stat, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_no_metadata import (
    build_site, install_fake_urllib, step_script as detect_step,
    FAKE_PIP_LICENSES_TEMPLATE, FAKE_PYTHON)
from test_license_check_warn_rendering import render

PKG = [{"Name": "shady", "Version": "1.0rc1", "License": "UNKNOWN"}]
DIST = {"shady-1.0rc1": ""}
GPL = "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"


def detect(tmp, releases, exclude=""):
    tmp.mkdir(parents=True, exist_ok=True)
    site = build_site(tmp, DIST)
    resp = {"https://pypi.org/pypi/shady/json": {
        "releases": {v: [{"filename": f"{v}.tar.gz"}] for v in releases}}}
    for v, info in releases.items():
        resp[f"https://pypi.org/pypi/shady/{v}/json"] = {"info": info}
    install_fake_urllib(site, resp)
    b = tmp / "bin"; b.mkdir()
    f = b / "pip-licenses"
    f.write_text(FAKE_PIP_LICENSES_TEMPLATE.format(payload=json.dumps(PKG)))
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    py = b / "python3"; py.write_text(FAKE_PYTHON); py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp / "o"; out.touch()
    env = dict(os.environ, PATH=f"{b}:{os.environ['PATH']}", PYTHONPATH=str(site),
               GITHUB_OUTPUT=str(out), DENY_NO_METADATA_INPUT="", EXCLUDE_LICENSES=exclude,
               FAIL_LICENSES="NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error")
    r = subprocess.run(["bash", "-e", "-c", detect_step()], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=40)
    assert r.returncode == 0, r.stdout + r.stderr
    L = out.read_text().splitlines()
    return json.loads(next(l for l in L if l.startswith("warnings="))[9:])


def test_the_real_payload_carries_offending_and_the_row_shows_only_it(tmp_path):
    w = detect(tmp_path / "a", {"1.0rc1": {"license": "", "classifiers": []},
                                "0.9": {"license": "Apache-2.0", "classifiers": [GPL]}})
    inh = w[0]["inherited"]
    print("\n  offending in payload:", inh.get("offending"))
    assert "offending" in inh, "the detect step did not carry offending: " + json.dumps(inh)
    assert inh["offending"] == [GPL], inh["offending"]

    (tmp_path / "b").mkdir(parents=True, exist_ok=True)
    line = next(l for l in render(tmp_path / "b", w).splitlines() if "shady" in l)
    print("  RENDERED:", line)
    assert "GNU General Public" in line, line
    assert "Apache-2.0" not in line, (
        "the row still names the permissive value as part of the reason: " + line)


def test_the_committed_test_only_exercises_the_fallback(tmp_path):
    """Shown, not asserted about: with no `offending` key the renderer lists
    every value, permissive ones included."""
    payload = [{"name": "shady", "version": "1.0rc1", "forbidden": True,
                "inherited": {"status": "found", "version": "0.9",
                              "license": "Apache-2.0", "values": ["Apache-2.0", GPL]}}]
    line = next(l for l in render(tmp_path, payload).splitlines() if "shady" in l)
    print("\n  FALLBACK RENDERED:", line)


def test_a_safe_found_row_is_unchanged(tmp_path):
    w = detect(tmp_path / "c", {"1.0rc1": {"license": "", "classifiers": []},
                                "0.9": {"license": "Apache-2.0", "classifiers": []}})
    assert w[0]["forbidden"] is False, w
    assert w[0]["inherited"]["offending"] == [], w[0]["inherited"]
    (tmp_path / "d").mkdir(parents=True, exist_ok=True)
    line = next(l for l in render(tmp_path / "d", w).splitlines() if "shady" in l)
    print("  SAFE ROW:", line)
    assert "forbidden" not in line, line
