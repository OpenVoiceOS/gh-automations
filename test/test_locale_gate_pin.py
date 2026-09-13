"""The policy job runs scripts/locale_gate.py at a pinned content hash; a
change to the script changes the pin here on purpose, never by drift."""

import hashlib
from pathlib import Path

PINNED = "a62948f7b1bfc0124c605d40cff489c86992d1f8287218e8a7ce8582ddad81ed"


def test_locale_gate_is_the_pinned_version():
    path = Path(__file__).parent.parent / "scripts" / "locale_gate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINNED
