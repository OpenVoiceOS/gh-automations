Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Added Skill Check and Release Preview Q&A sections.

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
