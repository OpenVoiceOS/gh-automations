"""Every shared workflow that runs tests takes the same pre-test hook.

`pre_test_command` exists because a test dependency is not always a pip
package or an apt package: a model download, a generated fixture, a binary
from a .deb. A caller that needs one and does not find the hook forks the
workflow instead, and a fork receives no later fix.

The hook must also expand inside the step that runs pytest. A separate step is
a separate shell process, so an export or a virtual-environment activation in
it is lost before pytest starts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed — skipping workflow YAML tests", allow_module_level=True)


WORKFLOWS = Path(__file__).parent.parent / ".github" / "workflows"

# The shared workflows that install a package and then run its tests.
TEST_RUNNING = {
    "coverage.yml": "coverage",
    "build-tests.yml": "build",
    "tts-intelligibility.yml": "tts_intelligibility",
}


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def _inputs(name: str) -> dict:
    on = _workflow(name)
    on = on.get(True) or on.get("on")
    return on["workflow_call"]["inputs"]


def _steps(name: str, job: str) -> list[dict]:
    jobs = _workflow(name)["jobs"]
    if job not in jobs:
        job = next(iter(jobs))
    return jobs[job]["steps"]


@pytest.mark.parametrize("workflow", sorted(TEST_RUNNING))
def test_the_hook_exists(workflow: str) -> None:
    assert "pre_test_command" in _inputs(workflow)


@pytest.mark.parametrize("workflow", sorted(TEST_RUNNING))
def test_the_hook_has_the_same_shape_everywhere(workflow: str) -> None:
    """A caller reads one input, not three that differ."""
    spec = _inputs(workflow)["pre_test_command"]
    assert spec["type"] == "string"
    assert spec["default"] == ""
    assert "before pytest" in spec["description"]


def _invoking_steps(steps: list[dict]) -> list[dict]:
    """Steps that INVOKE pytest, not steps that install it or read its report."""
    out = []
    for step in steps:
        for line in (step.get("run") or "").splitlines():
            stripped = line.strip()
            if stripped.startswith(("python -m pytest", "pytest ")):
                out.append(step)
                break
    return out


@pytest.mark.parametrize("workflow,job", sorted(TEST_RUNNING.items()))
def test_the_hook_runs_in_the_step_that_runs_pytest(workflow: str, job: str) -> None:
    running = _invoking_steps(_steps(workflow, job))
    assert running, f"{workflow} invokes no pytest"
    for step in running:
        body = step["run"]
        assert "${{ inputs.pre_test_command }}" in body, (
            f"{workflow}: the hook is not in the step that invokes pytest"
        )
        # Against the invoking line, not the first "pytest" in the text: the
        # comment above the hook names pytest too.
        lines = body.splitlines()
        hook_at = next(i for i, l in enumerate(lines)
                       if "${{ inputs.pre_test_command }}" in l and not l.strip().startswith("#"))
        pytest_at = next(i for i, l in enumerate(lines)
                         if l.strip().startswith(("python -m pytest", "pytest ")))
        assert hook_at < pytest_at, f"{workflow}: the hook expands after pytest"


# Shared workflows that invoke pytest and do NOT take the hook yet. A caller
# needing a non-pip, non-apt test dependency in one of these still has to fork
# it. Recorded here so the list is a fact rather than a memory, and so a NEW
# workflow that runs pytest cannot join it unnoticed.
KNOWN_WITHOUT_HOOK = {
    "channel-compat.yml",
    "coverage-pages.yml",   # deprecated, replaced by coverage.yml
    "intent-case-tests.yml",
    "ovoscope.yml",
}

NOT_REUSABLE = {"test.yml", "self-check.yml", "self-check-tts.yml"}


def test_the_set_without_the_hook_is_the_recorded_one() -> None:
    found = set()
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if path.name in TEST_RUNNING or path.name in NOT_REUSABLE:
            continue
        jobs = (_workflow(path.name).get("jobs") or {})
        for job in jobs.values():
            if isinstance(job, dict) and _invoking_steps(job.get("steps") or []):
                found.add(path.name)
    assert found == KNOWN_WITHOUT_HOOK, (
        f"new workflows invoking pytest without the hook: {sorted(found - KNOWN_WITHOUT_HOOK)}; "
        f"no longer present or now covered: {sorted(KNOWN_WITHOUT_HOOK - found)}"
    )
