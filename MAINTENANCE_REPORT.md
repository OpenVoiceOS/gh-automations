Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Log the master-freeze / dev-active branching decision and full documentation overhaul.

# Maintenance Report — `gh-automations`

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
