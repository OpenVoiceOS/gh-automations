
# Maintenance Report — `gh-automations`

---

## [2026-03-13] — Auto-install pipeline plugins in ovoscope.yml (CI fallback)

### AI-Assisted Implementation Summary

**Model Used:** Qwen 3.5
**Actions Taken:**

**Problem:** Skills using ovoscope E2E tests with `require_padatious: true` were failing CI because the workflow expected the pipeline plugin to be in `[test]` extras, but the PyPI package names differ from entry point names, causing confusion.

**Solution:** Enhanced `ovoscope.yml` to auto-install pipeline plugins as a **CI fallback** when `require_*: true` is set. Skills MUST still declare dependencies in `pyproject.toml` for local/distro testing.

**Changes to `.github/workflows/ovoscope.yml`:**
- Updated header comments to clarify auto-installation is a **CI fallback**, not a replacement for `pyproject.toml` dependencies
- Modified `Install System Dependencies` step to auto-add `swig libfann-dev` when `require_padatious: true`
- Added new `Install Pipeline Plugin Dependencies` step that:
  - Installs `ovos-adapt-parser` (PyPI name) if `require_adapt: true`
  - Installs `ovos-padatious` (PyPI name) if `require_padatious: true`
  - Installs `ovos-m2v-pipeline` if `require_m2v: true`
  - Prints installed pipeline entry points for debugging
  - Error messages remind maintainers to add deps to `pyproject.toml`
- Updated `Check required pipeline availability` step to reference auto-installation in error messages

**Documentation updates:**
- `README.md` — Added ovoscope.yml to workflow table
- `FAQ.md` — Added "Ovoscope Workflow" section with Q&As:
  - How to declare pipeline dependencies in `pyproject.toml` (REQUIRED)
  - What happens if you forget (CI fallback auto-installs)
  - Why `pyproject.toml` deps are needed (local testing, distro builds, reproducibility)
  - Why padatious requires swig and libfann-dev

**Impact:** 
- CI no longer fails when maintainers forget pipeline dependencies (auto-install fallback)
- Skills still require explicit `pyproject.toml` deps for local/distro testing
- Clear error messages guide maintainers to add missing dependencies

**Human Oversight Level:** Medium — user identified the CI failure and correct best practice; implementation autonomous with documentation updates.

---

## [2026-03-11] — Fourteenth session: Roadmap implementation — AUDIT.md, new workflows, tests

### AI-Assisted Implementation Summary

**Model Used:** Claude Sonnet 4.6
**Actions Taken:**

**Priority 1 — Hygiene:**
- Created `AUDIT.md` with 8 open issues (A-001 through A-008), 6 resolved issues (R-001 through R-006), and technical debt table. Each issue cites `file:LINE`.
- Added `# REMOVE AFTER: 2027-01-01` EOL date to `coverage-pages.yml` and `python-support.yml`.

**Priority 2 — Pending SUGGESTIONS:**
- Added `### Migrate codecov → coverage.yml` and `### Migrate @master → @dev refs` sections to `docs/repo-setup.md`.
- Added type-check and docs-check workflow examples to `docs/repo-setup.md`.

**Priority 3 — Quality:**
- Created `test/test_workflow_inputs.py` with 4 parametrized test classes (60+ assertions):
  - `TestWorkflowYaml` — valid YAML, `name:`, `on:`, `jobs:`, no floating `@latest`/`@main`/`@master` refs
  - `TestReusableWorkflow` — `workflow_call`, inputs, `runner` input with default, all inputs have types
  - `TestPrCommentWorkflow` — `pr_comment` boolean input with `default: true`
  - `TestDeprecatedWorkflow` — valid YAML, DEPRECATED comment, REMOVE AFTER date

**Priority 4 — New Workflows:**
- Created `.github/workflows/type-check.yml` — runs mypy, posts 🔎 Type Check section to PR comment. `fail_on_errors: false` by default (informational).
- Created `.github/workflows/docs-check.yml` — verifies required docs files (`docs/index.md`, `FAQ.md`, `QUICK_FACTS.md`), optional markdownlint. `fail_on_missing: false` by default (informational).

**Priority 5 — Documentation:**
- Added new workflows (`type-check.yml`, `docs-check.yml`) to `docs/index.md` workflow table and `README.md` workflow table.
- Added `## New Maintainer Checklist` section to `README.md` with Day 1 orientation, pre-change checklist, post-change checklist, and deprecated workflow notes.
- Added deprecated workflow EOL dates to `README.md` and `docs/index.md`.

**Human Oversight Level:** Medium — user provided the improvement plan; implementation autonomous with test verification.

---

## [2026-03-10] — Thirteenth session: Docs, tests, and ovoscope.yml section

### AI-Assisted Implementation Summary

**Model Used:** Claude Sonnet 4.6
**Actions Taken:**
- Added `## ovoscope.yml` section to `docs/workflow-reference.md` (inputs, steps, pipeline strategy, PR comment content, typical usage, notes)
- Fixed `opm_require_found` documented default `false→true` in `docs/workflow-reference.md`
- Added `g2p` to the `plugin_type` allowed values list in `docs/workflow-reference.md` and the scripts reference
- Updated opm-check PR comment content description to document the split table (OPM Detection + Entry Point Validation)
- Added notes on `ep_name` keying and `requires-python` validation
- Added section `<!-- section:ovoscope -->` to the OVOS PR Checks example block in docs
- Added 7 new tests to `test/test_scripts.py` (class `TestCheckOpmNewFeatures`): g2p in PLUGIN_TYPE_FINDERS, g2p in ABSTRACT_BASES, g2p auto-detection from pyproject.toml, multi-entry-point keying by ep_name, requires_python valid/violated/missing
- Updated `FAQ.md` with Q&A for ovoscope.yml pipeline inputs, g2p support, split PR table, opm_require_found default change, requires-python validation

**Human Oversight Level:** Medium — user directed which items were missing; implementation autonomously verified with `pytest` (156 passed)

---

## [2026-03-10] — Twelfth session: Coverage Pages workflow + CI/CD fixes

### AI-Assisted Implementation Summary

**Model Used:** Claude Opus 4.6
**Actions Taken:**
- Created `coverage-pages.yml` reusable workflow for deploying HTML coverage reports to GitHub Pages
- Removed Pages permissions from `coverage.yml` to fix `startup_failure` in repos without Pages enabled
- Updated all documentation: `workflow-reference.md`, `index.md`, `README.md`, `QUICK_FACTS.md`, `repo-setup.md`, `FAQ.md`
- Added caller workflows for ovoscope and ovos-skill-confucius-quotes

**Human Oversight Level:** High — user directed architecture decisions (separate workflow vs embedded boolean, push-to-dev trigger)

---

## [2026-03-10] — Eleventh session: 10 OPM Deep Enhancements

### AI-Assisted Implementation Summary

**Model Used:** Claude Haiku 4.5
**Oversight Level:** High (comprehensive plan reviewed, test-driven development)
**Changes:** 6 new functions in `check_opm.py`, 16 new tests, enhanced workflow, downstream integration

### Key Enhancements

**1. Plugin Import Validation** — `validate_plugin_import(module_path, class_name)`
- Attempts actual import of the declared entry point class
- Measures import time in milliseconds
- Detects missing dependencies, syntax errors, import-time failures
- Returns: `(ok: bool | None, time_ms: int | None, error: str | None)`
- Thresholds: warning > 200ms, error > 500ms (configurable via `--perf-threshold-ms`)

**2. Interface Compliance Check** — `check_plugin_interface(plugin_cls, short_type)`
- Verifies that plugin class inherits from correct abstract base
- Abstract base map covers all 9 OVOS plugin types (skill, tts, stt, wake_word, vad, phal, pipeline, utterance_transformer, tts_transformer)
- Gracefully handles missing ABCs (returns `None` instead of failing)
- Uses `issubclass()` for robust inheritance checking

**3. Metadata Extraction** — `extract_metadata()`
- Reads `project.name`, `project.version`, `project.authors`, `project.description`, `project.urls.homepage`, `project.requires-python` from `pyproject.toml`
- Fallback to regex parsing of `setup.py` for older projects
- Returns dict with all fields (None if missing)

**4. System Dependencies Detection** — `extract_system_deps()`
- Reads `[tool.ovos.build] system-dependencies` from `pyproject.toml`
- Establishes new OVOS convention for declaring build-time system requirements
- Returns list of package names (empty list if absent)

**5. Configuration Docs Validation** — `validate_config_docs(repo_root)`
- Searches entire repo (recursive glob) for `settingsmeta.json`
- Parses both `sections.fields` and flat `fields` structures
- Extracts configuration key names
- Returns: `(has_config: bool, keys: list[str], error: str | None)`

**6. Issue Collection & Status Computation**
- `collect_issues(result)` — scans validation results, generates structured issue list
- Issue severity: `error` | `warning` | `info`
- Checks: OPM detection, import success, import performance, interface compliance, config docs presence
- `compute_status(issues)` — rolls up to `pass` | `warning` | `fail`

### Workflow Enhancements

**build-tests.yml — New Inputs:**
- `opm_require_found: boolean` (default: false) — fail build if OPM can't detect
- `opm_validate_interface: boolean` (default: true) — check abstract base inheritance
- `opm_test_import: boolean` (default: true) — test import, measure time
- `opm_perf_threshold_ms: number` (default: 500) — import error threshold

**build-tests.yml — Fixed Artifact Bug:**
- Upload step now saves `/tmp/` instead of `/tmp/opm_result.json` directly
- `post_opm_report` download glob updated to match flattened artifact structure
- Artifact name format: `opm-result-{python-version}` contains `opm_result.json`

**build-tests.yml — Enhanced PR Comment:**
- Status header with severity icon (✅ PASS / ⚠️ WARNINGS / ❌ ERRORS)
- Plugin metadata block (name, version, description)
- System dependencies list
- Validation table with per-type status (OPM found, import ok/time, interface, config docs)
- Issues list with severity icons
- **NEW:** Downstream impact count (if available)

**Downstream Integration:**
- `post_opm_report` now calls `check_downstream.py` to count dependents
- Displays as: `🔗 N package(s) depend on this plugin`
- Warning added if breaking changes will affect other packages
- Non-blocking (continues even if downstream check fails)

### Testing

**New Tests (16 total, bringing test count from 107 → 123):**
- `test_extract_metadata_name` — read project name
- `test_extract_metadata_authors` — read authors list
- `test_extract_system_deps` — read [tool.ovos.build] section
- `test_extract_system_deps_missing` — empty list when absent
- `test_validate_plugin_import_success` — successful import
- `test_validate_plugin_import_module_not_found` — ImportError handling
- `test_validate_plugin_import_attribute_not_found` — AttributeError handling
- `test_check_plugin_interface_unknown_type` — unknown plugin type
- `test_validate_config_docs_found` — settingsmeta.json parsing
- `test_validate_config_docs_missing` — graceful absence
- `test_collect_issues_opm_not_found` — error generation
- `test_collect_issues_slow_import` — warning generation
- `test_compute_status_pass` — no issues
- `test_compute_status_warning` — only warnings
- `test_compute_status_fail` — any error
- `test_json_schema_complete` — full JSON schema validation

**All 123 tests pass** — verified with `uv run pytest test/test_scripts.py -v`

### Documentation Updates

**FAQ.md:**
- Updated Header: Last Edit timestamp
- Enhanced "JSON output formats" description
- Added 7 new Q&A entries:
  - "What are the new validation checks?"
  - "What is the import time threshold?"
  - "What does 'interface compliance' mean?"
  - "How do I declare system dependencies?"
  - "How do I configure OPM validation in build-tests.yml?"
  - "What happens if validation fails?"
  - "How do I migrate from entry_point to plugin_type?" (expanded)

**QUICK_FACTS.md:**
- Updated test count: 107 → 123
- Updated Header: Last Edit timestamp
- Added 6 new check_opm.py function entries with line numbers
- Updated build-tests.yml input list with 4 new inputs

**MAINTENANCE_REPORT.md (this file):**
- Added transparency report for session

### Backward Compatibility

✅ All changes are backward compatible:
- New CLI flags have sensible defaults (all enabled, safe thresholds)
- JSON schema additions are additive (no removed/renamed keys)
- Legacy `--entry-point` argument still works
- Existing workflow calls continue to work without changes
- Tests confirm no regressions (123/123 passing)

### Key Decisions

1. **Import test scope:** Test actual declared entry points, not OPM's cached finder result. More direct CI signal.
2. **Interface check fallback:** Return `None` (not `False`) when ABC can't be imported, to avoid false failures.
3. **No instantiation:** Skip full plugin instantiation (requires audio/hardware/config) — import + interface check is sufficient.
4. **Downstream count only:** Don't run full analysis in CI (too slow) — just count dependents, link to full check if needed.
5. **New convention:** `[tool.ovos.build] system-dependencies` established as OVOS standard; workflows can auto-read in future.
6. **Naming conflict resolution:** Renamed `validate_interface()` function to `check_plugin_interface()` to avoid shadowing with parameter name.

### Files Modified

- `scripts/check_opm.py` — 580 lines (was 267); +6 functions, +8 CLI args
- `.github/workflows/build-tests.yml` — +4 inputs, fixed artifact bug, enhanced OPM report, downstream integration
- `test/test_scripts.py` — +16 tests in TestCheckOpm class
- `FAQ.md` — +7 Q&A entries
- `QUICK_FACTS.md` — updated test count and inputs list
- `MAINTENANCE_REPORT.md` — this entry

---

## [2026-03-10] — Tenth implementation session: Multi-plugin OPM detection, coverage.yml enhancements, workflow migration

### Changes

**Enhanced `scripts/check_opm.py` — Multi-plugin type support (REWRITE, ~220 lines):**
- **Before**: Hardcoded skill-only check; required explicit `--entry-point` argument; no JSON output; no plugin type flexibility.
- **After**:
  - `--plugin-type` argument: accepts any OPM type name (skill, tts, stt, wake_word, vad, phal, pipeline, utterance_transformer, etc.) or `auto` (default)
  - `--output-json` argument: writes structured JSON result for workflow consumption
  - Auto-detection logic: scans `pyproject.toml` `[project.entry-points]` for `opm.*` groups or `setup.py` `entry_points` dict
  - JSON output format: `detected_types`, `entry_points`, `opm_found`, `plugin_classes`, `is_ovos_plugin`, `summary`
  - Plugin type→OPM function mapper: 9 plugin types (skill, tts, stt, wake_word, vad, phal, pipeline, utterance_transformer, tts_transformer)
  - Backward compatible: `--entry-point` still works for legacy calls

**Updated `.github/workflows/build-tests.yml`:**
- Added `plugin_type` input (default: `auto`) — passed to `check_opm.py --plugin-type`
- Added `opm_section` boolean input (default: `true` when `pr_comment` is true) — controls OPM PR comment section
- Enhanced OPM check step to use new flags and output JSON
- Added `post_opm_report` job: collects OPM JSON artifacts, formats PR comment section, posts via `update_pr_comment.py --section-id opm`
- OPM PR comment shows: detected types, entry points per type, OPM discovery status (✅/❌ found)

**Updated `scripts/update_pr_comment.py`:**
- Added `opm` flavor text pool (4 messages): "Let's see if this plugin can be found...", "Checking if the plugin ecosystem recognizes...", "I've verified the plugin's entry points!", "Plugin detection status..."

**Enhanced `coverage.yml` reusable workflow:**
- Added `system_deps` input (default: `""`) — space-separated apt package names
- Added "Install System Dependencies" step: runs `apt-get update` and `apt-get install` if `system_deps` is not empty
- Allows skills/packages with system dependencies to use coverage.yml without custom system setup

**Migrated `Skills/ovos-skill-hello-world/.github/workflows/unit_tests.yml`:**
- **Before**: Custom inline job using `py-cov-action/python-coverage-comment-action@v3` directly
- **After**: Calls `coverage.yml@dev` reusable workflow from gh-automations
- Simplified: 55 lines → 9 lines (removed permissions, setup, install, test, coverage logic — all handled by reusable)
- Gains: integrated OVOS PR Checks comment (instead of standalone coverage comment), system_deps support, min_coverage threshold, GitHub Pages publishing option
- Parameters: `python_version: "3.11"`, `system_deps: "swig libssl-dev portaudio19-dev libpulse-dev libfann-dev"`, `test_path: "test/"`, `coverage_source: "ovos_skill_hello_world"`

**Added tests for new `check_opm.py` (8 tests in `TestCheckOpm` class):**
- `test_find_plugin_class_valid` — extract class name from entry point
- `test_find_plugin_class_no_colon` — handle entry point without colon
- `test_find_plugin_class_with_comma` — handle trailing content after class
- `test_auto_detect_no_plugin` — empty list for non-plugin packages
- `test_auto_detect_skill_plugin` — find skill from pyproject.toml
- `test_auto_detect_tts_plugin` — find TTS plugin from pyproject.toml
- `test_auto_detect_multiple_plugins` — find multiple types
- `test_json_output_not_plugin` — JSON output for non-plugins

**Updated documentation:**
- `QUICK_FACTS.md`: Updated test count (93 → 107), added check_opm.py to Python scripts table, updated build-tests.yml inputs
- `FAQ.md`: Added "OPM Plugin Detection" section (7 Q&As) covering auto-detect, specific types, JSON output, build-tests integration, disabling, migration from entry_point

### Verification

- `uv run pytest test/test_scripts.py` — all 107 tests pass (99 pre-existing + 8 new)
- YAML validation: `build-tests.yml` and `coverage.yml` valid YAML syntax
- Backward compatible: existing `entry_point` usage still works; new `plugin_type` is optional

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Claude Haiku 4.5 |
| Session type | Implementation: multi-plugin OPM, workflow migration |
| Scope | 1 script rewrite (check_opm.py), 2 workflow enhancements (build-tests.yml, coverage.yml), 1 workflow migration (ovos-skill-hello-world), 8 unit tests, 2 docs updates |
| Testing | All 107 tests pass; YAML validation successful; backward compatible |
| Human oversight | Full plan created and approved by user before implementation |

---

## [2026-03-10] — Ninth implementation session: Bug fixes, Python version standardization, documentation accuracy

### Changes

**CRITICAL BUG FIX — Conditional checkout bug in 3 workflows:**
- `skill-check.yml`, `release-preview.yml`, `repo-health.yml` had a critical bug: gh-automations scripts were conditionally checked out (`if: inputs.pr_comment && event == pull_request`) but script run steps had no matching condition. This caused immediate job failure on `workflow_dispatch` or push events.
- **Fix**: Removed `if:` condition from all three checkout steps. Scripts are now always checked out. Individual post-comment steps retain their own conditions for PR-specific actions.

**Python 3.14 → 3.11 standardization (10 affected files):**
- Changed default `python_version` from `"3.14"` (pre-release, not stable until Oct 2026) to `"3.11"` (workspace standard per AGENTS.md) in:
  - `publish-alpha.yml` (2 instances), `publish-stable.yml` (2 instances), `license-check.yml`, `pip-audit.yml`, `downstream-check.yml`, `sync-translations.yml`, `skill-check.yml`, `release-preview.yml`, `repo-health.yml`
- Also updated `ovoscope/.github/workflows/unit_tests.yml` for consistency.

**Code cleanup:**
- Removed dead import of `_version_utils` from `scripts/check_release_channels.py` (was unused and misleading).
- Fixed `!=` operator handling in `check_release_channels.py`: improved regex to split on two-character operators (`>=`, `<=`, `==`, `!=`) correctly; added handling for `!=` in version comparison logic.

**Documentation accuracy fixes:**
- `QUICK_FACTS.md`: Updated test count (74 → 93), added missing workflows (`build-tests.yml`, `repo-health.yml`), fixed stale action version references.
- `docs/workflow-reference.md`: Fixed PyPI action version in docs table (`@master` → `@release/v1`).
- `ovoscope/FAQ.md`: Updated workflow count (7 → 9), added missing workflows to CI workflow list, fixed test count (58 → 104).
- `ovoscope/docs/ci-integration.md`: Added missing workflows to CI workflow table, updated Python version matrix in docs (3.10–3.14 instead of 3.10–3.11).

**Integration verification:**
- Confirmed `ovoscope` uses gh-automations correctly: all 8 reusable workflows at `@dev` branch, no deprecated `python-support.yml` references, no stale actions.

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Claude Haiku 4.5 |
| Session type | Full review + bug fix + documentation accuracy |
| Scope | 3 critical bugs, 10 Python version standardizations, 2 code cleanups, 5 documentation updates across 2 repos |
| Testing | No new tests added; all existing tests still pass (93 tests) |
| Human oversight | Reviewed by user via plan approval before implementation |

---

## [2026-03-09] — Eighth implementation session: PR comment improvements

### Changes

**#3 — Missing files check (`repo-health.yml` + `check_repo_health.py`):**
- New `scripts/check_repo_health.py`: checks for `version.py`, `README.md`, `LICENSE`, `pyproject.toml`/`setup.py`, `CHANGELOG.md`, `requirements.txt`. Validates version block markers.
- New `.github/workflows/repo-health.yml`: runs health check, posts `📋 Repo Health` section.

**#4 — First-time contributor greeting:**
- Added to `repo-health.yml`: detects `FIRST_TIME_CONTRIBUTOR` / `FIRST_TIMER` via `github.event.pull_request.author_association`. Posts a `👋 Welcome` section with onboarding tips.

**#5 — Breaking change banner:**
- Updated `release-preview.yml` formatting: when `bump_part == "major"`, adds a `> [!CAUTION]` GitHub alert block warning about downstream breakage.

**#6 — Build test results in PR comment:**
- Updated `build-tests.yml`: added `pr_comment` input (default: true), artifact upload per Python version, `post_build_report` aggregate job. Posts `🔨 Build Tests` section with per-version status table. Compact table when all pass; detailed table with failure reasons when issues found.

**#7 — Locale completeness progress bars:**
- Updated `skill-check.yml` formatting: translation coverage table now shows `█████░░░░░` progress bars (10 chars wide). Summary line counts complete/partial/incomplete languages.

**Tests:** 93 tests pass (added 9 new tests for `check_repo_health.py`).

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Claude Sonnet 4.6 |
| Actions | Created `check_repo_health.py` + `repo-health.yml`; updated `release-preview.yml`, `build-tests.yml`, `skill-check.yml`; added tests; updated FAQ.md |
| Human oversight | Tests verified passing |

---

## [2026-03-09] — Seventh implementation session: bulk skill migration

### Changes

**`scripts/migrate_skills.py` — new script:**
- Bulk-migrates all OVOS skill repos from `TigreGotico/gh-automations@master` to `OpenVoiceOS/gh-automations@dev`.
- Handles 4 cases: already migrated (skip), no workflows (create from scratch), easter-eggs (full rewrite), standard (update refs + add new workflows).
- Preserves per-skill `version_file` and `license_tests.yml` `with:` params.
- Deletes `sync_tx.yml` inline workflows; creates `sync_translations.yml` reusable wrappers.
- Rewrites legacy `coverage.yml` (py-cov-action v3 pattern) to use `coverage.yml@dev`.
- Creates missing `skill_check.yml`, `release_preview.yml`, `conventional-label.yml` per skill.
- Commits each repo independently with a conventional `ci:` commit message.
- Supports `--dry-run` and `--skill SKILL_NAME` for targeted runs.

### Skills processed

- **58 committed** (57 standard migration + 1 full rewrite for easter-eggs + 3 created from scratch)
- **2 skipped** (already migrated: `ovos-skill-icanhazdadjokes`, `ovos-skill-confucius-quotes`)
- **0 errors**

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Claude Sonnet 4.6 |
| Actions | Created `scripts/migrate_skills.py`; rewrote/created 290+ workflow files across 58 skill repos; updated FAQ.md and MAINTENANCE_REPORT.md |
| Human oversight | Dry-run verified before live run; spot-checked 5 skill repos post-migration |

---

## [2026-03-09] — Sixth implementation session: enhanced CI checks and PR reporting

### Changes

**`scripts/aggregate_python_results.py` — new script:**
- Generates a multi-mode (Regular/Editable) Python support matrix from matrix job results.
- Supports mapping status to icons (`success`, `failure`, `opm_failure`).
- Outputs Markdown table for PR comments.

**`scripts/check_release_channels.py` — new script:**
- Verifies package compatibility with `ovos-releases` channels (`Stable`, `Testing`, `Alpha`).
- Reads constraints files from `ovos-releases` repo.
- Simplified version comparison logic for OVOS-specific requirement patterns.

**`scripts/check_opm.py` — new script:**
- Verifies that a skill is correctly detected by `ovos-plugin-manager` after installation.
- Checks for entry point presence in `find_skill_plugins()`.

**`.github/workflows/python-support.yml` — new reusable workflow:**
- Runs a matrix of Python versions (3.8-3.12) and install modes (regular, editable).
- Installs `ovos-plugin-manager` and the package.
- Runs `check_opm.py` to verify entry point detection.
- Aggregates all results and channel compatibility into a `🐍 Python Support` PR comment section.

**`.github/workflows/release-preview.yml` — updated:**
- Integrated `check_release_channels.py` to show channel compatibility for the predicted next version.
- Added `package_name` input.

**`test/test_scripts.py` — extended:**
- Added `TestAggregatePythonResults` covering success, failure, and missing data scenarios.

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Gemini CLI |
| Actions taken | Created 3 scripts, 1 workflow; updated 1 workflow, 1 doc, 1 test file |
| Human oversight level | Plan reviewed and approved by user before implementation |

---

## [2026-03-09] — Fifth implementation session: skill-check + release-preview

### Changes

**`scripts/check_skill.py` — new script:**
- Analyses OVOS skill repos: `is_skill_repo()`, `find_locale_dir()`, `count_locale_files()`, `get_en_us_file_set()`, `check_skill_json()`, `check_translation_completeness()`, `check_gitlocalize_readiness()`, `run_checks()`.
- Stdlib only. Exits 0 always; callers decide pass/fail.

**`scripts/check_release.py` — new script:**
- Reads `version.py` via `_version_utils.read_version()`, predicts next version from PR labels/title.
- `CONVENTIONAL_PREFIXES` dict maps prefixes to bump parts. `detect_bump_part()` prefers labels over title.
- `compute_next_version()` mirrors `update_version.py:37-52` exactly.
- PR data via env vars `PR_LABELS_JSON` + `PR_TITLE` (avoids shell quoting issues in workflows).
- Stdlib only. Exits 1 only for malformed `version.py`; missing file exits 0.

**`.github/workflows/skill-check.yml` — new reusable workflow:**
- Follows canonical `pip-audit.yml` 3-phase pattern.
- 6 inputs: `runner`, `python_version`, `locale_dir`, `skip_if_not_skill`, `fail_on_missing_en_us`, `fail_on_invalid_skill_json`, `pr_comment`.
- Posts `🎙️ Skill` section to OVOS PR Checks comment (section-id: `skill`).

**`.github/workflows/release-preview.yml` — new reusable workflow:**
- Follows canonical `pip-audit.yml` 3-phase pattern.
- 4 inputs: `runner`, `python_version`, `version_file`, `pr_comment`.
- Posts `🏷️ Release Preview` section (section-id: `release`) with current/next version, bump signal table, conventional commit guidance.

**`test/test_scripts.py` — extended:**
- Added `TestIsSkillRepo`, `TestFindLocaleDir`, `TestCountLocaleFiles`, `TestGetEnUsFileSet`, `TestCheckSkillJson`, `TestCheckTranslationCompleteness`, `TestCheckGitlocalizeReadiness`, `TestSkillRunChecks` (8 classes, 30+ tests).
- Added `TestParsePrTitle`, `TestDetectBumpPart`, `TestComputeNextVersion`, `TestValidateVersionBlock`, `TestReleaseRunChecks` (5 classes, 20+ tests).

**`docs/workflow-reference.md` — updated:**
- Added `skill-check.yml` and `release-preview.yml` sections with full input tables, step descriptions, and typical usage.
- Extended PR Checks Comment Pattern example to show all 5 sections.
- Added `check_skill.py` and `check_release.py` script reference entries.

**`FAQ.md` — updated:**
- Added "Skill Check" section (7 Q&A entries).
- Added "Release Preview" section (4 Q&A entries).

**`SUGGESTIONS.md` — updated:**
- Added suggestion #9: add `skill-check.yml` opportunistically to OVOS skill repos.

### Transparency Report

| Field | Value |
|-------|-------|
| Model | Claude Sonnet 4.6 |
| Actions taken | Created 4 new files (2 scripts, 2 workflows); extended test file; updated docs/FAQ/SUGGESTIONS/MAINTENANCE_REPORT |
| Human oversight level | Plan reviewed and approved by user before implementation |

---

## [2026-03-09] — Fourth implementation session: unified PR comment (OVOS PR Checks)

### Changes

**`scripts/update_pr_comment.py` — new shared utility:**
- Manages a single "OVOS PR Checks" comment per PR, identified by `<!-- ovos-pr-checks -->` HTML marker.
- Each check type owns a named section delimited by `<!-- section:X --> … <!-- /section:X -->`.
- Finds-or-creates the comment (paginating the comments API), then regex-replaces or appends the section.
- Stdlib-only (no `requests`), uses `GITHUB_TOKEN` env var.
- All three check workflows (license, security, coverage) now call this script.

**`.github/workflows/license-check.yml`:**
- Added `pr_comment` boolean input (default `true`).
- Added gh-automations scripts checkout step (conditional on `pr_comment && pull_request`).
- Added `continue-on-error: true` to the license checker step so the PR comment always posts, even on failure.
- Added "Format license section" inline Python step — generates `⚖️ License Check` section content.
- Added "Post license section to PR comment" step calling `update_pr_comment.py`.
- Added final "Fail job if license check failed" step to preserve correct check status.

**`.github/workflows/pip-audit.yml`:**
- Added `pr_comment` boolean input (default `true`).
- Added `pip-audit` to the explicit install step so it's available as a CLI command.
- Added gh-automations scripts checkout step (conditional on `pr_comment && pull_request`).
- Added `continue-on-error: true` to the `pypa/gh-action-pip-audit` step.
- Added second pip-audit run (`--format=json`) for structured data to feed the PR comment.
- Added "Format security section" inline Python step — builds a vulnerability table from the JSON.
- Added "Post security section to PR comment" step calling `update_pr_comment.py`.
- Added final "Fail job if audit found vulnerabilities" step to preserve correct check status.

**`.github/workflows/coverage.yml`:**
- Removed `py-cov-action/python-coverage-comment-action@v3` (was posting a separate comment per PR).
- Removed `comment_pr` input — replaced by `pr_comment` (same semantics, now posts to aggregated comment).
- Added gh-automations scripts checkout step (conditional on `pr_comment && pull_request`).
- Added "Format coverage section" inline Python step — generates total %, threshold status, and a collapsible table of under-covered files (files below 80%, or all files if ≤ 10 total).
- Added "Post coverage section to PR comment" step calling `update_pr_comment.py`.
- Moved `Enforce Minimum Coverage Threshold` and `Fail job if tests failed` to the end, after the PR comment.

**`docs/workflow-reference.md`:**
- Updated `license-check.yml`, `pip-audit.yml`, `coverage.yml` inputs tables with `pr_comment`.
- Rewrote `coverage.yml` section to reflect new approach (no py-cov-action, aggregated comment).
- Added new "PR Checks Comment Pattern" section documenting the comment structure, section markers, and how to add new sections from any workflow.
- Added `scripts/update_pr_comment.py` to the Scripts Reference.

### Design

Workflows that run in a PR context and have reviewer-relevant output:

| Workflow | PR context? | Comment section |
|---|---|---|
| `license-check.yml` | ✅ yes | `⚖️ License Check` |
| `pip-audit.yml` | ✅ yes | `🔒 Security (pip-audit)` |
| `coverage.yml` | ✅ yes | `📊 Coverage` |
| `publish-alpha.yml` | ❌ post-merge | N/A |
| `publish-stable.yml` | ❌ push to master | N/A |
| `downstream-check.yml` | ❌ scheduled/push | N/A |
| `sync-translations.yml` | ❌ push/dispatch | N/A |

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Created `scripts/update_pr_comment.py`. Rewrote `license-check.yml`, `pip-audit.yml`, `coverage.yml`. Updated `docs/workflow-reference.md` with PR comment pattern section, `update_pr_comment.py` scripts reference, and updated inputs tables. Updated `MAINTENANCE_REPORT.md`.
- **Oversight**: Decision to use a single aggregated comment (vs separate per-workflow comments) confirmed by user direction. Decision to drop `py-cov-action` in favour of the aggregated comment was a design choice to avoid two separate coverage comments — can be reverted if the diff view is missed.

---

## [2026-03-09] — Third implementation session: reusable coverage workflow (no-codecov)

### Changes

**`.github/workflows/coverage.yml` — new reusable workflow:**
- Runs `pytest --cov` to generate `coverage.xml` and `coverage.json`.
- Writes a coverage summary table to `$GITHUB_STEP_SUMMARY`.
- Uploads `coverage.xml` as a workflow artifact (configurable name and retention days).
- Posts a PR diff comment via `py-cov-action/python-coverage-comment-action@v3` when triggered by `pull_request` events. Uses only `GITHUB_TOKEN` — no external service, no `CODECOV_TOKEN`.
- Optional minimum coverage threshold (`min_coverage` input, default `0` = disabled).
- Configurable `coverage_source` (maps to `--cov=`) so coverage measures only the calling package, not test helpers.
- Falls back gracefully if the package has no `[dev]` extras.

**Docs updated:**
- `docs/workflow-reference.md` — Added full `coverage.yml` section with inputs table, job steps, permissions note, standalone usage, inline usage, and codecov migration guide.
- `FAQ.md` — Added "Coverage Reports" section: why not codecov, how to add coverage, migration guide, PR comment troubleshooting.

### Context

78 of 222 OVOS repos already have some coverage setup (35%). Of those:
- 66 use `codecov/codecov-action` inline in `unit_tests.yml` — external service, requires CODECOV_TOKEN.
- 3 (`ovos-core`, `ovos-skill-count`, `ovos-skill-hello-world`) use `py-cov-action/python-coverage-comment-action@v3` — no external service.
- 7 have a standalone `coverage.yml` with codecov.
- 3 publish HTML reports to `gh-pages`.

The new `coverage.yml` standardises on the no-external-service pattern already established by the three ovos-core repos. Migration for codecov repos is opt-in and opportunistic.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Created `coverage.yml` reusable workflow. Updated `docs/workflow-reference.md` and `FAQ.md`. No existing files modified beyond the two docs files.
- **Oversight**: Coverage pattern (py-cov-action, no codecov) confirmed by user preference. Action version (`@v3`) and behaviour (GITHUB_TOKEN only) verified from survey of existing OVOS repos.

---

## [2026-03-09] — Second implementation session: bot guards, license policy, input ergonomics, notification fixes

### Changes

**`publish-alpha.yml`:**
- Added `skip_bot_prs` input (default `true`) — skips version bump for PRs from `allcontributors[bot]` and `pre-commit-ci[bot]`; renovate/dependabot intentionally still trigger bumps.
- Added `matrix_channel`, `matrix_homeserver`, `matrix_message` inputs — now passed through to the `notify` job rather than being hardcoded.
- `notify` job refactored: now calls `notify-matrix.yml@dev` as a reusable job instead of inlining the matrix action. Uses `format()` for the default message.

**`publish-stable.yml`:**
- Added `notify_matrix`, `matrix_channel`, `matrix_homeserver`, `matrix_message` inputs.
- Added `notify` job — stable releases now announce to Matrix (opt-in via `notify_matrix: true`).

**`notify-matrix.yml`:**
- Removed unnecessary `actions/checkout@v4` step. The Matrix action needs only the token and message.
- Added `runner` input.

**`license-check.yml` — universal donor policy alignment:**
- Upgraded `pilosus/action-pip-license-checker@v0.5.0` → `@v3` (2 major versions).
- Added `fail_licenses` input (default `StrongCopyleft,NetworkCopyleft,WeakCopyleft,Other,Error`) — makes the OVOS universal donor policy explicit in the workflow.
- Changed `exclude_licenses` default from `^(Mozilla).*$` → `^Mozilla Public License.*` (tighter, more intentional).
- Changed `exclude_packages` default from `^(tqdm).*` → `""` (tqdm is now covered by the MPL license exclusion, not name-based exclusion).
- Added `totals: true` and `headers: true` — license report is now readable in CI logs.
- Added a YAML comment block explaining the policy rationale for each category.

**`pip-audit.yml`:**
- Removed `strategy.matrix` (was `["3.10", "3.11"]`) — the `python_version` input was declared but never used because the matrix overrode it. Now uses `inputs.python_version` directly.
- Added YAML comment explaining what `GHSA-r9hx-vwmv-q579` is and why it is ignored.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Reviewed all 6 workflow files. Identified 6 issues (2 high, 3 medium, 1 low). Implemented all fixes. Updated FAQ, AUDIT, and workflow-reference docs. Verified `pilosus/action-pip-license-checker` categories via live README fetch (valid values: `WeakCopyleft`, `StrongCopyleft`, `NetworkCopyleft`, `Copyleft`, `Permissive`, `Other`, `Error`; action now at v3).
- **Oversight**: Universal donor policy framing confirmed by user context. Bot skip list (allcontributors, pre-commit-ci) determined by analysis of which bots open PRs to OVOS dev branches without changing runtime code.

---

## [2026-03-09] — Implementation session: scripts refactor, workflow fixes, new reusable workflows, test suite

### Changes

**Repository fork:**
- gh-automations forked from `TigreGotico/gh-automations` to `OpenVoiceOS/gh-automations` (now the canonical location).
- `TigreGotico/gh-automations` will be archived. GitHub redirects preserve backward compatibility for all existing `uses:` references.
- All internal references updated from `TigreGotico/gh-automations` → `OpenVoiceOS/gh-automations`.

**Workflow improvements (all changes on `dev` branch):**
- `publish-alpha.yml`: Added `ref: dev` to scripts checkout; changed `git checkout -b` → `git checkout -B` (idempotent branch creation); replaced `curl` PR-creation with `gh pr create` guarded by existing-PR check; pinned `pypa/gh-action-pypi-publish@master` → `release/v1`; pinned `pozetroninc/github-action-get-latest-release@master` → `v0.7.0`; migrated `Increment Version` step to use `working-directory: action/github/scripts` for cleaner script invocation.
- `publish-stable.yml`: Added `ref: dev` to scripts checkout; pinned `pypa/gh-action-pypi-publish@master` → `release/v1`; migrated `Declare Alpha stable` step to use `working-directory`.
- `downstream-check.yml`: Added `ref: dev` to scripts checkout; updated org name.
- New: `.github/workflows/sync-translations.yml` — reusable workflow standardising the per-repo `sync_tx.yml` pattern across OVOS skill repos. Fixes `github.actor` detection, standardises action versions, normalises commit message.
- New: `.github/workflows/test.yml` — runs `test/test_scripts.py` on Python 3.10/3.11/3.12.

**Scripts refactor:**
- New: `scripts/_version_utils.py` — shared `read_version`, `format_version`, `write_version_block` functions; correctly scoped within `START_VERSION_BLOCK/END_VERSION_BLOCK` markers; handles inline comments in version values.
- `scripts/update_version.py`: Migrated to use `_version_utils`; added `choices=` validation for `part` argument; added return value (new version string).
- `scripts/get_version.py`: Migrated to use `_version_utils`; simplified to 2 lines of logic.
- `scripts/remove_alpha.py`: Migrated to use `write_version_block` (scoped to block markers); eliminated `fileinput` in-place replacement which was unscoped.
- New: `scripts/migrate_refs.py` — bulk migration tool (`gh` CLI) for opening PRs across repos to change `@master` → `@dev`.

**Tests:**
- New: `test/test_scripts.py` — 30 test cases for `_version_utils`, `update_version`, `get_version`, `remove_alpha`; covers edge cases (stable→alpha bump, inline comments, content outside block preservation, idempotency).

### AI Transparency Report

- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Read all 4 Python scripts, all 6 workflow files, all existing docs. Implemented 6 of 7 SUGGESTIONS from the previous session. Created `_version_utils.py`, updated 3 scripts, rewrote 2 workflow files, updated 1 workflow file, created 3 new files (sync-translations.yml, test.yml, test_scripts.py, migrate_refs.py, _version_utils.py). Updated all docs to reflect new `OpenVoiceOS` org and resolved audit items.
- **Oversight**: Repository fork decision and master-freeze decision provided by human. All code changes derived from direct source analysis.

---

## [2026-03-09] — Branching model change & full documentation overhaul

### Decision

`master` is now **frozen** as the v1 baseline. All active development targets `dev`. Existing repos may continue using `@master` indefinitely; new repos and migrated repos should use `@dev`.

This decision was made because all 209 callers use `@master` without version pinning — any push to `master` immediately affects all callers. By freezing `master` and developing on `dev`, changes become opt-in.

### Changes

**Branching policy:**
- `master` frozen — no further commits. Preserved as v1 baseline for all existing callers.
- `dev` designated as the active development branch.
- `@v2` planned for future tagging from `dev` when breaking changes warrant a major version.

**Documentation — full overhaul:**
- `README.md` — Added versioning/branching policy section; updated all `@master` refs to `@dev` in usage examples; added scripts-checkout note.
- `docs/index.md` — Added branching policy table; added scripts-checkout explanation; expanded cross-references; updated all `@master` refs.
- `docs/release-flow.md` — Added new top-level section "gh-automations Versioning Policy" covering frozen master, active dev, planned v2, breaking-change classification table, migration steps, and scripts-checkout footgun.
- `docs/workflow-reference.md` — Updated all usage examples to `@dev`; added known-issues per workflow; added full Scripts Reference section with citations to source lines.
- `docs/repo-setup.md` — Updated all `@master` refs to `@dev`; added "Migrating an Existing Repo" section; expanded branch protection table.
- `FAQ.md` — Complete rewrite: 30+ Q&A covering versioning, migration, scripts checkout, release flow, bot guards, secrets, and common errors. All answers verified against source code.
- `QUICK_FACTS.md` — Expanded with branching policy table, workflow caller counts, script function citations, version bump rules, and external action risk table.
- `AUDIT.md` — Full rewrite replacing generic stubs: CRITICAL-001 (scripts checkout footgun), HIGH-001 (unpinned third-party actions), MEDIUM-001 (non-idempotent propose_release), MEDIUM-002 (duplicated read_version), LOW-001 (no script tests), LOW-002 (remove_alpha scope), LOW-003 (no migration tooling).
- `SUGGESTIONS.md` — Full rewrite with 7 evidence-backed, source-cited proposals replacing generic stubs.

### Verification

- All source files read before documenting behaviour. Citations verified against actual line numbers in `scripts/*.py` and `.github/workflows/*.yml`.
- No workflow files modified — documentation only.

### AI Transparency Report

- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Read all workflow YAML files, all Python scripts, and all existing docs. Identified branching policy gap, scripts-checkout footgun, unpinned action refs, and propose_release idempotency bug from source analysis. Rewrote all 8 documentation files with source-level citations.
- **Oversight**: Human decision to freeze `master` and activate `dev` was provided as instruction. All architectural details derived from reading actual source files, not assumed.

---

## [2026-03-08] — Initial compliance scaffold

### Changes
- Created `QUICK_FACTS.md` with machine-readable package metadata.
- Created `FAQ.md` with common Q&A.
- Created `MAINTENANCE_REPORT.md` (this file) as the change log.
- Created `SUGGESTIONS.md` with initial improvement proposals.
- Created `docs/index.md` as the documentation entry point.

### Rationale
Establishing the required file set mandated by `AGENTS.md` for all active workspace repositories.

### Verification
- All required files exist at repo root and `docs/` folder.
- No existing content was overwritten.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Generated boilerplate compliance scaffold (QUICK_FACTS, FAQ, MAINTENANCE_REPORT, SUGGESTIONS, docs/index).
- **Oversight**: Files were stubs — human review and enrichment required before treating as authoritative.

---

## 2026-03-10 — Fix downstream-check.yml Python 3.14 default

### Change
- `downstream-check.yml`: Changed default `python_version` from `"3.14"` to `"3.11"`

### Root Cause
Python 3.14 is a pre-release. Packages with C-extension wheels (e.g. `onnxruntime`, depended on by `ovos-stt-plugin-citrinet` and `ovos-tts-plugin-matxa-multispeaker-cat`) have no 3.14 wheels on PyPI. The constraints install step fails with `ResolutionImpossible`, causing daily downstream checks to fail for every repo using this workflow.

### Verification
Confirmed via `gh run view 22884585763 --log` on ovos-bus-client — error was `Cannot install ... because these package versions have conflicting dependencies` with `onnxruntime` as the conflict root.

### AI Transparency Report
- **AI Model**: Claude Sonnet 4.6
- **Actions Taken**: Analysed CI logs; identified Python version as root cause; changed default from 3.14 to 3.11
- **Oversight**: Human should verify next scheduled downstream run passes
