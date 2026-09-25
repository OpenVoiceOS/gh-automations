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
| `setuptools` | MIT (bundled `LICENSE` file only in 79.x) | Error | Permissive. The 79.x wheels declare no `License` field, no `License-Expression` and no license classifier, so the checker cannot find a license and reports `Error`. The bundled `LICENSE` file is the MIT text. 80.0 and later declare `License-Expression: MIT`, which the PEP 639 rule below reads. It is a build tool that almost every package pulls in. |
| `torchao` | BSD-3-Clause (bundled `LICENSE` only) | Other | Permissive. 0.18.0 declares no `License` field, no `License-Expression` and no license classifier, only `License-File: LICENSE`, so the checker cannot find a licence and reports `Other`. The `LICENSE` in the source repository `pytorch/ao` is the BSD-3-Clause text, © 2023 Meta, including the "neither the name of the copyright holder" clause that separates BSD-3-Clause from BSD-2-Clause; the project README carries a BSD-3-Clause badge. Same shape as `setuptools` 79.x above. Pulled transitively by the ML stack, and seen on `ovos-stt-plugin-nemo#39`. Added by Miro's ruling on decision `torchao-no-metadata-read-licence`. |

## Packages with a permissive PEP 639 expression

The workflow also excludes, with no entry in this table, a package that declares
its license only as a PEP 639 `License-Expression` when **every** SPDX identifier
in that expression is permissive. The checker does not parse the expression and
reports `Error` for these packages (for example `build`, `packaging`, `wheel`,
`urllib3`, `zipp` and `setuptools` 80 and later). The test
`test/test_license_check_pep639.py` runs the step against wheel METADATA samples. The permissive identifiers are: `0BSD`, `Apache-2.0`,
`BSD-1-Clause`, `BSD-2-Clause`, `BSD-3-Clause`, `BSD-3-Clause-Clear`, `CC0-1.0`,
`HPND`, `ISC`, `MIT`, `MIT-0`, `MIT-CMU`, `PSF-2.0`, `Python-2.0`, `Unlicense`
and `Zlib`. An expression that contains any other identifier stays with the
checker. The workflow does not choose between the options of a dual licence.

## Regex form

The workflow builds the central exclude pattern from these entries as a single
PCRE, anchored per package so it matches the exact distribution name (and is
case-insensitive, since the checker may normalise names):

```
(?i:^bidict([=<>!~ @;].*)?$)|(?i:^tqdm([=<>!~ @;].*)?$)
|(?i:^marisa[-_]trie([=<>!~ @;].*)?$)|(?i:^paho[-_]mqtt([=<>!~ @;].*)?$)
|(?i:^fsspec([=<>!~ @;].*)?$)|(?i:^skops([=<>!~ @;].*)?$)
|(?i:^orjson([=<>!~ @;].*)?$)|(?i:^timezonefinder[-_]data([=<>!~ @;].*)?$)
|(?i:^setuptools([=<>!~ @;].*)?$)|(?i:^torchao([=<>!~ @;].*)?$)
```

Shown across lines to fit; the workflow builds it as one pattern with no line
breaks. The `([=<>!~ @;].*)?` suffix is load-bearing: the checker matches the
resolved `name==version` requirement, so a bare `^name$` never fires.

Adding a package means adding a `^name$` alternation here and in the workflow's
inline list, plus a row above with its justification.

---
[← Workflow Reference](workflow-reference.md) · [Home](index.md) · [Repo Setup →](repo-setup.md)
