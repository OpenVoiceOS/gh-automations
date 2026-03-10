
# Audit Report — `gh-automations`

> Evidence-based findings from direct code analysis. All references include file and line number.

---

## Critical Issues

### ~~[CRITICAL-001] Scripts checkout has no pinned ref~~ — RESOLVED 2026-03-09

**Was:** `publish-alpha.yml`, `publish-stable.yml`, and `downstream-check.yml` all checked out `OpenVoiceOS/gh-automations` without a `ref:`, defaulting to the GitHub default branch regardless of the caller's `@master`/`@dev` ref.

**Fix applied:** Added `ref: dev` to all three workflow checkout steps. All callers now explicitly execute scripts from the `dev` branch.

---

## High Issues

### ~~[HIGH-001] Third-party actions pinned to `@master`~~ — RESOLVED 2026-03-09

**Was:** `pypa/gh-action-pypi-publish@master` in both `publish-alpha.yml` and `publish-stable.yml`; `pozetroninc/github-action-get-latest-release@master` in `publish-alpha.yml`.

**Fix applied:**
- `pypa/gh-action-pypi-publish` → pinned to `@release/v1` in both workflow files.
- `pozetroninc/github-action-get-latest-release` → pinned to `@v0.7.0`.

**Note:** `fadenb/matrix-chat-message@v0.0.6` is pinned to a tag but has not been updated since 2021 — consider replacing with a maintained alternative when time allows.

---

## Medium Issues

### ~~[MEDIUM-001] `propose_release` job is not idempotent~~ — RESOLVED 2026-03-09

**Was:** `git checkout -b release-${VERSION}` failed on retry if the branch already existed. PR creation used `curl` without checking for an existing PR.

**Fix applied:** Changed to `git checkout -B release-${VERSION}` (force-create). Replaced the `curl` PR-creation call with `gh pr create` guarded by a check for an existing open PR with the same head/base. Both steps are now idempotent on retry.

---

### ~~[MEDIUM-002] `read_version` logic is duplicated across two scripts~~ — RESOLVED 2026-03-09

**Fix applied:** Extracted shared logic into `scripts/_version_utils.py` (`read_version` at line 17, `format_version` at line 54, `write_version_block` at line 72). All version scripts now import from it. `remove_alpha.py` migrated to use `write_version_block` (resolving LOW-002 simultaneously).

**Additional fix (2026-03-09):** `_version_utils.py:43-49` — `split("=")[-1]` changed to `split("=", 1)[1]` so inline comments containing `=` (e.g. `VERSION_ALPHA = 0   # 0 = stable`) are parsed correctly.

---

## Low / Documentation Issues

### ~~[LOW-001] No unit tests for scripts~~ — RESOLVED 2026-03-09

**Fix applied:** Created `test/test_scripts.py` with 30 test cases covering `_version_utils`, `update_version`, `get_version`, and `remove_alpha`. Created `.github/workflows/test.yml` running tests on Python 3.10, 3.11, 3.12.

---

### ~~[LOW-002] `remove_alpha.py` does not scope to the version block~~ — RESOLVED 2026-03-09

**Fix applied:** `remove_alpha.py` now uses `write_version_block()` from `_version_utils.py`, which reads the full block first and rewrites only the block section. No longer uses `fileinput` in-place replacement.

---

### [LOW-003] Migration of 209 repos from `@master` → `@dev`

**Finding:** 209 repos currently call `@master`. There is no automated migration process.

**Decision (2026-03-09):** Bulk migration via script was considered and rejected (too risky — 209 unreviewed PRs). Migration will happen **opportunistically**: any time an agent or developer touches a repo's `.github/workflows/` files for another reason, they also update `@master` → `@dev` in the same PR. This rule is documented in workspace `AGENTS.md § 6`. No active tracking required; `@master` is frozen and safe indefinitely.

---

## Issues Resolved in Second Implementation Session (2026-03-09)

### ~~[HIGH-002] `license-check.yml` uses `pilosus/action-pip-license-checker@v0.5.0` (2 major versions behind)~~ — RESOLVED

**Was:** `@v0.5.0`. Current is `@v3`. Old version predates `StrongCopyleft`, `NetworkCopyleft` separate categories and other improvements.

**Fix applied:** Upgraded to `@v3`.

### ~~[HIGH-003] License check `fail` categories are opaque and misconfigured for universal donor policy~~ — RESOLVED

**Was:** `fail: 'Copyleft,Other,Error'` — `Copyleft` is an alias for all copyleft subtypes but doesn't make the policy readable. Old default `exclude_packages: '^(tqdm).*'` excluded by package name rather than by license (fragile). Old `exclude_licenses: '^(Mozilla).*$'` regex was too broad.

**Fix applied:** Changed default `fail_licenses` to `StrongCopyleft,NetworkCopyleft,WeakCopyleft,Other,Error` (explicit, policy-aligned). Changed `exclude_licenses` default to `^Mozilla Public License.*` (tighter regex, covers tqdm via license not name). Removed `tqdm` package exclusion. Added `fail_licenses` as a configurable input for repos with specific known exceptions.

### ~~[MEDIUM-003] `publish-alpha.yml` has no bot guards for maintenance bots~~ — RESOLVED

**Was:** Any merged PR triggered a version bump, including PRs from `allcontributors[bot]` (docs-only) and `pre-commit-ci[bot]` (formatting-only).

**Fix applied:** Added `skip_bot_prs` boolean input (default `true`). When enabled, PRs from `allcontributors[bot]` and `pre-commit-ci[bot]` do not trigger a version bump. Dep-update bots (renovate, dependabot) intentionally still trigger bumps.

### ~~[MEDIUM-004] Matrix notification inputs not passable through `publish-alpha.yml`~~ — RESOLVED

**Was:** The built-in `notify` job hardcoded the channel, homeserver, and message. Repos could not customise without calling `notify-matrix.yml` separately.

**Fix applied:** Added `matrix_channel`, `matrix_homeserver`, `matrix_message` inputs to both `publish-alpha.yml` and `publish-stable.yml`.

### ~~[MEDIUM-005] No Matrix notification on stable release~~ — RESOLVED

**Was:** `publish-stable.yml` had no notification job. Alpha merges notified; stable releases did not.

**Fix applied:** Added `notify_matrix` input and `notify` job to `publish-stable.yml`.

### ~~[LOW-004] `notify-matrix.yml` runs unnecessary `actions/checkout`~~ — RESOLVED

**Was:** `notify-matrix.yml` checked out the repo before sending a Matrix message. The checkout serves no purpose — the action only needs the token and message.

**Fix applied:** Removed the `checkout` step.

### ~~[LOW-005] `pip-audit.yml` `python_version` input is dead~~ — RESOLVED

**Was:** The `pip_audit` job used `strategy.matrix: python-version: ["3.10", "3.11"]` which overrode `inputs.python_version` entirely. The input was declared but never used.

**Fix applied:** Removed the `strategy.matrix` block. The job now uses `inputs.python_version` directly. Running on a single configurable version is consistent with other workflows and matches what callers expect.

---

## New Scripts Added (2026-03-09)

### `scripts/check_skill.py` — OVOS skill analyser

Analyses a checked-out skill repo: locale structure, en-us file counts, skill.json required fields (`skill_id`, `name`, `description`, `examples`, `tags`), per-language translation coverage, gitlocalize readiness. Used by `skill-check.yml` reusable workflow.

- `run_checks()` — `scripts/check_skill.py:220`
- Stdlib only. Exits 0 always.

### `scripts/check_release.py` — Next-version predictor

Reads `version.py`, predicts next version from PR labels/title using `CONVENTIONAL_PREFIXES` map. Mirrors `update_version.py:22` bump rules exactly. Used by `release-preview.yml` reusable workflow.

- `run_checks()` — `scripts/check_release.py:196`
- Stdlib only. Exits 1 only for malformed `version.py`.

---

## Documentation Gaps (Resolved in This Session)

| Item | Status |
|---|---|
| Versioning policy for gh-automations itself | ✅ Documented in `docs/release-flow.md`, `docs/index.md`, `README.md` |
| `@master` freeze announcement | ✅ Documented in all major doc files |
| Migration guide (`@master` → `@dev`) | ✅ Documented in `docs/repo-setup.md` |
| Scripts checkout footgun | ✅ Documented in `docs/index.md`, `docs/release-flow.md`, this file |
| Source-level citations in all docs | ✅ Added throughout `docs/workflow-reference.md` |
| Evidence-backed SUGGESTIONS.md | ✅ Replaced generic stubs with 7 specific proposals |
