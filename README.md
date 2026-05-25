
# gh-automations

Reusable GitHub Actions workflows and Python scripts for the [OpenVoiceOS](https://github.com/OpenVoiceOS) ecosystem.

Used by **209 repos** across the OVOS project. See [docs/repos.md](docs/repos.md) for the full list.

---

## Reusable Workflows

All workflows live in `.github/workflows/` and are called from other repos via:

```yaml
uses: OpenVoiceOS/gh-automations/.github/workflows/<name>.yml@dev
```

| Workflow | Purpose | Docs |
|----------|---------|------|
| `publish-alpha.yml` | Bump version, publish alpha to PyPI, open release PR | [reference](docs/workflow-reference.md#publish-alphayml) |
| `publish-stable.yml` | Remove alpha flag, publish stable to PyPI, tag release | [reference](docs/workflow-reference.md#publish-stableyml) |
| `build-tests.yml` | Build/install/test matrix across Python versions; channel compatibility | [reference](docs/workflow-reference.md#build-testsyml) |
| `opm-check.yml` | OPM plugin detection, interface validation, import timing | [reference](docs/workflow-reference.md#opm-checkyml) |
| `coverage.yml` | Run pytest with coverage; post diff report to PR comment | [reference](docs/workflow-reference.md#coverageyml) |
| `coverage-pages.yml` | Run tests with coverage; deploy HTML report to GitHub Pages | [reference](docs/workflow-reference.md#coverage-pagesyml) |
| `license-check.yml` | Check all dependency licenses for copyleft violations | [reference](docs/workflow-reference.md#license-checkyml) |
| `pip-audit.yml` | Scan dependencies for known CVEs; optional SARIF upload | [reference](docs/workflow-reference.md#pip-audityml) |
| `release-preview.yml` | Predict next version from PR labels/title | [reference](docs/workflow-reference.md#release-previewyml) |
| `repo-health.yml` | Required files check, version block validation, first-time contributor greeting | [reference](docs/workflow-reference.md#repo-healthyml) |
| `skill-check.yml` | Locale coverage and skill.json validity | [reference](docs/workflow-reference.md#skill-checkyml) |
| `locale-check.yml` | Verify locale folder is included in package build (pyproject.toml + SOURCES.txt) | [reference](docs/workflow-reference.md#locale-checkyml) |
| `ovoscope.yml` | End-to-end skill tests with auto-install of pipeline plugins | [reference](docs/workflow-reference.md#ovoscopeyml) |
| `downstream-check.yml` | Report which packages depend on a given package | [reference](docs/workflow-reference.md#downstream-checkyml) |
| `python-support.yml` | Install matrix (regular + editable) per Python version *(legacy — REMOVE AFTER 2027-01-01)* | [reference](docs/workflow-reference.md#python-supportyml-legacy) |
| `sync-translations.yml` | Sync gitlocalize-app[bot] translation commits | [reference](docs/workflow-reference.md#sync-translationsyml) |
| `notify-matrix.yml` | Send a message to the OVOS Matrix channel | [reference](docs/workflow-reference.md#notify-matrixyml) |
| `type-check.yml` | Run mypy; post 🔎 Type Check section to PR comment | [reference](docs/workflow-reference.md#type-checkyml) |
| `docs-check.yml` | Verify required docs files exist; optional markdownlint | [reference](docs/workflow-reference.md#docs-checkyml) |

---

## Quick Start

See [docs/repo-setup.md](docs/repo-setup.md) for the complete guide to setting up a new OVOS repo.

The minimum required files for a new package:

```
.github/workflows/
  conventional-label.yaml   # auto-label PRs by commit type
  release_workflow.yml       # alpha release on PR merge to dev
  publish_stable.yml         # stable release on PR merge to master
  license_tests.yml          # license compliance check
  build_tests.yml            # build/install/test matrix (build-tests.yml)
  repo_health.yml            # required-files check + contributor greeting
  release_preview.yml        # next-version prediction on every PR
```

For OVOS **plugin repos**, also add:

```
.github/workflows/
  opm_check.yml              # OPM plugin detection + interface validation
```

For OVOS **skill repos**, also add:

```
.github/workflows/
  skill_check.yml            # locale coverage + skill.json validity
  sync_translations.yml      # gitlocalize translation sync
```

---

## Release Flow

See [docs/release-flow.md](docs/release-flow.md) for the full lifecycle diagram.

```
PR merged to dev
    └─► publish-alpha.yml
            ├─ Bump version in version.py
            ├─ Publish alpha to PyPI
            └─ Open release PR to master

PR merged to master (after human review)
    └─► publish-stable.yml
            ├─ Remove alpha suffix
            ├─ Tag GitHub release
            └─ Sync master → dev
```

---

## Python Scripts

Scripts in `scripts/` are checked out by the reusable workflows at run time:

| Script | Purpose |
|--------|---------|
| `_version_utils.py` | Shared parsing: `read_version`, `format_version`, `write_version_block` |
| `update_version.py` | Bump version in `version.py` (major/minor/build/alpha) |
| `remove_alpha.py` | Set `VERSION_ALPHA = 0` (declare stable) |
| `get_version.py` | Read and print version string from `version.py` |
| `check_downstream.py` | Report downstream dependents via pipdeptree |
| `update_pr_comment.py` | Manage the shared OVOS PR Checks comment (find-or-create, section replace) |
| `check_skill.py` | Analyse skill locale structure, skill.json, and translation coverage |
| `check_locale_build.py` | Verify locale folder is included in package build (pyproject.toml + SOURCES.txt) |
| `check_release.py` | Predict next version from PR labels/title using conventional commit rules |
| `check_opm.py` | Detect OVOS plugins via OPM, validate interface, measure import time |

> **Note:** The reusable workflows check out this repo at runtime pinned to `ref: dev`.

---

## Bot Safety

All workflows include guards against accidental bot-triggered runs:

- **`publish-alpha.yml`** — `bump_version` job only runs when `github.event.pull_request.merged == true` or `workflow_dispatch`
- **`publish-stable.yml`** — `bump_version` job skips when `github.actor == 'github-actions[bot]'` (prevents infinite loop when the version commit triggers another push event)
- **`release_workflow.yml`** (per-repo) — supports `workflow_dispatch` for manual reruns

---

## Documentation

| File | Contents |
|------|---------|
| [docs/index.md](docs/index.md) | High-level overview and navigation |
| [docs/release-flow.md](docs/release-flow.md) | Full release lifecycle, versioning rules, channel overview |
| [docs/workflow-reference.md](docs/workflow-reference.md) | All inputs, outputs, and jobs for each reusable workflow |
| [docs/repo-setup.md](docs/repo-setup.md) | Step-by-step setup guide for new repos |
| [docs/repos.md](docs/repos.md) | All repos currently using these automations |
| [docs/maintenance.md](docs/maintenance.md) | Open technical debt and opportunistic rollouts |

---

## New Maintainer Checklist

If you have just inherited or taken ownership of this repo, complete these steps:

### Day 1 — Get oriented

1. **Read [`docs/index.md`](docs/index.md)** — workflow overview, scripts reference, and cross-references.
2. **Read [`docs/maintenance.md`](docs/maintenance.md)** — open technical debt and opportunistic rollouts.
3. **Run the test suite** to confirm nothing is broken:
   ```bash
   cd gh-automations
   pip install pytest pyyaml
   pytest test/ -v
   ```
4. **Check [`docs/repos.md`](docs/repos.md)** — many repos depend on this library. Understand the caller blast radius before any change.

### Before making changes

- **Check `dev` vs `master` semantics:** `dev` is active development; `master` is the frozen v1 stable baseline. All PRs target `dev`.
- **Test locally** before pushing: the test suite covers every Python script. Add tests for any new scripts.
- **Never force-push `master`** — caller repos use `@master` or `@dev` refs; a rewrite would break them.
- **Do not commit root-level `*.md` files.** Planning, audit, FAQ, and session-log files belong in `docs/` or in chat — not at the repo root. `README.md` is the only allowed root-level Markdown file.

### After making changes

1. Run `pytest test/ -v` — must be green before committing.
2. Review `docs/workflow-reference.md` — if inputs/outputs changed, update the reference.

### Deprecated workflows

Two workflows are deprecated and scheduled for removal on **2027-01-01**:
- `coverage-pages.yml` → migrate callers to `coverage.yml` with `deploy_pages: true`
- `python-support.yml` → migrate callers to `build-tests.yml`

Before removing either, check `docs/repos.md` for active callers.
