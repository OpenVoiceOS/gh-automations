"""ste_lint.py counts SLOP phrases and passes clean prose; run through the
script's own stdin path so the test sees what a workflow sees."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "ste_lint.py"


def lint(text):
    r = subprocess.run([sys.executable, str(SCRIPT), "--mode", "flavored"], input=text,
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def test_slop_phrases_are_counted():
    out = lint("It is important to note that this is a game changer.\n")
    assert out["violations"]["SLOP"] == 2
    assert out["pass"] is False


def test_clean_prose_passes_with_zero_slop():
    out = lint("Run the script. It prints the count.\n")
    assert out["violations"].get("SLOP", 0) == 0
    assert out["pass"] is True


def lint_file(tmp_path, text, name):
    f = tmp_path / name
    f.write_text(text)
    return subprocess.run([sys.executable, str(SCRIPT), "--mode", "flavored", str(f)],
                          capture_output=True, text=True)


def test_file_mode_prints_the_slop_count_and_the_exit_code(tmp_path):
    """A caller workflow reads one line per file. The line names the SLOP
    count, and the exit code says whether a file failed."""
    clean = lint_file(tmp_path, "Run the script. It prints the count.\n", "clean.md")
    assert "SLOP=  0" in clean.stdout
    assert " PASS " in clean.stdout
    assert clean.returncode == 0
    slop = lint_file(tmp_path, "It is important to note that this is a game changer.\n", "slop.md")
    assert "SLOP=  2" in slop.stdout
    assert " FAIL " in slop.stdout
    assert slop.returncode == 1
