# Setting Up a New OVOS Repo

This guide covers the minimal set of CI/CD files needed for a new OVOS Python package.

## Required Files

### 1. `version.py`

Place this inside your package directory (e.g. `my_package/version.py`):

```python
# The following lines are replaced during the release process.
# START_VERSION_BLOCK
VERSION_MAJOR = 0
VERSION_MINOR = 0
VERSION_BUILD = 1
VERSION_ALPHA = 1
# END_VERSION_BLOCK

__version__ = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}" + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
```

### 2. `pyproject.toml`

Configure dynamic versioning so the package version is always read from `version.py`:

```toml
[project]
name = "my-package"
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "my_package.version.__version__"}
```

### 3. `.github/workflows/conventional-label.yaml`

Auto-labels PRs based on conventional commit titles (drives version bump type):

```yaml
on:
  pull_request_target:
    types: [opened, edited]
name: conventional-release-labels
jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: bcoe/conventional-release-labels@v1
```

PR title prefixes → labels:
- `feat:` → `feature` (minor bump)
- `fix:` → `fix` (build bump)
- `BREAKING CHANGE:` → `breaking` (major bump)
- anything else → alpha-only bump

### 4. `.github/workflows/release_workflow.yml`

Triggers on PR merge to `dev`. Bumps version, publishes alpha, opens release PR.

The `publish_alpha` job must allow both merged PRs and manual dispatch:

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
    uses: TigreGotico/gh-automations/.github/workflows/publish-alpha.yml@master
    secrets: inherit
    with:
      branch: 'dev'
      version_file: 'my_package/version.py'  # ← update this
      update_changelog: true
      publish_prerelease: true
      propose_release: true
      changelog_max_issues: 100

  notify:
    if: github.event.pull_request.merged == true
    needs: publish_alpha
    uses: TigreGotico/gh-automations/.github/workflows/notify-matrix.yml@master
    secrets: inherit
    with:
      message: "new ${{ github.event.repository.name }} PR merged! https://github.com/${{ github.repository }}/pull/${{ github.event.number }}"

  publish_pypi:
    needs: publish_alpha
    if: success()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: dev
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install Build Tools
        run: python -m pip install build
      - name: Build
        run: python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@master
        with:
          password: ${{secrets.PYPI_TOKEN}}
```

### 5. `.github/workflows/publish_stable.yml`

Triggers on push to `master`. Declares stable, tags release, publishes.

The `if: github.actor != 'github-actions[bot]'` guard is **required** to prevent an infinite loop: the version commit from this workflow would otherwise retrigger itself on `push: master`.

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
      version_file: 'my_package/version.py'  # ← update this
      publish_release: true

  publish_pypi:
    needs: publish_stable
    if: success()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: master
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install Build Tools
        run: python -m pip install build
      - name: Build
        run: python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@master
        with:
          password: ${{secrets.PYPI_TOKEN}}

  sync_dev:
    needs: publish_stable
    if: success()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: master
      - name: Push master -> dev
        uses: ad-m/github-push-action@v0.8.0
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          branch: dev
```

---

## Optional Files

### `build_tests.yml` — Verify the package builds cleanly

```yaml
name: Run Build Tests
on:
  push:
    branches: [master]
  pull_request:
    branches: [dev]
    paths: ['pyproject.toml']
  workflow_dispatch:

jobs:
  build_tests:
    strategy:
      matrix:
        python-version: ["3.10", "3.11"]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: python -m pip install build wheel
      - run: python -m build
      - run: pip install .
```

### `license_tests.yml` — Check dependency licenses

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
      install_extras: ''          # e.g. '[extras]'
      system_deps: ''             # e.g. 'swig libfann-dev'
      # exclude_packages: '^(tqdm).*'       # default
      # exclude_licenses: '^(Mozilla).*$'   # default
```

### `downstream.yml` — Track downstream dependents

For core packages (e.g. `ovos-utils`, `ovos-bus-client`) that many other packages depend on:

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
      package_name: 'my-package'
```

### `pipaudit.yml` — CVE scanning

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
      install_extras: ''
```

---

## Required GitHub Secrets

| Secret | Usage |
|--------|-------|
| `PYPI_TOKEN` | Publish to PyPI (both alpha and stable) |
| `MATRIX_TOKEN` | Post notifications to Matrix chat |

## Branch Protection (recommended)

Configure in GitHub → Settings → Branches:
- `dev`: require PR, require status checks (`build_tests`, `unit_tests`)
- `master`: require PR, require review, no direct pushes

## Allowed Actors

Workflows use `github.actor` to block bots:

| Actor | Blocked by |
|-------|-----------|
| `github-actions[bot]` | `publish_stable.yml` — prevents loop on version commit |
| Closed-but-unmerged PRs | `publish-alpha.yml` — only runs when `merged == true` |

Manual dispatch is always allowed for both `release_workflow.yml` and `publish_stable.yml`.
