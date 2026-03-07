# OVOS Release Flow

All OVOS packages follow a rolling release model with three channels: **alpha**, **testing**, and **stable**. This document describes the full lifecycle from code change to published package.

## Branches

| Branch | Purpose |
|--------|---------|
| `dev` | Active development, receives PRs, publishes alpha releases automatically |
| `release-X.Y.ZaN` | Short-lived, auto-created on each PR merge to `dev`, used to propose a stable release |
| `master` | Stable, receives only reviewed release PRs |

## Versioning

Versions follow `MAJOR.MINOR.BUILD[aN]` where the alpha suffix is dropped on stable release.

The `version.py` file in each package is the authoritative source:

```python
# START_VERSION_BLOCK
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_BUILD = 3
VERSION_ALPHA = 4   # 0 = stable release
# END_VERSION_BLOCK

__version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
```

### Version bump rules (driven by PR labels set by conventional commits)

| Label | Bump | Example |
|-------|------|---------|
| `breaking` | major | `1.0.0a1` → `2.0.0a1` |
| `feature` | minor | `1.0.0a1` → `1.1.0a1` |
| `fix` | build | `1.0.0a1` → `1.0.1a1` |
| _(none)_ | alpha only | `1.0.0a1` → `1.0.0a2` |

Labels are assigned automatically by `conventional-label.yaml` based on the PR title (conventional commits format: `feat:`, `fix:`, `chore:`, `BREAKING CHANGE:`, etc.).

## Alpha Release (on PR merge to `dev`)

```
PR merged → dev
    │
    ▼
release_workflow.yml
    │   (trigger: pull_request types: [closed], branches: [dev])
    │   (also: workflow_dispatch for manual rerun)
    │
    ├─► publish_alpha job
    │   if: merged == true || workflow_dispatch
    │       └─► publish-alpha.yml (gh-automations)
    │               ├─ Determine version bump from PR labels
    │               ├─ Update version.py (bump version)
    │               ├─ Commit & push to dev
    │               ├─ [optional] Update CHANGELOG.md
    │               ├─ [optional] Create pre-release tag on GitHub
    │               └─ Create release-X.Y.ZaN branch + PR to master
    │
    ├─► publish_pypi job
    │       ├─ python -m build
    │       └─ Publish to PyPI (alpha)
    │
    └─► notify job
        if: merged == true
            └─► notify-matrix.yml (gh-automations)
                    └─ Post to OVOS Matrix channel
```

## Stable Release (on PR merge to `master`)

The `release-X.Y.ZaN` PR opened by the alpha flow requires **human review** before merging.

```
PR merged → master
    │
    ▼
publish_stable.yml
    │   (trigger: push: master OR workflow_dispatch)
    │
    ├─► publish_stable job
    │   if: github.actor != 'github-actions[bot]'   ← bot loop guard
    │       └─► publish-stable.yml (gh-automations)
    │               ├─ Remove alpha suffix (VERSION_ALPHA = 0)
    │               ├─ Commit & push to master
    │               └─ Create GitHub release tag
    │
    ├─► publish_pypi job
    │       ├─ python -m build
    │       └─ Publish to PyPI (stable)
    │
    └─► sync_dev job
            └─ Push master → dev (keep branches in sync)
```

### Why the bot guard is critical

`git-auto-commit-action` pushes the version commit directly to `master`. Without the guard,
this push would trigger another `push: master` event → another `publish_stable.yml` run →
another tag attempt (which fails since the tag already exists). The guard breaks this loop.

## Release Channels (ovos-releases)

After a stable release is published to PyPI, the [ovos-releases](https://github.com/OpenVoiceOS/ovos-releases) constraints files are updated:

| File | Channel | Trigger |
|------|---------|---------|
| `constraints-alpha.txt` | Alpha | Every 6 hours (cron) + manual |
| `constraints-testing.txt` | Testing | Manual |
| `constraints-stable.txt` | Stable | Manual |

Constraints use `>=` bounds (e.g. `ovos-utils>=0.3.0`) so users always get the latest compatible version within their chosen channel.

## Manual Reruns

Both `release_workflow.yml` and `publish_stable.yml` support `workflow_dispatch` for manual triggering from the GitHub Actions UI. This is useful when:
- A workflow failed due to a transient error (e.g. PyPI outage)
- A version bump was needed but the PR was merged without the right labels
- Testing the release pipeline on a new repo

The `publish_alpha` job in `release_workflow.yml` allows dispatch:
```yaml
if: github.event.pull_request.merged == true || github.event_name == 'workflow_dispatch'
```
