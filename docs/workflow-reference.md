# Reusable Workflow Reference

All reusable workflows are in `.github/workflows/` and are called via:

```yaml
uses: TigreGotico/gh-automations/.github/workflows/<name>.yml@master
```

---

## `publish-alpha.yml`

Runs on PR merge to `dev`. Bumps the version, optionally updates changelog and creates a pre-release tag, then opens a release PR to `master`.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `version_file` | string | `version.py` | Relative path to the `version.py` file |
| `branch` | string | `dev` | Source branch |
| `publish_prerelease` | boolean | `false` | Create a GitHub pre-release tag |
| `propose_release` | boolean | `true` | Open a PR from `release-X.Y.ZaN` to `master` |
| `update_changelog` | boolean | `false` | Generate and commit `CHANGELOG.md` |
| `changelog_file` | string | `CHANGELOG.md` | Path to changelog file |
| `changelog_max_issues` | number | `50` | Max issues to include in changelog |
| `runner` | string | `ubuntu-latest` | Runner label |
| `setup_py` | string | `setup.py` | **Deprecated.** Version is now read from `version_file`. |

### Outputs

| Output | Description |
|--------|-------------|
| `version` | The new version string (e.g. `1.2.3a4`) |
| `changelog` | Changelog content (if `update_changelog` is true) |

### Jobs

- `bump_version` — Determines bump type from PR labels, updates `version.py`, pushes commit
- `update_changelog` — Generates changelog since last stable release (conditional)
- `tag_prerelease` — Creates GitHub pre-release (conditional)
- `propose_release` — Creates `release-X.Y.ZaN` branch and opens PR to `master` (conditional)

### Bot guard

`bump_version` only runs when:
- A PR was **merged** (`github.event.pull_request.merged == true`), or
- Triggered manually (`workflow_dispatch`)

This prevents runs when a PR is closed without merging.

### Typical usage

```yaml
jobs:
  publish_alpha:
    if: github.event.pull_request.merged == true || github.event_name == 'workflow_dispatch'
    uses: TigreGotico/gh-automations/.github/workflows/publish-alpha.yml@master
    secrets: inherit
    with:
      branch: 'dev'
      version_file: 'my_package/version.py'
      update_changelog: true
      publish_prerelease: true
      propose_release: true
      changelog_max_issues: 100
```

---

## `publish-stable.yml`

Runs on push to `master` (or PR merge). Removes the alpha suffix from `version.py`, commits, then creates a GitHub release tag.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `version_file` | string | `version.py` | Relative path to the `version.py` file |
| `branch` | string | `master` | Target branch |
| `publish_release` | boolean | `true` | Create a GitHub release tag |
| `runner` | string | `ubuntu-latest` | Runner label |
| `setup_py` | string | `setup.py` | **Deprecated.** Not used. |

### Outputs

| Output | Description |
|--------|-------------|
| `version` | The stable version string (e.g. `1.2.3`) |

### Jobs

- `bump_version` — Sets `VERSION_ALPHA = 0` in `version.py`, commits and pushes
- `tag_release` — Creates GitHub release tag (conditional)

### Bot guard

`bump_version` skips when `github.actor == 'github-actions[bot]'`. This prevents an infinite loop: the version commit pushed by `git-auto-commit-action` would otherwise re-trigger this workflow on `push: master`.

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
    uses: TigreGotico/gh-automations/.github/workflows/publish-stable.yml@master
    secrets: inherit
    with:
      branch: 'master'
      version_file: 'my_package/version.py'
      publish_release: true
```

---

## `license-check.yml`

Checks all installed dependencies for copyleft or incompatible licenses. Uses [`pilosus/action-pip-license-checker`](https://github.com/pilosus/action-pip-license-checker).

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `install_extras` | string | `""` | pip extras, e.g. `[extras,linux]` |
| `system_deps` | string | `""` | Extra apt packages beyond `python3-dev libssl-dev` |
| `exclude_packages` | string | `^(tqdm).*` | Regex of package names to exclude |
| `exclude_licenses` | string | `^(Mozilla).*$` | Regex of license identifiers to exclude |
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
    uses: TigreGotico/gh-automations/.github/workflows/license-check.yml@master
    with:
      install_extras: '[extras]'
      system_deps: 'swig libfann-dev'
      exclude_packages: '^(tqdm|some-gpl-package).*'
```

---

## `notify-matrix.yml`

Sends a message to the OVOS Matrix channel. Uses [`fadenb/matrix-chat-message`](https://github.com/fadenb/matrix-chat-message).

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | _(required)_ | Message to send |
| `homeserver` | string | `matrix.org` | Matrix homeserver |
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
    uses: TigreGotico/gh-automations/.github/workflows/notify-matrix.yml@master
    secrets: inherit
    with:
      message: "new ${{ github.event.repository.name }} PR merged! https://github.com/${{ github.repository }}/pull/${{ github.event.number }}"
```

---

## `pip-audit.yml`

Scans installed dependencies for known CVEs using [`pypa/gh-action-pip-audit`](https://github.com/pypa/gh-action-pip-audit). Runs on Python 3.10 and 3.11 in parallel.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `install_extras` | string | `""` | pip extras to install |
| `system_deps` | string | `""` | Extra apt packages beyond `python3-dev` |
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
    uses: TigreGotico/gh-automations/.github/workflows/pip-audit.yml@master
    with:
      install_extras: '[all]'
```

---

## `downstream-check.yml`

Reports which packages in the ovos-releases alpha constraints depend on a given package. Uses `pipdeptree` and commits the report to the repo.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `package_name` | string | _(required)_ | PyPI package name to track |
| `constraints_url` | string | `https://raw.githubusercontent.com/OpenVoiceOS/ovos-releases/refs/heads/main/constraints-alpha.txt` | Constraints file URL |
| `output_file` | string | `downstream_report.txt` | Report output path |
| `commit_branch` | string | `dev` | Branch to commit report to |
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
    uses: TigreGotico/gh-automations/.github/workflows/downstream-check.yml@master
    secrets: inherit
    with:
      package_name: 'ovos-utils'
```

---

## Scripts

### `scripts/update_version.py`

Bumps the version in a `version.py` file.

```
usage: update_version.py <part> --version-file <path>

part: major | minor | build | alpha
```

Bump rules:
- `major`: `MAJOR += 1`, `MINOR = 0`, `BUILD = 0`, `ALPHA = 1`
- `minor`: `MINOR += 1`, `BUILD = 0`, `ALPHA = 1`
- `build`: `BUILD += 1`, `ALPHA = 1`
- `alpha`: `ALPHA += 1` (or `BUILD += 1` first if currently stable)

### `scripts/remove_alpha.py`

Sets `VERSION_ALPHA = 0` in a `version.py` file (declares stable).

```
usage: remove_alpha.py --version-file <path>
```

### `scripts/get_version.py`

Reads and prints the version string from a `version.py` file. Works without installing the package.

```
usage: get_version.py --version-file <path>
```

Output example: `1.2.3a4` or `1.2.3`

### `scripts/check_downstream.py`

Reports which installed packages depend on a given package, using pipdeptree.

```
usage: check_downstream.py --package <name> --output <file>
```

Requires `pipdeptree` to be installed in the environment.
