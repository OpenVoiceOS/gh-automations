"""lint.yml pins the ruff release the fleet lints with, and the rule set it
lints with (OPE-721, T-5021).

ruff's own default rule set is not a plain function of its release: a project
with no [tool.ruff] table in pyproject.toml gets one default regardless of
ruff version, and a project with any [tool.ruff] table, even an empty one,
gets a much wider one. A 222-repository remeasurement found 221 of them
report identical findings under ruff 0.15.22 and ruff 0.16.10, and the one
exception is the one repository that carries a [tool.ruff] table — not a
ruff-version effect. So the rule set the fleet lints with is pinned as an
explicit --select in ruff_args, not left to whichever default a ruff release
or a caller's pyproject.toml happens to produce. It is the same failure
actionlint already has a pin for (test_lint_actionlint.py, T-3335): the pin on
RUFF keeps the ruff build reproducible, and the pin on the --select list
keeps the rule set reproducible, and Renovate is the thing that moves the
version pin.

Unlike actionlint, ruff is not installed by test.yml, because no test here runs
ruff. So there is no second place to drift, and no equality test for the
version pin.
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

# The reviewed baseline (OPE-721): today's default for a repository with no
# [tool.ruff] table, written out so a change to it is a reviewed diff to this
# list, not a side effect of a ruff upgrade or a caller's pyproject.toml.
REVIEWED_SELECT = {
    "E101", "E401", "E402", "E501", "E701", "E702", "E703", "E711", "E712",
    "E713", "E714", "E721", "E722", "E731", "E741", "E742", "E743", "E902",
    "F401", "F402", "F403", "F404", "F405", "F406", "F407", "F501", "F502",
    "F503", "F504", "F505", "F506", "F507", "F508", "F509", "F521", "F522",
    "F523", "F524", "F525", "F541", "F601", "F602", "F621", "F622", "F631",
    "F632", "F633", "F634", "F701", "F702", "F704", "F706", "F707", "F722",
    "F811", "F821", "F822", "F823", "F841", "F842", "F901", "I001", "I002",
    "UP001", "UP003", "UP004", "UP005", "UP006", "UP007", "UP008", "UP009",
    "UP010", "UP011", "UP012", "UP013", "UP014", "UP015", "UP017", "UP018",
    "UP019", "UP020", "UP021", "UP022", "UP023", "UP024", "UP025", "UP026",
    "UP028", "UP029", "UP030", "UP031", "UP032", "UP033", "UP034", "UP035",
    "UP036", "UP037", "UP039", "UP040", "UP041", "UP042", "UP043", "UP044",
    "UP045", "UP046", "UP047", "UP049", "UP050",
}


def ruff_args_default():
    wf = yaml.safe_load(WORKFLOW.read_text())
    on = wf[True]  # yaml reads the `on` key as True
    return on["workflow_call"]["inputs"]["ruff_args"]["default"]


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


def test_ruff_args_selects_the_reviewed_rule_set_explicitly():
    args = ruff_args_default()
    assert "--select" in args, (
        "ruff_args has no --select: the rule set is whatever ruff's own "
        "default resolves to for each caller's pyproject.toml, which is not "
        "the same set for a caller with a [tool.ruff] table as for one "
        "without (OPE-721)."
    )
    selected = args.split("--select", 1)[1].strip().split()[0]
    codes = set(selected.split(","))
    assert codes == REVIEWED_SELECT, (
        "ruff_args --select no longer matches the reviewed baseline. "
        f"added: {sorted(codes - REVIEWED_SELECT)}, "
        f"removed: {sorted(REVIEWED_SELECT - codes)}. "
        "Widening or narrowing the fleet's rule set is a reviewed change: "
        "update REVIEWED_SELECT here together with ruff_args in lint.yml."
    )
