"""check_downstream.py must not report "No dependents found" when pipdeptree
did not run (T-2899). The workflow never installed pipdeptree, `python -m
pipdeptree` failed on every run, and the script turned an empty stdout into
a clean report."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_downstream  # noqa: E402

yaml = pytest.importorskip("yaml")


class R:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_a_failed_pipdeptree_raises_not_reports(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R(1, "", "No module named pipdeptree"))
    with pytest.raises(check_downstream.DownstreamError, match="exited 1.*No module named pipdeptree"):
        check_downstream.get_downstream("ovos-plugin-manager")


def test_a_clean_empty_tree_still_reads_no_dependents(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R(0, "", ""))
    assert check_downstream.get_downstream("x") == "No dependents found for x\n"


def test_a_real_tree_is_sorted(monkeypatch):
    tree = "ovos-plugin-manager==2.0\n  ovos-workshop==4.0\n  ovos-audio==1.0\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R(0, tree, ""))
    out = check_downstream.get_downstream("ovos-plugin-manager")
    assert out.splitlines()[1:] == ["  ovos-audio==1.0", "  ovos-workshop==4.0"]


def test_main_exits_2_with_an_error_annotation_when_pipdeptree_is_absent(tmp_path):
    """Run against the real interpreter of this test, where pipdeptree is
    not installed unless someone put it there."""
    try:
        import pipdeptree  # noqa: F401
        pytest.skip("pipdeptree is installed here")
    except ImportError:
        pass
    out = tmp_path / "r.txt"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/check_downstream.py"), "--package", "x", "--output", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "::error title=downstream-check did not run::" in r.stdout
    assert not out.exists()


def test_workflow_installs_pipdeptree():
    wf = yaml.safe_load((ROOT / ".github/workflows/downstream-check.yml").read_text())
    step = next(s for s in next(iter(wf["jobs"].values()))["steps"] if s.get("name") == "Install OVOS ecosystem and pipdeptree")
    assert "uv pip install pipdeptree" in step["run"]
