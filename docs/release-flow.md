Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Remove stale @master branching narrative; fix all script line numbers; fix propose_release diagram (gh pr create); fix scripts-checkout note.

# OVOS Release Flow

All OVOS packages follow a rolling release model with three channels: **alpha**, **testing**, and **stable**. This document describes the full lifecycle from code change to published package, and separately covers the versioning strategy for gh-automations itself.

---

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

`_version_utils.py:17` (`read_version`) parses this block. `update_version.py:22` (`update_version`) rewrites it via `write_version_block` at `_version_utils.py:72`. `remove_alpha.py:17` (`update_alpha`) sets `VERSION_ALPHA = 0` using `write_version_block`. `get_version.py:15` (`get_version`) reads and formats the string.

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
    │                   git checkout -B release-X.Y.ZaN  (force-create, idempotent)
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
