
# Setting Up a New OVOS Repo

This guide covers the minimal CI/CD files for a new OVOS Python package. All workflow references use `@dev`: the active branch of gh-automations. If you are migrating an existing repo that currently uses `@master`, see [Migrating an Existing Repo](#migrating-an-existing-repo) below.

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

Do **not** hard-code the version in `pyproject.toml`: it must always come from `version.py`.

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

The `publish_alpha` job **must** allow both merged PRs and manual dispatch: the `workflow_dispatch` clause enables manual reruns from the GitHub Actions UI:

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
      publish_pypi: true        # builds with python -m build, publishes to PyPI
      notify_matrix: true       # posts to OVOS Matrix channel
      changelog_max_issues: 100
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
      publish_pypi: true        # builds with python -m build, publishes to PyPI
      sync_dev: true            # pushes master → dev after stable release
      notify_matrix: true       # posts to OVOS Matrix channel
```

---

## Optional Files

### `build_tests.yml`: Build, install, and test across Python versions

```yaml
name: Run Build Tests
on:
  push:
    branches: [master]
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  build_tests:
    uses: OpenVoiceOS/gh-automations/.github/workflows/build-tests.yml@dev
    secrets: inherit
    with:
      python_versions: '["3.10", "3.11", "3.12"]'
      test_path: 'test/'            # optional: run pytest after install
      package_name: 'my-package'    # needed for channel compatibility check
      version_file: 'my_package/version.py'  # needed for channel compatibility check
```

To skip test execution and only verify build+install, omit `test_path` (defaults to empty: build/install only).

### `opm_check.yml`: OPM plugin detection (plugin repos only)

```yaml
name: OPM Check
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  opm_check:
    uses: OpenVoiceOS/gh-automations/.github/workflows/opm-check.yml@dev
    secrets: inherit
    with:
      plugin_type: auto             # auto-detect from pyproject.toml entry points
      opm_require_found: true       # fail if OPM cannot discover the plugin
      opm_perf_threshold_ms: 500    # warn if import takes longer than 500ms
```

### `license_tests.yml`: Check dependency licenses

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
      system_deps: ''             # e.g. 'portaudio19-dev'
      # exclude_packages: '^(chardet).*'         # per-package exclusions
      # exclude_licenses: '^Mozilla Public License.*'  # MPL allowed by default
```

### `downstream.yml`: Track downstream dependents

For core packages (e.g. `ovos-utils`, `ovos-bus-client`) that many other packages depend on. The report is uploaded as a workflow artifact (no longer committed to the branch).

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

### `pipaudit.yml`: CVE scanning

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

### `coverage.yml`: Test coverage with PR diff comments

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

### `coverage_pages.yml`: Deploy coverage HTML to GitHub Pages

Use `coverage.yml` with `deploy_pages: true`: no separate file needed. Requires Pages enabled in repo settings (Source: Deploy from a branch → `gh-pages`).

```yaml
name: Coverage
on:
  push:
    branches: [dev]
  pull_request:
    branches: [dev]
  workflow_dispatch:
permissions:
  contents: write   # required for the gh-pages git push
jobs:
  coverage:
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'   # measure only your own code
      deploy_pages: true              # push HTML report to gh-pages branch
```

**Prerequisites**: Go to repo Settings → Pages → Source → select "Deploy from a branch" → `gh-pages`.

### `lint.yml`: Ruff + pre-commit

```yaml
name: Lint
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  lint:
    uses: OpenVoiceOS/gh-automations/.github/workflows/lint.yml@dev
    secrets: inherit
    with:
      ruff: true          # ruff check . (default)
      pre_commit: false   # set true if you have .pre-commit-config.yaml
```

Results are posted to the OVOS PR Checks comment. The job fails if any tool finds issues.

### `skill_check.yml`: Skill locale + skill.json (skill repos only)

```yaml
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

Default `skip_if_not_skill: true` means this safely no-ops on non-skill repos.

### `type_check.yml`: mypy static type checking

```yaml
name: Type Check
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  type_check:
    uses: OpenVoiceOS/gh-automations/.github/workflows/type-check.yml@dev
    secrets: inherit
    with:
      mypy_args: 'my_package'    # check only your own code
      fail_on_errors: false      # informational only (default)
```

Results are posted to the OVOS PR Checks comment. Set `fail_on_errors: true` to block merges on type errors.

### `docs_check.yml`: Required documentation file check

```yaml
name: Docs Check
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  docs_check:
    uses: OpenVoiceOS/gh-automations/.github/workflows/docs-check.yml@dev
    secrets: inherit
    with:
      required_files: 'README.md'   # default
      fail_on_missing: false    # informational only (default)
```

Posts a 📚 Docs section showing which required files are present or missing. Set `fail_on_missing: true` to fail the job when any listed file is absent.

### `release_preview.yml`: Next-version prediction

```yaml
name: Release Preview
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  release_preview:
    uses: OpenVoiceOS/gh-automations/.github/workflows/release-preview.yml@dev
    secrets: inherit
```

### `repo_health.yml`: Required-files check + first-time contributor greeting

```yaml
name: Repo Health
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:
jobs:
  repo_health:
    uses: OpenVoiceOS/gh-automations/.github/workflows/repo-health.yml@dev
    secrets: inherit
    with:
      version_file: 'my_package/version.py'  # if empty, auto-detects
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
| `dev` | Require PR before merging. Require status checks (`build_tests`, `unit_tests`) to pass |
| `master` | Require PR before merging. Require at least 1 approving review. No direct pushes |

---

## Allowed Actors

| Actor | Blocked by | Reason |
|-------|-----------|--------|
| `github-actions[bot]` | `publish_stable.yml` `if:` guard | Prevents loop when the version commit pushes to `master` |
| Closed-but-unmerged PRs | `publish-alpha.yml` `bump_version` job `if:` | Only runs when `merged == true` |

Manual dispatch (`workflow_dispatch`) is always allowed for both `release_workflow.yml` and `publish_stable.yml`.

---

## Migrating an Existing Repo

### Migrate codecov → `coverage.yml` (66 repos affected)

If your repo currently uses `codecov/codecov-action` in `unit_tests.yml`, migrate to the self-hosted `coverage.yml` workflow:

**Step 1:** Remove the codecov upload step from `unit_tests.yml`:

```yaml
# REMOVE this step:
- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v3    # or v2/v4/v5
  with:
    token: ${{ secrets.CODECOV_TOKEN }}
```

**Step 2:** Add a new `coverage.yml` workflow (see [Optional Files → coverage.yml](#coverageyml--test-coverage-with-pr-diff-comments)):

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
      coverage_source: 'my_package'
```

**Step 3:** Remove the `CODECOV_TOKEN` secret from the repo if it was only used for coverage uploads.

**Why migrate?** `coverage.yml` is self-hosted (no external account required), uses only `GITHUB_TOKEN`,
and produces a consistent PR comment format across caller repos.

**Note:** Do NOT do a bulk migration wave: migrate opportunistically when touching a repo's `.github/workflows/` for another reason.

### Migrate `@master` → `@dev` refs

All new repos should reference `@dev`. If you find `@master` refs in a repo's caller workflows:

```yaml
# Before:
uses: OpenVoiceOS/gh-automations/.github/workflows/build-tests.yml@master
# After:
uses: OpenVoiceOS/gh-automations/.github/workflows/build-tests.yml@dev
```

Do this opportunistically when touching any workflow file in a repo.

---
[← License Whitelist](license-whitelist.md) · [Home](index.md) · [Repos →](repos.md)
