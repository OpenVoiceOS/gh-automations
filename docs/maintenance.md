# Maintenance

<!-- agent-hint: how to change this repo safely, and the open technical debt. verify: pytest test/ -->

This page tells a maintainer how to change `gh-automations` safely. It also lists the open technical debt and the opportunistic rollouts.

## Change this repo

Many repos call these workflows at `@dev`, so a defect on `dev` breaks their CI at once. See [repos.md](repos.md) and the caller counts in [index.md](index.md) before you change a workflow.

1. Open each pull request against `dev`. `master` is the frozen stable baseline. Never force-push `master` or `dev`, because caller repos reference them.
2. Run the test suite:

   ```bash
   uv pip install pytest pyyaml ovos-plugin-manager actionlint-py
   pytest test/ -v
   ```

3. Add a test for each new script in `scripts/`.
4. When an input, a default or an output changes, update [workflow-reference.md](workflow-reference.md).
5. Keep Markdown files in `docs/`. `README.md` is the only Markdown file at the repo root.

The safety rules for workflow files are in [index.md](index.md#for-agents).

## Bot guards

- `publish-alpha.yml`: the `bump_version` job runs only when the pull request is merged, or on `workflow_dispatch`. With `skip_bot_prs: true` (the default), it skips pull requests from `allcontributors[bot]` and `pre-commit-ci[bot]`. Renovate and Dependabot pull requests make an alpha.
- `publish-stable.yml`: the `bump_version` job skips when `github.actor` is `github-actions[bot]`. This stops a loop when the version commit starts another push event.

## Open issues

### Deprecated workflows pending removal
**Files:** `.github/workflows/coverage-pages.yml`, `.github/workflows/python-support.yml`

Both carry a `REMOVE AFTER: 2027-01-01` banner. Before removal, confirm zero active callers via `docs/repos.md`. Both still use `uv pip install`: frozen for back-compat until removal.

### `continue-on-error: true` requires discipline
**Files:** `skill-check.yml`, `pip-audit.yml`, `coverage.yml`, `opm-check.yml`, `spec-lint.yml`

The three-phase pattern (`continue-on-error: true` → format section → post PR comment → explicit `exit 1`) is intentional. If a future contributor removes the re-raise step, tool failures become invisible. Every `continue-on-error: true` step carries an inline reference to its mandatory re-raise.

### No YAML schema tests for workflow inputs
`test/test_workflow_inputs.py` covers parse-ability and the `timeout-minutes` invariant. It does not yet assert that every reusable workflow declares the section-id input pattern or that `uses:` refs in calling repos resolve. Worth extending opportunistically.

### Codecov dependency in caller repos
66 OVOS caller repos still use `codecov/codecov-action`. `coverage.yml` (this repo) is the self-hosted replacement using only `GITHUB_TOKEN`. Migrate opportunistically: never bulk-migrate.

## Opportunistic rollouts

### `skill-check.yml` in OVOS skill repos
Add to skill repos' `.github/workflows/` whenever touching them for any other reason. Default settings are safe: non-skill repos silently pass.

### `spec-lint.yml` in skill repos with locale folders
Same pattern. Validates `locale/` against OVOS-INTENT-1/-2 via `ovos-spec-lint`. Default `skip_if_no_locale: true` makes it safe for non-skill repos.

### `pyproject.toml` native version support
All OVOS repos use the `version.py` block. For non-OVOS repos and future migration, `_version_utils.py` could detect and read/write `[project] version` in `pyproject.toml` when `version.py` is absent. Lower priority: the OVOS `version.py` format is mandatory and is not going away.

---
[← Repos](repos.md) · [Home](index.md)
