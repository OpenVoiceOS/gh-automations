# gh-automations

Reusable GitHub Actions workflows and scripts for the [OpenVoiceOS](https://github.com/OpenVoiceOS) ecosystem.

Used by **209 repos** across the OVOS project. See [docs/repos.md](docs/repos.md) for the full list.

---

## Reusable Workflows

All workflows live in `.github/workflows/` and are called from other repos via:

```yaml
uses: TigreGotico/gh-automations/.github/workflows/<name>.yml@master
```

| Workflow | Purpose | Docs |
|----------|---------|------|
| `publish-alpha.yml` | Bump version, publish alpha to PyPI, open release PR | [reference](docs/workflow-reference.md#publish-alphayml) |
| `publish-stable.yml` | Remove alpha flag, publish stable to PyPI, tag release | [reference](docs/workflow-reference.md#publish-stableyml) |
| `license-check.yml` | Check all dependency licenses for copyleft violations | [reference](docs/workflow-reference.md#license-checkyml) |
| `notify-matrix.yml` | Send a message to the OVOS Matrix channel | [reference](docs/workflow-reference.md#notify-matrixyml) |
| `pip-audit.yml` | Scan dependencies for known CVEs | [reference](docs/workflow-reference.md#pip-audityml) |
| `downstream-check.yml` | Report which packages depend on a given package | [reference](docs/workflow-reference.md#downstream-checkyml) |

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
  build_tests.yml            # build smoke test
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

## Scripts

Python scripts in `scripts/` are used by the reusable workflows:

| Script | Purpose |
|--------|---------|
| `update_version.py` | Bump version in `version.py` (major/minor/build/alpha) |
| `remove_alpha.py` | Set `VERSION_ALPHA = 0` (declare stable) |
| `get_version.py` | Read and print version string from `version.py` |
| `check_downstream.py` | Report downstream dependents via pipdeptree |

---

## Bot Safety

All workflows include guards against accidental bot-triggered runs:

- **`publish-alpha.yml`** — `bump_version` job only runs when `github.event.pull_request.merged == true` or `workflow_dispatch`
- **`publish-stable.yml`** — `bump_version` job skips when `github.actor == 'github-actions[bot]'` (prevents infinite loop when the version commit triggers another push event)
- **`release_workflow.yml`** (per-repo) — supports `workflow_dispatch` for manual reruns; `publish_alpha` job allows both merged PRs and manual dispatch

---

## Documentation

| File | Contents |
|------|---------|
| [docs/release-flow.md](docs/release-flow.md) | Full release lifecycle, versioning rules, channel overview |
| [docs/workflow-reference.md](docs/workflow-reference.md) | All inputs, outputs, and jobs for each reusable workflow |
| [docs/repo-setup.md](docs/repo-setup.md) | Step-by-step setup guide for new repos |
| [docs/improvements.md](docs/improvements.md) | Planned improvements and migration status |
| [docs/repos.md](docs/repos.md) | All repos currently using these automations |
