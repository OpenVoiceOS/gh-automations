"""The central whitelist's `torchao` entry.

`torchao` 0.18.0 declares no `License`, no `License-Expression` and no
licence classifier, only `License-File: LICENSE`, so the checker reports
category "Other" and the row fails. That was seen on
`ovos-stt-plugin-nemo#39`. Its `LICENSE` in `pytorch/ao` is BSD-3-Clause.
Miro ruled it into the central exclude on decision
`torchao-no-metadata-read-licence`.

The anchoring is what these cases are really about. The checker matches
against the resolved `name==version` requirement, so the entry has to carry
the version suffix, and it has to stop at a package whose name merely starts
with the same letters: `torchaudio` sits in the same dependency tree.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Build exclude regex"


@pytest.fixture(scope="module")
def central() -> str:
    """The central whitelist alternation, read out of the step's source."""
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["license_tests"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    m = re.search(r"central = \((.*?)\)\n", script, re.S)
    assert m, "the central whitelist assignment moved"
    return "".join(re.findall(r'r"([^"]+)"', m.group(1)))


def matches(pattern: str, requirement: str) -> bool:
    return bool(re.match(pattern, requirement))


def test_torchao_is_in_the_central_whitelist(central):
    assert "torchao" in central, central


@pytest.mark.parametrize("requirement", [
    "torchao",
    "torchao==0.18.0",
    "torchao==0.18.0a1",
    "torchao @ file:///tmp/torchao-0.18.0-py3-none-any.whl",
    "torchao; python_version >= '3.10'",
])
def test_the_resolved_requirement_is_excluded(central, requirement):
    assert matches(central, requirement), central


@pytest.mark.parametrize("requirement", [
    "torchaudio==2.1.0",     # same prefix, different package, same tree
    "torchao-extra==1.0",    # a longer distribution name
    "mytorchao==1.0",        # the anchor must hold at the start
    "torch==2.1.0",
])
def test_a_neighbour_is_not_excluded(central, requirement):
    assert not matches(central, requirement), central


def test_an_existing_entry_still_matches(central):
    """A control: if the alternation were broken the cases above could pass
    for the wrong reason."""
    assert matches(central, "setuptools==79.0.1"), central
    assert matches(central, "tqdm==4.66.0"), central


def test_the_documentation_carries_the_same_entry():
    """`docs/license-whitelist.md` calls itself the human-auditable source of
    truth and says to change both together."""
    doc = (ROOT / "docs/license-whitelist.md").read_text()
    assert "| `torchao` |" in doc, "no table row for torchao"
    assert "BSD-3-Clause" in doc.split("| `torchao` |")[1].split("\n")[0], \
        "the torchao row does not name the licence"
