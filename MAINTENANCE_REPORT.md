Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Log the master-freeze / dev-active branching decision and full documentation overhaul.

# Maintenance Report — `gh-automations`

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
