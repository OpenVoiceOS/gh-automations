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
