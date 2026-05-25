# Maintenance Notes

Tracker for open technical debt and opportunistic improvements in `gh-automations`. Closed items are dropped — `git log` is the history.

## Open issues

### Deprecated workflows pending removal
**Files:** `.github/workflows/coverage-pages.yml`, `.github/workflows/python-support.yml`

Both carry a `REMOVE AFTER: 2027-01-01` banner. Before removal, confirm zero active callers via `docs/repos.md`. Both still use `python -m pip install` directly (rather than `uv`) — frozen for back-compat until removal.

### `continue-on-error: true` requires discipline
**Files:** `skill-check.yml`, `pip-audit.yml`, `coverage.yml`, `opm-check.yml`, `spec-lint.yml`

The three-phase pattern (`continue-on-error: true` → format section → post PR comment → explicit `exit 1`) is intentional. If a future contributor removes the re-raise step, tool failures become invisible. Every `continue-on-error: true` step carries an inline reference to its mandatory re-raise.

### No YAML schema tests for workflow inputs
`test/test_workflow_inputs.py` covers parse-ability and the `timeout-minutes` invariant. It does not yet assert that every reusable workflow declares the section-id input pattern or that `uses:` refs in calling repos resolve. Worth extending opportunistically.

### Codecov dependency in caller repos
66 OVOS caller repos still use `codecov/codecov-action`. `coverage.yml` (this repo) is the self-hosted replacement using only `GITHUB_TOKEN`. Migrate opportunistically — never bulk-migrate.

## Opportunistic rollouts

### `skill-check.yml` in OVOS skill repos
Add to skill repos' `.github/workflows/` whenever touching them for any other reason. Default settings are safe — non-skill repos silently pass.

### `spec-lint.yml` in skill repos with locale folders
Same pattern. Validates `locale/` against OVOS-INTENT-1/-2 via `ovos-spec-lint`. Default `skip_if_no_locale: true` makes it safe for non-skill repos.

### `pyproject.toml` native version support
All OVOS repos use the `version.py` block. For non-OVOS repos and future migration, `_version_utils.py` could detect and read/write `[project] version` in `pyproject.toml` when `version.py` is absent. Lower priority — the OVOS `version.py` format is mandatory and is not going away.
