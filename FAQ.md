
# FAQ — `gh-automations`

## General

### What is `gh-automations`?

`gh-automations` is the shared GitHub Actions automation library for all OpenVoiceOS repositories. It provides reusable workflows (in `.github/workflows/`) and Python scripts (in `scripts/`) that implement the OVOS rolling-release model: automated version bumping, alpha publishing to PyPI, and stable release gating via human-reviewed PRs.

### Where is it hosted?

[OpenVoiceOS/gh-automations](https://github.com/OpenVoiceOS/gh-automations) — the canonical location since 2026-03-09. It is not a Python package you install — it is a GitHub repository that other repos call via the `uses:` directive in their workflow files.

The original `TigreGotico/gh-automations` is now archived. GitHub preserves redirects, so existing repos that still reference `TigreGotico/gh-automations` will continue to work, but should be updated to `OpenVoiceOS/gh-automations` opportunistically.

### How many repos use it?

209 OVOS repositories as of 2026-03-09. See [docs/repos.md](docs/repos.md) for the full list.

---

## Versioning & Branching of gh-automations Itself

### Which ref should new repos use — `TigreGotico/gh-automations@@master` or `OpenVoiceOS/gh-automations@dev`?

`OpenVoiceOS/gh-automations@dev`. The `TigreGotico/gh-automations@master` branch of gh-automations is **frozen** as the v1 baseline. All active development — bug fixes, new features, improvements — targets `dev`. New repos and repos that opt in via migration should call `@dev`.

### Will `TigreGotico/gh-automations@master` stop working?

No. `master` is frozen, not deleted. Repos still calling `@master` will continue to receive exactly the same behaviour they always have. There is no deadline to migrate.

### What is `[OpenVoiceOS/gh-automations@dev` and how is it different from `TigreGotico/gh-automations@master`?

`OpenVoiceOS/gh-automations@dev` is the active development branch. After the freeze, `OpenVoiceOS/gh-automations@dev` will receive:
- Bug fixes (e.g. pinning third-party action refs)
- New optional inputs (fully backward-compatible)
- Documentation improvements
- Any improvements that don't break existing callers

### When will `@v2` be tagged?

When enough breaking changes accumulate to warrant a formal major version — e.g. input renames, removed jobs, changed output names. There is no fixed timeline.

### What counts as a breaking change?

Changes that require callers to update their workflow files:
- Removing or renaming an existing input
- Removing or renaming an existing job (breaks callers that use `needs:`)
- Removing or renaming an existing output
- Changing an existing input's default value in a behaviour-altering way
- Adding a new required input (no default)

Adding new optional inputs with sensible defaults is **not** breaking.

### How do I migrate from `@master` to `@dev`?

In each repo's `.github/workflows/` files, replace:
```
OpenVoiceOS/gh-automations/.github/workflows/foo.yml@master
```
with:
```
OpenVoiceOS/gh-automations/.github/workflows/foo.yml@dev
```

Open a PR, wait for CI, merge. No functional changes on day one.

---

## Scripts Checkout

### The workflows checkout `OpenVoiceOS/gh-automations` without a ref — what branch does that use?

It uses whichever branch is set as the **GitHub default branch** of `OpenVoiceOS/gh-automations`, regardless of whether the calling workflow uses `@master` or `@dev`.

This means:
- While `master` is the GitHub default branch → all callers (both `@master` and `@dev`) run scripts from `master`.
- If the default branch is changed to `dev` → all callers run scripts from `dev`.

See [SUGGESTIONS.md](SUGGESTIONS.md#3-pin-the-scripts-checkout-ref-in-reusable-workflows) for the proposed fix (add `ref:` to the checkout step).

### Why don't the workflows pin a ref when checking out scripts?

Historical omission. The scripts have been stable and the default branch has always matched the intended source. It is a known risk — see [AUDIT.md](AUDIT.md).

---

## Release Flow

### What triggers a version bump?

A PR merge to `dev` in the target repo. The `release_workflow.yml` fires, calls `publish-alpha.yml@dev`, which reads PR labels set by `conventional-label.yaml` to determine the bump type.

### How are PR labels mapped to version bumps?

| PR title prefix | Label | Bump |
|---|---|---|
| `BREAKING CHANGE:` | `breaking` | major |
| `feat:` | `feature` | minor |
| `fix:` | `fix` | build |
| anything else | _(none)_ | alpha only |

See `update_version.py:37-52` for the bump logic and `publish-alpha.yml:69-107` for the label detection.

### What happens if I merge a PR without any conventional-commit prefix?

The version alpha counter increments only: e.g. `1.2.3a4` → `1.2.3a5`. If the current version is already stable (`VERSION_ALPHA == 0`), the build number increments first, then alpha is set to 1: `1.2.3` → `1.2.4a1` (see `update_version.py:50-52`).

### What is `propose_release` and how does the release PR get created?

When `propose_release: true` (the default), `publish-alpha.yml` creates a branch named `release-X.Y.ZaN` from `dev` and opens a PR to `master` using the GitHub API (see `publish-alpha.yml:178-203`). A human must review and merge this PR to trigger the stable release.

### What happens when the release PR is merged?

`publish_stable.yml` in the calling repo fires on `push: master`. It calls `publish-stable.yml@dev`, which runs `remove_alpha.py` to set `VERSION_ALPHA = 0`, commits and pushes to `master`, then creates a GitHub release tag.

### How do I rerun a failed release workflow?

Both `release_workflow.yml` and `publish_stable.yml` support `workflow_dispatch`. Go to the repo → Actions → select the workflow → Run workflow.

The `publish_alpha` job condition includes `|| github.event_name == 'workflow_dispatch'` so manual dispatch works even without a PR event.

### Can two PRs merged in quick succession cause a version conflict?

Yes, if the first run hasn't committed the version bump before the second run reads `version.py`. This is a known race condition. In practice it is rare and resolves by rerunning the failed job manually.

---

## Bot Guards & Infinite Loop Prevention

### Why does `publish_stable.yml` check `github.actor != 'github-actions[bot]'`?

`git-auto-commit-action` pushes the version commit (removing the alpha suffix) to `master`. Without the guard, this push would trigger another `push: master` event → another run of `publish_stable.yml` → another attempt to remove an already-absent alpha suffix and tag an already-existing tag → failure or loop.

The guard is at `publish-stable.yml:37` in gh-automations and also in the calling repo's `publish_stable.yml` job condition. Both layers are required for full protection.

### Why is the bot guard in both places?

Belt and suspenders. If only the reusable workflow had it, a misconfigured calling repo could still loop. If only the calling repo had it, a future change to the reusable workflow that bypassed the guard would break everything. Both layers ensure the protection holds regardless of which side changes.

### Does `publish-alpha.yml` have a bot loop risk?

Much lower risk. The `bump_version` job condition (`merged == true || workflow_dispatch`) blocks runs from closed-but-unmerged PRs and from random push events. However if someone force-pushes to `dev` as `github-actions[bot]` and the PR event condition is met, a loop is theoretically possible. In practice this has not been observed.

---

## Secrets & Permissions

### What secrets do I need?

| Secret | Required for |
|--------|-------------|
| `PYPI_TOKEN` | Publishing to PyPI (alpha and stable) |
| `MATRIX_TOKEN` | Matrix notifications via `notify-matrix.yml` |

For organisation repos these are typically set at org level and inherited automatically via `secrets: inherit`.

### Why does the workflow use `secrets: inherit`?

Reusable workflows do not automatically receive the calling repo's secrets — they must be explicitly forwarded. `secrets: inherit` passes all of the caller's secrets to the reusable workflow. This is the standard approach for organisation-managed secrets.

### Do I need `id-token: write` permissions for PyPI publishing?

No. All OVOS workflows use `PYPI_TOKEN` (token-based auth via `pypa/gh-action-pypi-publish`). OIDC trusted publishing (`id-token: write`) is **not used and must not be added**. Adding `id-token: write` to a caller workflow that calls `publish-stable.yml` or `publish-alpha.yml` will cause GitHub to reject the workflow with "nested job is requesting id-token: write but is only allowed id-token: none."

The only permissions needed on caller workflows are:
```yaml
permissions:
  contents: write        # for git-auto-commit-action version bumps
  pull-requests: write   # for release PR creation (release_workflow.yml only)
```

---

## Bot Guards

### Which bots trigger a version bump?

Any merged PR to `dev` triggers `publish-alpha.yml` → version bump. For bots:

| Bot | Triggers bump? | Rationale |
|---|---|---|
| `renovate[bot]` | **Yes** | Dep update = new alpha is correct |
| `dependabot[bot]` | **Yes** | Dep update = new alpha is correct |
| `allcontributors[bot]` | **No** (when `skip_bot_prs: true`) | Doc-only, no code change |
| `pre-commit-ci[bot]` | **No** (when `skip_bot_prs: true`) | Formatting/linting, no code change |
| `gitlocalize-app[bot]` | **No** | Pushes directly to `dev`, not via PR — never triggers `pull_request` event |
| `github-actions[bot]` | **No** | Blocked in `publish-stable.yml`; doesn't open PRs to dev in normal operation |

### How do I disable bot PR skipping?

Set `skip_bot_prs: false` in your `release_workflow.yml`. All merged PRs, including from maintenance bots, will then bump the version.

### What if a bot I use is not on the skip list?

The `skip_bot_prs` input only skips `allcontributors[bot]` and `pre-commit-ci[bot]`. To skip additional bots, call `publish-alpha.yml` with `skip_bot_prs: false` and add your own `if:` condition on the calling job:

```yaml
jobs:
  publish_alpha:
    if: |
      (github.event.pull_request.merged == true &&
       github.event.pull_request.user.login != 'mybot[bot]') ||
      github.event_name == 'workflow_dispatch'
    uses: OpenVoiceOS/gh-automations/.github/workflows/publish-alpha.yml@dev
    with:
      skip_bot_prs: false
      ...
```

---

## Workflow Script Checkout

### Why do some workflows fail with "file not found" on non-PR events?

Prior to 2026-03-10, `skill-check.yml`, `release-preview.yml`, and `repo-health.yml` conditionally checked out the gh-automations scripts **only** when the workflow was triggered by a `pull_request` event. However, the script run steps had no matching condition, so if the workflow fired via `workflow_dispatch` or `push`, the scripts path would not exist → immediate job failure.

**Fix (2026-03-10)**: The checkout step is now unconditional in all three workflows. The scripts are always available. Individual post-comment steps still have their own conditions for PR-specific actions (e.g. posting to the PR comment only on `pull_request` events).

### What workflows were affected?

`skill-check.yml`, `release-preview.yml`, and `repo-health.yml`.

### What was the user impact?

Skill repos or repos using these workflows with `workflow_dispatch` triggers would experience job failures. The fix is transparent to callers.

---

## License Check & Universal Donor Policy

### What is the OVOS universal donor policy?

OVOS packages are Apache 2.0. This is a permissive "universal donor" license — it can be included in GPL, proprietary, or any other project. To preserve this, OVOS packages must not **depend on** licenses that would restrict redistribution.

### Which license categories fail the check?

By default:

| Category | What it covers | Fails? |
|---|---|---|
| `StrongCopyleft` | GPL v2, GPL v3 | **Yes** — incompatible with Apache 2.0 |
| `NetworkCopyleft` | AGPL | **Yes** — triggered by network use |
| `WeakCopyleft` | LGPL, EUPL | **Yes** (conservative) — flag for review |
| `Other` | EULA, non-standard | **Yes** — unknown terms |
| `Error` | package not found | **Yes** — can't audit unknown |
| MPL | Mozilla Public License | **No** — file-level copyleft, safe as library |

### Why is LGPL in the fail list?

LGPL is technically safe to *use* as a library (no modification of LGPL code). However the default policy flags it for human review so maintainers make a conscious decision. A repo with a known, acceptable LGPL dep can exclude it by package name via `exclude_packages`.

### Why is MPL allowed?

MPL-2.0 is file-level copyleft: only the MPL-licensed *files themselves* must remain open if modified. Using an MPL library from Apache 2.0 code (without modifying the MPL files) is safe. The default `exclude_licenses: '^Mozilla Public License.*'` allows it.

### How do I allow a specific LGPL package I know is safe?

```yaml
jobs:
  license_tests:
    uses: OpenVoiceOS/gh-automations/.github/workflows/license-check.yml@dev
    with:
      exclude_packages: '^(chardet|some-lgpl-package).*'
```

### Why was `tqdm` excluded by name in the old config?

tqdm uses MPL-2.0. The old config excluded it by name (`^(tqdm).*`) which was fragile. The new config excludes MPL by license name via `exclude_licenses: '^Mozilla Public License.*'`, which covers tqdm and any other MPL package automatically.

---

## Translation Sync

### What is `sync-translations.yml`?

A reusable workflow that standardises the per-repo `sync_tx.yml` translation sync pattern. It runs `scripts/sync_translations.py` (in the calling repo) when `gitlocalize-app[bot]` pushes a commit, or on manual dispatch.

### Why replace the per-repo `sync_tx.yml` with this?

The per-repo files have inconsistencies:
- Some use `actions/checkout@v2` and `actions/setup-python@v1` (deprecated).
- Some use `github.event.head_commit.author.username` for bot detection — this is unreliable. The correct field is `github.actor`.
- `stefanzweifel/git-auto-commit-action` versions vary (`@v4`, `@v5`, `@v7`).
- Commit messages differ across repos.

The reusable workflow fixes all of these in one place.

### How do I migrate a skill repo's `sync_tx.yml`?

Replace the entire file with:

```yaml
name: Sync Translations
on:
  workflow_dispatch:
  push:
    branches: [dev]

jobs:
  sync_translations:
    uses: OpenVoiceOS/gh-automations/.github/workflows/sync-translations.yml@dev
    secrets: inherit
    with:
      branch: dev
```

---

## Common Errors

### "Tag already exists" error in `tag_release`

The stable release tag (e.g. `1.2.3`) was already created by a previous run. This usually means `publish_stable.yml` ran twice (the bot guard failed or was missing). Check that both the calling job and `publish-stable.yml:37` have the `github.actor != 'github-actions[bot]'` guard.

### `propose_release` fails with "branch already exists"

`git checkout -b release-X.Y.ZaN` fails if the branch was already created by a previous run attempt. Manually delete the branch (`git push origin --delete release-X.Y.ZaN`) then rerun. See [SUGGESTIONS.md](SUGGESTIONS.md#4-use-git-checkout--b-in-propose_release) for the proposed permanent fix.

### Version file not found

The `version_file` input path is relative to the repository root. If your `version.py` is at `my_package/version.py`, pass `version_file: 'my_package/version.py'`. The default `version.py` only works if the file is at the repo root.

### PyPI publish fails with "File already exists"

A package with that version was already uploaded. This happens when `python -m build` is run twice for the same version. Rerun after bumping the alpha counter manually in `version.py`, or skip if the package is already on PyPI.

---

## Coverage Reports

### Why not codecov?

OVOS uses `coverage.yml` — a reusable workflow in this repo — which stores reports as GitHub workflow artifacts and posts PR diff comments using only `GITHUB_TOKEN`. No external service, no `CODECOV_TOKEN` to manage, no bot account on the repo.

`py-cov-action/python-coverage-comment-action@v3` (used by `ovos-core`, `ovos-skill-count`, and `ovos-skill-hello-world`) does the PR comment part. It reads `coverage.xml`, diffs against the base branch automatically, and posts the result to the PR thread using `GITHUB_TOKEN`.

### How do I add coverage to my repo?

Add a `coverage.yml` in `.github/workflows/`:

```yaml
name: Coverage
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:

jobs:
  coverage:
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'   # measure only your own code
      min_coverage: 80                # optional: fail below 80%
```

### Can I run coverage as part of my existing `unit_tests.yml`?

Yes. Add a job that depends on your test job:

```yaml
  coverage:
    needs: unit_tests
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'
```

Note: you'll need to generate `coverage.xml` in your test job and share it (via artifact upload/download) OR let `coverage.yml` run its own pytest pass. The simplest approach is a standalone `coverage.yml` that runs independently on each PR.

### How do I migrate away from codecov?

1. Remove the `codecov/codecov-action` step (or the standalone `coverage.yml` that calls it).
2. Add a call to `OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev` (see above).
3. Remove `CODECOV_TOKEN` from your repo secrets if it was only used for coverage upload.

No badge URL changes are needed if you were only using the Codecov bot comment — the new PR comment comes from GitHub Actions directly.

### What does the coverage report look like?

- **Job summary**: A Markdown table showing total coverage %, Python version, and source path. Visible in the Actions run page.
- **Artifact**: `coverage.xml` uploaded as a workflow artifact (default retention: 14 days). Useful for local analysis with `coverage report`.
- **PR comment**: A diff table showing which lines in changed files gained or lost coverage, posted by `py-cov-action`. Only appears on `pull_request` events.

### Can I enforce a minimum coverage percentage?

Yes. Set `min_coverage: 80` (or any integer). The job will fail if total coverage falls below this threshold. Default is `0` (disabled).

### The PR comment is not appearing — why?

`comment_pr: true` only fires on `pull_request` events. If you trigger the workflow via `workflow_dispatch` or `push`, no comment is posted (but the job summary is still written). Also check that the workflow has `pull-requests: write` permission — the reusable workflow declares this internally, but if the calling job overrides `permissions:` to a stricter set, comments will fail silently.

---

### How do I deploy coverage reports to GitHub Pages?

Use the dedicated `coverage-pages.yml` reusable workflow. It runs tests with coverage and deploys the HTML report to GitHub Pages on push to `dev` (not on PRs). This is separate from `coverage.yml`, which handles PR comments.

```yaml
name: Coverage Pages
on:
  push:
    branches: [dev]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  coverage_pages:
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage-pages.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'
```

**Prerequisites**: Enable Pages in repo Settings → Pages → Source → "GitHub Actions".

### Why are coverage.yml and coverage-pages.yml separate workflows?

`coverage.yml` runs on PRs and posts results to the PR comment — it only needs `pull-requests: write` and `contents: read`. `coverage-pages.yml` deploys to GitHub Pages and needs `pages: write` and `id-token: write` (OIDC). If these permissions were in `coverage.yml`, repos without Pages enabled would get `startup_failure` errors because GitHub rejects jobs requesting `pages: write` when Pages is not configured.

### `update_changelog` step fails

`github-changelog-generator-action@v2.3` requires `GITHUB_TOKEN` to read issues and PRs. Ensure `secrets: inherit` is set on the `publish_alpha` job. Also check that the repo has at least one closed issue or merged PR — empty changelogs sometimes cause the action to error.

---

## Skill Check

### What does `skill-check.yml` do?

It runs `scripts/check_skill.py` against the checked-out repo and posts a `🎙️ Skill` section to the OVOS PR Checks comment. Checks include:

- **is_skill** — looks for `ovos.plugin.skill` in `setup.py`, `pyproject.toml`, or `setup.cfg`
- **Locale directory** — auto-detects the shallowest `locale/` dir containing `en-us/`
- **en-us file counts** — counts `.intent`, `.voc`, `.dialog`, `.rx`, `.entity` files
- **skill.json validity** — checks presence and required fields: `skill_id`, `name`, `description`, `examples`, `tags`
- **Translation coverage** — for each non-en-us language: files present / en-us file count × 100%
- **Gitlocalize readiness** — `scripts/sync_translations.py`, `translations/`, workflow calling `sync-translations.yml`

### Does skill-check fail for non-skill repos?

No. By default `skip_if_not_skill: true` — the check silently passes and posts `ℹ️ Not an OVOS skill repo — check skipped.` in the PR comment. Set it to `false` only if you want to enforce that every repo must be a skill.

### How is translation coverage calculated?

`coverage = files_present_in_lang / len(en_us_files) × 100`. Icons: ✅ ≥95% · ⚠️ 50–94% · ❌ <50%. `skill.json` is excluded from the file set.

### What are the required fields in skill.json?

`skill_id`, `name`, `description`, `examples`, `tags`. Missing fields are listed in the PR comment and, if `fail_on_invalid_skill_json: true`, the job fails.

### How does locale auto-detection work?

`find_locale_dir()` does an `os.walk` from the repo root, collecting all directories named `locale` that contain an `en-us` sub-directory. The shallowest match wins (package-level `<pkg>/locale/en-us/` is preferred over a root-level `locale/en-us/`). Override with `locale_dir: 'path/to/locale'` if needed.

### How do I add skill-check to a skill repo?

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

---

## Release Preview

### What does `release-preview.yml` do?

It runs `scripts/check_release.py` and posts a `🏷️ Release Preview` section to the OVOS PR Checks comment. Shows:

- Current version from `version.py`
- Predicted next version based on PR labels / title
- Which signal triggered the bump (label, title prefix, or none)
- Warning if no conventional commit prefix found

### How is the next version predicted?

Labels take precedence over the PR title. Priority within labels: major > minor > build. If no label matches, the PR title is scanned for conventional commit prefixes (`feat:`, `fix:`, `docs:`, etc.). If nothing matches, an alpha-only bump is predicted.

| Prefix / Label | Bump |
|----------------|------|
| `breaking`, `breaking change:`, `feat!:`, `fix!:` | major |
| `feature`, `enhancement`, `feat:`, `feature:` | minor |
| `fix`, `bug`, `bugfix`, `fix:` | build |
| `docs:`, `chore:`, `refactor:`, `test:`, `style:`, `perf:`, `ci:`, `build:` | alpha only |
| _(nothing)_ | alpha only |

### Does release-preview fail the job?

Only if `version.py` is present but unparseable (malformed block markers). If `version.py` is simply absent, the job exits 0 and posts `ℹ️ No version.py found — release preview not available.`

### What env vars does check_release.py read?

`PR_LABELS_JSON` — JSON array of label objects from `github.event.pull_request.labels` (set automatically by the workflow). `PR_TITLE` — PR title string. Both can also be passed via `--pr-labels-json` and `--pr-title` CLI args.

---

## Bulk Skill Migration

### How were all 59 OVOS skill repos migrated from TigreGotico to OpenVoiceOS@dev?

A migration script at `scripts/migrate_skills.py` was run on 2026-03-09. It processed 60 skill directories in `Skills/`, skipping 2 that were already migrated (`ovos-skill-icanhazdadjokes`, `ovos-skill-confucius-quotes`) and committing the rest.

### What did the migration script change per skill?

For each skill repo:
- `release_workflow.yml` — **Rewritten**: removed inline translations job, updated ref to `OpenVoiceOS/gh-automations@dev`, added `publish_pypi: true` and `notify_matrix: true`
- `publish_stable.yml` — **Rewritten**: updated ref to `OpenVoiceOS/gh-automations@dev`, added `notify_matrix: true`
- `license_tests.yml` — **Updated ref** to `OpenVoiceOS@dev`, existing `with:` params preserved
- `skill_check.yml` — **Created** (new file calling `skill-check.yml@dev`)
- `release_preview.yml` — **Created** (new file calling `release-preview.yml@dev`)
- `conventional-label.yml` — **Created** where missing

### What about skills with sync_tx.yml?

9 skills with an inline `sync_tx.yml` had it deleted and replaced with `sync_translations.yml` (calling the reusable `sync-translations.yml@dev` workflow). Skills: `ovos-skill-fallback-chatgpt`, `ovos-skill-mark1-ctrl`, `ovos-skill-moon-game`, `ovos-skill-randomness`, `ovos-skill-wikihow`, `skill-ovos-radio-spain`, `skill-ovos-radio-tuga`, `ovos-skill-easter-eggs`.

### What about ovos-skill-easter-eggs?

Easter-eggs previously used `neongeckocom/.github@master` (not OVOS automation at all). The migration performed a full rewrite: removed `propose_release.yml`, `publish_alpha.yml`, `publish_release.yml`, `update_skill_json.yml`, and `sync_tx.yml`. The `skill_tests.yml` multi-version matrix was preserved as-is. All standard OVOS workflows were added.

### What about skills with no .github/workflows directory?

3 skills (`ovos-skill-cave-adventure-game`, `ovos-skill-music-assistant`, `ovos-skill-white-house-adventure`) had the full workflow set created from scratch: `release_workflow.yml`, `publish_stable.yml`, `license_tests.yml`, `skill_check.yml`, `release_preview.yml`, `conventional-label.yml`.

---

## Repo Health Check

### What does repo-health.yml check?

`repo-health.yml` verifies that required project files exist: `version.py`, `README.md`, `LICENSE`, and at least one of `pyproject.toml`/`setup.py`. Also checks `CHANGELOG.md` and `requirements.txt` as optional. Validates that `version.py` has `START_VERSION_BLOCK`/`END_VERSION_BLOCK` markers. Posts a `📋 Repo Health` section to the PR comment.

### Does it greet first-time contributors?

Yes. If `github.event.pull_request.author_association` is `FIRST_TIME_CONTRIBUTOR` or `FIRST_TIMER`, a `👋 Welcome` section is added to the PR comment with onboarding tips.

### How do I add it to my repo?

Call it from your PR workflow:

```yaml
jobs:
  repo_health:
    uses: OpenVoiceOS/gh-automations/.github/workflows/repo-health.yml@dev
    secrets: inherit
```

---

## Build Tests

### What does build-tests.yml do?

Runs `python -m build` across a configurable Python version matrix (default: 3.10, 3.11, 3.12), installs the built wheel, and optionally runs pytest. Posts a `🔨 Build Tests` section to the PR comment showing per-version build/install/test status.

### How does the PR comment look?

If all versions pass: a compact table with ✅ for Build, Install, Tests columns. If any fail: a detailed table with status icons (❌ build_failed, 🔶 install_failed, ⚠️ tests_failed) and descriptions.

---

## OPM Plugin Detection

### What is the OPM multi-plugin type detection?

Enhanced `check_opm.py` script that auto-detects any OVOS plugin type (skill, TTS, STT, wake word, VAD, PHAL, pipeline, etc.) from `pyproject.toml` or `setup.py` entry points. Previously only skills could be validated.

### How does auto-detection work?

`check_opm.py --plugin-type auto` scans for `[project.entry-points."opm.*"]` sections in `pyproject.toml` or `entry_points` dict in `setup.py`. Returns a list of detected plugin types (e.g., `opm.skill`, `opm.tts`).

### Can I check a specific plugin type?

Yes. `check_opm.py --plugin-type tts` checks if OPM can find TTS plugins, regardless of what entry points are declared. Useful for workflows that target a specific plugin type.

### What output formats does check_opm.py support?

- **Exit code** — 0 if detected, 1 if not detected or error.
- **Standard output** — Human-readable message (e.g., `✅ OVOS plugin detected: skill, tts`).
- **JSON output** — `--output-json /tmp/result.json` writes structured data with fields:
  - Basic: `detected_types`, `entry_points`, `opm_found`, `plugin_classes`, `is_ovos_plugin`, `summary`
  - Enhanced: `metadata` (name, version, authors, description, homepage, requires_python)
  - Validation: `import_ok`, `import_time_ms`, `interface_ok`, `abstract_base`, `has_config_docs`, `config_keys`
  - Issues & Status: `issues` (list of severity/message/check), `status` (pass|warning|fail)

### How does build-tests.yml use OPM detection?

When `plugin_type: auto` (default), the workflow:
1. Runs `check_opm.py --plugin-type auto --output-json /tmp/opm_result.json`
2. Uploads the JSON result as an artifact
3. The `post_opm_report` job collects results and posts a `🔌 Plugin Detection` section to the PR comment

For backward compatibility, if `entry_point` is set, the old skill-only check is used.

### Can I disable the OPM PR comment section?

Yes. Set `opm_section: false` in your `build-tests.yml` call. The OPM check still runs (needed for build matrix status), but the dedicated section is not posted.

### What does the OPM PR comment section show?

The enhanced section includes:
- **Status header** — overall result (✅ PASS / ⚠️ WARNINGS / ❌ ERRORS) with issue count
- **Plugin info** — name, version, description (from metadata)
- **System dependencies** — declared build system packages
- **Validation table** — per-type status for OPM discovery, import test, interface compliance, config docs
- **Issues list** — errors/warnings/info with severity icons
- **Downstream impact** — count of packages that depend on this plugin (if > 0)

If not an OVOS plugin: `ℹ️ Not an OVOS plugin — OPM check skipped.`

### What are the new validation checks?

`check_opm.py` now performs:
1. **Plugin import test** (`--test-import`) — attempts to import the declared plugin class and measures time
2. **Interface compliance** (`--validate-interface`) — checks that the class inherits from the correct abstract base
3. **Metadata extraction** — reads name, version, authors, description from pyproject.toml
4. **System dependencies detection** — reads `[tool.ovos.build] system-dependencies` from pyproject.toml
5. **Config docs validation** — checks for `settingsmeta.json` and extracts configuration keys

All flags default to `true` and can be toggled via new CLI args.

### What is the import time threshold?

`--perf-threshold-ms` (default: 500) sets the error threshold. Import times are categorized as:
- < 200ms: ✅ normal
- 200-500ms: ⚠️ warning (slow)
- > 500ms: ❌ error (very slow)

Slow imports can indicate missing dependencies or inefficient module initialization.

### What does "interface compliance" mean?

Each plugin type (skill, tts, stt, etc.) must inherit from a specific abstract base:
- **skill** — `ovos_workshop.skills.ovos.OVOSSkill`
- **tts** — `ovos_plugin_manager.templates.tts.TTS`
- **stt** — `ovos_plugin_manager.templates.stt.STT`
- (and so on for other types)

If a plugin class doesn't inherit from the correct base, it won't be recognized by OPM at runtime.

### How do I declare system dependencies?

Add a `[tool.ovos.build]` section to `pyproject.toml`:
```toml
[tool.ovos.build]
system-dependencies = ["libespeak-ng-dev", "libportaudio2"]
```

These are automatically passed to `apt-get install` in CI and can be auto-detected by workflows in the future.

### How do I configure OPM validation in build-tests.yml?

New inputs (all optional, defaults are safe):
```yaml
opm_require_found: false          # Fail build if OPM can't find plugin
opm_validate_interface: true       # Check abstract base inheritance
opm_test_import: true              # Test import and measure time
opm_perf_threshold_ms: 500         # Import time error threshold (ms)
```

Example:
```yaml
- uses: OpenVoiceOS/gh-automations/.github/workflows/build-tests.yml@dev
  with:
    plugin_type: "auto"
    opm_validate_interface: true
    opm_perf_threshold_ms: 250      # stricter than default
```

### What happens if validation fails?

The CI build does **not** fail by default. Instead:
- Errors/warnings are collected and displayed in the PR comment
- Status is set to `pass` | `warning` | `fail`
- Only if you set `opm_require_found: true` will OPM detection failure cause the build matrix job to fail

This allows you to monitor plugin health without blocking releases.

### How do I migrate from entry_point to plugin_type?

Old (skill-only):
```yaml
entry_point: "ovos-skill-my-skill"
```

New (multi-type, auto-detect, enhanced validation):
```yaml
plugin_type: "auto"
opm_section: true
opm_test_import: true
opm_validate_interface: true
```

Both work, but `plugin_type: auto` is more flexible and scalable.

---

## Breaking Change Banner

### When does the breaking change banner appear?

In the `🏷️ Release Preview` section, a `[!CAUTION]` alert appears when the PR labels or title trigger a MAJOR version bump. It warns that downstream dependents may break and recommends a compatibility check before merging.

---

## ovoscope.yml — Pipeline Inputs

### What are `require_adapt`, `require_padatious`, and `require_m2v`?

Boolean inputs to `ovoscope.yml` that control what happens when a pipeline plugin is absent.

- `false` (default): tests that use the missing pipeline are **skipped** silently via `is_pipeline_available()`.
- `true`: CI **fails before running any tests** with a clear error message listing which package to add to `[test]` deps.

Use `require_adapt: true` in skills that test Adapt intents so CI fails explicitly if `ovos-adapt-pipeline-plugin` is missing from test dependencies.

### Which pipelines are always available in ovoscope.yml?

`PADACIOSO_PIPELINE` (pure-Python padacioso, bundled with `ovos-workshop`) is always available. No `require_padacioso` input is needed. The three optional pipelines (`ADAPT`, `PADATIOUS`, `M2V`) require separate packages.

### How does the pipeline availability check work?

An inline Python step reads the `opm.pipeline` entry point group using `importlib.metadata.entry_points()` and checks whether the expected plugin name is present. If it is absent and the corresponding `require_*` input is `true`, the step exits with code 1 before pytest runs.

---

## opm-check.yml — g2p Plugin Support

### Does opm-check.yml support g2p plugins?

Yes. `g2p` was added as a supported plugin type in `check_opm.py` (`PLUGIN_TYPE_FINDERS` and `ABSTRACT_BASES`). Use `plugin_type: g2p` or `plugin_type: auto` (which auto-detects `opm.g2p` entry points from `pyproject.toml`).

### What changed in the OPM detection PR table?

The PR comment now uses two separate tables:

1. **OPM Detection** — one row per detected plugin *type* (e.g. `skill`, `tts`), showing Wheel OPM, Editable OPM, and `requires-python` compliance.
2. **Entry Point Validation** — one row per named *entry point* (e.g. `ovos-tts-plugin-example`), showing import time, interface compliance, and config docs.

This allows packages that register multiple entry points per type (e.g. a multi-voice TTS) to have each entry point validated independently.

### What does `opm_require_found` default to now?

`true`. The default changed from `false` to `true` in the OPM check improvements commit. Jobs now fail by default if OPM cannot discover the plugin. Set `opm_require_found: false` for repos that are not OVOS plugins and should pass silently.

### What is `requires-python` validation in opm-check?

`check_opm.py` reads `requires-python` from `pyproject.toml` and checks it against the running Python version using the `packaging` library (if installed). The result is reported as `requires_python_ok` in the JSON output and displayed in the OPM Detection table. A mismatch is reported as an error in the issues list.

---

## Locale Progress Bars

### What changed in the Skill Check translation table?

The `🎙️ Skill` section now shows progress bars for each language's translation coverage. Each bar is 10 characters wide (█ filled, ░ empty) with a percentage and file count. A summary line at the top shows how many languages are complete/partial/incomplete.

## Downstream Check Failures

### Why does the "Track Downstream Dependencies" workflow fail with `ResolutionImpossible`?

The `downstream-check.yml` reusable workflow installs the full OVOS constraints stack. Some downstream packages (e.g. `ovos-stt-plugin-citrinet`, `ovos-tts-plugin-matxa-multispeaker-cat`) depend on `onnxruntime`, which only publishes pre-built wheels for stable CPython versions. If `python_version` is set to a pre-release (e.g. `3.14`), pip cannot find compatible onnxruntime wheels and fails with a dependency conflict.

**Fix**: The default `python_version` was changed from `"3.14"` to `"3.11"` (2026-03-10). Callers can still override with `python_version: "3.12"` etc., but should not use pre-release versions unless all downstream packages support them.
