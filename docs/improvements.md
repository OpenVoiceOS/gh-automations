# CI/CD Improvement Tracker

Patterns extracted or centralized in `gh-automations`, and remaining work across OVOS repos.

---

## Reusable Workflows — Status

| Workflow | Status | Rollout |
|----------|--------|---------|
| `publish-alpha.yml` | ✅ Done | All repos |
| `publish-stable.yml` | ✅ Done | All repos |
| `license-check.yml` | ✅ Done | All 126 repos with `license_tests.yml` migrated |
| `notify-matrix.yml` | ✅ Done | All 189 inline `notify:` jobs migrated |
| `downstream-check.yml` | ✅ Done | All 13 repos with `downstream.yml` migrated |
| `pip-audit.yml` | ⚠️ Partial | Only `ovos-core` and `ovos-plugin-manager` |

---

## Completed Fixes (Session 2026-03)

### Bot loop vulnerability — FIXED
**Problem:** `publish_stable.yml` triggered on `push: master`. The version commit from
`git-auto-commit-action` would retrigger the workflow, causing double-tagging or failures.

**Fix:** Added `if: github.actor != 'github-actions[bot]'` to:
- `bump_version` job inside the reusable `publish-stable.yml`
- `publish_stable` job in all 203 calling `publish_stable.yml` files

### workflow_dispatch missing — FIXED
**Problem:** 62 `release_workflow.yml` files had no `workflow_dispatch:` trigger, making
manual reruns impossible.

**Fix:** Added `workflow_dispatch:` to all 62 files.

### Manual dispatch blocked by job-level if — FIXED
**Problem:** 63 `release_workflow.yml` files had `if: github.event.pull_request.merged == true`
on the `publish_alpha` job — this silently blocked manual dispatch.

**Fix:** Changed condition to `github.event.pull_request.merged == true || github.event_name == 'workflow_dispatch'`.

### Stale `actions/create-release@v1` — FIXED
**Problem:** 58 `publish_stable.yml` and `release_workflow.yml` files had leftover
`Create Release` steps referencing non-existent `${{ steps.version.outputs.version }}`.

**Fix:** Removed all stale steps. Release creation is handled by the reusable `publish-stable.yml`.

### Invalid action versions — FIXED
**Problem:** 308 workflow files used `actions/checkout@v6` or `actions/setup-python@v6`
(neither version exists). Also `python-version: 3.14` in ~85 files.

**Fix:** Bulk-replaced with `@v4`, `@v5`, and `'3.11'` across 472 files.

### `setup.py` build commands — FIXED
**Problem:** Many files still used `python setup.py bdist_wheel` (legacy, requires `setup.py`).

**Fix:** Replaced with `python -m build` across all affected files.

### Inline `downstream.yml` — FIXED
**Problem:** 13 repos had duplicated inline downstream tracking using `pip install -r constraints-alpha.txt`
(which installs everything in the file, taking many minutes).

**Fix:** Migrated to reusable `downstream-check.yml` which uses `pip install -c constraints.txt <package>`.

### Legacy publish_minor/major/build workflows — FIXED
**Problem:** 13 repos (e.g. `ovos-lingua-franca`, `ovos-vad-plugin-webrtcvad`) still used old
single-purpose publish workflows instead of the unified release flow.

**Fix:** Replaced with standard `release_workflow.yml` + `publish_stable.yml` + `conventional-label.yaml`.

---

## Remaining Work

### Expand `pip-audit.yml` rollout — MEDIUM PRIORITY

Currently only `ovos-core` and `ovos-plugin-manager` run pip-audit. All packages with
runtime dependencies should check for known CVEs.

Suggested initial rollout:
```
ovos-workshop, ovos-bus-client, ovos-config, ovos-utils, ovos-plugin-manager,
ovos-dinkum-listener, ovos-audio, ovos-gui, ovos-PHAL
```

Add to each repo as `pipaudit.yml`:
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

### Trigger ovos-releases on stable publish — HIGH PRIORITY

After a stable release, users on the stable channel can wait up to 6 hours for the
constraints file to pick up the new version (current cron interval).

**Proposed:** After `publish-stable.yml` completes, dispatch a `repository_dispatch` to
`ovos-releases` to trigger `gen_constraints.yml` immediately.

Add to `publish-stable.yml` as an optional job:
```yaml
  trigger_constraints_update:
    needs: bump_version
    if: ${{ always() && needs.bump_version.result == 'success' && inputs.trigger_ovos_releases }}
    runs-on: ubuntu-latest
    steps:
      - uses: peter-evans/repository-dispatch@v3
        with:
          token: ${{ secrets.OVOS_RELEASES_DISPATCH_TOKEN }}
          repository: OpenVoiceOS/ovos-releases
          event-type: stable-package-published
          client-payload: '{"package": "${{ github.repository }}", "version": "${{ needs.bump_version.outputs.version }}"}'
```

Requires: `OVOS_RELEASES_DISPATCH_TOKEN` secret (a PAT with `repo` scope on `ovos-releases`).

### Add `renovate.json` to all repos — LOW PRIORITY

Renovate bot keeps action versions and dependency pins current automatically.
The shared config should be centralized in `TigreGotico/gh-automations` and referenced by all repos:

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "packageRules": [
    {"matchManagers": ["github-actions"], "automerge": true}
  ]
}
```

### OIDC trusted publishing for PyPI — LOW PRIORITY

Currently all repos use `PYPI_TOKEN` secrets, requiring per-repo token rotation.
OIDC trusted publishing would eliminate the need for tokens:

1. Configure trusted publisher on PyPI (per package, linked to the GitHub repo and workflow)
2. Remove `password: ${{secrets.PYPI_TOKEN}}` from `pypa/gh-action-pypi-publish`
3. Add `permissions: id-token: write` to the publish job

### Clean up `.bak` files — LOW PRIORITY

Many repos have leftover `setup.py.bak` and `MANIFEST.in.bak` from the pyproject.toml migration.
These should be removed via a bulk script.

### Add `SECURITY.md` and `CODEOWNERS` templates — LOW PRIORITY

No OVOS repos currently have `SECURITY.md` or `CODEOWNERS`. These can be templated once
and placed in a `.github/` repository for org-wide defaults.
