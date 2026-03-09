Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Full rewrite with comprehensive Q&A covering versioning policy, migration, scripts, bot guards, and known issues; all answers verified against source code.

# FAQ — `gh-automations`

## General

### What is `gh-automations`?

`gh-automations` is the shared GitHub Actions automation library for all OpenVoiceOS repositories. It provides reusable workflows (in `.github/workflows/`) and Python scripts (in `scripts/`) that implement the OVOS rolling-release model: automated version bumping, alpha publishing to PyPI, and stable release gating via human-reviewed PRs.

### Where is it hosted?

[TigreGotico/gh-automations](https://github.com/TigreGotico/gh-automations). It is not a Python package you install — it is a GitHub repository that other repos call via the `uses:` directive in their workflow files.

### How many repos use it?

209 OVOS repositories as of 2026-03-09. See [docs/repos.md](docs/repos.md) for the full list.

---

## Versioning & Branching of gh-automations Itself

### Which ref should new repos use — `@master` or `@dev`?

`@dev`. The `master` branch of gh-automations is **frozen** as the v1 baseline. All active development — bug fixes, new features, improvements — targets `dev`. New repos and repos that opt in via migration should call `@dev`.

### Will `@master` stop working?

No. `master` is frozen, not deleted. Repos still calling `@master` will continue to receive exactly the same behaviour they always have. There is no deadline to migrate.

### What is `@dev` and how is it different from `@master`?

`@dev` is the active development branch. After the freeze, `@dev` will receive:
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
TigreGotico/gh-automations/.github/workflows/foo.yml@master
```
with:
```
TigreGotico/gh-automations/.github/workflows/foo.yml@dev
```

Open a PR, wait for CI, merge. No functional changes on day one.

---

## Scripts Checkout

### The workflows checkout `TigreGotico/gh-automations` without a ref — what branch does that use?

It uses whichever branch is set as the **GitHub default branch** of `TigreGotico/gh-automations`, regardless of whether the calling workflow uses `@master` or `@dev`.

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

## Common Errors

### "Tag already exists" error in `tag_release`

The stable release tag (e.g. `1.2.3`) was already created by a previous run. This usually means `publish_stable.yml` ran twice (the bot guard failed or was missing). Check that both the calling job and `publish-stable.yml:37` have the `github.actor != 'github-actions[bot]'` guard.

### `propose_release` fails with "branch already exists"

`git checkout -b release-X.Y.ZaN` fails if the branch was already created by a previous run attempt. Manually delete the branch (`git push origin --delete release-X.Y.ZaN`) then rerun. See [SUGGESTIONS.md](SUGGESTIONS.md#4-use-git-checkout--b-in-propose_release) for the proposed permanent fix.

### Version file not found

The `version_file` input path is relative to the repository root. If your `version.py` is at `my_package/version.py`, pass `version_file: 'my_package/version.py'`. The default `version.py` only works if the file is at the repo root.

### PyPI publish fails with "File already exists"

A package with that version was already uploaded. This happens when `python -m build` is run twice for the same version. Rerun after bumping the alpha counter manually in `version.py`, or skip if the package is already on PyPI.

### `update_changelog` step fails

`github-changelog-generator-action@v2.3` requires `GITHUB_TOKEN` to read issues and PRs. Ensure `secrets: inherit` is set on the `publish_alpha` job. Also check that the repo has at least one closed issue or merged PR — empty changelogs sometimes cause the action to error.
