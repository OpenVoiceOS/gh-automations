"""Attacks on the "Detect packages with no licence metadata" step (T-3825 review).
Drives the step exactly as shipped, extracted from the YAML, same technique
as test_license_check_no_metadata.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_no_metadata import run_step, matches


def test_attack_pep639_expression_only_is_not_metadata_less(tmp_path):
    """A PEP 639 License-Expression-only package must NOT be excluded."""
    packages = [{"Name": "build", "Version": "1.3.0", "License": "UNKNOWN"}]
    dists = {"build-1.3.0": "License-Expression: MIT\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert not matches(regex, "build==1.3.0"), f"EXCLUDED, regex={regex!r}"
    assert warnings == [], warnings


def test_attack_gpl_expression_only_is_not_metadata_less(tmp_path):
    """A forbidden licence declared ONLY as an expression must still reach pilosus."""
    packages = [{"Name": "some-gpl", "Version": "1.0"}, ]
    dists = {"some-gpl-1.0": "License-Expression: GPL-3.0-or-later\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert not matches(regex, "some-gpl==1.0"), f"EXCLUDED, regex={regex!r}"
    assert warnings == [], warnings


def test_attack_gpl_classifier_only_is_not_metadata_less(tmp_path):
    packages = [{"Name": "clsonly", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"clsonly-1.0": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert not matches(regex, "clsonly==1.0"), f"EXCLUDED, regex={regex!r}"


def test_attack_name_collision_cannot_swallow_a_forbidden_package(tmp_path):
    """The separator class [-_.] must not let one metadata-less name exclude a
    DIFFERENT, forbidden package."""
    packages = [
        {"Name": "foo-bar", "Version": "1.0", "License": "UNKNOWN"},   # metadata-less
        {"Name": "foobar", "Version": "9.9", "License": "GNU General Public License v3"},
        {"Name": "foo-barbaz", "Version": "9.9", "License": "GNU General Public License v3"},
        {"Name": "xfoo-bar", "Version": "9.9", "License": "GNU General Public License v3"},
    ]
    dists = {
        "foo_bar-1.0": "",
        "foobar-9.9": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n",
        "foo_barbaz-9.9": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n",
        "xfoo_bar-9.9": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n",
    }
    regex, warnings = run_step(tmp_path, packages, dists)
    assert matches(regex, "foo-bar==1.0"), regex
    for req in ("foobar==9.9", "foo-barbaz==9.9", "xfoo-bar==9.9"):
        assert not matches(regex, req), f"{req} swallowed by {regex!r}"
    # the separator class is the point: the same project spelled with _ or . must match
    assert matches(regex, "foo_bar==1.0") and matches(regex, "foo.bar==1.0"), regex


def test_attack_regex_metacharacters_in_a_name(tmp_path):
    """A name carrying regex metacharacters must not widen the alternation."""
    packages = [{"Name": "a+b", "Version": "1.0", "License": "UNKNOWN"},
                {"Name": "ab", "Version": "9.9", "License": "GNU General Public License v3"},
                {"Name": "aab", "Version": "9.9", "License": "GNU General Public License v3"}]
    dists = {"a+b-1.0": "",
             "ab-9.9": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n",
             "aab-9.9": "Classifier: License :: OSI Approved :: GNU General Public License v3 (GPLv3)\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    for req in ("ab==9.9", "aab==9.9"):
        assert not matches(regex, req), f"{req} swallowed by {regex!r}"


def test_attack_unknown_license_string_is_treated_as_absent(tmp_path):
    """pip-licenses reports 'UNKNOWN'; the step must not read that as metadata."""
    packages = [{"Name": "nometa", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"nometa-1.0": ""}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert matches(regex, "nometa==1.0"), regex
    assert warnings[0]["inherited"]["status"] == "unavailable", warnings
