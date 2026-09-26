"""lint.yml pins the ruff release the fleet lints with (T-5021).

ruff chooses its rules by default, so the release IS the rule set. Unpinned,
ruff 0.16.0 widened that default: measured over 420 callers at one moment, the
findings went from 10409 to 75711, 108 repositories went from none to some, and
7 LOST a finding, none of them having changed a line. ruff does not fail this
job (continue-on-error, and only actionlint fails it), so the pin protects a
report people can read rather than a red. It is the same failure actionlint
already has a pin for (test_lint_actionlint.py, T-3335), so these tests are the
same shape: the pin is exact, and Renovate is the thing that moves it.

Unlike actionlint, ruff is not installed by test.yml, because no test here runs
ruff. So there is no second place to drift, and no equality test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/lint.yml"

RUFF_PIN = re.compile(r"ruff==([0-9][0-9.]*)")


def lint_env():
    return yaml.safe_load(WORKFLOW.read_text())["env"]


def test_the_ruff_pin_is_exact():
    pin = lint_env()["RUFF"]
    m = RUFF_PIN.fullmatch(pin)
    assert m, f"lint.yml env RUFF is not an exact pin: {pin!r}"
    # An exact release, not a range or a floor: three dotted numbers.
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", m.group(1)), m.group(1)


def test_the_install_step_uses_the_pin_and_not_bare_ruff():
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["lint"]["steps"]
    step = next(s for s in steps if s.get("name") == "Install ruff")
    run = step["run"]
    assert "$RUFF" in run, run
    # `uv pip install ruff` is the defect this test exists to prevent.
    assert not re.search(r"install\s+ruff(\s|$)", run), run


def test_renovate_moves_the_ruff_pin():
    cfg = json.loads((ROOT / "renovate.json").read_text())
    managers = [c for c in cfg.get("customManagers", []) if c.get("depNameTemplate") == "ruff"]
    assert managers, "renovate.json has no custom manager for ruff"
    # Renovate writes RE2 named groups, (?<name>); Python spells them (?P<name>)
    pattern = re.compile(managers[0]["matchStrings"][0].replace("(?<", "(?P<"))
    assert pattern.search(lint_env()["RUFF"]), \
        "the Renovate matchString does not match lint.yml's pin"


def test_the_pin_holds_the_pre_0_16_default_rule_set():
    """0.16.0 is the release that widened the default selection, so the pin
    must stay below it until that change is priced and adopted on purpose."""
    version = RUFF_PIN.fullmatch(lint_env()["RUFF"]).group(1)
    major, minor, _ = (int(x) for x in version.split("."))
    assert (major, minor) < (0, 16), (
        f"ruff is pinned to {version}, which carries the widened 0.16 default "
        "rule set. Adopting it is a fleet-wide decision: it is 65000 more "
        "findings across 420 measured callers. Record it, then move this test."
    )
