"""A caller's `exclude_packages` that starts with a global inline flag.

HiveMind-core passes `(?i)^(hivemind|...).*`. Joined as `(...)|((?i)^...)`,
Python rejects it: a global flag must stand at the start of the expression.
The step turns the leading flags into a scoped group `(?i:...)`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/license-check.yml"
STEP = "Build exclude regex"


def build(tmp_path: Path, caller: str) -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["license_tests"]["steps"]
    run = next(s for s in steps if s.get("name") == STEP)["run"]
    script = run.split("<<'PYEOF'", 1)[1].split("\n", 1)[1].split("\nPYEOF", 1)[0]
    env = {**os.environ, "CALLER_EXCLUDE": caller,
           "COMBINED_EXCLUDE": "", "NO_METADATA_EXCLUDE": ""}
    out = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                         capture_output=True, text=True, check=True).stdout
    return next(l for l in out.splitlines() if l.startswith("regex="))[6:]


def test_leading_global_flag_compiles_and_keeps_its_meaning(tmp_path):
    merged = re.compile(build(tmp_path, "(?i)^(hivemind|tqdm).*"))
    assert merged.match("HiveMind-core==1.0")
    assert merged.match("TQDM")
    assert not merged.match("requests==2.31.0")


def test_plain_caller_pattern_is_unchanged(tmp_path):
    merged = build(tmp_path, "^foo.*")
    assert "|(^foo.*)" in merged
    assert re.match(merged, "foo==1.0")
    assert not re.match(merged, "Foo==1.0")
