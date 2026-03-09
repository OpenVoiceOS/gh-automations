Last Edit: Claude Sonnet 4.6 - 2026-03-09 - Motive: Document master-freeze / dev-active branching; update all @master refs; add versioning policy; expand cross-references.

# gh-automations

`gh-automations` (hosted at [TigreGotico/gh-automations](https://github.com/TigreGotico/gh-automations)) is the shared GitHub Actions automation library for all OpenVoiceOS repositories. It provides reusable workflows and Python scripts that implement the OVOS rolling-release model: bump version on PR merge to `dev`, publish alpha to PyPI, open a release PR to `master`, then on merge declare stable and tag.

As of 2026-03-09 it is used by **209 OVOS repositories**.

---

## Branching & Versioning Policy

gh-automations itself follows the same `dev` / `master` model it enforces in all calling repos.

| Ref | Status | Use for |
|-----|--------|---------|
| `@master` | **Frozen (v1)** | Legacy callers. No new development. Do not use for new repos. |
| `@dev` | **Active** | All new repos and migrated repos. Receives all fixes and new features. |
| `@v2` _(future)_ | Planned | Will be tagged from `dev` when breaking changes warrant a formal major version. |

**Why freeze `@master`?**
Every OVOS repo calls these workflows with `@<ref>`. Because GitHub resolves the ref at call time, pinning to `@master` means all 209 callers would instantly receive any change merged to `master`. By freezing `master` and doing all work on `dev`, changes are opt-in: a repo migrates when its maintainer opens a PR changing `@master` → `@dev`.

### Scripts checkout note

The reusable workflows check out this repo at runtime to access `scripts/` — but without a pinned ref:

```yaml
- uses: actions/checkout@v4
  with:
    repository: TigreGotico/gh-automations
    path: action/github/
    # no ref: — uses default branch
```

This means whichever branch is set as **GitHub default branch** is what all callers (regardless of `@master` or `@dev`) will use for scripts. Keep the default branch in sync with the intent:
- While `@master` is the recommended ref → keep `master` as default.
- When `@dev` becomes the recommended ref → change the GitHub default branch to `dev`.

See [SUGGESTIONS.md](../SUGGESTIONS.md#3-pin-the-scripts-checkout-ref-in-reusable-workflows) for the proposed fix.

---

## Reusable Workflows

All workflows are called with:
```yaml
uses: TigreGotico/gh-automations/.github/workflows/<name>.yml@dev
```

| Workflow | Purpose | Used by |
|---|---|---|
| `publish-alpha.yml` | Bump version, publish alpha to PyPI, open release PR | All 209 repos — `release_workflow.yml` |
| `publish-stable.yml` | Remove alpha suffix, tag stable release | All 209 repos — `publish_stable.yml` |
| `license-check.yml` | Scan dependencies for copyleft/incompatible licenses | 126 repos — `license_tests.yml` |
| `notify-matrix.yml` | Post release notifications to OVOS Matrix channel | All 209 repos — `release_workflow.yml` (notify job) |
| `pip-audit.yml` | Scan installed dependencies for CVEs | Selected repos — `pipaudit.yml` |
| `downstream-check.yml` | Report which packages depend on a given package | 13 repos — `downstream.yml` |

Full input/output/job reference: [workflow-reference.md](workflow-reference.md)

---

## Python Scripts

Located in `scripts/`. Checked out by the reusable workflows at run time — not installed as a package.

| Script | Key function | Purpose |
|---|---|---|
| `update_version.py` | `update_version(part, version_file)` — `scripts/update_version.py:34` | Bump `VERSION_MAJOR/MINOR/BUILD/ALPHA` in `version.py` |
| `remove_alpha.py` | `update_alpha(version_file)` — `scripts/remove_alpha.py:10` | Set `VERSION_ALPHA = 0` (declare stable) |
| `get_version.py` | `get_version(version_file)` — `scripts/get_version.py:5` | Read and print current version string |
| `check_downstream.py` | `get_downstream(package_name)` — `scripts/check_downstream.py:61` | Report reverse dependencies using `pipdeptree` |

All four scripts share the same `version.py` block format:

```python
# START_VERSION_BLOCK
VERSION_MAJOR = 1
VERSION_MINOR = 2
VERSION_BUILD = 3
VERSION_ALPHA = 4   # 0 = stable
# END_VERSION_BLOCK
```

`read_version()` in `update_version.py:11` and `get_version()` in `get_version.py:5` implement identical parsing logic. See [SUGGESTIONS.md](../SUGGESTIONS.md#1-deduplicate-read_version-logic) for the proposed consolidation.

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
| [ovos-utils](https://github.com/OpenVoiceOS/ovos-utils) | All 6 workflows (downstream tracking: 13 repos depend on it) |
| [ovos-bus-client](https://github.com/OpenVoiceOS/ovos-bus-client) | All 6 workflows |
| [ovos-workshop](https://github.com/OpenVoiceOS/ovos-workshop) | All 6 workflows |
| [ovos-messagebus](../../ovos-messagebus/docs/index.md) | `publish-alpha.yml`, `publish-stable.yml`, `license-check.yml`, `notify-matrix.yml` |
| [ovos-releases](https://github.com/OpenVoiceOS/ovos-releases) | Manages `constraints-alpha/testing/stable.txt` — updated after stable releases |
| [raspOVOS](../../raspOVOS/docs/index.md) | Uses `constraints-alpha.txt` URL as `CONSTRAINTS` env var during image builds |

### Related workspace documentation

- [OpenVoiceOS Workspace — AGENTS.md](../../AGENTS.md)
- [Package Inventory](../../PACKAGE_INVENTORY.md)
