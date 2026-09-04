"""
Unit tests for codename resolution (scripts/resolve_codename.py).

Runs without any external dependencies beyond the Python standard library.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from resolve_codename import advance_codename, resolve_codename  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(tmp_path: Path, names: list[str], current: str | None = None) -> Path:
    """Create a codenames/ directory with CODENAMES and optionally CURRENT."""
    d = tmp_path / "codenames"
    d.mkdir()
    registry = d / "CODENAMES"
    registry.write_text(
        "# comment line\n" + "\n".join(names) + "\n"
    )
    if current is not None:
        (d / "CURRENT").write_text(current + "\n")
    return d


# ---------------------------------------------------------------------------
# resolve_codename
# ---------------------------------------------------------------------------

class TestResolveCodename:
    def test_returns_current(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta", "Gamma"], current="Alpha")
        assert resolve_codename(str(d)) == "Alpha"

    def test_returns_mid_pointer(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta", "Gamma"], current="Beta")
        assert resolve_codename(str(d)) == "Beta"

    def test_strips_whitespace_from_current(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta"], current="Alpha")
        # Overwrite with extra whitespace
        (d / "CURRENT").write_text("  Alpha  \n")
        assert resolve_codename(str(d)) == "Alpha"

    def test_raises_if_registry_missing(self, tmp_path: Path) -> None:
        d = tmp_path / "codenames"
        d.mkdir()
        (d / "CURRENT").write_text("Alpha\n")
        with pytest.raises(FileNotFoundError, match="CODENAMES"):
            resolve_codename(str(d))

    def test_raises_if_pointer_missing(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha"], current=None)
        with pytest.raises(FileNotFoundError, match="CURRENT"):
            resolve_codename(str(d))

    def test_raises_if_current_not_in_registry(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta"], current="Omega")
        with pytest.raises(ValueError, match="Omega"):
            resolve_codename(str(d))

    def test_raises_if_current_is_empty(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha"], current=None)
        (d / "CURRENT").write_text("   \n")
        with pytest.raises(ValueError, match="empty"):
            resolve_codename(str(d))

    def test_comment_lines_not_counted_as_names(self, tmp_path: Path) -> None:
        """Lines starting with # must not be treated as valid codenames."""
        d = _make_registry(tmp_path, ["Alpha"], current=None)
        (d / "CURRENT").write_text("# comment\n")
        with pytest.raises(ValueError):
            resolve_codename(str(d))


# ---------------------------------------------------------------------------
# advance_codename
# ---------------------------------------------------------------------------

class TestAdvanceCodename:
    def test_advance_first_to_second(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta", "Gamma"], current="Alpha")
        old, new = advance_codename(str(d))
        assert old == "Alpha"
        assert new == "Beta"
        assert resolve_codename(str(d)) == "Beta"

    def test_advance_middle(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta", "Gamma"], current="Beta")
        old, new = advance_codename(str(d))
        assert old == "Beta"
        assert new == "Gamma"

    def test_pointer_file_updated(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta"], current="Alpha")
        advance_codename(str(d))
        assert (d / "CURRENT").read_text().strip() == "Beta"

    def test_raises_at_last_name(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta"], current="Beta")
        with pytest.raises(ValueError, match="last codename"):
            advance_codename(str(d))

    def test_raises_if_current_not_in_registry(self, tmp_path: Path) -> None:
        d = _make_registry(tmp_path, ["Alpha", "Beta"], current="Omega")
        with pytest.raises(ValueError, match="Omega"):
            advance_codename(str(d))

    def test_idempotent_registry_after_advance(self, tmp_path: Path) -> None:
        """Advancing must not alter the CODENAMES file itself."""
        d = _make_registry(tmp_path, ["Alpha", "Beta", "Gamma"], current="Alpha")
        original_registry = (d / "CODENAMES").read_text()
        advance_codename(str(d))
        assert (d / "CODENAMES").read_text() == original_registry


# ---------------------------------------------------------------------------
# Live registry sanity
# ---------------------------------------------------------------------------

class TestLiveRegistry:
    """Validate the actual codenames/ directory shipped with gh-automations."""

    CODENAMES_DIR = Path(__file__).parent.parent / "codenames"

    def test_registry_exists(self) -> None:
        assert (self.CODENAMES_DIR / "CODENAMES").is_file(), \
            "codenames/CODENAMES registry file is missing"

    def test_current_exists(self) -> None:
        assert (self.CODENAMES_DIR / "CURRENT").is_file(), \
            "codenames/CURRENT pointer file is missing"

    def test_current_is_valid(self) -> None:
        name = resolve_codename(str(self.CODENAMES_DIR))
        assert name, "Resolved codename must be non-empty"

    def test_registry_has_sufficient_names(self) -> None:
        registry = (self.CODENAMES_DIR / "CODENAMES").read_text()
        names = [
            l.strip()
            for l in registry.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        assert len(names) >= 5, \
            f"CODENAMES registry has only {len(names)} entries; add more"

    def test_no_duplicate_names(self) -> None:
        registry = (self.CODENAMES_DIR / "CODENAMES").read_text()
        names = [
            l.strip()
            for l in registry.splitlines()
            if l.strip() and not l.strip().startswith("#")
        ]
        assert len(names) == len(set(names)), "Duplicate names found in CODENAMES registry"

    def test_current_is_in_registry(self) -> None:
        # resolve_codename already checks this, but be explicit for the live registry
        resolve_codename(str(self.CODENAMES_DIR))  # raises if not in registry
