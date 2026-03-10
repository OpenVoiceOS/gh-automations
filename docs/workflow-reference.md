
# Reusable Workflow Reference

All reusable workflows are in `.github/workflows/` and are called via:

```yaml
uses: OpenVoiceOS/gh-automations/.github/workflows/<name>.yml@dev
```

> **Ref:** Always use `@dev`.

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
| `matrix_channel` | string | `!WjxEKjjINpyBRPFgxl:krbel.duckdns.org` | Matrix room ID (default: OVOS main channel) |
| `matrix_homeserver` | string | `matrix.org` | Matrix homeserver URL |
| `matrix_message` | string | `""` | Custom Matrix message. Empty = default "PR merged" message. |
| `skip_bot_prs` | boolean | `true` | Skip version bump for PRs from `allcontributors[bot]` and `pre-commit-ci[bot]`. Renovate and Dependabot are intentionally NOT skipped. |
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
| `bump_version` | `merged == true && not a skipped bot \|\| workflow_dispatch` | Determines bump type from PR labels, calls `update_version.py`, commits and pushes to `branch` via `git-auto-commit-action@v5`. Skips PRs from `allcontributors[bot]` and `pre-commit-ci[bot]` when `skip_bot_prs: true`. |
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

### Notes

- `publish_pypi: true` uses `pypa/gh-action-pypi-publish@release/v1` (pinned to stable tag).
- `propose_release` uses `git checkout -B` (force-create) and `gh pr create` with duplicate-check — both steps are idempotent on retry.

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
| `notify_matrix` | boolean | `false` | Send Matrix notification on stable release |
| `matrix_channel` | string | `!WjxEKjjINpyBRPFgxl:krbel.duckdns.org` | Matrix room ID |
| `matrix_homeserver` | string | `matrix.org` | Matrix homeserver URL |
| `matrix_message` | string | `""` | Custom message. Empty = default "stable release" message. |
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
| `notify` | `notify_matrix: true` + `bump_version` succeeded | Calls `notify-matrix.yml@dev` with configurable channel and message |

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

## `build-tests.yml`

Runs build, install, and optionally tests across a configurable matrix of Python versions. Posts a `🔨 Build Tests` section to the PR comment. Also performs a **channel compatibility check** when `package_name` and `version_file` are provided.

**Source:** `.github/workflows/build-tests.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_versions` | string | `'["3.10", "3.11", "3.12", "3.13", "3.14"]'` | JSON array of Python versions to test against |
| `system_deps` | string | `""` | Extra apt packages to install before building (space-separated). Base packages `python3-dev libssl-dev` are always installed. |
| `install_extras` | string | `""` | pip extras appended when installing the built wheel, e.g. `test` or `dev,test` |
| `test_path` | string | `""` | Path passed to pytest after install. Leave empty to skip test execution (build/install verification only). |
| `pr_comment` | boolean | `true` | Post a `🔨 Build Tests` section to the OVOS PR Checks comment. Only fires on `pull_request` events. |
| `package_name` | string | `""` | Package name for the channel compatibility check. If empty, auto-reads from `pyproject.toml`/`setup.py`. Both `package_name` and `version_file` must resolve for the channel check to run. |
| `version_file` | string | `""` | Path to `version.py` in the calling repo (relative to repo root). If empty, auto-detects. Needed for the channel compatibility check. |

### Jobs

| Job | Description |
|-----|-------------|
| `build_tests` | Matrix job. Runs `python -m build`, installs the resulting wheel (with extras if specified), optionally runs `pytest`. Saves per-version result as an artifact. |
| `post_build_report` | Runs after the matrix, only on PR events with `pr_comment: true`. Downloads all result artifacts, runs the channel compatibility check, formats and posts the `section:build` PR comment. |

### Channel compatibility check

The `post_build_report` job checks out [OpenVoiceOS/ovos-releases](https://github.com/OpenVoiceOS/ovos-releases) and calls `scripts/check_release_channels.py` to verify whether the current version of the package is already pinned or constrained in the alpha/testing/stable channel files. This check only runs when both `package_name` and a readable `version_file` can be resolved. If either is missing or the version cannot be parsed, the channel check is silently skipped and the rest of the PR comment is still posted.

### Typical usage

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
      install_extras: 'test'
      test_path: 'test/'
      package_name: 'my-package'
      version_file: 'my_package/version.py'
```

### Notes

- OPM (plugin detection) inputs were removed from this workflow. Use [`opm-check.yml`](#opm-checkyml) for OPM validation.
- The matrix uses `fail-fast: false` so all versions are tested even if one fails.

---

## `opm-check.yml`

Runs OPM (OVOS Plugin Manager) plugin detection and validation on a **single Python version**. Verifies the plugin is discoverable after wheel install, and optionally after editable install (to catch entry-point registration issues). Posts a `🔌 Plugin Detection` section to the PR comment.

**Source:** `.github/workflows/opm-check.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.11` | Python version to use (OPM detection does not vary by Python version) |
| `system_deps` | string | `""` | Extra apt packages to install before building (space-separated) |
| `install_extras` | string | `""` | pip extras appended when installing the built package, e.g. `dev` |
| `plugin_type` | string | `auto` | Plugin type to detect: `auto` (reads from entry points), `skill`, `tts`, `stt`, `wake_word`, `vad`, `phal`, `pipeline`, `utterance_transformer`, `tts_transformer` |
| `entry_point` | string | `""` | Legacy: specific entry point ID to verify (bypasses `plugin_type` auto-detection) |
| `opm_require_found` | boolean | `false` | Fail the job if OPM cannot discover the plugin |
| `opm_validate_interface` | boolean | `true` | Check that the plugin class inherits from the correct abstract base class |
| `opm_test_import` | boolean | `true` | Test that the plugin class is importable and measure import time in ms |
| `opm_perf_threshold_ms` | number | `500` | Import time above this value (ms) is reported as an error |
| `pr_comment` | boolean | `true` | Post a `🔌 Plugin Detection` section to the OVOS PR Checks comment. Only fires on `pull_request` events. |

### Jobs

| Job | Description |
|-----|-------------|
| `opm_check` | Installs `ovos-plugin-manager`, builds the wheel, installs it, then runs `check_opm.py` with `--validate-interface`/`--test-import` flags as configured. If the package is confirmed as an OVOS plugin, re-installs in editable mode and runs a detection-only check (no interface validation, no import test) to catch entry-point registration differences. Uploads `opm_result.json` and `opm_result_editable.json` as artifacts. |
| `post_opm_report` | Downloads the JSON artifacts, formats a PR comment section with status, plugin metadata, system deps, detected types, a validation table (wheel vs editable, import time, interface, config docs), and issues list. Also calls `check_downstream.py` to count dependents and appends the downstream impact note if count > 0. |

### PR comment content

```
✅ Plugin Status: PASS

Plugin Info:
- Name: ovos-tts-plugin-example
- Version: 1.2.3a4
- Description: Example TTS plugin for OVOS

Plugin Types: tts

Validation Table:

| Type | Wheel OPM | Editable OPM | Import | Interface | Config Docs |
|------|-----------|--------------|--------|-----------|-------------|
| tts  | ✅        | ✅           | ✅ 42ms | ✅       | ✅          |

🔗 Downstream Impact: 3 package(s) depend on this plugin
```

Non-plugin repos: `ℹ️ Not an OVOS plugin — OPM check skipped.`

### Typical usage

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
      plugin_type: auto
      opm_require_found: true
      opm_perf_threshold_ms: 500
```

### Notes

- `opm_require_found: false` (default) means the job passes even if OPM cannot find the plugin. This is the safe default for repos that may not be OVOS plugins. Set `opm_require_found: true` to enforce discoverability.
- The editable OPM check runs only when the wheel check confirms `is_ovos_plugin: true` in the JSON output, avoiding unnecessary editable install for non-plugin repos.
- `plugin_type: auto` reads `[project.entry-points."opm.*"]` sections from `pyproject.toml` (or equivalent in `setup.py`) to detect all plugin types the package declares.

---

## `coverage.yml`

Runs `pytest --cov`, generates a coverage report, posts it to the job summary, uploads the XML as an artifact, and (on pull requests) posts a `📊 Coverage` section in the shared OVOS PR Checks comment.

For deploying HTML coverage reports to GitHub Pages, see [`coverage-pages.yml`](#coverage-pagesyml).

**Source:** `.github/workflows/coverage.yml`

### Design choices

- No codecov bot, no external accounts, no `CODECOV_TOKEN`.
- PR comment shows total coverage %, threshold pass/fail, and a collapsible table of under-covered files (files below 80%, or all files if ≤ 10). The `coverage.xml` artifact is available for deep inspection.
- PR comment is a section in the shared [OVOS PR Checks comment](#pr-checks-comment-pattern) — one comment per PR, not a separate coverage comment.
- Job summary is always written (push, dispatch, and PR events alike).
- Pages deployment is a separate workflow (`coverage-pages.yml`) to avoid requiring `pages: write` / `id-token: write` permissions from all callers — only repos that opt in need those.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.11` | Python version to run tests under |
| `system_deps` | string | `""` | Extra apt packages to install before testing (space-separated) |
| `install_extras` | string | `""` | Extra pip install arguments run before tests, e.g. `.[dev]` or `-r requirements/test.txt`. If empty, the package is installed via `pip install -e .[dev]` (falling back to bare install). |
| `test_path` | string | `test/` | Path passed to pytest |
| `coverage_source` | string | `.` | `--cov=<value>` — set to your package directory (e.g. `ovos_core`) to measure only your own code |
| `min_coverage` | number | `0` | Minimum total coverage %. Job fails if below threshold. `0` = disabled. |
| `pr_comment` | boolean | `true` | Post a `📊 Coverage` section to the shared OVOS PR Checks comment. Only fires on `pull_request` events. |
| `artifact_name` | string | `coverage-report` | Name of the uploaded coverage XML artifact |
| `artifact_retention_days` | number | `14` | Days to retain the artifact |

### Jobs

| Job step | Description |
|----------|-------------|
| Checkout + scripts checkout | Checks out the calling repo and (on PR events) the gh-automations scripts |
| Setup Python + Install Dependencies | Installs `pytest`, `pytest-cov`, `coverage[toml]`, `ovoscope`, and the package itself |
| Run Tests with Coverage | `pytest --cov --cov-report=xml --cov-report=json --cov-report=html --cov-report=term-missing`. `continue-on-error: true` so the PR comment posts even when tests fail. |
| Extract Coverage Percentage | Reads `coverage.json` for `totals.percent_covered` |
| Write Job Summary | Coverage table written to `$GITHUB_STEP_SUMMARY` |
| Format coverage section | Generates the PR comment content from `coverage.json` |
| Post coverage section to PR comment | Calls `scripts/update_pr_comment.py` to find-or-create-and-update the OVOS PR Checks comment |
| Upload Coverage XML Artifact | Uploads `coverage.xml` as a workflow artifact |
| Enforce Minimum Coverage Threshold | Fails if `min_coverage > 0` and total is below threshold |
| Fail job if tests failed | Re-raises test failure after the PR comment has been posted |

### Typical usage

```yaml
name: Coverage
on:
  pull_request:
    branches: [dev]
  workflow_dispatch:

permissions:
  pull-requests: write
  contents: read

jobs:
  coverage:
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'
      min_coverage: 80
```

### Known issues

- `pr_comment` only fires on `pull_request` events — job summary is written for all events.
- If all tests are skipped and `coverage.xml` is never generated, the PR comment will note that coverage data is unavailable rather than failing.

---

## `coverage-pages.yml`

Runs `pytest --cov` and deploys the HTML coverage report to GitHub Pages. Designed to run on `push` to `dev` (not PRs), so the Pages site always reflects the latest merged code.

**Source:** `.github/workflows/coverage-pages.yml`

### Design choices

- Separated from `coverage.yml` because GitHub Pages deployment requires `pages: write` and `id-token: write` permissions. Including those in `coverage.yml` caused `startup_failure` in repos that don't enable Pages.
- Callers must grant `pages: write`, `id-token: write`, and `contents: read` at their workflow level.
- The repo must have GitHub Pages enabled with source set to **GitHub Actions** (not `gh-pages` branch).

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.11` | Python version to run tests under |
| `system_deps` | string | `""` | Extra apt packages to install before testing (space-separated) |
| `install_extras` | string | `""` | Extra pip install arguments run before tests |
| `test_path` | string | `test/` | Path passed to pytest |
| `coverage_source` | string | `.` | `--cov=<value>` — set to your package directory |
| `gh_pages_subdir` | string | `coverage` | Sub-directory within the Pages site, e.g. `coverage` → `https://org.github.io/repo/coverage/`. Empty string = deploy at root. |

### Jobs

| Job step | Description |
|----------|-------------|
| Checkout | Checks out the calling repo |
| Setup Python + Install Dependencies | Installs `pytest`, `pytest-cov`, `coverage[toml]`, `ovoscope`, and the package itself |
| Run Tests with Coverage | `pytest --cov --cov-report=html:htmlcov`. `continue-on-error: true` so deployment proceeds even with test failures. |
| Prepare HTML report | Copies `htmlcov/` to `_pages_output/` (with optional subdirectory) |
| Upload Pages artifact | `actions/upload-pages-artifact@v3` |
| Deploy to GitHub Pages | `actions/deploy-pages@v4` |

### Typical usage

```yaml
name: Coverage Pages
on:
  push:
    branches: [dev]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  coverage_pages:
    uses: OpenVoiceOS/gh-automations/.github/workflows/coverage-pages.yml@dev
    secrets: inherit
    with:
      coverage_source: 'my_package'
```

### Prerequisites

1. Enable GitHub Pages in repo settings → Source: **GitHub Actions**
2. Grant `pages: write` and `id-token: write` permissions in the calling workflow

---

## `license-check.yml`

Checks all installed dependencies for licenses incompatible with the **OVOS universal donor policy** (Apache 2.0). Uses [`pilosus/action-pip-license-checker@v3`](https://github.com/pilosus/action-pip-license-checker). Also runs `pip-licenses` to generate a full per-package breakdown shown in a collapsible table in the PR comment.

**Source:** `.github/workflows/license-check.yml`

### Universal Donor Policy

OVOS packages are Apache 2.0. To preserve this as a universal donor license:

| Category | Examples | Default action |
|---|---|---|
| `StrongCopyleft` | GPL v2, GPL v3 | **Fail** — incompatible with Apache 2.0 distribution |
| `NetworkCopyleft` | AGPL | **Fail** — triggered by network use, not just distribution |
| `WeakCopyleft` | LGPL, EUPL | **Fail** (conservative) — safe as-a-library, but flag for review |
| `Other` | EULA, custom | **Fail** — unknown terms = unknown risk |
| `Error` | not found | **Fail** — can't audit what you can't see |
| MPL (Mozilla Public License) | MPL-2.0 | **Allowed** — file-level copyleft, safe as Apache 2.0 library user |

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.14` | Python version |
| `install_extras` | string | `""` | pip extras to install alongside the package, e.g. `[extras,linux]` |
| `system_deps` | string | `""` | Extra `apt-get` packages beyond the base `python3-dev libssl-dev` |
| `exclude_packages` | string | `""` | PCRE regex of package names to exclude from the check |
| `exclude_licenses` | string | `^Mozilla Public License.*` | PCRE regex of license identifiers to exclude. Default allows MPL. |
| `fail_licenses` | string | `StrongCopyleft,NetworkCopyleft,WeakCopyleft,Other,Error` | Comma-separated license categories that cause failure. See policy table above. |
| `warn_only` | boolean | `false` | When true, report violations in the PR comment but do NOT fail the job. Useful for repos in transition. |
| `pr_comment` | boolean | `true` | Post a `⚖️ License Check` section to the shared OVOS PR Checks comment. Only fires on `pull_request` events. |

### PR comment content

The comment includes:
- Status header (pass/fail + package count)
- Violations report (if any) in a code block
- License distribution summary (e.g. `42× MIT, 18× Apache Software License, ...`)
- Full per-package breakdown in a collapsible `<details>` table with columns: Package, Version, License, URL. Packages with violations are flagged with ⚠️.
- Policy footnote

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

## `pip-audit.yml`

Scans installed dependencies for known CVEs using [`pypa/gh-action-pip-audit`](https://github.com/pypa/gh-action-pip-audit). Optionally uploads a SARIF report to GitHub's Security tab.

**Source:** `.github/workflows/pip-audit.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.14` | Python version to audit against |
| `install_extras` | string | `""` | pip extras to install |
| `system_deps` | string | `""` | Extra `apt-get` packages beyond `python3-dev` |
| `ignore_vulns` | string | `GHSA-r9hx-vwmv-q579` | Newline-separated GHSA IDs to ignore. Default ignores GHSA-r9hx-vwmv-q579 (setuptools path traversal — dev-only, not exploitable at OVOS runtime). |
| `warn_only` | boolean | `false` | When true, report vulnerabilities in the PR comment but do NOT fail the job. Useful for repos that want visibility without blocking merges. |
| `pr_comment` | boolean | `true` | Post a `🔒 Security (pip-audit)` section to the shared OVOS PR Checks comment. Only fires on `pull_request` events. |
| `upload_sarif` | boolean | `true` | Upload a SARIF report to GitHub's Security tab (Code scanning alerts). Requires the repo to have GitHub Advanced Security enabled, or be public. Uses `github/codeql-action/upload-sarif@v3`. `continue-on-error: true` so the job does not fail for private repos without GHAS. |

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

## `release-preview.yml`

Reads `version.py`, predicts the next version from PR labels and/or title using conventional commit prefixes, and posts a `🏷️ Release Preview` section to the OVOS PR Checks comment. Also performs a channel compatibility check when a package name is resolvable.

**Source:** `.github/workflows/release-preview.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.14` | Python version |
| `package_name` | string | `""` | Package name for the channel compatibility check. If empty, auto-reads from `pyproject.toml`/`setup.py`. |
| `version_file` | string | `""` | Path to `version.py` (relative to repo root). If empty, auto-detects. |
| `pr_comment` | boolean | `true` | Post `🏷️ Release Preview` section to OVOS PR Checks comment |

### Permissions

`pull-requests: write`, `contents: read`

### Steps

| Step | Description |
|------|-------------|
| Checkout + scripts checkout | Checks out the calling repo and (on PR events) the gh-automations scripts |
| Setup Python | `actions/setup-python@v5` |
| Run release check | `check_release.py --version-file … --output-json /tmp/release-report.json`. Env vars: `PR_LABELS_JSON`, `PR_TITLE`. `continue-on-error: true`. |
| Format release section | Inline Python reads `release-report.json` → `release-section.md` |
| Post release section to PR comment | Calls `update_pr_comment.py` with `--section-id release` |
| Fail job if release check failed | Re-raises only for malformed `version.py` (parse error) |

### Bump detection rules

Labels take precedence over PR title. Priority: major > minor > build.

| Label | Bump |
|-------|------|
| `breaking`, `breaking change` | major |
| `feature`, `enhancement` | minor |
| `fix`, `bug`, `bugfix` | build |

| PR title prefix | Bump |
|-----------------|------|
| `breaking change:`, `feat!:`, `fix!:` | major |
| `feat:`, `feature:` | minor |
| `fix:` | build |
| `docs:`, `chore:`, `refactor:`, `test:`, `style:`, `perf:`, `ci:`, `build:` | alpha only |
| _(no prefix)_ | alpha only |

### PR comment content (with label)

```
**Current:** `1.2.3a4` → **Next:** `1.3.0a1`

| Signal | Value |
|--------|-------|
| Label | `feature` |
| PR title | `feat: add multi-language support` |
| Bump | minor |

✅ PR title follows conventional commit format.
```

### PR comment content (no label, no prefix)

```
**Current:** `1.2.3a4` → **Next:** `1.2.3a5`

| Signal | Value |
|--------|-------|
| Label | _(none)_ |
| PR title | `update readme` |
| Bump | alpha |

⚠️ No conventional commit prefix — alpha-only bump.
Suggested: `fix: update the thing` or `feat: update the thing`
```

No `version.py` found: `ℹ️ No version.py found — release preview not available.`

### Typical usage

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

---

## `repo-health.yml`

Checks that a repo contains the required files (`README`, `LICENSE`, `pyproject.toml`/`setup.py`, `version.py` with valid block markers) and greets first-time contributors.

**Source:** `.github/workflows/repo-health.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `version_file` | string | `""` | Path to `version.py` (relative to repo root). If empty, auto-detects root or `pkg/version.py`. |
| `pr_comment` | boolean | `true` | Post a `📋 Repo Health` section to the OVOS PR Checks comment. Only fires on `pull_request` events. |

### PR comment content

- Current version from `version.py`
- Per-file status: ✅ present / ❌ required and missing / ⚠️ optional and missing
- Version block marker validation (START/END_VERSION_BLOCK)
- First-time contributor greeting (separate `👋 Welcome` section posted in the same PR comment when `author_association` is `FIRST_TIME_CONTRIBUTOR` or `FIRST_TIMER`)

### Typical usage

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
      version_file: 'my_package/version.py'
```

---

## `skill-check.yml`

Analyses an OVOS skill repository for locale structure, language coverage, skill.json validity, and gitlocalize readiness. Silently passes for non-skill repos by default.

**Source:** `.github/workflows/skill-check.yml`

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `python_version` | string | `3.11` | Python version |
| `locale_dir` | string | `""` | Locale root path. Empty = auto-detect. |
| `skip_if_not_skill` | boolean | `true` | Silently pass if no `ovos.plugin.skill` entry point found |
| `fail_on_missing_en_us` | boolean | `true` | Fail if en-us locale directory is absent |
| `fail_on_invalid_skill_json` | boolean | `false` | Fail if en-us skill.json is invalid or missing required fields |
| `pr_comment` | boolean | `true` | Post `🎙️ Skill` section to OVOS PR Checks comment |

### Permissions

`pull-requests: write`, `contents: read`

### Steps

Follows the canonical 3-phase pattern (`continue-on-error` → format → post → re-raise):

| Step | Description |
|------|-------------|
| Checkout + scripts checkout | Checks out the calling repo and (on PR events) the gh-automations scripts |
| Setup Python | `actions/setup-python@v5` |
| Run skill check | `check_skill.py --repo-root . --locale-dir … --output-json /tmp/skill-report.json`. `continue-on-error: true`. |
| Format skill section | Inline Python reads `skill-report.json` → `skill-section.md` |
| Post skill section to PR comment | Calls `update_pr_comment.py` with `--section-id skill` |
| Skip if not an OVOS skill repo | Exits 0 if `is_skill: false` and `skip_if_not_skill: true` |
| Fail if en-us locale is missing | Exits 1 if `has_en_us: false` and `fail_on_missing_en_us: true` |
| Fail if skill.json is invalid | Exits 1 if JSON malformed or required fields missing and `fail_on_invalid_skill_json: true` |
| Fail job if skill check failed | Re-raises error after comment is posted |

### PR comment content

```
🎙️ **ovos-skill-hello-world.openvoiceos** — 14 languages

**en-us:** 2 intents · 4 dialogs · skill.json ✅

<details><summary>Translation coverage (13 languages)</summary>

| Language | Coverage |
|----------|----------|
| ca-es | ✅ 100% (6/6) |
| de-de | ⚠️ 83.3% (5/6) |

</details>

**Gitlocalize:** ✅ sync script · ✅ translations/ · ✅ sync workflow
```

Coverage icons: ✅ ≥95% · ⚠️ 50–94% · ❌ <50%. Non-skill repos: `ℹ️ Not an OVOS skill repo — check skipped.`

### Typical usage

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

### Skill repos with gitlocalize

To also enforce gitlocalize readiness, set `fail_on_invalid_skill_json: true` and ensure your repo has a `scripts/sync_translations.py` and `translations/` directory before enabling the check.

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

## `python-support.yml` *(legacy)*

Runs an install matrix across Python versions and install modes (regular + editable). Optionally checks OPM detection using a legacy `entry_point` ID. Posts a `🐍 Python Support` section to the PR comment.

**Source:** `.github/workflows/python-support.yml`

> **Legacy status:** Most repos now use [`build-tests.yml`](#build-testsyml) which provides the same build/install matrix without the editable-mode complexity, plus pytest integration. For OPM detection, use [`opm-check.yml`](#opm-checkyml). Retain `python-support.yml` only for repos that specifically need editable-mode compatibility testing.

### Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `runner` | string | `ubuntu-latest` | Runner label |
| `package_name` | string | `""` | Package name for the channel compatibility check |
| `python_versions` | string | `'["3.10", "3.11", "3.12", "3.13", "3.14"]'` | JSON array of Python versions |
| `version_file` | string | `""` | Path to `version.py` for the channel compatibility check |
| `install_modes` | string | `'["regular", "editable"]'` | JSON array of install modes |
| `install_extras` | string | `""` | pip extras to install |
| `system_deps` | string | `""` | Extra apt packages beyond `python3-dev libssl-dev` |
| `entry_point` | string | `""` | Legacy OPM entry point ID to verify (only used when set) |
| `pr_comment` | boolean | `true` | Post `🐍 Python Support` section to OVOS PR Checks comment |

---

## `sync-translations.yml`

Synchronises [gitlocalize-app](https://gitlocalize.com/) translation commits. Runs `scripts/sync_translations.py` in the calling repo when triggered by a push from `gitlocalize-app[bot]` or by manual `workflow_dispatch`.

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

Some existing `sync_tx.yml` files use `github.event.head_commit.author.username == 'gitlocalize-app[bot]'` for bot detection. This field is not reliable. The reusable workflow uses `github.actor == 'gitlocalize-app[bot]'` which is correct. When migrating, remove the old per-repo `sync_tx.yml` and replace with a call to this reusable workflow.

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

## PR Checks Comment Pattern

The following workflows post their results as named sections in a **single shared PR comment** rather than separate bot comments:

| Workflow | Section ID | Section title |
|----------|-----------|---------------|
| `repo-health.yml` | `health` | `📋 Repo Health` |
| `repo-health.yml` | `welcome` | `👋 Welcome` (first-time contributors only) |
| `release-preview.yml` | `release` | `🏷️ Release Preview` |
| `pip-audit.yml` | `security` | `🔒 Security (pip-audit)` |
| `license-check.yml` | `license` | `⚖️ License Check` |
| `python-support.yml` | `python_support` | `🐍 Python Support` |
| `build-tests.yml` | `build` | `🔨 Build Tests` |
| `opm-check.yml` | `opm` | `🔌 Plugin Detection` |
| `coverage.yml` | `coverage` | `📊 Coverage` |
| `skill-check.yml` | `skill` | `🎙️ Skill` |

The comment is identified by the HTML marker `<!-- ovos-pr-checks -->` in its body. Each workflow manages its own section:

```
<!-- ovos-pr-checks -->
## OVOS PR Checks

<!-- section:health -->
### 📋 Repo Health
✅ All required files present.
...
<!-- /section:health -->

<!-- section:build -->
### 🔨 Build Tests
✅ All versions pass
...
<!-- /section:build -->

<!-- section:opm -->
### 🔌 Plugin Detection
✅ Plugin Status: PASS
...
<!-- /section:opm -->

<!-- section:coverage -->
### 📊 Coverage
✅ **87.3%** total coverage
...
<!-- /section:coverage -->

<!-- section:license -->
### ⚖️ License Check
✅ No license violations found (42 packages).
...
<!-- /section:license -->

<!-- section:security -->
### 🔒 Security (pip-audit)
✅ No known vulnerabilities found.
...
<!-- /section:security -->

<!-- section:release -->
### 🏷️ Release Preview
**Current:** `0.0.1a4` → **Next:** `0.0.2a1`
...
<!-- /section:release -->
```

Sections appear as each workflow completes. Reruns update only the relevant section without touching others.

The aggregation logic lives in `scripts/update_pr_comment.py` — see the [Scripts Reference](#scripts-reference) below.

### Adding a new section

To add a new check type to the aggregated comment from any workflow:

1. Generate the section content as a markdown file (e.g. `/tmp/my-section.md`).
2. Check out gh-automations and call the script:

```yaml
- name: Checkout gh-automations scripts
  if: github.event_name == 'pull_request'
  uses: actions/checkout@v4
  with:
    repository: OpenVoiceOS/gh-automations
    ref: dev
    path: _gh_automations/

- name: Post section to PR comment
  if: github.event_name == 'pull_request'
  run: |
    python3 _gh_automations/scripts/update_pr_comment.py \
      --repo "${{ github.repository }}" \
      --pr "${{ github.event.pull_request.number }}" \
      --section-id "my-check" \
      --title "🔍 My Check" \
      --content-file /tmp/my-section.md
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

The `permissions: pull-requests: write` must be declared on the calling job.

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

### `scripts/check_opm.py`

Detects and validates OVOS plugins via OPM. Supports multi-plugin-type repos. Outputs a structured JSON report.

**Key functions:**
- `auto_detect_plugin_types()` — `scripts/check_opm.py:308` — scans `[project.entry-points."opm.*"]` in `pyproject.toml` or `setup.py`
- `validate_plugin_import(module_path, class_name)` — `scripts/check_opm.py:132` — imports the class, measures time in ms, detects missing dependencies
- `check_plugin_interface(plugin_cls, short_type)` — `scripts/check_opm.py:152` — verifies `issubclass()` against the correct abstract base (9 types)
- `extract_metadata()` — `scripts/check_opm.py:54` — reads name, version, authors, description, homepage, requires_python
- `extract_system_deps()` — `scripts/check_opm.py:108` — reads `[tool.ovos.build] system-dependencies`
- `validate_config_docs(repo_root)` — `scripts/check_opm.py:176` — searches for `settingsmeta.json`
- `collect_issues(result)` — `scripts/check_opm.py:217` — aggregates issues list
- `compute_status(issues)` — `scripts/check_opm.py:292` — returns `pass`, `warning`, or `fail`
- `check_opm(plugin_type, entry_point, output_json, ...)` — `scripts/check_opm.py:406` — main entry point

```
usage: check_opm.py \
    [--plugin-type auto|skill|tts|stt|wake_word|vad|phal|pipeline|utterance_transformer|tts_transformer] \
    [--entry-point <id>] \
    [--output-json <path>] \
    [--validate-interface | --no-validate-interface] \
    [--test-import | --no-test-import] \
    [--perf-threshold-ms <ms>]
```

### `scripts/check_skill.py`

Analyses a checked-out OVOS skill repository. Outputs a JSON report. Stdlib only.

**Key functions:**
- `is_skill_repo(repo_root)` — `scripts/check_skill.py:39`
- `find_locale_dir(repo_root, override="")` — `scripts/check_skill.py:52`
- `check_translation_completeness(locale_dir, en_us_files)` — `scripts/check_skill.py:157`
- `run_checks(repo_root, locale_dir_override="")` — `scripts/check_skill.py:220`

```
usage: check_skill.py [--repo-root .] [--locale-dir ""] [--output-json /tmp/skill-report.json]
```

### `scripts/check_release.py`

Reads `version.py`, predicts next version from PR labels/title. Stdlib only.

**Key functions:**
- `detect_bump_part(labels, pr_title)` — `scripts/check_release.py:74`
- `compute_next_version(major, minor, build, alpha, part)` — `scripts/check_release.py:120`
- `run_checks(version_file, pr_labels_json, pr_title)` — `scripts/check_release.py:196`

```
usage: check_release.py --version-file version.py \
    [--pr-labels-json "[]"] \
    [--pr-title ""] \
    [--output-json /tmp/release-report.json]

env vars (override CLI): PR_LABELS_JSON, PR_TITLE
```

### `scripts/update_pr_comment.py`

Manages the shared **OVOS PR Checks** comment on a pull request. Finds the comment by the invisible HTML marker `<!-- ovos-pr-checks -->`, then replaces or appends the named section. Creates the comment if it doesn't exist yet.

Uses only Python stdlib (`urllib`, `json`, `re`) — no extra dependencies.

**Key logic:**
- `find_ovos_comment(repo, pr_number)` — paginates the PR comments API to find the marker — `scripts/update_pr_comment.py:56`
- `insert_or_replace_section(body, section_id, title, content)` — regex replace within `<!-- section:X --> … <!-- /section:X -->` delimiters — `scripts/update_pr_comment.py:81`

```
usage: update_pr_comment.py \
    --repo owner/repo \
    --pr 123 \
    --section-id coverage \
    --title "📊 Coverage" \
    --content-file /tmp/section.md

environment: GITHUB_TOKEN   (required)
```
