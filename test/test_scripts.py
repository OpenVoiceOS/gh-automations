"""
Unit tests for gh-automations Python scripts.

Tests all public functions in:
  - scripts/_version_utils.py  (read_version, format_version, write_version_block)
  - scripts/update_version.py  (update_version)
  - scripts/get_version.py     (get_version)
  - scripts/remove_alpha.py    (update_alpha)

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

from _version_utils import format_version, read_version, write_version_block  # noqa: E402
from get_version import get_version  # noqa: E402
from remove_alpha import update_alpha  # noqa: E402
from update_version import update_version  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STABLE_VERSION_PY = textwrap.dedent("""\
    # The following lines are replaced during the release process.
    # START_VERSION_BLOCK
    VERSION_MAJOR = 1
    VERSION_MINOR = 2
    VERSION_BUILD = 3
    VERSION_ALPHA = 0
    # END_VERSION_BLOCK

    __version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
""")

ALPHA_VERSION_PY = textwrap.dedent("""\
    # The following lines are replaced during the release process.
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
        # 1.2.3a4 → 2.0.0a1
        result = update_version("major", str(alpha_version_file))
        assert result == "2.0.0a1"
        assert read_version(str(alpha_version_file)) == (2, 0, 0, 1)

    def test_minor_bump(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 → 1.3.0a1
        result = update_version("minor", str(alpha_version_file))
        assert result == "1.3.0a1"
        assert read_version(str(alpha_version_file)) == (1, 3, 0, 1)

    def test_build_bump(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 → 1.2.4a1
        result = update_version("build", str(alpha_version_file))
        assert result == "1.2.4a1"
        assert read_version(str(alpha_version_file)) == (1, 2, 4, 1)

    def test_alpha_bump_from_alpha(self, alpha_version_file: Path) -> None:
        # 1.2.3a4 → 1.2.3a5
        result = update_version("alpha", str(alpha_version_file))
        assert result == "1.2.3a5"
        assert read_version(str(alpha_version_file)) == (1, 2, 3, 5)

    def test_alpha_bump_from_stable(self, stable_version_file: Path) -> None:
        # 1.2.3 (alpha=0) → 1.2.4a1 (build increments first)
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
        # alpha=0 (stable) → BUILD increments first
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
