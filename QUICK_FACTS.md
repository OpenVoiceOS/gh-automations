
# Quick Facts — `gh-automations`

| Feature | Details |
|---------|---------|
| Repository | [OpenVoiceOS/gh-automations](https://github.com/OpenVoiceOS/gh-automations) |
| Type | GitHub Actions reusable workflow library (not an installable Python package) |
| License | Apache-2.0 |
| Active branch | `dev` — all new repos should call `@dev` |
| Python scripts | `scripts/` — checked out at runtime, not installed |
| Unit tests | `test/test_scripts.py` — 123 tests, run with `uv run pytest` |
| Callers | 209 OVOS repositories |

---

## Reusable Workflows (15 total)

| Workflow | Callers | Key inputs |
|----------|---------|-----------|
| `publish-alpha.yml` | 209 repos | `version_file`, `propose_release`, `update_changelog`, `publish_pypi`, `notify_matrix` |
| `publish-stable.yml` | 209 repos | `version_file`, `publish_release`, `sync_dev`, `publish_pypi`, `notify_matrix` |
| `build-tests.yml` | All repos | `python_versions`, `install_extras`, `system_deps`, `test_path` |
| `ovoscope.yml` | Skill repos | `python_version`, `install_extras`, `system_deps`, `test_path` |
| `opm-check.yml` | Plugin repos | `plugin_type`, `entry_point`, `opm_require_found`, `opm_validate_interface`, `opm_test_import`, `opm_perf_threshold_ms` |
| `coverage.yml` | Selected repos | `coverage_source`, `min_coverage`, `system_deps`, `publish_to_gh_pages`, `pr_comment` |
| `license-check.yml` | 126 repos | `install_extras`, `system_deps`, `exclude_packages`, `fail_licenses`, `warn_only` |
| `pip-audit.yml` | Selected repos | `install_extras`, `ignore_vulns`, `warn_only`, `upload_sarif`, `pr_comment` |
| `release-preview.yml` | All repos | `version_file`, `package_name`, `pr_comment` |
| `repo-health.yml` | All repos | `version_file`, `pr_comment` |
| `skill-check.yml` | Skill repos | `locale_dir`, `skip_if_not_skill`, `fail_on_missing_en_us`, `pr_comment` |
| `downstream-check.yml` | 13 repos | `package_name`, `constraints_url` |
| `python-support.yml` | Legacy | `python_versions`, `install_modes`, `entry_point`, `package_name`, `version_file` |
| `sync-translations.yml` | Skill repos | `branch`, `script_path` |
| `notify-matrix.yml` | 209 repos | `message`, `channel`, `homeserver` |

---

## PR Checks Comment Sections

Each workflow that posts to the shared OVOS PR Checks comment uses a unique section ID:

| Section ID | Title | Posted by |
|-----------|-------|-----------|
| `health` | `📋 Repo Health` | `repo-health.yml` |
| `welcome` | `👋 Welcome` | `repo-health.yml` (first-time contributors only) |
| `release` | `🏷️ Release Preview` | `release-preview.yml` |
| `security` | `🔒 Security (pip-audit)` | `pip-audit.yml` |
| `license` | `⚖️ License Check` | `license-check.yml` |
| `python_support` | `🐍 Python Support` | `python-support.yml` *(legacy)* |
| `build` | `🔨 Build Tests` | `build-tests.yml` |
| `opm` | `🔌 Plugin Detection` | `opm-check.yml` |
| `coverage` | `📊 Coverage` | `coverage.yml` |
| `ovoscope` | `🔌 Skill Tests (ovoscope)` | `ovoscope.yml` |
| `skill` | `🎙️ Skill` | `skill-check.yml` |

---

## Python Scripts

| Script | Key function | Line |
|--------|-------------|------|
| `_version_utils.py` | `read_version(version_file)` | `17` |
| `_version_utils.py` | `format_version(major, minor, build, alpha)` | `54` |
| `_version_utils.py` | `write_version_block(version_file, ...)` | `72` |
| `update_version.py` | `update_version(part, version_file)` | `22` |
| `remove_alpha.py` | `update_alpha(version_file)` | `17` |
| `get_version.py` | `get_version(version_file)` | `15` |
| `check_downstream.py` | `get_downstream(package_name)` | `61` |
| `check_downstream.py` | `sort_pipdeptree_output(text)` | `53` |
| `check_opm.py` | `extract_metadata()` | `54` |
| `check_opm.py` | `extract_system_deps()` | `108` |
| `check_opm.py` | `validate_plugin_import(module_path, class_name)` | `132` |
| `check_opm.py` | `check_plugin_interface(plugin_cls, short_type)` | `152` |
| `check_opm.py` | `validate_config_docs(repo_root)` | `176` |
| `check_opm.py` | `collect_issues(result)` | `217` |
| `check_opm.py` | `compute_status(issues)` | `292` |
| `check_opm.py` | `auto_detect_plugin_types()` | `308` |
| `check_opm.py` | `check_opm(plugin_type, entry_point, output_json, ...)` | `406` |
| `update_pr_comment.py` | `find_ovos_comment(repo, pr_number)` | `56` |
| `update_pr_comment.py` | `insert_or_replace_section(body, section_id, ...)` | `81` |
| `check_skill.py` | `run_checks(repo_root, locale_dir_override)` | `220` |
| `check_skill.py` | `find_locale_dir(repo_root, override)` | `52` |
| `check_skill.py` | `check_translation_completeness(locale_dir, ...)` | `157` |
| `check_release.py` | `run_checks(version_file, pr_labels_json, pr_title)` | `196` |
| `check_release.py` | `detect_bump_part(labels, pr_title)` | `74` |
| `check_release.py` | `compute_next_version(major, minor, build, alpha, part)` | `120` |

---

## `version.py` Block Format

```python
# START_VERSION_BLOCK
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_BUILD = 3
VERSION_ALPHA = 4   # 0 = stable
# END_VERSION_BLOCK

__version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
```

---

## Version Bump Rules

| Label | Bump | Example |
|-------|------|---------|
| `breaking` | major | `1.2.3a4` → `2.0.0a1` |
| `feature` | minor | `1.2.3a4` → `1.3.0a1` |
| `fix` | build | `1.2.3a4` → `1.2.4a1` |
| _(none)_ | alpha | `1.2.3a4` → `1.2.3a5` |
| _(none, currently stable)_ | build+alpha | `1.2.3` → `1.2.4a1` |

---

## Required Secrets (per calling repo)

| Secret | Used by |
|--------|---------|
| `PYPI_TOKEN` | `release_workflow.yml`, `publish_stable.yml` |
| `MATRIX_TOKEN` | `notify-matrix.yml` |
| `GITHUB_TOKEN` | All (auto-provided by GitHub Actions) |

---

## Key External Actions Used

| Action | Pinned to | Risk |
|--------|-----------|------|
| `actions/checkout` | `@v4` | Low |
| `actions/setup-python` | `@v5` | Low |
| `stefanzweifel/git-auto-commit-action` | `@v5` | Low |
| `ncipollo/release-action` | `@v1` | Low |
| `pypa/gh-action-pypi-publish` | `@release/v1` | Low |
| `pozetroninc/github-action-get-latest-release` | `@v0.7.0` | Low |
| `bcoe/conventional-release-labels` | `@v1` | Low |
| `ad-m/github-push-action` | `@v0.8.0` | Low |
| `fadenb/matrix-chat-message` | `@v0.0.6` | Low |
