Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Added suggestion #9 — add skill-check.yml opportunistically to OVOS skill repos.

# Suggestions — `gh-automations`

> Proposed improvements for human developers. Each entry cites the specific file and line where the issue is observed, the proposed fix, and the estimated impact.

---

## ~~1. Deduplicate `read_version` logic~~ — DONE 2026-03-09

`scripts/_version_utils.py` created with `read_version` (line 17), `format_version` (line 54), `write_version_block` (line 72). All version scripts import from it. Inline-comment parsing bug also fixed (`split("=", 1)`).

---

## ~~2. Pin third-party action refs~~ — DONE 2026-03-09

`pypa/gh-action-pypi-publish` → `@release/v1`; `pozetroninc/github-action-get-latest-release` → `@v0.7.0`. Remaining: `fadenb/matrix-chat-message@v0.0.6` is pinned to a tag but unmaintained since 2021 — replace when opportunity arises.

---

## ~~3. Pin the scripts checkout ref in reusable workflows~~ — DONE 2026-03-09

`ref: dev` added to all scripts checkout steps in `publish-alpha.yml:100`, `publish-stable.yml:68`, and all new PR-comment workflows.

---

## ~~4. Use `git checkout -B` in `propose_release`~~ — DONE 2026-03-09

`publish-alpha.yml:230` now uses `git checkout -B release-${VERSION}`.

---

## ~~5. Replace `curl` PR creation with `gh pr create`~~ — DONE 2026-03-09

`publish-alpha.yml:244` now uses `gh pr create` with an existing-PR check — fully idempotent on retry.

---

## 6. ~~Bulk-migration script for `@master` → `@dev`~~ — N/A

No longer relevant. All repos should use `@dev`.

---

## ~~7. Test the Python scripts with a matrix of Python versions~~ — DONE 2026-03-09

`test/test_scripts.py` created with 74 tests covering all scripts. `test.yml` CI workflow runs on Python 3.10, 3.11, 3.12.

---

## 8. Standardise coverage reporting — migrate 66 codecov repos to `coverage.yml`

**Problem:** 78 of 222 OVOS repos have some coverage setup. Of those:
- 66 repos use `codecov/codecov-action@v2/v3/v4/v5` inline in `unit_tests.yml` — external service, requires `CODECOV_TOKEN` secret, adds an external dependency to every PR.
- 3 repos (`ovos-core`, `ovos-skill-count`, `ovos-skill-hello-world`) already use `py-cov-action/python-coverage-comment-action@v3` — no external service.
- 7 have standalone `coverage.yml` files calling codecov.
- 144 repos have no coverage at all.

There is no standard approach, `CODECOV_TOKEN` must be managed as an org secret, and codecov bot comments add noise to PRs without a consistent format.

**Available fix:** `coverage.yml` (added 2026-03-09) — a reusable workflow using only `GITHUB_TOKEN`. Produces job summaries, XML artifacts, and PR diff comments via `py-cov-action`. No external account required.

**Migration per repo (opportunistic):** When touching a repo's `.github/workflows/` for any other reason, also:
1. Remove the `codecov/codecov-action` step from `unit_tests.yml`.
2. Add a call to `OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev`.
3. Remove `CODECOV_TOKEN` from repo secrets if it was only used there.

**Do NOT** do a bulk migration wave (same reasoning as `@master` → `@dev` migration in suggestion #6).

**Estimated impact:** Low effort per repo (~15 minutes). Eliminates an external service dependency and standardises the PR coverage experience across all 222 repos.

---

## 9. Add `skill-check.yml` opportunistically to OVOS skill repos

**Problem:** OVOS skill repos have no automated checks for locale completeness, skill.json validity, or gitlocalize readiness. Translation gaps (e.g. a language added to en-us but not ported to de-de) are only caught at release time or by user reports.

**Available fix:** `skill-check.yml` (added 2026-03-09) — a reusable workflow that posts a `🎙️ Skill` section to the OVOS PR Checks comment on every PR. No external service, no extra secrets.

**Migration per repo (opportunistic):** When touching a skill repo's `.github/workflows/` for any other reason, also add:

```yaml
# .github/workflows/skill-check.yml
name: Skill Check
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:

jobs:
  skill_check:
    uses: OpenVoiceOS/gh-automations/.github/workflows/skill-check.yml@dev
    secrets: inherit
```

Default settings are safe for all repos: `skip_if_not_skill: true` means non-skill repos silently pass. `fail_on_invalid_skill_json: false` means the job is informational only until maintainers opt in to stricter enforcement.

**Do NOT** do a bulk migration wave.

**Estimated impact:** Trivial per repo (~5 minutes). Gives maintainers locale coverage at a glance on every PR and nudges them toward better gitlocalize integration.
