# License whitelist

Central, audited list of packages that the license check (`license-check.yml`)
flags by category but which are safe under the OVOS universal-donor policy
(Apache 2.0). The reusable workflow applies this list by default, so individual
repos can leave `exclude_packages` empty and still pass. Per-repo
`exclude_packages` values are still honoured: they are unioned with this list,
not replaced.

This Markdown file is the human-auditable source of truth. The workflow embeds
the equivalent PCRE regex inline (`.github/workflows/license-check.yml`, the
`Build exclude regex` step), with a one-line justification comment per entry.
When you change one, change the other to match.

## How an entry is justified

A package belongs here only if **all** of the following hold:

- The license metadata trips the checker (`WeakCopyleft`, `StrongCopyleft`,
  `Other`, or `Error`).
- The package is used as an unmodified library dependency (we link/import it,
  we do not modify or redistribute its source).
- Under that usage, the real obligations are permissive: either the package is
  genuinely permissive and only mis-detected, or it is dual-licensed with a
  permissive option we elect.

Padding the list defeats its purpose. Add a package only with a correct,
specific justification.

## Whitelisted packages

| Package | Declared license | Flagged category | Justification |
|---------|------------------|------------------|---------------|
| `tqdm` | `MPL-2.0 AND MIT` | WeakCopyleft | Dual-licensed. The MIT option makes it fully permissive to use as a library; the checker flags it only because of the MPL-2.0 component. We use `tqdm` as an unmodified, imported progress-bar dependency (pulled transitively by `huggingface_hub`, and thus by many OVOS ML repos): no MPL-2.0 files are modified or redistributed, so the MIT terms govern and it is compatible with Apache 2.0 distribution. |
| `marisa-trie` | `MIT AND (BSD-2-Clause OR LGPL-2.1-or-later)` | WeakCopyleft | Dual-licensed. The checker flags the whole expression because of the LGPL-2.1-or-later option, but the license grants an explicit `BSD-2-Clause OR LGPL` choice: we elect the permissive BSD-2-Clause. We use `marisa-trie` as an unmodified, imported static-trie library (pulled transitively via `langcodes`/`language_data`, and thus by many OVOS repos that resolve language data): no source is modified or redistributed, so the BSD-2-Clause terms govern and it is compatible with Apache 2.0 distribution. |
| `paho-mqtt` | `EPL-2.0 OR BSD-3-Clause` | WeakCopyleft | Dual-licensed. The license grants an explicit `EPL-2.0 OR BSD-3-Clause` choice: we elect the permissive BSD-3-Clause. The checker flags the whole expression because of the EPL-2.0 option. We use `paho-mqtt` as an unmodified, imported MQTT client library (a direct dependency of the `*2mqtt` bridges and other OVOS/TigreGotico MQTT integrations): no source is modified or redistributed, so the BSD-3-Clause terms govern and it is compatible with Apache 2.0 distribution. |

## Regex form

The workflow builds the central exclude pattern from these entries as a single
PCRE, anchored per package so it matches the exact distribution name (and is
case-insensitive, since the checker may normalise names):

```
(?i:^tqdm$)|(?i:^marisa[-_]trie$)|(?i:^paho[-_]mqtt$)
```

Adding a package means adding a `^name$` alternation here and in the workflow's
inline list, plus a row above with its justification.

---
[← Workflow Reference](workflow-reference.md) · [Home](index.md) · [Repo Setup →](repo-setup.md)
