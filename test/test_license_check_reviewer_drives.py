"""Drives the "Detect packages with no licence metadata" step against the
PyPI-history inherited-licence lookup added to close the metadata-less
false-green (T-2477 follow-up): a package with no local licence metadata
whose PyPI release history reports a forbidden licence must still fail, a
permissive inherited licence must still be excluded (the control), and a
lookup failure must not change the outcome either way.

Also covers DENY_NO_METADATA (name-normalised, scoped to the named package
only) and the PyPI literal string "UNKNOWN": the lookup must treat it as
absent licence metadata, the same way the step's own local-metadata read
already does, rather than letting it fall through classify() to "Other" and
fail a package for a release that carries no more information than the one
installed."""
import json, os, stat, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_no_metadata import (
    build_site, install_fake_urllib, step_script, matches,
    FAKE_PIP_LICENSES_TEMPLATE, FAKE_PYTHON)


def drive(tmp_path, packages, dists, responses=None, fail=None, deny=None, exclude=None):
    site = build_site(tmp_path, dists)
    if responses is not None:
        install_fake_urllib(site, responses)
    bindir = tmp_path / "bin"; bindir.mkdir()
    f = bindir / "pip-licenses"
    f.write_text(FAKE_PIP_LICENSES_TEMPLATE.format(payload=json.dumps(packages)))
    f.chmod(f.stat().st_mode | stat.S_IEXEC)
    py = bindir / "python3"; py.write_text(FAKE_PYTHON)
    py.chmod(py.stat().st_mode | stat.S_IEXEC)
    out = tmp_path / "gh_out"; out.touch()
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", PYTHONPATH=str(site),
               GITHUB_OUTPUT=str(out),
               FAIL_LICENSES=fail or "NetworkCopyleft,StrongCopyleft,WeakCopyleft,Other,Error",
               EXCLUDE_LICENSES=exclude or "",
               DENY_NO_METADATA_INPUT=deny or "")
    if responses is None:
        env.update(HTTPS_PROXY="http://127.0.0.1:1", https_proxy="http://127.0.0.1:1",
                   NO_PROXY="", no_proxy="")
    r = subprocess.run(["bash", "-e", "-c", step_script()], cwd=tmp_path, env=env,
                       capture_output=True, text=True, timeout=40)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = out.read_text().splitlines()
    regex = next(l for l in lines if l.startswith("regex="))[len("regex="):]
    warns = json.loads(next(l for l in lines if l.startswith("warnings="))[len("warnings="):])
    return regex, warns


SHADY_PKG = [{"Name": "shady", "Version": "1.0rc1", "License": "UNKNOWN"}]
SHADY_DIST = {"shady-1.0rc1": ""}
def shady_pypi(lic):
    return {
        "https://pypi.org/pypi/shady/json": {"releases": {
            "1.0rc1": [{"filename": "a.tar.gz"}], "0.9": [{"filename": "b.tar.gz"}]}},
        "https://pypi.org/pypi/shady/1.0rc1/json": {"info": {"license": "", "classifiers": []}},
        "https://pypi.org/pypi/shady/0.9/json": {"info": {"license": lic, "classifiers": []}},
    }


def shady_pypi_info(license="", license_expression="", classifiers=None):
    return {
        "https://pypi.org/pypi/shady/json": {"releases": {
            "1.0rc1": [{"filename": "a.tar.gz"}], "0.9": [{"filename": "b.tar.gz"}]}},
        "https://pypi.org/pypi/shady/1.0rc1/json": {"info": {"license": "", "classifiers": []}},
        "https://pypi.org/pypi/shady/0.9/json": {"info": {
            "license": license, "license_expression": license_expression,
            "classifiers": classifiers or []}},
    }


def test_the_finding_is_fixed_gpl_inherited_is_not_excluded(tmp_path):
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi("GPL-3.0-or-later"))
    assert warns[0]["inherited"]["license"] == "GPL-3.0-or-later", warns
    assert warns[0]["forbidden"] is True, warns
    assert not matches(regex, "shady==1.0rc1"), f"STILL EXCLUDED: {regex!r}"


def test_permissive_inherited_is_still_excluded(tmp_path):
    """The control: the fix must not turn every inherited lookup into a failure."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi("Apache-2.0"))
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), f"NOT excluded: {regex!r}"


def test_agpl_and_lgpl_inherited_are_not_excluded(tmp_path):
    for i, lic in enumerate(("GNU Affero General Public License v3", "LGPL-2.1", "MPL-2.0")):
        d = tmp_path / f"case{i}"; d.mkdir()
        regex, warns = drive(d, SHADY_PKG, SHADY_DIST, shady_pypi(lic))
        assert warns[0]["forbidden"] is True, (lic, warns)
        assert not matches(regex, "shady==1.0rc1"), (lic, regex)


def test_unavailable_lookup_is_still_excluded(tmp_path):
    """A network failure must not become a failure OR a silent pass change."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST)
    assert warns[0]["inherited"]["status"] == "unavailable", warns
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), regex


def test_deny_input_makes_a_named_package_fail(tmp_path):
    pkgs = [{"Name": "tokenizers", "Version": "1.0.0rc2", "License": "UNKNOWN"}]
    dists = {"tokenizers-1.0.0rc2": ""}
    regex, warns = drive(tmp_path, pkgs, dists, deny="tokenizers")
    assert not matches(regex, "tokenizers==1.0.0rc2"), f"deny ignored: {regex!r}"


def test_deny_input_is_name_normalised(tmp_path):
    pkgs = [{"Name": "foo_bar", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"foo_bar-1.0": ""}
    for i, spelling in enumerate(("Foo-Bar", "foo.bar", " foo_bar ")):
        d = tmp_path / f"s{i}"; d.mkdir()
        regex, _ = drive(d, pkgs, dists, deny=spelling)
        assert not matches(regex, "foo-bar==1.0"), f"deny {spelling!r} ignored: {regex!r}"


def test_deny_does_not_deny_a_different_package(tmp_path):
    pkgs = [{"Name": "keepme", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"keepme-1.0": ""}
    regex, _ = drive(tmp_path, pkgs, dists, deny="tokenizers")
    assert matches(regex, "keepme==1.0"), regex


def test_narrowed_fail_licenses_makes_an_unmatched_licence_pass(tmp_path):
    """Sensitivity of the pasted categoriser: a licence string classify() does
    not match becomes "Other". With a caller that drops "Other" from
    fail_licenses, such a package is excluded and the job is green."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST,
                         shady_pypi("Some-Bespoke-Copyleft-2.0"),
                         fail="StrongCopyleft,NetworkCopyleft")
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), f"NOT excluded: {regex!r}"


def test_pypi_unknown_licence_string_is_not_a_false_hard_failure(tmp_path):
    """CodeRabbit's open thread at license-check.yml:400, driven.

    If PyPI reports the literal string "UNKNOWN" for an older release, the
    lookup must treat it as absent licence metadata, the same way the step's
    own read of the installed metadata already does 14 lines above (T-3831
    review at 09dfa9e). Before the fix, the lookup counted "UNKNOWN" as
    found, classify() could not match it so it fell to "Other", which is in
    the default fail_licenses, and the package was wrongly kept as a hard
    failure for a release that carries no more licence information than the
    one installed.
    """
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi("UNKNOWN"))
    assert warns[0]["inherited"]["status"] == "none", warns
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), f"STILL A FALSE HARD FAILURE: {regex!r}"


def test_pypi_none_and_empty_and_lowercase_unknown_are_all_treated_as_absent(tmp_path):
    for i, lic in enumerate(("", "unknown", "UNKNOWN")):
        d = tmp_path / f"u{i}"; d.mkdir()
        regex, warns = drive(d, SHADY_PKG, SHADY_DIST, shady_pypi(lic))
        assert warns[0]["inherited"]["status"] == "none", (lic, warns)
        assert warns[0]["forbidden"] is False, (lic, warns)
        assert matches(regex, "shady==1.0rc1"), (lic, regex)


def test_a_later_forbidden_classifier_is_not_shadowed_by_an_earlier_permissive_one(tmp_path):
    """CodeRabbit's finding at _released_licence: the lookup used to keep only
    the FIRST "License :: " classifier. A permissive first classifier with a
    GPL second classifier must still classify as forbidden."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi_info(
        classifiers=[
            "License :: OSI Approved :: MIT License",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        ]))
    assert warns[0]["forbidden"] is True, warns
    assert not matches(regex, "shady==1.0rc1"), f"STILL EXCLUDED: {regex!r}"


def test_exclude_licenses_applies_to_the_inherited_licence(tmp_path):
    """CodeRabbit's finding: the inherited-licence forbidden check ignored the
    caller's exclude_licenses input. A caller who excludes MPL-2.0 must have
    the package excluded and warned, even though its inherited licence
    classifies as WeakCopyleft (a fail category by default)."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST,
                         shady_pypi("MPL-2.0"), exclude=r"^MPL-2\.0$")
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), f"NOT excluded: {regex!r}"


def test_exclude_licenses_does_not_swallow_a_classifier_form_mpl_by_default(tmp_path):
    """The companion control: without a caller exclude for MPL, the
    classifier-form spelling of MPL is still forbidden under the default
    policy."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi_info(
        classifiers=["License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"]))
    assert warns[0]["forbidden"] is True, warns
    assert not matches(regex, "shady==1.0rc1"), f"STILL EXCLUDED: {regex!r}"


def test_exclude_licenses_matches_the_classifier_form_of_an_inherited_licence(tmp_path):
    """CodeRabbit's finding: exclude_licenses matched the raw inherited value
    only, so a caller excluding the licence-field spelling ("^Mozilla Public
    License.*") never matched the classifier spelling PyPI actually reports
    ("License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"). The
    package must be excluded and warned, same as the licence-field form."""
    regex, warns = drive(tmp_path, SHADY_PKG, SHADY_DIST, shady_pypi_info(
        classifiers=["License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"]),
        exclude=r"^Mozilla Public License.*")
    assert warns[0]["forbidden"] is False, warns
    assert matches(regex, "shady==1.0rc1"), f"NOT excluded: {regex!r}"
