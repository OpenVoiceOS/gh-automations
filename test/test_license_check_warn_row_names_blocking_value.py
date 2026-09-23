"""What a maintainer actually reads when a later value is the blocking one."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_license_check_warn_rendering import render


def test_the_warn_row_shows_the_blocking_value(tmp_path):
    payload = [{
        "name": "shady", "version": "1.0rc1", "forbidden": True,
        "inherited": {
            "status": "found", "version": "0.9",
            "license": "Apache-2.0",
            "values": ["Apache-2.0",
                       "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"],
        },
    }]
    out = render(tmp_path, payload)
    line = next(l for l in out.splitlines() if "shady" in l)
    print("\nRENDERED:", line)
    assert "GNU General Public" in line, (
        "the WARN row names Apache-2.0 as forbidden and never shows the GPL "
        "classifier that actually blocks it: " + line)
