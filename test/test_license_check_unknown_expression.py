"""T-3963, the second finding: "UNKNOWN" is not licence metadata.

The no-metadata step skips a package when it finds any licence metadata of its
own: a License field, a License-Expression, or a `License ::` classifier. The
License field already dropped the placeholder "UNKNOWN", and the expression did
not, so a distribution whose only metadata was `License-Expression: UNKNOWN`
counted as having a licence and never reached the scan.

Drives the step exactly as shipped, through the harness of
test_license_check_no_metadata.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_no_metadata import run_step


def test_an_unknown_expression_is_no_licence_metadata(tmp_path) -> None:
    """The package must reach the no-metadata scan, not be skipped."""
    packages = [{"Name": "placeholder-pkg", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"placeholder-pkg-1.0": "License-Expression: UNKNOWN\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    names = [w["name"] for w in warnings]
    assert "placeholder-pkg" in names, (
        "an UNKNOWN License-Expression counted as licence metadata, so the "
        f"package was skipped by the no-metadata scan: {warnings}")


def test_a_real_expression_still_skips_the_scan(tmp_path) -> None:
    """The control: a real expression is metadata and must still be left alone."""
    packages = [{"Name": "real-pkg", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"real-pkg-1.0": "License-Expression: MIT\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    names = [w["name"] for w in warnings]
    assert "real-pkg" not in names, (
        f"a real License-Expression must leave the package to the other "
        f"checks, not to the no-metadata scan: {warnings}")


def test_the_placeholder_is_matched_whatever_its_case(tmp_path) -> None:
    packages = [{"Name": "lower-pkg", "Version": "1.0", "License": "UNKNOWN"}]
    dists = {"lower-pkg-1.0": "License-Expression: unknown\n"}
    regex, warnings = run_step(tmp_path, packages, dists)
    assert "lower-pkg" in [w["name"] for w in warnings]
