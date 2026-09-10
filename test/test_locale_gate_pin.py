"""The policy job runs scripts/locale_gate.py at a pinned content hash; a
change to the script changes the pin here on purpose, never by drift."""

import hashlib
from pathlib import Path

PINNED = "561c0fd3a78896885b329e786e1856e6899e6ef18c36be9400da95f40c55ea57"


def test_locale_gate_is_the_pinned_version():
    path = Path(__file__).parent.parent / "scripts" / "locale_gate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINNED
