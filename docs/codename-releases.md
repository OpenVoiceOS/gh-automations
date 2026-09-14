# OVOS Codename Releases

Stable releases of the OVOS core-centric stack may carry a human-readable **codename**
that groups a set of packages under one named milestone.  The mechanism is opt-in,
additive, and does not change any versioning or PyPI behaviour.

---

## Scheme

Codenames follow an **alphabetical sequence of IAU-recognised star names** —
single-word, unambiguous, and culturally neutral per the
[IAU Working Group on Star Names](https://www.iau.org/science/scientific_bodies/working_groups/280/).

The full ordered list lives in [`codenames/CODENAMES`](../codenames/CODENAMES).
The active name is a single line in [`codenames/CURRENT`](../codenames/CURRENT).

**Current active codename:** see `codenames/CURRENT`.

### Why star names?

- Single-word, globally pronounceable, no cultural baggage.
- Alphabetical ordering maps naturally to release generations (A = first cycle, B = second, …).
- The IAU list is long enough that OVOS will not run out.
- The scheme is **swappable**: replace the CODENAMES file contents and reset CURRENT to
  adopt a different theme without touching any workflow logic.

---

## Mapping to the roadmap

Each codename cycle corresponds to a major OVOS roadmap milestone:

| Cycle | Codename | Roadmap milestone |
|-------|----------|-------------------|
| 1     | Achernar | Namespace migration V2 — ovos-bus-client 2.x stack-wide rollout |
| 2     | Betelgeuse | _(next cycle — TBD)_ |
| …     | …        | … |

A cycle groups one or more stable releases across the OVOS core stack
(ovos-core, ovos-workshop, ovos-bus-client, etc.) that collectively deliver the milestone.
Individual plugin stable releases typically do **not** carry a codename unless they are
part of the milestone.

---

## Opting in

Add `codename: true` to the `publish-stable.yml@dev` call in your repo's stable workflow:

```yaml
# publish_stable.yml (in the consuming repo)
jobs:
  publish_stable:
    if: github.actor != 'github-actions[bot]'
    uses: OpenVoiceOS/gh-automations/.github/workflows/publish-stable.yml@dev
    with:
      codename: true          # <-- opt in here
      publish_release: true
      sync_dev: true
    secrets: inherit
```

When `codename: true`:

1. The `bump_version` job resolves `codenames/CURRENT` from the gh-automations checkout.
2. The GitHub release is named `OVOS <version> "<Codename>"` (e.g. `OVOS 1.3.0 "Achernar"`).
3. The release notes gain a `## <Codename> release` header before the auto-generated changelog.
4. If `notify_matrix: true`, the Matrix message includes the codename.
5. The `codename` output is available to downstream jobs via `needs.<job>.outputs.codename`.

When `codename: false` (default), all existing behaviour is unchanged.

---

## Advancing the pointer

The pointer is advanced **manually** — never automatically.  A human must decide when a
new stable cycle begins.

### Using the workflow (recommended)

1. Go to **Actions → Propose Codename Advance** in the `gh-automations` repo.
2. Run with `dry_run: true` first to preview the transition.
3. Run with `dry_run: false` to advance the pointer and open a draft PR.
4. Review and merge the PR into `dev`.

### Manually

```bash
# In a local clone of gh-automations on a feature branch:
python scripts/resolve_codename.py --codenames-dir codenames --advance
git add codenames/CURRENT
git commit -m "chore(codenames): advance cycle pointer Achernar -> Betelgeuse"
# Open a draft PR into dev
```

### Rules

- Advance the pointer only when the previous cycle is complete (all milestone packages
  have a stable release under that codename).
- Never skip names (the alphabetical order is the record of history).
- If the registry has fewer than 3 names remaining after the current position, append
  new names to `codenames/CODENAMES` before advancing.

---

## Adding names to the registry

Edit [`codenames/CODENAMES`](../codenames/CODENAMES) and append new star names at the
end (one per line, no trailing whitespace).  Open a PR into `dev`.

Do **not** reorder or remove names that have already been consumed (pointer position is
based on order, not lookup; reordering would silently change history).

---

## Resolution script

`scripts/resolve_codename.py` is a zero-dependency Python script:

```bash
# Print the current codename
python scripts/resolve_codename.py --codenames-dir codenames

# Advance the pointer (writes codenames/CURRENT)
python scripts/resolve_codename.py --codenames-dir codenames --advance

# Custom registry location
python scripts/resolve_codename.py --codenames-dir /path/to/codenames
```

Exit code 0 on success, 1 on error (missing file, invalid pointer, no next name).
