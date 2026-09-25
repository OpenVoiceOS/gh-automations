"""T-3963: an unrecognised licence value must not condemn a row on its own.

`classify()` answers "Other" for anything it does not match, and "Other" is in
the default FAIL_LICENSES. So a package whose licence field reads
`Apache-2.0 AND <something the lists do not know>` used to count as offending
on the unrecognised half, and no exclude could clear it, because an exclude is
written against real licence names. `torchao 0.18.0` is the case that was
found, in ovos-stt-plugin-nemo#39.

The rule is now: fail on a NAMED forbidden category, and keep "Other" as a
judgement on the row as a whole. Both halves are tested here, for each of the
three pasted copies, and the second half is what stops the fix being
fail-open.

The second test covers the other finding of the same re-review: "UNKNOWN" is
dropped from the License field and was not dropped from License-Expression.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"

STEPS = (
    "Detect combined-license packages safe by component",
    "Detect packages with no licence metadata",
    "Re-check Error rows from installed metadata",
)

WANTED_FUNCS = ("classify", "row_offending")
WANTED_LISTS = ("NETWORK", "STRONG", "WEAK", "PERMISSIVE")


def _step_source(step_name: str) -> str:
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    return next(s for s in steps if s.get("name") == step_name)["run"]


def _namespace(step_name: str, fail_licenses: str) -> dict:
    """classify() and row_offending() from one step, with nothing else run.

    The step itself reads files and the network, so only the definitions are
    taken and evaluated, the way the parity test takes them.
    """
    tree = ast.parse(_step_source(step_name))
    picked: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in WANTED_FUNCS:
            picked.append(node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in WANTED_LISTS:
                picked.append(node)
    names = {n.name for n in picked if isinstance(n, ast.FunctionDef)}
    assert names == set(WANTED_FUNCS), (step_name, names)

    import re as _re
    fail_categories = {c.strip() for c in fail_licenses.split(",") if c.strip()}
    if "Copyleft" in fail_categories:
        fail_categories |= {"StrongCopyleft", "NetworkCopyleft", "WeakCopyleft"}
    ns = {"re": _re, "fail_categories": fail_categories,
          "named_fail": fail_categories - {"Other", "Error"}}
    exec(compile(ast.Module(body=picked, type_ignores=[]), "<step>", "exec"), ns)
    return ns


DEFAULT_FAIL = "StrongCopyleft,NetworkCopyleft,WeakCopyleft,Other,Error"
UNRECOGNISED = "Weird Custom Terms 1.0"


@pytest.mark.parametrize("step", STEPS)
def test_a_permissive_row_survives_one_unrecognised_value(step) -> None:
    """The defect: Apache-2.0 beside an unknown string used to fail."""
    ns = _namespace(step, DEFAULT_FAIL)
    assert ns["classify"](UNRECOGNISED) == "Other"
    assert ns["row_offending"](["Apache-2.0", UNRECOGNISED]) == []


@pytest.mark.parametrize("step", STEPS)
def test_a_row_of_nothing_but_unrecognised_values_still_fails(step) -> None:
    """The other half: unknown terms are still unknown risk.

    Without this the fix would be fail-open, and a package whose only licence
    value is unparseable would pass.
    """
    ns = _namespace(step, DEFAULT_FAIL)
    assert ns["row_offending"]([UNRECOGNISED]) == [UNRECOGNISED]
    assert ns["row_offending"]([UNRECOGNISED, "Another Odd Licence"]) == [
        UNRECOGNISED, "Another Odd Licence"]


@pytest.mark.parametrize("step", STEPS)
def test_a_named_forbidden_value_still_fails_beside_a_permissive_one(step) -> None:
    ns = _namespace(step, DEFAULT_FAIL)
    assert ns["row_offending"](["Apache-2.0", "GPL-3.0"]) == ["GPL-3.0"]
    assert ns["row_offending"](["MIT", "GNU Affero General Public License v3"]) == [
        "GNU Affero General Public License v3"]


@pytest.mark.parametrize("step", STEPS)
def test_a_named_value_wins_over_an_unrecognised_one(step) -> None:
    """The report names what is actually forbidden, not the unknown string."""
    ns = _namespace(step, DEFAULT_FAIL)
    assert ns["row_offending"](["GPL-3.0", UNRECOGNISED]) == ["GPL-3.0"]


@pytest.mark.parametrize("step", STEPS)
def test_a_caller_that_drops_Other_keeps_an_unrecognised_row(step) -> None:
    ns = _namespace(step, "StrongCopyleft,NetworkCopyleft,WeakCopyleft,Error")
    assert ns["row_offending"]([UNRECOGNISED]) == []
    assert ns["row_offending"](["GPL-3.0"]) == ["GPL-3.0"]


@pytest.mark.parametrize("step", STEPS)
def test_an_empty_row_is_not_a_finding(step) -> None:
    ns = _namespace(step, DEFAULT_FAIL)
    assert ns["row_offending"]([]) == []
    assert ns["row_offending"](["", None]) == []


@pytest.mark.parametrize("step", STEPS)
def test_the_three_copies_agree_value_by_value(step) -> None:
    """Behaviour parity, beside the text parity the other test asserts."""
    baseline = _namespace(STEPS[0], DEFAULT_FAIL)
    ns = _namespace(step, DEFAULT_FAIL)
    for values in (["Apache-2.0", UNRECOGNISED], [UNRECOGNISED],
                   ["Apache-2.0", "GPL-3.0"], ["MPL-2.0"], []):
        assert ns["row_offending"](values) == baseline["row_offending"](values), values
