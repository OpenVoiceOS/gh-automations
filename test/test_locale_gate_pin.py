"""The policy job runs scripts/locale_gate.py at a pinned content hash; a
change to the script changes the pin here on purpose, never by drift."""

import hashlib
from pathlib import Path

PINNED = "acb91b8efd45a2bab770af0605ec74fa8bb940cbcbb5d186d306b3fe6c3b2558"


def test_locale_gate_is_the_pinned_version():
    path = Path(__file__).parent.parent / "scripts" / "locale_gate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINNED
