
# AUDIT.md — `gh-automations`

> Evidence-based record of known issues, technical debt, and security risks.
> Each entry cites `file:LINE` and includes recommended action.
> Last updated: 2026-03-13.

---

## Open Issues

### A-001 — Deprecated workflows have no scheduled removal date

**Severity:** Low — no runtime impact; adds maintenance burden.

**Files:**
- `.github/workflows/coverage-pages.yml:1-4` — superseded by `coverage.yml deploy_pages: true`
- `.github/workflows/python-support.yml:1-9` — superseded by `build-tests.yml`

**Detail:**
Both files carry deprecation notices (added 2026-03-10) but no hard EOL date.
Callers who never migrate will continue to receive updates even after the workflows are obsolete.

**Recommended action:**
- Add `# REMOVE AFTER: 2027-01-01` comment (done in this session).
- Before removal, verify zero active callers in `docs/repos.md`.

---

### A-002 — `continue-on-error: true` on tool steps (silent pass-through risk)

**Severity:** Low — by design, but requires discipline to maintain.

**Files:**
- `.github/workflows/skill-check.yml:65-68` — `Run skill check` step
- `.github/workflows/pip-audit.yml:87-90` — `Run pip-audit` step
- `.github/workflows/coverage.yml:108-120` — `Run Tests with Coverage` step
- `.github/workflows/opm-check.yml:120-122` — `Verify OPM Detection (wheel install)` step

**Detail:**
The pattern `continue-on-error: true` → format section → post PR comment → explicit `exit 1` is correct and intentional.
The risk is that a future contributor removes the "re-raise" step at the end, making tool failures invisible.

**Recommended action:**
Add a comment on every `continue-on-error: true` step cross-referencing the mandatory re-raise step.
The three-phase pattern is documented in `skill-check.yml:5-8` and should be applied consistently.

---

### A-003 — Vendor-pinned third-party actions at older patch versions

**Severity:** Medium — supply chain risk if upstream repos are compromised.

**Files (external action references):**

| Workflow | Action | Version | Risk |
|----------|--------|---------|------|
| `.github/workflows/opm-check.yml` | `actions/checkout@v4` | v4 floating tag | Low — trusted GH action |
| `.github/workflows/opm-check.yml` | `actions/upload-artifact@v4` | v4 floating tag | Low |
| `.github/workflows/pip-audit.yml` | `github/codeql-action/upload-sarif@v4` | v4 floating tag | Low |
| `.github/workflows/build-tests.yml` | `ad-m/github-push-action@v0.8.0` | v0.8.0 pinned tag | Medium — less-maintained action |
| `.github/workflows/release-preview.yml` | `pozetroninc/github-action-get-latest-release@v0.7.0` | v0.7.0 pinned tag | Medium — less-maintained action |

**Detail:**
`ad-m/github-push-action` and `pozetroninc/github-action-get-latest-release` are third-party actions
with limited maintenance activity. Using a floating `@v0.x.y` tag means a compromised tag would execute
arbitrary code with the calling repo's `GITHUB_TOKEN`. SHA-pinning is the gold standard.

**Recommended action:**
Replace third-party action tags with full commit SHAs:
```yaml
# Before:
uses: ad-m/github-push-action@v0.8.0
# After (example — verify current SHA):
uses: ad-m/github-push-action@d91a481090679876  # v0.8.0
```
Run `gh api repos/ad-m/github-push-action/git/ref/tags/v0.8.0` to get the current SHA.

---

### A-004 — `coverage-pages.yml` still uses `python -m pip` (not `uv`)

**Severity:** Low — only affects the deprecated workflow; callers that haven't migrated still use it.

**File:** `.github/workflows/coverage-pages.yml:64-73`

**Detail:**
The deprecated `coverage-pages.yml` uses `python -m pip install` directly. The workspace standard
(CLAUDE.md §2) is `uv`. Since this file is deprecated and frozen for backwards compatibility,
migration is deferred until removal.

**Recommended action:** Deferred — no action until `coverage-pages.yml` is removed (A-001).

---

### A-005 — `python-support.yml` still uses `pip install` directly

**Severity:** Low — deprecated workflow.

**File:** `.github/workflows/python-support.yml:82-95`

**Detail:** Same as A-004 — deprecated file, frozen for compat.

**Recommended action:** Deferred — remove the file on 2027-01-01 per A-001.

---

### A-006 — `repo-health.yml` uses Python 3.14 (pre-release)

**Severity:** Low — cosmetic; Python 3.14 is not yet stable (as of 2026-03-11).

**File:** `.github/workflows/repo-health.yml:42`

```yaml
python-version: "3.14"
```

**Detail:**
Using a pre-release Python version for infrastructure workflows is unusual. The default should be
`3.11` (stable LTS) or `3.12`. This was likely set during Python 3.14 matrix testing work.

**Recommended action:**
Change default `python_version` to `"3.11"` in `repo-health.yml` and any other workflows
that default to `"3.14"`.

---

### A-007 — No workflow integration tests

**Severity:** Medium — workflow YAML errors are only caught when workflows run in CI.

**Detail:**
`test/test_scripts.py` covers all Python scripts thoroughly (156 tests as of 2026-03-10).
However, the 18 YAML workflow files themselves are not validated programmatically.
A missing `on.workflow_call.inputs` key, a bad `uses:` ref, or a YAML syntax error will
only surface when the workflow is triggered in a real repo.

**Recommended action:**
Create `test/test_workflow_inputs.py` to:
- Parse each `.github/workflows/*.yml` and verify it is valid YAML.
- Assert `on.workflow_call.inputs` exists for all reusable workflows.
- Verify required inputs are present (at minimum: `runner`, `pr_comment`).
- Check that all `uses:` refs inside workflows are pinned to a version tag or SHA.

See `test/test_workflow_inputs.py` (created in this session).

---

### A-008 — 66 OVOS repos still upload to codecov (external service dependency)

**Severity:** Low — cosmetic and operational; no security risk, but adds an org secret dependency.

**Detail (from `SUGGESTIONS.md:52-57`):**
66 repos use `codecov/codecov-action@v2-v5`, which requires a `CODECOV_TOKEN` secret and
external service availability. `coverage.yml` (added 2026-03-09) provides a self-hosted alternative
using only `GITHUB_TOKEN`.

**Recommended action:** Migrate opportunistically per `SUGGESTIONS.md #8`.

---

## Resolved Issues

| ID | Description | Resolution | Date |
|----|-------------|------------|------|
| R-001 | `fadenb/matrix-chat-message` action abandoned | Replaced with inline `curl` to Matrix CS API v3 | 2026-03-10 |
| R-002 | `@master` refs in reusable workflows | All scripts checkout refs changed to `ref: dev` | 2026-03-09 |
| R-003 | Python 3.14 wheel unavailability in downstream check | Changed default Python to 3.11 for downstream-check | 2026-03-10 |
| R-004 | OPM editable-install entry-point registration bugs | Added editable check phase to `opm-check.yml` | 2026-03-10 |
| R-005 | `read_version` duplicated across all version scripts | Extracted to `scripts/_version_utils.py` | 2026-03-09 |
| R-006 | Missing tests for `update_pr_comment.py` | `test/test_update_pr_comment.py` added (26 tests) | 2026-03-10 |
| R-007 | No CI check for locale packaging configuration | `locale-check.yml` workflow + `check_locale_build.py` script (11 tests) | 2026-03-13 |

---

## Technical Debt

| Area | Debt | File | Priority |
|------|------|------|----------|
| Workflows | No YAML integration tests | `test/` (missing file) | Medium |
| Workflows | `coverage-pages.yml` and `python-support.yml` not yet removed | `.github/workflows/` | Low |
| Scripts | `update_pr_comment.py` is 2000+ lines — monolithic | `scripts/update_pr_comment.py` | Low |
| Docs | `docs/repos.md` manually maintained — may drift from actual callers | `docs/repos.md` | Low |
| Actions | `ad-m/github-push-action` and `pozetroninc/github-action-get-latest-release` not SHA-pinned | `.github/workflows/build-tests.yml`, `release-preview.yml` | Medium |
