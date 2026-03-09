Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Update all @master refs to @dev; add versioning policy note; document scripts checkout footgun; expand known issues per-workflow.

# Reusable Workflow Reference

All reusable workflows are in `.github/workflows/` and are called via:

```yaml
uses: OpenVoiceOS/gh-automations/.github/workflows/<name>.yml@dev
```

> **Ref policy:** Use `@dev` for all new repos and migrations. `@master` is frozen (v1 baseline).
> See [release-flow.md — gh-automations Versioning Policy](release-flow.md#gh-automations-versioning-policy) for the full rationale.

---

## `publish-alpha.yml`

Runs on PR merge to `dev`. Bumps the version, optionally updates changelog and creates a pre-release tag, then opens a release PR to `master`.

**Source:** `.github/workflows/publish-alpha.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `version_file` | string | `version.py` | Relative path to the `version.py` file inside the repo |
| `branch` | string | `dev` | Source branch to checkout and commit back to |
| `publish_prerelease` | boolean | `false` | Create a GitHub pre-release tag after version bump |
| `propose_release` | boolean | `true` | Open a PR from `release-X.Y.ZaN` to `master` |
| `update_changelog` | boolean | `false` | Generate and commit `CHANGELOG.md` using `github-changelog-generator` |
| `changelog_file` | string | `CHANGELOG.md` | Path to the changelog file |
| `changelog_max_issues` | number | `50` | Max issues to include in changelog |
| `publish_pypi` | boolean | `false` | Publish to PyPI after version bump (built inline within this workflow) |
| `notify_matrix` | boolean | `false` | Send Matrix notification on merged PR |
| `runner` | string | `ubuntu-latest` | Runner label |
| `setup_py` | string | `setup.py` | **Deprecated.** Accepted but not used. Version is read from `version_file`. |

### Outputs

| Output | Description |
|--------|-------------|
| `version` | The new version string (e.g. `1.2.3a4`), from `bump_version` job |
| `changelog` | Changelog content (only populated when `update_changelog: true`) |

### Jobs

| Job | Condition | Description |
|-----|-----------|-------------|
| `bump_version` | `merged == true \|\| workflow_dispatch` | Determines bump type from PR labels, calls `update_version.py`, commits and pushes to `branch` via `git-auto-commit-action@v5` |
| `update_changelog` | `update_changelog: true` + `bump_version` succeeded | Calls `github-changelog-generator-action@v2.3`, commits result |
| `tag_prerelease` | `publish_prerelease: true` + `bump_version` succeeded | Creates GitHub pre-release via `ncipollo/release-action@v1` |
| `propose_release` | `propose_release: true` + `bump_version` succeeded | Creates `release-X.Y.ZaN` branch, opens PR to `master` via GitHub API |
| `publish_pypi` | `publish_pypi: true` + `bump_version` succeeded | Builds with `python -m build`, publishes via `pypa/gh-action-pypi-publish@master` |
| `notify` | `notify_matrix: true` + `bump_version` succeeded + PR merged | Calls `notify-matrix.yml` with a canned message |

### Bot guard

`bump_version` only runs when:
- A PR was **merged** (`github.event.pull_request.merged == true`), or
- Triggered manually (`workflow_dispatch`)

This prevents spurious runs when a PR is closed without merging.

### Typical usage

```yaml
name: Release Alpha and Propose Stable

on:
  workflow_dispatch:
  pull_request:
    types: [closed]
    branches: [dev]

jobs:
  publish_alpha:
    if: github.event.pull_request.merged == true || github.event_name == 'workflow_dispatch'
    uses: OpenVoiceOS/gh-automations/.github/workflows/publish-alpha.yml@dev
    secrets: inherit
    with:
      branch: 'dev'
      version_file: 'my_package/version.py'
      update_changelog: true
      publish_prerelease: true
      propose_release: true
      changelog_max_issues: 100
```

### Known issues

- `pypa/gh-action-pypi-publish@master` and `pozetroninc/github-action-get-latest-release@master` are pinned to `@master` rather than a fixed ref — any upstream breaking change would silently affect all callers. See [AUDIT.md](../AUDIT.md).
- `propose_release` job uses `git checkout -b release-${VERSION}` — if the branch already exists (e.g. after a failed retry), this step will fail. Proposed fix: use `git checkout -B`. See [SUGGESTIONS.md](../SUGGESTIONS.md#4-use-git-checkout--b-in-propose_release).

---

## `publish-stable.yml`

Runs on push to `master` (typically triggered by merging the release PR). Removes the alpha suffix from `version.py`, commits, then creates a GitHub release tag.

**Source:** `.github/workflows/publish-stable.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `version_file` | string | `version.py` | Relative path to `version.py` |
| `branch` | string | `master` | Branch to checkout and commit the stable version to |
| `publish_release` | boolean | `true` | Create a GitHub release tag |
| `publish_pypi` | boolean | `false` | Publish to PyPI after declaring stable |
| `sync_dev` | boolean | `false` | Push `master` → `dev` after stable release to keep branches in sync |
| `runner` | string | `ubuntu-latest` | Runner label |
| `setup_py` | string | `setup.py` | **Deprecated.** Accepted but not used. |

### Outputs

| Output | Description |
|--------|-------------|
| `version` | The stable version string (e.g. `1.2.3`), from `bump_version` job |

### Jobs

| Job | Condition | Description |
|-----|-----------|-------------|
| `bump_version` | `github.actor != 'github-actions[bot]'` | Calls `remove_alpha.py`, commits via `git-auto-commit-action@v5` |
| `tag_release` | `publish_release: true` + `bump_version` succeeded | Creates GitHub release via `ncipollo/release-action@v1` |
| `publish_pypi` | `publish_pypi: true` + `bump_version` succeeded | Builds and publishes to PyPI (stable) |
| `sync_dev` | `sync_dev: true` + `bump_version` succeeded | Pushes `master` → `dev` via `ad-m/github-push-action@v0.8.0` |

### Bot guard

`bump_version` skips when `github.actor == 'github-actions[bot]'` (`publish-stable.yml:37`). This prevents an infinite loop: the version commit pushed by `git-auto-commit-action` would otherwise re-trigger this workflow on `push: master`.

The calling repo's `publish_stable.yml` job **also** carries this guard (`if: github.actor != 'github-actions[bot]'`) for belt-and-suspenders protection.

### Typical usage

```yaml
name: Stable Release
on:
  push:
    branches: [master]
  workflow_dispatch:

jobs:
  publish_stable:
    if: github.actor != 'github-actions[bot]'
    uses: OpenVoiceOS/gh-automations/.github/workflows/publish-stable.yml@dev
    secrets: inherit
    with:
      branch: 'master'
      version_file: 'my_package/version.py'
      publish_release: true
      sync_dev: true
```

---

## `license-check.yml`

Checks all installed dependencies for copyleft or incompatible licenses. Uses [`pilosus/action-pip-license-checker`](https://github.com/pilosus/action-pip-license-checker).

**Source:** `.github/workflows/license-check.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `install_extras` | string | `""` | pip extras to install alongside the package, e.g. `[extras,linux]` |
| `system_deps` | string | `""` | Extra `apt-get` packages beyond the base `python3-dev libssl-dev` |
| `exclude_packages` | string | `^(tqdm).*` | Regex of package names to exclude from the check |
| `exclude_licenses` | string | `^(Mozilla).*$` | Regex of license identifiers to exclude from the check |
| `python_version` | string | `3.11` | Python version |
| `runner` | string | `ubuntu-latest` | Runner label |

### Typical usage

```yaml
name: Run License Tests
on:
  push:
    branches: [master]
  pull_request:
    branches: [dev]
  workflow_dispatch:

jobs:
  license_tests:
    uses: OpenVoiceOS/gh-automations/.github/workflows/license-check.yml@dev
    with:
      install_extras: '[extras]'
      system_deps: 'swig libfann-dev'
      exclude_packages: '^(tqdm|some-gpl-package).*'
```

---

## `notify-matrix.yml`

Sends a message to the OVOS Matrix channel. Uses [`fadenb/matrix-chat-message`](https://github.com/fadenb/matrix-chat-message).

**Source:** `.github/workflows/notify-matrix.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | _(required)_ | Message text to send |
| `homeserver` | string | `matrix.org` | Matrix homeserver URL |
| `channel` | string | `!WjxEKjjINpyBRPFgxl:krbel.duckdns.org` | Matrix room ID |

### Secrets

| Secret | Description |
|--------|-------------|
| `MATRIX_TOKEN` | Matrix access token (inherited via `secrets: inherit`) |

### Typical usage

```yaml
  notify:
    if: github.event.pull_request.merged == true
    needs: publish_alpha
    uses: OpenVoiceOS/gh-automations/.github/workflows/notify-matrix.yml@dev
    secrets: inherit
    with:
      message: "new ${{ github.event.repository.name }} PR merged! https://github.com/${{ github.repository }}/pull/${{ github.event.number }}"
```

---

## `pip-audit.yml`

Scans installed dependencies for known CVEs using [`pypa/gh-action-pip-audit`](https://github.com/pypa/gh-action-pip-audit). Runs on Python 3.10 and 3.11 in parallel.

**Source:** `.github/workflows/pip-audit.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `install_extras` | string | `""` | pip extras to install |
| `system_deps` | string | `""` | Extra `apt-get` packages beyond `python3-dev` |
| `ignore_vulns` | string | `GHSA-r9hx-vwmv-q579` | Newline-separated vulnerability IDs to ignore |
| `python_version` | string | `3.11` | Python version |
| `runner` | string | `ubuntu-latest` | Runner label |

### Typical usage

```yaml
name: Pip Audit
on:
  push:
    branches: [dev, master]
  workflow_dispatch:

jobs:
  pip_audit:
    uses: OpenVoiceOS/gh-automations/.github/workflows/pip-audit.yml@dev
    with:
      install_extras: '[all]'
```

---

## `downstream-check.yml`

Reports which packages in the ovos-releases alpha constraints depend on a given package. Uses `pipdeptree` and commits the sorted report to the repo, so repeated runs only generate a new commit when the actual dependency tree changes.

**Source:** `.github/workflows/downstream-check.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `package_name` | string | _(required)_ | PyPI package name to track (e.g. `ovos-utils`) |
| `constraints_url` | string | `https://raw.githubusercontent.com/OpenVoiceOS/ovos-releases/refs/heads/main/constraints-alpha.txt` | Constraints file URL to install from |
| `output_file` | string | `downstream_report.txt` | Report output path (relative to repo root) |
| `commit_branch` | string | `dev` | Branch to commit the report to |
| `python_version` | string | `3.11` | Python version |
| `runner` | string | `ubuntu-latest` | Runner label |

### Typical usage

```yaml
name: Track Downstream Dependencies
on:
  push:
    branches: [dev]
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:

jobs:
  check_downstream:
    uses: OpenVoiceOS/gh-automations/.github/workflows/downstream-check.yml@dev
    secrets: inherit
    with:
      package_name: 'ovos-utils'
```

---

## `sync-translations.yml`

Synchronises [gitlocalize-app](https://gitlocalize.com/) translation commits. Runs `scripts/sync_translations.py` in the calling repo when triggered by a push from `gitlocalize-app[bot]` or by manual `workflow_dispatch`.

Standardises the per-repo `sync_tx.yml` pattern found across all OVOS skill repos. Issues fixed over the per-repo pattern:
- Old repos used `actions/checkout@v2` and `actions/setup-python@v1` — updated to `@v4`/`@v5`
- `github.actor` is the correct field for bot detection (some repos incorrectly used `github.event.head_commit.author.username`)
- `stefanzweifel/git-auto-commit-action` standardised to `@v5`
- Commit message normalised to `chore: sync translations`

**Source:** `.github/workflows/sync-translations.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `branch` | string | `dev` | Branch to checkout, run the script on, and commit back to |
| `python_version` | string | `3.11` | Python version |
| `runner` | string | `ubuntu-latest` | Runner label |
| `script_path` | string | `scripts/sync_translations.py` | Relative path to the sync script in the calling repo |

### Typical usage

Replace the per-repo `sync_tx.yml` with:

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
      # script_path: scripts/sync_translations.py  # default
```

### Known issues

Some existing `sync_tx.yml` files use `github.event.head_commit.author.username == 'gitlocalize-app[bot]'` for bot detection. This field is not reliable for filtering. The reusable workflow uses `github.actor == 'gitlocalize-app[bot]'` which is the correct field. When migrating, remove the old per-repo `sync_tx.yml` and replace with a call to this reusable workflow.

---

## Scripts Reference

The following Python scripts are checked out from this repo at workflow run time and are not installed as a Python package.

### `scripts/_version_utils.py`

Shared version-block parsing utilities imported by all other scripts.

**Key functions:**
- `read_version(version_file: str) -> tuple[int, int, int, int]` — `scripts/_version_utils.py:18` — parses `START_VERSION_BLOCK/END_VERSION_BLOCK`, returns `(major, minor, build, alpha)`
- `format_version(major, minor, build, alpha) -> str` — `scripts/_version_utils.py:51` — formats PEP 440 string
- `write_version_block(version_file, major, minor, build, alpha)` — `scripts/_version_utils.py:70` — rewrites only the block, preserving all surrounding content

### `scripts/update_version.py`

Bumps the version in a `version.py` file.

**Key function:** `update_version(part: str, version_file: str) -> str` — `scripts/update_version.py:18`

```
usage: update_version.py <part> --version-file <path>

part: major | minor | build | alpha
```

Bump rules (implemented at `scripts/update_version.py:37-52`):

| Part | Effect |
|------|--------|
| `major` | `MAJOR += 1`, `MINOR = 0`, `BUILD = 0`, `ALPHA = 1` |
| `minor` | `MINOR += 1`, `BUILD = 0`, `ALPHA = 1` |
| `build` | `BUILD += 1`, `ALPHA = 1` |
| `alpha` | `ALPHA += 1`; if currently stable (`ALPHA == 0`): `BUILD += 1` first |

### `scripts/remove_alpha.py`

Sets `VERSION_ALPHA = 0` in a `version.py` file (declares stable).

**Key function:** `update_alpha(version_file: str)` — `scripts/remove_alpha.py:10`

Uses `fileinput.input(..., inplace=True)` to rewrite lines in-place. Replaces any line starting with `VERSION_ALPHA` with `VERSION_ALPHA = 0`.

```
usage: remove_alpha.py --version-file <path>
```

### `scripts/get_version.py`

Reads and prints the version string from a `version.py` file. Works without installing the package.

**Key function:** `get_version(version_file: str) -> str` — `scripts/get_version.py:5`

```
usage: get_version.py --version-file <path>
```

Output example: `1.2.3a4` or `1.2.3`

### `scripts/check_downstream.py`

Reports which installed packages depend on a given package, using `pipdeptree`. Output is sorted deterministically so repeated runs only generate a git commit when the actual dependency tree changes.

**Key function:** `get_downstream(package_name: str) -> str` — `scripts/check_downstream.py:61`

**Helper:** `sort_pipdeptree_output(text: str) -> str` — `scripts/check_downstream.py:53`

```
usage: check_downstream.py --package <name> --output <file>
```

Requires `pipdeptree` to be installed in the environment before calling.
