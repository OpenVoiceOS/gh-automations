"""GitHub Actions rejects a workflow whose step `if:` reads `secrets`: the run fails with 0 jobs."""
import pathlib
import re

import pytest
import yaml

WORKFLOWS = sorted(pathlib.Path(__file__).resolve().parents[1].joinpath(".github", "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_step_condition_reads_secrets(path):
    doc = yaml.safe_load(path.read_text())
    bad = [
        f"{job}/{step.get('name', i)}"
        for job, body in (doc.get("jobs") or {}).items()
        for i, step in enumerate(body.get("steps") or [])
        if re.search(r"\bsecrets\.", str(step.get("if", "")))
    ]
    assert bad == []
