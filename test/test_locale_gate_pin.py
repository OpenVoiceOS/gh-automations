"""The policy job runs scripts/locale_gate.py at a pinned content hash; a
change to the script changes the pin here on purpose, never by drift."""

import hashlib
from pathlib import Path

PINNED = "69a6bd0270ad49a2594cf34e792821ec9157630c9e5df5fc13d881585ee346bd"


def test_locale_gate_is_the_pinned_version():
    path = Path(__file__).parent.parent / "scripts" / "locale_gate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINNED
