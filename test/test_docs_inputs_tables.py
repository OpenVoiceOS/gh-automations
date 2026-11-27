import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_generated_inputs_tables_match_workflows():
    result = subprocess.run([sys.executable, str(ROOT / "docs/gen_inputs.py"), "--check"])
    assert result.returncode == 0, "run python docs/gen_inputs.py"
