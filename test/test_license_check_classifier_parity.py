"""The categoriser (NETWORK/STRONG/WEAK/PERMISSIVE lists and classify()) is
pasted into two independent inline steps of license-check.yml — "Detect
combined-license packages safe by component" and "Detect packages with no
licence metadata" — because the steps cannot import from one another. Nothing
enforced the two copies staying equal, and a drift is fail-open: classify()
returns "Other" for anything it does not match, so a pattern added to one
copy but not the other makes that copy call a genuinely forbidden licence
"Other", and a caller that has narrowed FAIL_LICENSES away from "Other"
excludes the package instead of failing on it.

This test extracts both copies from the workflow text and asserts the lists
and the classify() source are identical, so a future edit to one copy that
is not mirrored in the other fails here instead of shipping silently."""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"

STEP_COMBINED = "Detect combined-license packages safe by component"
STEP_NO_METADATA = "Detect packages with no licence metadata"

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


def test_the_two_pasted_categorisers_are_identical():
    combined_src = _step_source(STEP_COMBINED)
    no_metadata_src = _step_source(STEP_NO_METADATA)

    combined_lists = _extract_lists(combined_src)
    no_metadata_lists = _extract_lists(no_metadata_src)

    assert set(combined_lists) == set(LIST_NAMES), combined_lists.keys()
    assert set(no_metadata_lists) == set(LIST_NAMES), no_metadata_lists.keys()
    for name in LIST_NAMES:
        assert combined_lists[name] == no_metadata_lists[name], (
            f"{name} drifted between the two pasted categorisers")

    assert _extract_classify_body(combined_src) == _extract_classify_body(no_metadata_src), (
        "classify() drifted between the two pasted categorisers")
