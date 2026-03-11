"""
Integration tests for gh-automations reusable workflow YAML files.

Validates:
- All .yml files in .github/workflows/ are syntactically valid YAML.
- All reusable workflows have `on.workflow_call` defined.
- Reusable workflows have at least one input defined in `on.workflow_call.inputs`.
- The standard `runner` and `pr_comment` inputs exist where expected.
- All `uses:` references inside workflow job steps are pinned to a tag or SHA
  (not floating @latest, @main, or @master).
- Deprecated workflows are flagged but not broken.

Runs without any external dependencies beyond PyYAML (stdlib-compatible).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

try:
    import yaml
except ImportError:
    pytest.skip("PyYAML not installed — skipping workflow YAML tests", allow_module_level=True)


WORKFLOWS_DIR = Path(__file__).parent.parent / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("*.yml"))

# Workflows known to be deprecated (still valid YAML, just marked for removal)
DEPRECATED_WORKFLOWS = {
    "coverage-pages.yml",
    "python-support.yml",
}

# Workflows that use `workflow_call` (reusable).
# Excluded: test.yml (gh-automations' own CI, not a reusable workflow)
#           notify-matrix.yml (internal-only, not designed for external callers)
NON_REUSABLE_WORKFLOWS = {"test.yml", "notify-matrix.yml"}
REUSABLE_WORKFLOWS = {f.name for f in WORKFLOW_FILES} - NON_REUSABLE_WORKFLOWS


def load_workflow(path: Path) -> dict[str, Any]:
    """Load a workflow YAML file and return its parsed content."""
    with open(path) as f:
        return yaml.safe_load(f)


def get_all_uses_refs(workflow: dict[str, Any]) -> list[str]:
    """Extract all `uses:` values from a workflow (in steps and jobs)."""
    refs = []
    jobs = workflow.get("jobs", {}) or {}
    for job in jobs.values():
        # Job-level `uses:` (workflow_call)
        if "uses" in job:
            refs.append(job["uses"])
        # Step-level `uses:`
        for step in (job.get("steps") or []):
            if "uses" in step:
                refs.append(step["uses"])
    return refs


# ─────────────────────────────────────────────────────────────────────────────
# Parametrize over all workflow files
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("wf_path", WORKFLOW_FILES, ids=lambda p: p.name)
class TestWorkflowYaml:
    """Suite that runs once per workflow file."""

    def test_valid_yaml(self, wf_path: Path) -> None:
        """Every workflow file must be valid YAML."""
        content = load_workflow(wf_path)
        assert isinstance(content, dict), f"{wf_path.name}: top-level is not a mapping"

    def test_has_name(self, wf_path: Path) -> None:
        """Every workflow should have a `name:` field."""
        content = load_workflow(wf_path)
        assert "name" in content, f"{wf_path.name}: missing `name:` field"

    def test_has_on_trigger(self, wf_path: Path) -> None:
        """Every workflow must declare at least one trigger under `on:`."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)  # YAML `on` may parse as bool True
        assert on, f"{wf_path.name}: missing `on:` trigger"

    def test_has_jobs(self, wf_path: Path) -> None:
        """Every workflow must define at least one job."""
        content = load_workflow(wf_path)
        jobs = content.get("jobs", {})
        assert jobs, f"{wf_path.name}: no jobs defined"

    def test_no_floating_uses_refs(self, wf_path: Path) -> None:
        """
        Steps must not use floating action refs (@latest, @main, @master).
        Pinned versions (@v4, @v0.8.0) and SHAs are allowed.
        External gh-automations self-references (@dev) are also allowed.
        """
        content = load_workflow(wf_path)
        refs = get_all_uses_refs(content)
        floating_pattern = re.compile(r"@(latest|main|master)$")
        violations = [r for r in refs if floating_pattern.search(r)]
        assert not violations, (
            f"{wf_path.name}: floating action refs found (use @vX.Y.Z or SHA instead): "
            f"{violations}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests specific to reusable (workflow_call) workflows
# ─────────────────────────────────────────────────────────────────────────────

REUSABLE_WF_PATHS = [p for p in WORKFLOW_FILES if p.name in REUSABLE_WORKFLOWS]


@pytest.mark.parametrize("wf_path", REUSABLE_WF_PATHS, ids=lambda p: p.name)
class TestReusableWorkflow:
    """Suite that runs once per reusable workflow file."""

    def test_has_workflow_call_trigger(self, wf_path: Path) -> None:
        """Reusable workflows must have `on.workflow_call:` defined."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        assert isinstance(on, dict), f"{wf_path.name}: `on:` is not a mapping"
        assert "workflow_call" in on, (
            f"{wf_path.name}: missing `on.workflow_call:` — required for reusable workflows"
        )

    def test_has_inputs(self, wf_path: Path) -> None:
        """Reusable workflows should define at least one input."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {})
        assert inputs, f"{wf_path.name}: `on.workflow_call.inputs` is empty or missing"

    def test_runner_input_exists(self, wf_path: Path) -> None:
        """Reusable workflows should expose a `runner` input for flexibility."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        assert "runner" in inputs, (
            f"{wf_path.name}: missing `runner` input — callers cannot override the runner"
        )

    def test_runner_input_has_default(self, wf_path: Path) -> None:
        """The `runner` input must have a default so callers don't need to specify it."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        runner = inputs.get("runner", {})
        assert "default" in runner, (
            f"{wf_path.name}: `runner` input has no default value"
        )

    def test_all_inputs_have_types(self, wf_path: Path) -> None:
        """Every declared input must have an explicit `type:` field."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        missing_type = [name for name, spec in inputs.items() if not (spec or {}).get("type")]
        assert not missing_type, (
            f"{wf_path.name}: inputs missing `type:` declaration: {missing_type}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests for PR-comment workflows (must expose pr_comment input)
# ─────────────────────────────────────────────────────────────────────────────

PR_COMMENT_WORKFLOWS = {
    "build-tests.yml",
    "coverage.yml",
    "downstream-check.yml",
    "license-check.yml",
    "lint.yml",
    "opm-check.yml",
    "ovoscope.yml",
    "pip-audit.yml",
    "release-preview.yml",
    "repo-health.yml",
    "skill-check.yml",
    "type-check.yml",
    "docs-check.yml",
}
PR_COMMENT_WF_PATHS = [p for p in WORKFLOW_FILES if p.name in PR_COMMENT_WORKFLOWS]


@pytest.mark.parametrize("wf_path", PR_COMMENT_WF_PATHS, ids=lambda p: p.name)
class TestPrCommentWorkflow:
    """Workflows that post PR comments must expose a `pr_comment` boolean input."""

    def test_has_pr_comment_input(self, wf_path: Path) -> None:
        """PR-comment workflows must have a `pr_comment` boolean input."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        assert "pr_comment" in inputs, (
            f"{wf_path.name}: missing `pr_comment` input"
        )

    def test_pr_comment_input_is_boolean(self, wf_path: Path) -> None:
        """The `pr_comment` input must be typed as boolean."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        pr_comment = inputs.get("pr_comment", {})
        assert (pr_comment or {}).get("type") == "boolean", (
            f"{wf_path.name}: `pr_comment` input type must be 'boolean', "
            f"got: {(pr_comment or {}).get('type')!r}"
        )

    def test_pr_comment_default_is_true(self, wf_path: Path) -> None:
        """The `pr_comment` input should default to true."""
        content = load_workflow(wf_path)
        on = content.get("on") or content.get(True)
        wc = on.get("workflow_call", {}) or {}
        inputs = wc.get("inputs", {}) or {}
        pr_comment = inputs.get("pr_comment", {})
        assert (pr_comment or {}).get("default") is True, (
            f"{wf_path.name}: `pr_comment` default should be true"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Deprecated workflow sanity checks
# ─────────────────────────────────────────────────────────────────────────────

DEPRECATED_WF_PATHS = [p for p in WORKFLOW_FILES if p.name in DEPRECATED_WORKFLOWS]


@pytest.mark.parametrize("wf_path", DEPRECATED_WF_PATHS, ids=lambda p: p.name)
class TestDeprecatedWorkflow:
    """Deprecated workflows must still be valid and must carry a deprecation notice."""

    def test_is_valid_yaml(self, wf_path: Path) -> None:
        """Deprecated workflows must still parse as valid YAML."""
        content = load_workflow(wf_path)
        assert isinstance(content, dict)

    def test_has_deprecation_comment(self, wf_path: Path) -> None:
        """Deprecated workflows must carry a DEPRECATED comment near the top."""
        raw = wf_path.read_text()
        assert "DEPRECATED" in raw, (
            f"{wf_path.name}: no DEPRECATED comment found — "
            "deprecated workflows must document their supersession"
        )

    def test_has_eol_date(self, wf_path: Path) -> None:
        """Deprecated workflows must carry a REMOVE AFTER date comment."""
        raw = wf_path.read_text()
        assert "REMOVE AFTER" in raw, (
            f"{wf_path.name}: no 'REMOVE AFTER: YYYY-MM-DD' comment found — "
            "deprecated workflows must have a scheduled removal date"
        )
