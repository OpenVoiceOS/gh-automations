Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Update all @master refs to @dev; add migration section for existing repos; expand branch protection and secret requirements.

# Setting Up a New OVOS Repo

This guide covers the minimal CI/CD files for a new OVOS Python package. All workflow references use `@dev` — the active branch of gh-automations. If you are migrating an existing repo that currently uses `@master`, see [Migrating an Existing Repo](#migrating-an-existing-repo) below.

---

## Required Files

### 1. `version.py`

Place this inside your package directory (e.g. `my_package/version.py`). The block between the marker comments is the only part that automation reads and rewrites:

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

Configure dynamic versioning so the package version is always read from `version.py` at build time:

```toml
[project]
name = "my-package"
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "my_package.version.__version__"}
```

Do **not** hard-code the version in `pyproject.toml` — it must always come from `version.py`.

### 3. `.github/workflows/conventional-label.yaml`

Auto-labels PRs based on conventional commit title prefixes. These labels drive the version bump type.

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

Label mapping:

| PR title prefix | Label assigned | Version bump |
|---|---|---|
| `feat:` | `feature` | minor |
| `fix:` | `fix` | build |
| `BREAKING CHANGE:` | `breaking` | major |
| anything else | _(none)_ | alpha only |

### 4. `.github/workflows/release_workflow.yml`

Triggers on PR merge to `dev`. Bumps version, publishes alpha, opens release PR.

The `publish_alpha` job **must** allow both merged PRs and manual dispatch — the `workflow_dispatch` clause enables manual reruns from the GitHub Actions UI:

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
      version_file: 'my_package/version.py'  # ← update this path
      update_changelog: true
      publish_prerelease: true
      propose_release: true
      changelog_max_issues: 100

  notify:
    if: github.event.pull_request.merged == true
    needs: publish_alpha
    uses: OpenVoiceOS/gh-automations/.github/workflows/notify-matrix.yml@dev
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

The `if: github.actor != 'github-actions[bot]'` guard is **required** on the calling job. Without it, the auto-commit pushed by the workflow would retrigger `push: master` and loop.

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
      version_file: 'my_package/version.py'  # ← update this path
      publish_release: true
      sync_dev: true

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
    uses: OpenVoiceOS/gh-automations/.github/workflows/license-check.yml@dev
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
    uses: OpenVoiceOS/gh-automations/.github/workflows/downstream-check.yml@dev
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
    uses: OpenVoiceOS/gh-automations/.github/workflows/pip-audit.yml@dev
    with:
      install_extras: ''
```

---

## Required GitHub Secrets

Configure these under repo Settings → Secrets and variables → Actions:

| Secret | Usage |
|--------|-------|
| `PYPI_TOKEN` | Publish to PyPI (both alpha and stable) |
| `MATRIX_TOKEN` | Post notifications to Matrix chat (only if using `notify-matrix.yml`) |

For organisation repos, these are usually set at the organisation level and inherited.

---

## Branch Protection (recommended)

Configure under repo Settings → Branches:

| Branch | Rules |
|--------|-------|
| `dev` | Require PR before merging; require status checks (`build_tests`, `unit_tests`) to pass |
| `master` | Require PR before merging; require at least 1 approving review; no direct pushes |

---

## Allowed Actors

| Actor | Blocked by | Reason |
|-------|-----------|--------|
| `github-actions[bot]` | `publish_stable.yml` `if:` guard | Prevents loop when the version commit pushes to `master` |
| Closed-but-unmerged PRs | `publish-alpha.yml` `bump_version` job `if:` | Only runs when `merged == true` |

Manual dispatch (`workflow_dispatch`) is always allowed for both `release_workflow.yml` and `publish_stable.yml`.

---

## Migrating an Existing Repo

If your repo currently calls `@master` workflows, migration to `@dev` is a single PR per repo:

1. Find all `.github/workflows/*.yml` files that call gh-automations.
2. Replace every occurrence of `@master` (in `uses:` lines referencing `OpenVoiceOS/gh-automations`) with `@dev`.
3. Open the PR targeting `dev` (or `master` if your repo has no dev branch).
4. Wait for CI to pass.
5. Merge.

There is no functional difference on day one — `@dev` currently contains the same workflows as `@master` plus any fixes applied since the freeze. The benefit is that future improvements land automatically in your repo once you are on `@dev`.

**Bulk migration** across many repos is best done with a script using the GitHub API or `gh` CLI to open PRs programmatically.
