"""
Unit tests for gh-automations Python scripts.

Tests all public functions in:
  - scripts/_version_utils.py  (read_version, format_version, write_version_block)
  - scripts/update_version.py  (update_version)
  - scripts/get_version.py     (get_version)
  - scripts/remove_alpha.py    (update_alpha)
  - scripts/update_pr_comment.py (build_section, insert_or_replace_section)
  - scripts/check_opm.py (auto_detect_plugin_types, check_opm, find_plugin_class)
  - scripts/aggregate_python_results.py (main)
  - scripts/check_release_channels.py (parse_constraints, check_version_against_constraint)

Runs without any external dependencies beyond the Python standard library.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

# Make scripts/ importable from the test directory
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from _version_utils import format_version, read_version, write_version_block, find_version_file  # noqa: E402
from get_version import get_version  # noqa: E402
from remove_alpha import update_alpha  # noqa: E402
from update_version import update_version  # noqa: E402
from update_pr_comment import build_section, insert_or_replace_section  # noqa: E402
from check_opm import (  # noqa: E402
    auto_detect_plugin_types,
    check_opm,
    find_plugin_class,
    extract_metadata,
    extract_system_deps,
    validate_plugin_import,
    check_plugin_interface,
    validate_config_docs,
    collect_issues,
    compute_status,
)
from aggregate_python_results import main as aggregate_main  # noqa: E402
from check_release_channels import parse_constraints, check_version_against_constraint # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STABLE_VERSION_PY = textwrap.dedent("""\
    # Header comment
    import os

    # START_VERSION_BLOCK
    VERSION_MAJOR = 1
    VERSION_MINOR = 2
    VERSION_BUILD = 3
    VERSION_ALPHA = 0
    # END_VERSION_BLOCK

    __version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
""")

ALPHA_VERSION_PY = textwrap.dedent("""\
    # START_VERSION_BLOCK
    VERSION_MAJOR = 1
    VERSION_MINOR = 2
    VERSION_BUILD = 3
    VERSION_ALPHA = 4
    # END_VERSION_BLOCK

    __version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
""")


@pytest.fixture()
def stable_version_file(tmp_path: Path) -> Path:
    """Return a version.py path containing a stable (alpha=0) version."""
    f = tmp_path / "version.py"
    f.write_text(STABLE_VERSION_PY)
    return f


@pytest.fixture()
def alpha_version_file(tmp_path: Path) -> Path:
    """Return a version.py path containing an alpha version."""
    f = tmp_path / "version.py"
    f.write_text(ALPHA_VERSION_PY)
    return f


# ---------------------------------------------------------------------------
# _version_utils.read_version
# ---------------------------------------------------------------------------

class TestReadVersion:
    def test_reads_stable(self, stable_version_file: Path) -> None:
        assert read_version(str(stable_version_file)) == (1, 2, 3, 0)

    def test_reads_alpha(self, alpha_version_file: Path) -> None:
        assert read_version(str(alpha_version_file)) == (1, 2, 3, 4)

    def test_ignores_content_before_block(self, tmp_path: Path) -> None:
        """Lines before START_VERSION_BLOCK must not be parsed."""
        f = tmp_path / "version.py"
        f.write_text(
            "VERSION_MAJOR = 99  # red herring outside block\n"
            "# START_VERSION_BLOCK\n"
            "VERSION_MAJOR = 1\n"
            "VERSION_MINOR = 0\n"
            "VERSION_BUILD = 0\n"
            "VERSION_ALPHA = 0\n"
            "# END_VERSION_BLOCK\n"
        )
        assert read_version(str(f)) == (1, 0, 0, 0)

    def test_ignores_content_after_block(self, tmp_path: Path) -> None:
        """Lines after END_VERSION_BLOCK must not be parsed."""
        f = tmp_path / "version.py"
        f.write_text(
            "# START_VERSION_BLOCK\n"
            "VERSION_MAJOR = 2\n"
            "VERSION_MINOR = 0\n"
            "VERSION_BUILD = 0\n"
            "VERSION_ALPHA = 1\n"
            "# END_VERSION_BLOCK\n"
            "VERSION_MAJOR = 99  # red herring after block\n"
        )
        assert read_version(str(f)) == (2, 0, 0, 1)

    def test_handles_inline_comment(self, tmp_path: Path) -> None:
        """Values with trailing inline comments (e.g. '# 0 = stable') are parsed correctly."""
        f = tmp_path / "version.py"
        f.write_text(
            "# START_VERSION_BLOCK\n"
            "VERSION_MAJOR = 1\n"
            "VERSION_MINOR = 0\n"
            "VERSION_BUILD = 0\n"
            "VERSION_ALPHA = 0   # 0 = stable\n"
            "# END_VERSION_BLOCK\n"
        )
        assert read_version(str(f)) == (1, 0, 0, 0)


# ---------------------------------------------------------------------------
# _version_utils.format_version
# ---------------------------------------------------------------------------

class TestFormatVersion:
    def test_stable(self) -> None:
        assert format_version(1, 2, 3, 0) == "1.2.3"

    def test_alpha(self) -> None:
        assert format_version(1, 2, 3, 4) == "1.2.3a4"

    def test_alpha_one(self) -> None:
        assert format_version(0, 0, 1, 1) == "0.0.1a1"

    def test_zero_version(self) -> None:
        assert format_version(0, 0, 0, 0) == "0.0.0"


# ---------------------------------------------------------------------------
# _version_utils.write_version_block
# ---------------------------------------------------------------------------

class TestWriteVersionBlock:
    def test_preserves_content_before_block(self, stable_version_file: Path) -> None:
        write_version_block(str(stable_version_file), 2, 0, 0, 1)
        content = stable_version_file.read_text()
        assert "# Header comment" in content
        assert "import os" in content

    def test_preserves_content_after_block(self, stable_version_file: Path) -> None:
        write_version_block(str(stable_version_file), 2, 0, 0, 1)
        content = stable_version_file.read_text()
        assert "__version__" in content  # after-block content preserved

    def test_updates_values(self, stable_version_file: Path) -> None:
        write_version_block(str(stable_version_file), 2, 1, 0, 3)
        assert read_version(str(stable_version_file)) == (2, 1, 0, 3)

    def test_roundtrip(self, alpha_version_file: Path) -> None:
        original = read_version(str(alpha_version_file))
        write_version_block(str(alpha_version_file), *original)
        assert read_version(str(alpha_version_file)) == original


# ---------------------------------------------------------------------------
# update_version.update_version
# ---------------------------------------------------------------------------

class TestUpdateVersion:
    def test_major_bump(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 -> 2.0.0a1
        result = update_version("major", str(alpha_version_file))
        assert result == "2.0.0a1"
        assert read_version(str(alpha_version_file)) == (2, 0, 0, 1)

    def test_minor_bump(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 -> 1.3.0a1
        result = update_version("minor", str(alpha_version_file))
        assert result == "1.3.0a1"
        assert read_version(str(alpha_version_file)) == (1, 3, 0, 1)

    def test_build_bump(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 -> 1.2.4a1
        result = update_version("build", str(alpha_version_file))
        assert result == "1.2.4a1"
        assert read_version(str(alpha_version_file)) == (1, 2, 4, 1)

    def test_alpha_bump_from_alpha(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 -> 1.2.3a5
        result = update_version("alpha", str(alpha_version_file))
        assert result == "1.2.3a5"
        assert read_version(str(alpha_version_file)) == (1, 2, 3, 5)

    def test_alpha_bump_from_stable(self, stable_version_file: Path) -> None:
        # 1.2.3 (alpha=0) -> 1.2.4a1 (build increments first)
        result = update_version("alpha", str(stable_version_file))
        assert result == "1.2.4a1"
        assert read_version(str(stable_version_file)) == (1, 2, 4, 1)

    def test_invalid_part_raises(self, stable_version_file: Path) -> None:
        with pytest.raises(ValueError, match="Unknown version part"):
            update_version("patch", str(stable_version_file))

    def test_major_bump_resets_minor_and_build(self, alpha_version_file: Path) -> None:
        update_version("major", str(alpha_version_file))
        major, minor, build, alpha = read_version(str(alpha_version_file))
        assert minor == 0
        assert build == 0

    def test_minor_bump_resets_build(self, alpha_version_file: Path) -> None:
        update_version("minor", str(alpha_version_file))
        _, _, build, _ = read_version(str(alpha_version_file))
        assert build == 0


# ---------------------------------------------------------------------------
# get_version.get_version
# ---------------------------------------------------------------------------

class TestGetVersion:
    def test_stable(self, stable_version_file: Path) -> None:
        assert get_version(str(stable_version_file)) == "1.2.3"

    def test_alpha(self, alpha_version_file: Path) -> None:
        assert get_version(str(alpha_version_file)) == "1.2.3a4"

    def test_consistent_with_update_version(self, alpha_version_file: Path) -> None:
        new_ver = update_version("minor", str(alpha_version_file))
        assert get_version(str(alpha_version_file)) == new_ver


# ---------------------------------------------------------------------------
# remove_alpha.update_alpha
# ---------------------------------------------------------------------------

class TestUpdateAlpha:
    def test_removes_alpha_suffix(self, alpha_version_file: Path) -> None:
        update_alpha(str(alpha_version_file))
        assert get_version(str(alpha_version_file)) == "1.2.3"

    def test_idempotent_on_stable(self, stable_version_file: Path) -> None:
        update_alpha(str(stable_version_file))
        assert get_version(str(stable_version_file)) == "1.2.3"

    def test_preserves_major_minor_build(self, alpha_version_file: Path) -> None:
        update_alpha(str(alpha_version_file))
        major, minor, build, alpha = read_version(str(alpha_version_file))
        assert (major, minor, build) == (1, 2, 3)
        assert alpha == 0

    def test_preserves_content_after_block(self, alpha_version_file: Path) -> None:
        update_alpha(str(alpha_version_file))
        content = alpha_version_file.read_text()
        assert "__version__" in content


# ---------------------------------------------------------------------------
# update_pr_comment.py
# ---------------------------------------------------------------------------

class TestUpdatePrComment:
    def test_build_section(self) -> None:
        section = build_section("test", "Title", "Hello")
        assert "<!-- section:test -->" in section
        assert "### Title" in section
        assert "Hello" in section
        assert "<!-- /section:test -->" in section

    def test_insert_new_section(self) -> None:
        body = "Initial body"
        new_body = insert_or_replace_section(body, "test", "Title", "Hello")
        assert "Initial body" in new_body
        assert "<!-- section:test -->" in new_body
        assert "### Title" in new_body
        assert "Hello" in new_body

    def test_replace_existing_section(self) -> None:
        initial = (
            "Header\n\n"
            "<!-- section:test -->\n"
            "### Old Title\n\n"
            "Old content\n"
            "<!-- /section:test -->\n"
            "Footer"
        )
        updated = insert_or_replace_section(initial, "test", "New Title", "New content")
        assert "Header" in updated
        assert "Footer" in updated
        assert "### Old Title" not in updated
        assert "### New Title" in updated
        assert "New content" in updated
        assert "<!-- section:test -->" in updated
        assert "<!-- /section:test -->" in updated

    def test_idempotent_replace(self) -> None:
        initial = (
            "Header\n\n"
            "<!-- section:test -->\n"
            "### Title\n\n"
            "Content\n"
            "<!-- /section:test -->"
        )
        # Content match (whitespace stripped)
        updated = insert_or_replace_section(initial, "test", "Title", "  Content  ")
        assert "Content" in updated


# ---------------------------------------------------------------------------
# check_opm.py
# ---------------------------------------------------------------------------

class TestCheckOpm:
    def test_find_plugin_class_valid(self) -> None:
        """Extract class name from entry point string."""
        result = find_plugin_class("skill", "my-skill = mypackage.skills:MySkillClass")
        assert result == "MySkillClass"

    def test_find_plugin_class_no_colon(self) -> None:
        """Handle entry point without colon."""
        result = find_plugin_class("skill", "my-skill")
        assert result is None

    def test_find_plugin_class_with_comma(self) -> None:
        """Handle entry point with trailing content after class."""
        result = find_plugin_class("skill", "my-skill = pkg:MyClass, other")
        assert result == "MyClass"

    def test_auto_detect_no_plugin(self, tmp_path: Path) -> None:
        """Auto-detect should return empty list for non-plugin packages."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Create a pyproject.toml without any opm.* entry points
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"my-package\"\n"
            )
            result = auto_detect_plugin_types()
            assert result == []
        finally:
            os.chdir(original_dir)

    def test_auto_detect_skill_plugin(self, tmp_path: Path) -> None:
        """Auto-detect should find skill plugin from pyproject.toml."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"ovos-skill-hello-world\"\n"
                "\n"
                "[project.entry-points.\"opm.skill\"]\n"
                "\"ovos-skill-hello-world\" = \"ovos_skill_hello_world:HelloWorldSkill\"\n"
            )
            result = auto_detect_plugin_types()
            assert "opm.skill" in result
        finally:
            os.chdir(original_dir)

    def test_auto_detect_tts_plugin(self, tmp_path: Path) -> None:
        """Auto-detect should find TTS plugin from pyproject.toml."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"ovos-tts-plugin-espeak\"\n"
                "\n"
                "[project.entry-points.\"opm.tts\"]\n"
                "\"espeak-tts\" = \"ovos_tts_plugin_espeak:EspeakTTSPlugin\"\n"
            )
            result = auto_detect_plugin_types()
            assert "opm.tts" in result
        finally:
            os.chdir(original_dir)

    def test_auto_detect_multiple_plugins(self, tmp_path: Path) -> None:
        """Auto-detect should find multiple plugin types."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"ovos-multi-plugin\"\n"
                "\n"
                "[project.entry-points.\"opm.skill\"]\n"
                "\"my-skill\" = \"mypkg:MySkill\"\n"
                "\n"
                "[project.entry-points.\"opm.tts\"]\n"
                "\"my-tts\" = \"mypkg:MyTTS\"\n"
            )
            result = auto_detect_plugin_types()
            assert "opm.skill" in result
            assert "opm.tts" in result
        finally:
            os.chdir(original_dir)

    def test_json_output_not_plugin(self, tmp_path: Path) -> None:
        """JSON output should indicate non-plugin package."""
        import os
        import json

        original_dir = os.getcwd()
        json_file = tmp_path / "result.json"
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"regular-package\"\n"
            )
            check_opm("auto", output_json=str(json_file))
            result = json.loads(json_file.read_text())
            assert result["is_ovos_plugin"] is False
            assert result["detected_types"] == []
        finally:
            os.chdir(original_dir)

    def test_extract_metadata_name(self, tmp_path: Path) -> None:
        """Extract metadata should read project name from pyproject.toml."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"my-plugin\"\n"
                'version = "1.2.3"\n'
                'description = "A test plugin"\n'
            )
            metadata = extract_metadata()
            assert metadata["name"] == "my-plugin"
            assert metadata["version"] == "1.2.3"
            assert metadata["description"] == "A test plugin"
        finally:
            os.chdir(original_dir)

    def test_extract_metadata_authors(self, tmp_path: Path) -> None:
        """Extract metadata should read authors from pyproject.toml."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"my-plugin\"\n"
                "authors = [\n"
                '    {name = "Alice", email = "alice@example.com"},\n'
                '    {name = "Bob"}\n'
                "]\n"
            )
            metadata = extract_metadata()
            assert len(metadata["authors"]) == 2
            assert metadata["authors"][0]["name"] == "Alice"
        finally:
            os.chdir(original_dir)

    def test_extract_system_deps(self, tmp_path: Path) -> None:
        """Extract system deps should read from [tool.ovos.build]."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\nname = \"my-plugin\"\n"
                "[tool.ovos.build]\n"
                'system-dependencies = ["libespeak-ng-dev", "libportaudio2"]\n'
            )
            deps = extract_system_deps()
            assert "libespeak-ng-dev" in deps
            assert "libportaudio2" in deps
        finally:
            os.chdir(original_dir)

    def test_extract_system_deps_missing(self, tmp_path: Path) -> None:
        """Extract system deps should return empty list if section absent."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\nname = \"my-plugin\"\n"
            )
            deps = extract_system_deps()
            assert deps == []
        finally:
            os.chdir(original_dir)

    def test_validate_plugin_import_success(self) -> None:
        """Test successful import validation."""
        ok, time_ms, error = validate_plugin_import("json", "dumps")
        assert ok is True
        assert time_ms is not None and time_ms >= 0
        assert error is None

    def test_validate_plugin_import_module_not_found(self) -> None:
        """Test import validation with nonexistent module."""
        ok, time_ms, error = validate_plugin_import("nonexistent_module_xyz", "SomeClass")
        assert ok is False
        assert time_ms is None
        assert error is not None
        assert "ImportError" in error

    def test_validate_plugin_import_attribute_not_found(self) -> None:
        """Test import validation with nonexistent class."""
        ok, time_ms, error = validate_plugin_import("json", "NonexistentClass")
        assert ok is False
        assert time_ms is None
        assert error is not None
        assert "AttributeError" in error

    def test_check_plugin_interface_unknown_type(self) -> None:
        """Test interface check with unknown plugin type."""
        class DummyClass:
            pass

        ok, abc_name, error = check_plugin_interface(DummyClass(), "unknown_type")
        assert ok is None
        assert error is not None

    def test_validate_config_docs_found(self, tmp_path: Path) -> None:
        """Test config docs validation when settingsmeta.json exists."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            settingsmeta_path = tmp_path / "settingsmeta.json"
            settingsmeta_path.write_text(
                '{"sections": [{"fields": [{"name": "setting1"}, {"name": "setting2"}]}]}'
            )
            has_config, keys, error = validate_config_docs()
            assert has_config is True
            assert "setting1" in keys
            assert "setting2" in keys
            assert error is None
        finally:
            os.chdir(original_dir)

    def test_validate_config_docs_missing(self, tmp_path: Path) -> None:
        """Test config docs validation when settingsmeta.json doesn't exist."""
        import os
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            has_config, keys, error = validate_config_docs()
            assert has_config is False
            assert keys == []
            assert error is None
        finally:
            os.chdir(original_dir)

    def test_collect_issues_opm_not_found(self) -> None:
        """Test issue collection for OPM detection failure."""
        result = {
            "opm_found": {"opm.skill": False},
            "validation": {
                "import_ok": {},
                "import_time_ms": {},
                "interface_ok": {},
                "abstract_base": {},
                "has_config_docs": True,
                "config_keys": [],
            },
            "issues": [],
            "status": "pass",
        }
        issues = collect_issues(result)
        assert any(issue["severity"] == "error" and "OPM could not detect" in issue["message"] for issue in issues)

    def test_collect_issues_slow_import(self) -> None:
        """Test issue collection for slow import."""
        result = {
            "opm_found": {"opm.tts": True},
            "validation": {
                "import_ok": {"tts": True},
                "import_time_ms": {"tts": 300},  # Between 200 and 500
                "interface_ok": {},
                "abstract_base": {},
                "has_config_docs": True,
                "config_keys": [],
            },
            "issues": [],
            "status": "pass",
        }
        issues = collect_issues(result)
        # Should have warning about slow import
        slow_import_issues = [i for i in issues if "slow" in i["message"].lower()]
        assert len(slow_import_issues) > 0
        assert slow_import_issues[0]["severity"] == "warning"

    def test_compute_status_pass(self) -> None:
        """Test status computation with no issues."""
        status = compute_status([])
        assert status == "pass"

    def test_compute_status_warning(self) -> None:
        """Test status computation with only warnings."""
        issues = [
            {"severity": "warning", "message": "Test warning", "check": "test"}
        ]
        status = compute_status(issues)
        assert status == "warning"

    def test_compute_status_fail(self) -> None:
        """Test status computation with errors."""
        issues = [
            {"severity": "error", "message": "Test error", "check": "test"},
            {"severity": "warning", "message": "Test warning", "check": "test"}
        ]
        status = compute_status(issues)
        assert status == "fail"

    def test_json_schema_complete(self, tmp_path: Path) -> None:
        """Test that JSON output has all expected schema keys."""
        import os
        import json
        original_dir = os.getcwd()
        json_file = tmp_path / "result.json"
        try:
            os.chdir(tmp_path)
            (tmp_path / "pyproject.toml").write_text(
                "[project]\n"
                "name = \"my-plugin\"\n"
            )
            check_opm("auto", output_json=str(json_file))
            result = json.loads(json_file.read_text())
            # Check for all expected keys
            assert "detected_types" in result
            assert "entry_points" in result
            assert "opm_found" in result
            assert "plugin_classes" in result
            assert "is_ovos_plugin" in result
            assert "summary" in result
            assert "metadata" in result
            assert "system_deps" in result
            assert "validation" in result
            assert "issues" in result
            assert "status" in result
            # Check validation sub-keys
            validation = result["validation"]
            assert "import_ok" in validation
            assert "import_time_ms" in validation
            assert "interface_ok" in validation
            assert "abstract_base" in validation
            assert "has_config_docs" in validation
            assert "config_keys" in validation
        finally:
            os.chdir(original_dir)


# ---------------------------------------------------------------------------
# check_opm.py — new feature tests (g2p, multi-ep, requires_python)
# ---------------------------------------------------------------------------

class TestCheckOpmNewFeatures:
    """Tests for features added in the OPM check improvements commit."""

    def test_g2p_in_plugin_type_finders(self) -> None:
        """g2p plugin type must be registered in PLUGIN_TYPE_FINDERS."""
        from check_opm import PLUGIN_TYPE_FINDERS
        assert "g2p" in PLUGIN_TYPE_FINDERS
        assert "find_g2p_plugins" in PLUGIN_TYPE_FINDERS["g2p"]

    def test_g2p_in_abstract_bases(self) -> None:
        """g2p plugin type must have a registered abstract base class."""
        from check_opm import ABSTRACT_BASES
        assert "g2p" in ABSTRACT_BASES
        module, cls = ABSTRACT_BASES["g2p"]
        assert "g2p" in module
        assert cls  # non-empty class name

    def test_auto_detect_g2p_plugin(self, tmp_path: Path) -> None:
        """auto_detect_plugin_types should discover a g2p plugin from pyproject.toml."""
        import os
        from check_opm import auto_detect_plugin_types
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            "name = \"ovos-g2p-plugin-example\"\n"
            "\n"
            "[project.entry-points.\"opm.g2p\"]\n"
            "\"ovos-g2p-plugin-example\" = \"ovos_g2p_example:MyG2PPlugin\"\n"
        )
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = auto_detect_plugin_types()
        finally:
            os.chdir(original_dir)
        # auto_detect_plugin_types returns a list of full group names like ['opm.g2p']
        assert "opm.g2p" in result

    def test_multi_entry_point_keyed_by_ep_name(self, tmp_path: Path) -> None:
        """A TTS plugin with two entry points must produce two separate import_ok keys."""
        import os
        import json
        from check_opm import check_opm
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            "name = \"ovos-tts-multi-voice\"\n"
            "\n"
            "[project.entry-points.\"opm.tts\"]\n"
            "\"ovos-tts-multi-voice-standard\" = \"os:getcwd\"\n"
            "\"ovos-tts-multi-voice-neural\" = \"os:getenv\"\n"
        )
        json_file = tmp_path / "result.json"
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            check_opm(
                "auto",
                output_json=str(json_file),
                test_import=True,
                validate_interface=False,
            )
            result = json.loads(json_file.read_text())
        finally:
            os.chdir(original_dir)
        import_ok = result["validation"]["import_ok"]
        # Both entry point names must appear as separate keys
        assert "ovos-tts-multi-voice-standard" in import_ok
        assert "ovos-tts-multi-voice-neural" in import_ok

    def test_requires_python_valid(self, tmp_path: Path) -> None:
        """requires_python_ok should be True when running Python satisfies the constraint."""
        import os
        import json
        import sys
        from check_opm import check_opm
        major, minor = sys.version_info.major, sys.version_info.minor
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            f"name = \"my-plugin\"\n"
            f"requires-python = \">={major}.{minor}\"\n"
        )
        json_file = tmp_path / "result.json"
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            check_opm("auto", output_json=str(json_file))
            result = json.loads(json_file.read_text())
        finally:
            os.chdir(original_dir)
        assert result["validation"]["requires_python_declared"] == f">={major}.{minor}"
        assert result["validation"]["requires_python_running"] == f"{major}.{minor}"
        # With the packaging library present requires_python_ok is True; without it, None
        assert result["validation"]["requires_python_ok"] in (True, None)

    def test_requires_python_violation_reported(self, tmp_path: Path) -> None:
        """requires_python_ok should be False for an impossible constraint."""
        import os
        import json
        from check_opm import check_opm
        pyproject = tmp_path / "pyproject.toml"
        # Require Python 99.0 — no running interpreter can satisfy this
        pyproject.write_text(
            "[project]\n"
            "name = \"my-plugin\"\n"
            "requires-python = \">=99.0\"\n"
        )
        json_file = tmp_path / "result.json"
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            check_opm("auto", output_json=str(json_file))
            result = json.loads(json_file.read_text())
        finally:
            os.chdir(original_dir)
        # packaging absent → None (skip); packaging present → False
        assert result["validation"]["requires_python_ok"] in (False, None)
        if result["validation"]["requires_python_ok"] is False:
            issues = result["issues"]
            assert any("requires_python" in i.get("check", "") for i in issues)

    def test_requires_python_missing(self, tmp_path: Path) -> None:
        """requires_python_ok should be None when no requires-python is declared."""
        import os
        import json
        from check_opm import check_opm
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[project]\n"
            "name = \"my-plugin\"\n"
        )
        json_file = tmp_path / "result.json"
        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            check_opm("auto", output_json=str(json_file))
            result = json.loads(json_file.read_text())
        finally:
            os.chdir(original_dir)
        assert result["validation"]["requires_python_ok"] is None
        assert result["validation"]["requires_python_declared"] is None


# ---------------------------------------------------------------------------
# aggregate_python_results.py
# ---------------------------------------------------------------------------

class TestAggregatePythonResults:
    def test_aggregate_multi_mode(self, tmp_path: Path) -> None:
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        # Create success for 3.11-regular, failure for 3.11-editable
        (results_dir / "3.11-regular.txt").write_text("success")
        (results_dir / "3.11-editable.txt").write_text("failure")
        
        output_file = tmp_path / "report.md"
        
        import sys
        original_argv = sys.argv
        sys.argv = [
            "aggregate_python_results.py",
            "--results-dir", str(results_dir),
            "--output", str(output_file),
            "--versions", "3.11",
            "--modes", "regular,editable"
        ]
        try:
            aggregate_main()
        finally:
            sys.argv = original_argv
            
        report = output_file.read_text()
        assert "🐍 **Python Support Matrix**" in report
        assert "| Mode | 3.11 |" in report
        assert "| Regular | ✅ |" in report
        assert "| Editable | ❌ |" in report
        assert "Installation failed" in report

# ---------------------------------------------------------------------------
# check_release_channels.py
# ---------------------------------------------------------------------------

class TestCheckReleaseChannels:
    def test_parse_constraints(self) -> None:
        content = "ovos-core>=1.3.1,<1.4.0\n# comment\nonnxruntime<=1.20.1\n"
        constraints = parse_constraints(content)
        assert constraints["ovos-core"] == "ovos-core>=1.3.1,<1.4.0"
        assert constraints["onnxruntime"] == "onnxruntime<=1.20.1"

    def test_check_version_compatible(self) -> None:
        # 1.3.2a1 vs >=1.3.1,<1.4.0
        icon, note = check_version_against_constraint("1.3.2a1", "ovos-core>=1.3.1,<1.4.0")
        assert icon == "✅"
        assert note == "Compatible"

    def test_check_version_too_new(self) -> None:
        # 1.4.0a1 vs >=1.3.1,<1.4.0
        icon, note = check_version_against_constraint("1.4.0a1", "ovos-core>=1.3.1,<1.4.0")
        assert icon == "❌"
        assert "Too new" in note

    def test_check_version_too_old(self) -> None:
        # 1.2.0 vs >=1.3.1
        icon, note = check_version_against_constraint("1.2.0", "ovos-core>=1.3.1")
        assert icon == "❌"
        assert "Too old" in note


# ---------------------------------------------------------------------------
# check_skill.py
# ---------------------------------------------------------------------------

from check_skill import (  # noqa: E402
    check_gitlocalize_readiness,
    check_skill_json,
    check_translation_completeness,
    count_locale_files,
    find_locale_dir,
    get_en_us_file_set,
    is_skill_repo,
    run_checks as skill_run_checks,
)


def _make_skill_repo(tmp_path: Path, *, entry_point: bool = True, langs: list[str] | None = None) -> Path:
    """Create a minimal fake OVOS skill directory structure."""
    if entry_point:
        setup_py = tmp_path / "setup.py"
        setup_py.write_text(
            "from setuptools import setup\n"
            "setup(entry_points={'ovos.plugin.skill': ['demo=demo:DemoSkill']})\n"
        )
    locale_dir = tmp_path / "skill_pkg" / "locale"
    en_us = locale_dir / "en-us"
    en_us.mkdir(parents=True)
    (en_us / "hello.intent").write_text("hello\nhi\n")
    (en_us / "greet.dialog").write_text("Hello!\n")
    (en_us / "skill.json").write_text(
        '{"skill_id": "demo.test", "name": "Demo", "description": "A demo", '
        '"examples": ["hi"], "tags": ["demo"]}'
    )
    for lang in langs or []:
        lang_dir = locale_dir / lang
        lang_dir.mkdir(parents=True)
        (lang_dir / "hello.intent").write_text("hallo\n")
    return tmp_path


class TestIsSkillRepo:
    def test_detects_setup_py(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text("entry_points={'ovos.plugin.skill': []}")
        assert is_skill_repo(str(tmp_path)) is True

    def test_detects_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[project.entry-points.'ovos.plugin.skill']\ndemo = 'demo:DemoSkill'\n"
        )
        assert is_skill_repo(str(tmp_path)) is True

    def test_returns_false_for_non_skill(self, tmp_path: Path) -> None:
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup(name='notaskill')\n")
        assert is_skill_repo(str(tmp_path)) is False

    def test_returns_false_for_empty_dir(self, tmp_path: Path) -> None:
        assert is_skill_repo(str(tmp_path)) is False


class TestFindLocaleDir:
    def test_finds_en_us(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path)
        result = find_locale_dir(str(repo))
        assert result is not None
        assert result.endswith("locale")

    def test_override_takes_precedence(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path)
        override = str(repo / "skill_pkg" / "locale")
        assert find_locale_dir(str(repo), override) == override

    def test_returns_none_when_no_locale(self, tmp_path: Path) -> None:
        assert find_locale_dir(str(tmp_path)) is None


class TestCountLocaleFiles:
    def test_counts_correctly(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path)
        en_us = repo / "skill_pkg" / "locale" / "en-us"
        counts = count_locale_files(str(en_us))
        assert counts["intent"] == 1
        assert counts["dialog"] == 1
        assert counts["total"] == 2  # skill.json excluded

    def test_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        counts = count_locale_files(str(d))
        assert counts["total"] == 0


class TestGetEnUsFileSet:
    def test_returns_relative_paths(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path)
        locale_dir = repo / "skill_pkg" / "locale"
        files = get_en_us_file_set(str(locale_dir))
        assert "hello.intent" in files
        assert "greet.dialog" in files
        # skill.json excluded
        assert not any("skill.json" in f for f in files)

    def test_empty_when_no_en_us(self, tmp_path: Path) -> None:
        locale = tmp_path / "locale"
        locale.mkdir()
        assert get_en_us_file_set(str(locale)) == set()


class TestCheckSkillJson:
    def test_valid_json(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path)
        en_us = repo / "skill_pkg" / "locale" / "en-us"
        result = check_skill_json(str(en_us))
        assert result["exists"] is True
        assert result["valid_json"] is True
        assert result["missing_fields"] == []
        assert result["skill_id"] == "demo.test"

    def test_missing_file(self, tmp_path: Path) -> None:
        d = tmp_path / "lang"
        d.mkdir()
        result = check_skill_json(str(d))
        assert result["exists"] is False

    def test_missing_fields(self, tmp_path: Path) -> None:
        d = tmp_path / "lang"
        d.mkdir()
        (d / "skill.json").write_text('{"name": "Demo"}')
        result = check_skill_json(str(d))
        assert result["valid_json"] is True
        assert "skill_id" in result["missing_fields"]
        assert "examples" in result["missing_fields"]

    def test_invalid_json(self, tmp_path: Path) -> None:
        d = tmp_path / "lang"
        d.mkdir()
        (d / "skill.json").write_text("{not valid json}")
        result = check_skill_json(str(d))
        assert result["valid_json"] is False


class TestCheckTranslationCompleteness:
    def test_full_coverage(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path, langs=["de-de"])
        locale_dir = repo / "skill_pkg" / "locale"
        # de-de has hello.intent only; en-us has hello.intent + greet.dialog
        en_us_files = get_en_us_file_set(str(locale_dir))
        results = check_translation_completeness(str(locale_dir), en_us_files)
        assert len(results) == 1
        assert results[0]["lang"] == "de-de"
        assert results[0]["present"] == 1
        assert results[0]["total"] == 2

    def test_empty_en_us_set(self, tmp_path: Path) -> None:
        locale = tmp_path / "locale"
        locale.mkdir()
        (locale / "de-de").mkdir()
        assert check_translation_completeness(str(locale), set()) == []


class TestCheckGitlocalizeReadiness:
    def test_all_present(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "sync_translations.py").write_text("")
        (tmp_path / "translations").mkdir()
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "sync.yml").write_text("uses: sync-translations.yml\n")
        result = check_gitlocalize_readiness(str(tmp_path))
        assert result["sync_script_exists"] is True
        assert result["translations_dir_exists"] is True
        assert result["sync_workflow_exists"] is True

    def test_all_absent(self, tmp_path: Path) -> None:
        result = check_gitlocalize_readiness(str(tmp_path))
        assert result["sync_script_exists"] is False
        assert result["translations_dir_exists"] is False
        assert result["sync_workflow_exists"] is False


class TestSkillRunChecks:
    def test_non_skill_repo(self, tmp_path: Path) -> None:
        report = skill_run_checks(str(tmp_path))
        assert report["is_skill"] is False

    def test_skill_repo_full(self, tmp_path: Path) -> None:
        repo = _make_skill_repo(tmp_path, langs=["de-de", "fr-fr"])
        report = skill_run_checks(str(repo))
        assert report["is_skill"] is True
        assert report["has_en_us"] is True
        assert report["skill_id"] == "demo.test"
        assert report["languages"] == 3  # en-us + de-de + fr-fr
        assert len(report["translations"]) == 2


# ---------------------------------------------------------------------------
# check_release.py
# ---------------------------------------------------------------------------

from check_release import (  # noqa: E402
    compute_next_version,
    detect_bump_part,
    parse_pr_title,
    run_checks as release_run_checks,
    validate_version_block,
)


class TestParsePrTitle:
    def test_feat_prefix(self) -> None:
        prefix, remainder = parse_pr_title("feat: add multilingual support")
        assert prefix == "feat:"
        assert "multilingual" in remainder

    def test_fix_prefix(self) -> None:
        prefix, _ = parse_pr_title("fix: correct typo")
        assert prefix == "fix:"

    def test_breaking_prefix(self) -> None:
        prefix, _ = parse_pr_title("breaking change: remove old api")
        assert prefix == "breaking change:"

    def test_no_prefix(self) -> None:
        prefix, remainder = parse_pr_title("just a normal title")
        assert prefix is None
        assert remainder is None

    def test_case_insensitive(self) -> None:
        prefix, _ = parse_pr_title("Feat: uppercase")
        assert prefix == "feat:"


class TestDetectBumpPart:
    def test_label_feature(self) -> None:
        part, source = detect_bump_part(["feature"], "")
        assert part == "minor"
        assert "label" in source

    def test_label_breaking(self) -> None:
        part, source = detect_bump_part(["breaking"], "")
        assert part == "major"

    def test_label_takes_precedence_over_title(self) -> None:
        part, source = detect_bump_part(["bug"], "feat: some feature")
        assert part == "build"  # label (bug→build) wins over title (feat→minor)

    def test_title_fallback(self) -> None:
        part, source = detect_bump_part([], "feat: new feature")
        assert part == "minor"
        assert "title" in source

    def test_no_signal(self) -> None:
        part, source = detect_bump_part([], "update readme")
        assert part == "alpha"
        assert source == "none"

    def test_docs_prefix_gives_alpha(self) -> None:
        part, source = detect_bump_part([], "docs: update readme")
        assert part == "alpha"
        assert "title" in source

    def test_label_priority_major_beats_minor(self) -> None:
        part, _ = detect_bump_part(["feature", "breaking"], "")
        assert part == "major"


class TestComputeNextVersion:
    def test_major_bump(self) -> None:
        assert compute_next_version(1, 2, 3, 4, "major") == (2, 0, 0, 1)

    def test_minor_bump(self) -> None:
        assert compute_next_version(1, 2, 3, 4, "minor") == (1, 3, 0, 1)

    def test_build_bump(self) -> None:
        assert compute_next_version(1, 2, 3, 4, "build") == (1, 2, 4, 1)

    def test_alpha_bump_from_alpha(self) -> None:
        assert compute_next_version(1, 2, 3, 4, "alpha") == (1, 2, 3, 5)

    def test_alpha_bump_from_stable(self) -> None:
        # alpha=0 (stable) -> BUILD increments first
        assert compute_next_version(1, 2, 3, 0, "alpha") == (1, 2, 4, 1)

    def test_mirrors_update_version_major(self, stable_version_file: Path) -> None:
        """compute_next_version must match update_version.py for major."""
        result_str = update_version("major", str(stable_version_file))
        major, minor, build, alpha = read_version(str(stable_version_file))
        # verify compute_next_version gives same result from original coords
        orig = (1, 2, 3, 0)
        nm, ni, nb, na = compute_next_version(*orig, "major")
        from _version_utils import format_version as fv
        assert fv(nm, ni, nb, na) == result_str


class TestValidateVersionBlock:
    def test_valid_file(self, alpha_version_file: Path) -> None:
        result = validate_version_block(str(alpha_version_file))
        assert result["has_start_marker"] is True
        assert result["has_end_marker"] is True
        assert result["parseable"] is True
        assert result["error"] is None

    def test_missing_file(self, tmp_path: Path) -> None:
        result = validate_version_block(str(tmp_path / "nonexistent.py"))
        assert result["parseable"] is False
        assert result["error"] is not None

    def test_missing_markers(self, tmp_path: Path) -> None:
        f = tmp_path / "version.py"
        f.write_text("VERSION_MAJOR = 1\n")
        result = validate_version_block(str(f))
        assert result["has_start_marker"] is False
        assert result["has_end_marker"] is False


class TestReleaseRunChecks:
    def test_file_not_found(self, tmp_path: Path) -> None:
        report = release_run_checks(str(tmp_path / "version.py"))
        assert report["status"] == "file_not_found"
        assert report["current_version"] is None

    def test_predicts_minor_from_label(self, alpha_version_file: Path) -> None:
        import json as _json
        labels_json = _json.dumps([{"name": "feature"}])
        report = release_run_checks(str(alpha_version_file), labels_json, "")
        assert report["status"] == "ok"
        assert report["current_version"] == "1.2.3a4"
        assert report["next_version"] == "1.3.0a1"
        assert report["bump_part"] == "minor"

    def test_predicts_from_title(self, stable_version_file: Path) -> None:
        report = release_run_checks(str(stable_version_file), "[]", "fix: correct typo")
        assert report["bump_part"] == "build"
        assert report["has_conventional_prefix"] is True

    def test_no_signal_gives_alpha(self, alpha_version_file: Path) -> None:
        report = release_run_checks(str(alpha_version_file), "[]", "update readme")
        assert report["bump_part"] == "alpha"
        assert report["has_conventional_prefix"] is False

    def test_labels_json_plain_strings(self, alpha_version_file: Path) -> None:
        import json as _json
        report = release_run_checks(str(alpha_version_file), _json.dumps(["breaking"]), "")
        assert report["bump_part"] == "major"


# ---------------------------------------------------------------------------
# check_repo_health.py
# ---------------------------------------------------------------------------

from check_repo_health import (  # noqa: E402
    check_required_files,
    check_version_file,
    run_checks as health_run_checks,
)


class TestCheckRequiredFiles:
    def test_all_present(self, tmp_path: Path) -> None:
        (tmp_path / "version.py").write_text("VERSION = 1")
        (tmp_path / "README.md").write_text("# README")
        (tmp_path / "LICENSE").write_text("Apache 2.0")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"')
        results = check_required_files(str(tmp_path))
        for item in results:
            if item["required"]:
                assert item["exists"] is True

    def test_missing_readme(self, tmp_path: Path) -> None:
        (tmp_path / "version.py").write_text("V = 1")
        (tmp_path / "LICENSE").write_text("Apache 2.0")
        results = check_required_files(str(tmp_path))
        readme = [r for r in results if r["file"] == "README.md"][0]
        assert readme["exists"] is False

    def test_setup_group(self, tmp_path: Path) -> None:
        """At least one of pyproject.toml/setup.py must exist."""
        results = check_required_files(str(tmp_path))
        setup_items = [r for r in results if r.get("group") == "setup"]
        assert len(setup_items) == 2
        assert all(r["group_satisfied"] is False for r in setup_items)

        (tmp_path / "setup.py").write_text("setup()")
        results = check_required_files(str(tmp_path))
        setup_items = [r for r in results if r.get("group") == "setup"]
        assert any(r["group_satisfied"] is True for r in setup_items)

    def test_optional_files(self, tmp_path: Path) -> None:
        results = check_required_files(str(tmp_path))
        changelog = [r for r in results if r["file"] == "CHANGELOG.md"][0]
        assert changelog["required"] is False
        assert changelog["exists"] is False


class TestCheckVersionFile:
    def test_valid_version(self, alpha_version_file: Path) -> None:
        result = check_version_file(str(alpha_version_file.parent), alpha_version_file.name)
        assert result["exists"] is True
        assert result["has_start_marker"] is True
        assert result["has_end_marker"] is True

    def test_missing_file(self, tmp_path: Path) -> None:
        result = check_version_file(str(tmp_path), "version.py")
        assert result["exists"] is False

    def test_no_markers(self, tmp_path: Path) -> None:
        (tmp_path / "version.py").write_text("__version__ = '1.0.0'\n")
        result = check_version_file(str(tmp_path), "version.py")
        assert result["exists"] is True
        assert result["has_start_marker"] is False


class TestHealthRunChecks:
    def test_full_repo(self, tmp_path: Path) -> None:
        (tmp_path / "version.py").write_text(
            "# START_VERSION_BLOCK\n"
            "VERSION_MAJOR = 1\nVERSION_MINOR = 0\n"
            "VERSION_BUILD = 0\nVERSION_ALPHA = 0\n"
            "# END_VERSION_BLOCK\n"
        )
        (tmp_path / "README.md").write_text("# Test")
        (tmp_path / "LICENSE").write_text("Apache 2.0")
        (tmp_path / "pyproject.toml").write_text('[project]\nname="test"')
        report = health_run_checks(str(tmp_path))
        assert report["version"]["exists"] is True
        assert report["version"]["has_start_marker"] is True
        files = report["files"]
        assert all(f["exists"] for f in files if f["required"])

    def test_empty_repo(self, tmp_path: Path) -> None:
        report = health_run_checks(str(tmp_path))
        assert report["version"]["exists"] is False
        required = [f for f in report["files"] if f["required"]]
        assert all(not f["exists"] for f in required)


# ---------------------------------------------------------------------------
# _version_utils.find_version_file
# ---------------------------------------------------------------------------

class TestFindVersionFile:
    def test_finds_hint(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "custom_pkg"
        pkg_dir.mkdir()
        v_file = pkg_dir / "version.py"
        v_file.write_text("VERSION = 1")
        
        result = find_version_file(str(tmp_path), "custom_pkg/version.py")
        assert result is not None
        assert Path(result) == v_file

    def test_finds_root(self, tmp_path: Path) -> None:
        v_file = tmp_path / "version.py"
        v_file.write_text("VERSION = 1")
        
        result = find_version_file(str(tmp_path))
        assert result is not None
        assert Path(result) == v_file

    def test_finds_in_package_dir(self, tmp_path: Path) -> None:
        pkg_dir = tmp_path / "my_package"
        pkg_dir.mkdir()
        v_file = pkg_dir / "version.py"
        v_file.write_text("VERSION = 1")
        
        result = find_version_file(str(tmp_path))
        assert result is not None
        assert Path(result) == v_file

    def test_ignores_common_dirs(self, tmp_path: Path) -> None:
        # Create version.py in an ignored dir
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "version.py").write_text("VERSION = 1")
        
        # Should not find it
        assert find_version_file(str(tmp_path)) is None
        
        # Create in a real package dir
        pkg_dir = tmp_path / "real_pkg"
        pkg_dir.mkdir()
        v_file = pkg_dir / "version.py"
        v_file.write_text("VERSION = 1")
        
        result = find_version_file(str(tmp_path))
        assert result is not None
        assert Path(result) == v_file

    def test_finds_via_pyproject_toml(self, tmp_path: Path) -> None:
        # Setup pyproject.toml with a package name
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "my-cool-package"')
        
        # Create version.py in the mapped package dir (dashes to underscores)
        pkg_dir = tmp_path / "my_cool_package"
        pkg_dir.mkdir()
        v_file = pkg_dir / "version.py"
        v_file.write_text("VERSION = 1")
        
        result = find_version_file(str(tmp_path))
        assert result is not None
        assert Path(result) == v_file

    def test_returns_none_if_not_found(self, tmp_path: Path) -> None:
        assert find_version_file(str(tmp_path)) is None
