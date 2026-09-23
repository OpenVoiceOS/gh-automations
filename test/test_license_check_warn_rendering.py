"""The "Format license section for PR comment" step renders one WARN line per
no-metadata package (T-3825 review). Each of the four `inherited["status"]`
shapes gets its own sentence, and a "found" inherited licence that classifies
as forbidden must read differently from a safe "found" one: the review found
that a forbidden inherited licence was silently excluded from the hard
failure, so its WARN row states plainly that it is forbidden and still
fails, rather than reading like the benign case.

Drives the step exactly as shipped, extracted from the YAML."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Format license section for PR comment"


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = next(iter(wf["jobs"].values()))["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def render(tmp_path: Path, no_metadata_warnings: list[dict]) -> str:
    # The step reads /tmp/pip-licenses.json for the full breakdown; absent
    # here, so the breakdown section is empty and only the WARN section
    # under test is exercised.
    section_path = tmp_path / "license-section.md"
    env = dict(os.environ, OUTCOME="success", REPORT="",
               TOTAL_PACKAGES="0",
               NO_METADATA_WARNINGS=json.dumps(no_metadata_warnings))
    # The step body is a `python3 - <<'PYEOF' ... PYEOF` heredoc; run it
    # under bash, same as the runner would, rather than re-deriving the
    # heredoc parsing ourselves.
    script = step_script().replace("/tmp/license-section.md", str(section_path))
    r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, env=env,
                        capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    return section_path.read_text()


def test_found_safe_licence_reads_as_a_plain_inherited_note(tmp_path):
    text = render(tmp_path, [{"name": "tokenizers", "version": "1.0.1",
                               "inherited": {"status": "found", "version": "1.0.2",
                                             "license": "Apache-2.0"},
                               "forbidden": False}])
    assert "inherited from tokenizers 1.0.2: Apache-2.0" in text, text
    assert "forbidden" not in text, text


def test_none_status_reads_as_no_release_carries_metadata(tmp_path):
    text = render(tmp_path, [{"name": "tokenizers", "version": "1.0.1",
                               "inherited": {"status": "none"}, "forbidden": False}])
    assert "no released version carries licence metadata either" in text, text


def test_unavailable_status_reads_as_lookup_unavailable(tmp_path):
    text = render(tmp_path, [{"name": "tokenizers", "version": "1.0.1",
                               "inherited": {"status": "unavailable"}, "forbidden": False}])
    assert "licence lookup unavailable" in text, text


def test_found_forbidden_licence_states_it_is_forbidden_and_still_fails(tmp_path):
    text = render(tmp_path, [{"name": "shady", "version": "1.0rc1",
                               "inherited": {"status": "found", "version": "0.9",
                                             "license": "GPL-3.0-or-later"},
                               "forbidden": True}])
    assert "inherited from shady 0.9: GPL-3.0-or-later" in text, text
    assert "forbidden" in text, text
    assert "still fails" in text, text
