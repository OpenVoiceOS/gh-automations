"""The policy job runs scripts/locale_gate.py at a pinned content hash; a
change to the script changes the pin here on purpose, never by drift."""

import hashlib
from pathlib import Path

PINNED = "dd9d2fa40c075543bb035a8f9e5473c3678fffaff362a293d61e157c9afb251c"


def test_locale_gate_is_the_pinned_version():
    path = Path(__file__).parent.parent / "scripts" / "locale_gate.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PINNED
