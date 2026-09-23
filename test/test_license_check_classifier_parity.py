"""The categoriser (NETWORK/STRONG/WEAK/PERMISSIVE lists and classify()) is
pasted into three independent inline steps of license-check.yml — "Detect
combined-license packages safe by component", "Detect packages with no
licence metadata" and "Re-check Error rows from installed metadata" —
because the steps cannot import from one another. Nothing enforced the
copies staying equal, and a drift is fail-open: classify() returns "Other"
for anything it does not match, so a pattern added to one copy but not the
others makes that copy call a genuinely forbidden licence "Other", and a
caller that has narrowed FAIL_LICENSES away from "Other" excludes the
package instead of failing on it.

This test extracts all three copies from the workflow text and asserts the
lists and the classify() source are identical, so a future edit to one copy
that is not mirrored in the others fails here instead of shipping silently."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"

STEP_COMBINED = "Detect combined-license packages safe by component"
STEP_NO_METADATA = "Detect packages with no licence metadata"
STEP_RECHECK = "Re-check Error rows from installed metadata"

LIST_NAMES = ("NETWORK", "STRONG", "WEAK", "PERMISSIVE")


def _step_source(step_name: str) -> str:
    import pytest
    yaml = pytest.importorskip("yaml")
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == step_name)["run"]
    assert "${{" not in script, script
    return script


def _extract_lists(source: str) -> dict[str, list]:
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in LIST_NAMES:
                found[target.id] = ast.literal_eval(node.value)
    return found


def _extract_classify_body(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "classify":
            # Compare the dedented, unparsed body, so differing surrounding
            # indentation between the two pasted copies does not matter.
            return "\n".join(ast.unparse(stmt) for stmt in node.body)
    raise AssertionError("classify() not found in step source")


def _extract_copyleft_expansion(source: str) -> str:
    # Each copy parses FAIL_LICENSES into `fail_categories` and, when the
    # caller passed the umbrella value "Copyleft", expands it to the three
    # concrete categories: `if "Copyleft" in fail_categories:
    # fail_categories |= {...}`. Pasted a third time alongside the lists and
    # classify() above (CONFIRMED 4, PR #151 review): a copy that drops one
    # category from the expanded set is fail-open the same way a drifted
    # PERMISSIVE/WEAK list is, and nothing enforced it staying equal either.
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Constant)
                and test.left.value == "Copyleft"):
            return "\n".join(ast.unparse(stmt) for stmt in node.body)
    raise AssertionError("Copyleft fail_categories expansion not found in step source")


def test_the_pasted_categorisers_are_identical():
    sources = {
        STEP_COMBINED: _step_source(STEP_COMBINED),
        STEP_NO_METADATA: _step_source(STEP_NO_METADATA),
        STEP_RECHECK: _step_source(STEP_RECHECK),
    }

    lists = {step: _extract_lists(src) for step, src in sources.items()}
    for step, found in lists.items():
        assert set(found) == set(LIST_NAMES), (step, found.keys())

    baseline_step, baseline = STEP_COMBINED, lists[STEP_COMBINED]
    for step, found in lists.items():
        for name in LIST_NAMES:
            assert found[name] == baseline[name], (
                f"{name} drifted between {baseline_step!r} and {step!r}")

    classify_bodies = {step: _extract_classify_body(src) for step, src in sources.items()}
    baseline_body = classify_bodies[STEP_COMBINED]
    for step, body in classify_bodies.items():
        assert body == baseline_body, (
            f"classify() drifted between {baseline_step!r} and {step!r}")

    expansions = {step: _extract_copyleft_expansion(src) for step, src in sources.items()}
    baseline_expansion = expansions[STEP_COMBINED]
    for step, expansion in expansions.items():
        assert expansion == baseline_expansion, (
            f"the Copyleft fail_categories expansion drifted between "
            f"{baseline_step!r} and {step!r}")
