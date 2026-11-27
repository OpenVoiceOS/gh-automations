# gh-automations

<!-- agent-hint: reusable GitHub Actions workflows for OpenVoiceOS repos. Start at docs/index.md, section "For agents". Inputs and defaults: docs/workflow-reference.md. verify: pytest test/ -->

`gh-automations` holds the reusable GitHub Actions workflows and the helper scripts that OpenVoiceOS repos call for CI and releases. A repo calls a workflow here and does not keep its own copy of the CI logic.

## Call a workflow

A caller repo adds a small workflow file that names the reusable workflow at the `dev` ref:

```yaml
# .github/workflows/build_tests.yml in the caller repo
name: Build Tests
on:
  pull_request:
    branches: [dev]
jobs:
  build_tests:
    uses: OpenVoiceOS/gh-automations/.github/workflows/build-tests.yml@dev
    secrets: inherit
```

Each reusable workflow checks out this repo at run time to get the scripts in `scripts/`. The `gh_automations_ref` input sets that ref; the default is `dev`.

## Documentation

| Page | Contents |
|---|---|
| [docs/index.md](docs/index.md) | Overview, workflow catalog, callers per workflow, hints for agents |
| [docs/repo-setup.md](docs/repo-setup.md) | The workflow files for a new repo |
| [docs/release-flow.md](docs/release-flow.md) | Alpha and stable release lifecycle |
| [docs/workflow-reference.md](docs/workflow-reference.md) | Inputs, defaults and jobs of each workflow |
| [docs/license-whitelist.md](docs/license-whitelist.md) | Packages that the license check accepts |
| [docs/repos.md](docs/repos.md) | Repos that call these workflows |
| [docs/maintenance.md](docs/maintenance.md) | Maintainer procedures and open technical debt |

## Credits

Developed by [TigreGótico](https://tigregotico.pt) for [OpenVoiceOS](https://openvoiceos.org).

[![NGI0 Commons Fund](./ngi.png)](https://nlnet.nl/project/OpenVoiceOS)

This project was funded through the [NGI0 Commons Fund](https://nlnet.nl/commonsfund), a fund established by [NLnet](https://nlnet.nl) with financial support from the European Commission's [Next Generation Internet](https://ngi.eu) programme, under the aegis of [DG Communications Networks, Content and Technology](https://commission.europa.eu/about-european-commission/departments-and-executive-agencies/communications-networks-content-and-technology_en) under grant agreement No [101135429](https://cordis.europa.eu/project/id/101135429).

## License

Apache-2.0, see [LICENSE](./LICENSE).
