
# gh-automations

`gh-automations` (hosted at [OpenVoiceOS/gh-automations](https://github.com/OpenVoiceOS/gh-automations)) is the shared GitHub Actions automation library for all OpenVoiceOS repositories. It provides reusable workflows and Python scripts that implement the OVOS rolling-release model: bump version on PR merge to `dev`, publish alpha to PyPI, open a release PR to `master`, then on merge declare stable and tag.

As of 2026-03-09 it is used by **209 OVOS repositories**. All calling repos should reference `@dev`:

```yaml
uses: OpenVoiceOS/gh-automations/.github/workflows/<name>.yml@dev
```

### Scripts checkout

The reusable workflows check out this repo at runtime to access `scripts/`, pinned to `ref: dev`:

```yaml
- uses: actions/checkout@v4
  with:
    repository: OpenVoiceOS/gh-automations
    ref: dev
    path: _gh_automations/
```

---

## Reusable Workflows

All workflows are called with:
```yaml
uses: OpenVoiceOS/gh-automations/.github/workflows/<name>.yml@dev
```

| Workflow | Purpose | Used by |
|---|---|---|
| `publish-alpha.yml` | Bump version, publish alpha to PyPI, open release PR | All 209 repos — `release_workflow.yml` |
| `publish-stable.yml` | Remove alpha suffix, tag stable release, sync dev | All 209 repos — `publish_stable.yml` |
| `build-tests.yml` | Build/install/test matrix across Python versions; channel compatibility check | All repos — `build_tests.yml` |
| `opm-check.yml` | OPM plugin detection, interface validation, import timing | Plugin repos — `opm_check.yml` |
| `coverage.yml` | Run pytest with coverage; post diff report to PR comment | Selected repos — `coverage.yml` |
| `coverage-pages.yml` | Run tests with coverage and deploy HTML report to GitHub Pages | Selected repos — `coverage_pages.yml` |
| `license-check.yml` | Scan dependencies for copyleft/incompatible licenses | 126 repos — `license_tests.yml` |
| `pip-audit.yml` | Scan installed dependencies for CVEs; optional SARIF upload | Selected repos — `pipaudit.yml` |
| `release-preview.yml` | Predict next version from PR labels/title | All repos — `release_preview.yml` |
| `repo-health.yml` | Check required files, version block, greet first-time contributors | All repos — `repo_health.yml` |
| `skill-check.yml` | Locale coverage and skill.json validity | Skill repos — `skill_check.yml` |
| `downstream-check.yml` | Report which packages depend on a given package | 13 repos — `downstream.yml` |
| `python-support.yml` | Install matrix (regular + editable) per Python version *(legacy — REMOVE AFTER 2027-01-01)* | Superseded by `build-tests.yml` for most repos |
| `sync-translations.yml` | Sync gitlocalize-app[bot] translation commits | Skill repos — `sync_translations.yml` |
| `notify-matrix.yml` | Post release notifications to OVOS Matrix channel | Via `publish-alpha.yml`/`publish-stable.yml` `notify_matrix` input |
| `type-check.yml` | Run mypy and post 🔎 Type Check section to PR comment | Repos with type hints |
| `docs-check.yml` | Verify required docs files exist; optional markdownlint | All repos |

Full input/output/job reference: [workflow-reference.md](workflow-reference.md)

---

## Python Scripts

Located in `scripts/`. Checked out by the reusable workflows at run time — not installed as a package.

| Script | Key function | Purpose |
|---|---|---|
| `_version_utils.py` | `read_version(version_file)` — `scripts/_version_utils.py:17` | Parse `version.py` block; shared by all version scripts |
| `_version_utils.py` | `format_version(major, minor, build, alpha)` — `scripts/_version_utils.py:54` | Format PEP 440 version string |
| `_version_utils.py` | `write_version_block(version_file, ...)` — `scripts/_version_utils.py:72` | Rewrite block, preserve surrounding content |
| `update_version.py` | `update_version(part, version_file)` — `scripts/update_version.py:22` | Bump `VERSION_MAJOR/MINOR/BUILD/ALPHA` in `version.py` |
| `remove_alpha.py` | `update_alpha(version_file)` — `scripts/remove_alpha.py:17` | Set `VERSION_ALPHA = 0` (declare stable) |
| `get_version.py` | `get_version(version_file)` — `scripts/get_version.py:15` | Read and print current version string |
| `check_downstream.py` | `get_downstream(package_name)` — `scripts/check_downstream.py:61` | Report reverse dependencies using `pipdeptree` |
| `update_pr_comment.py` | `find_ovos_comment(repo, pr)` — `scripts/update_pr_comment.py:56` | Find-or-create the shared OVOS PR Checks comment |
| `update_pr_comment.py` | `insert_or_replace_section(body, ...)` — `scripts/update_pr_comment.py:81` | Replace a named section in the shared PR comment |
| `check_skill.py` | `run_checks(repo_root, ...)` — `scripts/check_skill.py:220` | Full skill locale and skill.json analysis |
| `check_release.py` | `run_checks(version_file, ...)` — `scripts/check_release.py:196` | Predict next version from PR labels/title |
| `check_opm.py` | `check_opm(plugin_type, entry_point, ...)` — `scripts/check_opm.py:406` | OPM plugin detection, interface validation, import timing |

All version scripts share the `version.py` block format:

```python
# START_VERSION_BLOCK
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_BUILD = 3
VERSION_ALPHA = 4   # 0 = stable
# END_VERSION_BLOCK
```

---

## Documentation

- [Release Flow](release-flow.md) — Full lifecycle: alpha → stable → channel constraints; gh-automations own versioning policy
- [Workflow Reference](workflow-reference.md) — All inputs, outputs, jobs, and bot guards for each reusable workflow
- [Repo Setup](repo-setup.md) — Step-by-step guide for adding CI/CD to a new OVOS repo (uses `@dev`)
- [Repos](repos.md) — Complete inventory of all 209 repos using gh-automations, grouped by category

---

## Quick Links

| Resource | Path |
|----------|------|
| Machine-readable facts | [`../QUICK_FACTS.md`](../QUICK_FACTS.md) |
| Common questions | [`../FAQ.md`](../FAQ.md) |
| Change log | [`../MAINTENANCE_REPORT.md`](../MAINTENANCE_REPORT.md) |
| Known issues | [`../AUDIT.md`](../AUDIT.md) |
| Improvement proposals | [`../SUGGESTIONS.md`](../SUGGESTIONS.md) |

---

## Cross-References

### Key repos that call these workflows

| Repo | Workflows used |
|---|---|
| [ovos-core](https://github.com/OpenVoiceOS/ovos-core) | `publish-alpha.yml`, `publish-stable.yml`, `license-check.yml`, `notify-matrix.yml`, `downstream-check.yml` |
| [ovos-utils](https://github.com/OpenVoiceOS/ovos-utils) | All core workflows (downstream tracking: 13 repos depend on it) |
| [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client) | All core workflows |
| [ovos-workshop](https://github.com/OpenVoiceOS/ovos-workshop) | All core workflows |
| [ovos-messagebus](../../ovos-messagebus/docs/index.md) | `publish-alpha.yml`, `publish-stable.yml`, `license-check.yml`, `notify-matrix.yml` |
| [ovos-releases](https://github.com/OpenVoiceOS/ovos-releases) | Manages `constraints-alpha/testing/stable.txt` — updated after stable releases |
| [raspOVOS](../../raspOVOS/docs/index.md) | Uses `constraints-alpha.txt` URL as `CONSTRAINTS` env var during image builds |

### Related workspace documentation

- [OpenVoiceOS Workspace — AGENTS.md](../../AGENTS.md)
- [Package Inventory](../../PACKAGE_INVENTORY.md)
