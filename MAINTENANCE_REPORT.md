Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Added skill-check.yml, release-preview.yml, check_skill.py, check_release.py; updated tests, docs, FAQ, SUGGESTIONS.

# Maintenance Report — `gh-automations`

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
