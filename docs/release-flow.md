Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Document master-freeze / dev-active model for gh-automations itself; update all @master refs; add gh-automations versioning lifecycle section.

# OVOS Release Flow

All OVOS packages follow a rolling release model with three channels: **alpha**, **testing**, and **stable**. This document describes the full lifecycle from code change to published package, and separately covers the versioning strategy for gh-automations itself.

---

## gh-automations Versioning Policy

gh-automations is a reusable workflow library, not an installable Python package. It does not have a `version.py` of its own. Instead it is versioned via **Git refs** that callers pin in their workflow files.

| Ref | Status | Semantics |
|-----|--------|-----------|
| `@master` | **Frozen (v1)** | The original stable baseline. Frozen in place — no new commits will land on `master`. Repos still calling `@master` will keep working exactly as before, indefinitely. |
| `@dev` | **Active** | All fixes, new features, and improvements target `dev`. New repos and repos that opt in by migrating should call `@dev`. |
| `@v2` _(future)_ | Planned | Will be tagged from `dev` when breaking changes (input renames, removed jobs, changed outputs) accumulate to the point where a formal major version bump is warranted. |

### How to migrate a repo from `@master` to `@dev`

Open a PR in the target repo with the following change in every `.github/workflows/` file:

```
# Before
uses: TigreGotico/gh-automations/.github/workflows/publish-alpha.yml@master

# After
uses: TigreGotico/gh-automations/.github/workflows/publish-alpha.yml@dev
```

Repeat for every `uses:` and `license_tests.yml` / `downstream.yml` reference in the repo.
Verify CI passes, then merge.

### What counts as a breaking change requiring `@v3` (or `@v2`→next)?

| Change type | Breaking? |
|---|---|
| New optional input with a default value | No — existing callers are unaffected |
| Bug fix that does not change outputs | No |
| New job that does not affect existing job names | No |
| Removing or renaming an existing input | **Yes** |
| Removing or renaming an existing output | **Yes** |
| Renaming a job (breaks callers that `needs:` the old name) | **Yes** |
| Changing the default value of an existing input in a way that alters behaviour | **Yes** |
| Adding a new **required** input (no default) | **Yes** |

### Scripts checkout note

The reusable workflow files checkout this repo at runtime to access `scripts/` via:

```yaml
- uses: actions/checkout@v4
  with:
    repository: TigreGotico/gh-automations
    path: action/github/
    # no ref: specified — uses the GitHub default branch
```

This means the scripts that actually run are determined by whichever branch is set as the **GitHub default branch** of `TigreGotico/gh-automations`, regardless of which ref (`@master` or `@dev`) the calling workflow uses to select the workflow file. See [SUGGESTIONS.md](../SUGGESTIONS.md#3-pin-the-scripts-checkout-ref-in-reusable-workflows) for the proposed fix.

---

## Branches (per-repo)

Every OVOS package repo uses the following branch structure:

| Branch | Purpose |
|--------|---------|
| `dev` | Active development. Receives PRs. Publishes alpha releases automatically on merge. |
| `release-X.Y.ZaN` | Short-lived. Auto-created on each PR merge to `dev`. Used to propose a stable release. Deleted after PR to `master` is opened. |
| `master` | Stable. Receives only reviewed release PRs opened by automation. |

---

## Versioning (per-repo)

Versions follow `MAJOR.MINOR.BUILD[aN]` where the alpha suffix (`a1`, `a2`, …) is dropped on stable release.

The `version.py` file in each package is the authoritative source. The block between the marker comments is the only part that automation reads and rewrites:

```python
# START_VERSION_BLOCK
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_BUILD = 3
VERSION_ALPHA = 4   # 0 = stable release
# END_VERSION_BLOCK

__version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
```

`update_version.py:11-31` (`read_version`) parses this block. `update_version.py:34-63` (`update_version`) rewrites it. `remove_alpha.py:10-17` (`update_alpha`) sets `VERSION_ALPHA = 0` using `fileinput` in-place replacement. `get_version.py:5-28` (`get_version`) reads and formats the string.

### Version bump rules (driven by PR labels from conventional commits)

Labels are assigned automatically by `conventional-label.yaml` using `bcoe/conventional-release-labels@v1`, which maps PR title prefixes to labels:

| PR title prefix | Label assigned | Version bump |
|---|---|---|
| `BREAKING CHANGE:` | `breaking` | **Major**: `1.2.3a4` → `2.0.0a1` |
| `feat:` | `feature` | **Minor**: `1.2.3a4` → `1.3.0a1` |
| `fix:` | `fix` | **Build**: `1.2.3a4` → `1.2.4a1` |
| `chore:`, `docs:`, other | _(none)_ | **Alpha only**: `1.2.3a4` → `1.2.3a5` |

If the current version is already stable (alpha = 0), an unlabelled bump first increments `BUILD`:
`1.2.3` → `1.2.4a1` (implemented at `update_version.py:50-52`).

---

## Alpha Release (on PR merge to `dev`)

```
PR merged → dev
    │
    ▼
release_workflow.yml  (per-repo)
    │   trigger: pull_request types:[closed] branches:[dev]
    │   also:    workflow_dispatch
    │
    ├─► publish_alpha job
    │   if: merged == true || workflow_dispatch
    │       └─► publish-alpha.yml@dev  (gh-automations)
    │               │
    │               ├─ [bump_version job]
    │               │   Checkout repo + gh-automations scripts
    │               │   Determine bump part from PR labels
    │               │   update_version.py <part> --version-file ...
    │               │   git-auto-commit-action → push to dev
    │               │
    │               ├─ [update_changelog job]  (optional: update_changelog: true)
    │               │   Generate CHANGELOG.md since last stable release
    │               │   Commit and push to dev
    │               │
    │               ├─ [tag_prerelease job]  (optional: publish_prerelease: true)
    │               │   Create GitHub pre-release tag (e.g. 1.2.3a4)
    │               │
    │               └─ [propose_release job]  (optional: propose_release: true)
    │                   git checkout -b release-X.Y.ZaN
    │                   git push origin release-X.Y.ZaN
    │                   curl → open PR to master
    │
    ├─► publish_pypi job  (per-repo, inline)
    │       python -m pip install build
    │       python -m build
    │       pypa/gh-action-pypi-publish → PyPI (alpha)
    │
    └─► notify job
        if: merged == true
            └─► notify-matrix.yml@dev  (gh-automations)
                    fadenb/matrix-chat-message → OVOS Matrix channel
```

---

## Stable Release (on PR merge to `master`)

The `release-X.Y.ZaN` PR opened by the alpha flow requires **human review** before merging. This is the only manual gate in the pipeline.

```
PR merged → master
    │
    ▼
publish_stable.yml  (per-repo)
    │   trigger: push: branches:[master]
    │   also:    workflow_dispatch
    │
    ├─► publish_stable job
    │   if: github.actor != 'github-actions[bot]'   ← CRITICAL bot loop guard
    │       └─► publish-stable.yml@dev  (gh-automations)
    │               │
    │               ├─ [bump_version job]
    │               │   remove_alpha.py → VERSION_ALPHA = 0
    │               │   git-auto-commit-action → push to master
    │               │
    │               └─ [tag_release job]  (optional: publish_release: true)
    │                   ncipollo/release-action → GitHub release tag
    │
    ├─► publish_pypi job  (per-repo, inline)
    │       python -m build
    │       pypa/gh-action-pypi-publish → PyPI (stable)
    │
    └─► sync_dev job  (optional: sync_dev: true)
            ad-m/github-push-action → pushes master → dev
```

### Why the bot guard is critical

`git-auto-commit-action` pushes the version commit (removing alpha) directly to `master`. Without the `if: github.actor != 'github-actions[bot]'` guard on both the calling repo's `publish_stable` job **and** inside `publish-stable.yml`'s `bump_version` job, this push would trigger another `push: master` event → another run → another tag attempt → failure (tag already exists) or infinite loop.

The guard is belt-and-suspenders: it exists at both layers (`publish_stable.yml:37` in gh-automations, and in each repo's `publish_stable.yml` calling job).

---

## Release Channels (ovos-releases)

After a stable release is published to PyPI, the [ovos-releases](https://github.com/OpenVoiceOS/ovos-releases) constraints files are updated:

| File | Channel | Trigger |
|------|---------|---------|
| `constraints-alpha.txt` | Alpha | Every 6 hours (cron) + manual |
| `constraints-testing.txt` | Testing | Manual |
| `constraints-stable.txt` | Stable | Manual |

Constraints use `>=` bounds (e.g. `ovos-utils>=0.3.0`) so users always get the latest compatible version within their chosen channel.

---

## Manual Reruns

Both `release_workflow.yml` and `publish_stable.yml` support `workflow_dispatch` for manual triggering from the GitHub Actions UI. This is useful when:
- A workflow failed due to a transient error (e.g. PyPI outage)
- A version bump was needed but the PR was merged without the right labels
- Testing the release pipeline on a new repo

The `publish_alpha` job in `release_workflow.yml` allows dispatch:
```yaml
if: github.event.pull_request.merged == true || github.event_name == 'workflow_dispatch'
```
