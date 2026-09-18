#!/usr/bin/env python3
"""Convert a pip-audit JSON report into a SARIF 2.1.0 report.

pip-audit has no `sarif` output format (it emits columns, json,
cyclonedx-json, cyclonedx-xml and markdown). A `--format=sarif` call exits 2
with a usage error, so the workflow that asked for one always uploaded an
empty report and the Security tab stayed empty. This script builds the SARIF
from the JSON report that the audit step already writes.

Usage:
    pip_audit_sarif.py --input <pip-audit.json> --output <report.sarif>
"""
import argparse
import json
import pathlib
import sys

MANIFESTS = ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg")


class ReportError(Exception):
    """The pip-audit report is absent, unreadable, or not a pip-audit report.

    This is not the same as a report that lists no vulnerability. An audit
    that did not run must never write a report that says the code is clean:
    code scanning keeps one analysis per (ref, category), so a clean report
    closes every alert the last good run raised.
    """


def find_manifest(root: pathlib.Path) -> str:
    """Return the dependency file to attach the alerts to.

    Code scanning shows an alert only if the result has a location. A
    dependency vulnerability has no source line, so each alert points at the
    dependency file of the repository.
    """
    for name in MANIFESTS:
        if (root / name).is_file():
            return name
    return MANIFESTS[0]


def load_dependencies(path: pathlib.Path) -> list:
    """Read the pip-audit report, or raise ReportError.

    The shape changed between versions: older releases write a list, newer
    releases write {"dependencies": [...]}. Any other shape, an unreadable
    file, or truncated JSON means the audit did not complete. Raise, so that
    the caller writes no report at all.
    """
    try:
        with path.open() as handle:
            data = json.load(handle)
    except OSError as err:
        raise ReportError(f"cannot read {path}: {err}") from err
    except json.JSONDecodeError as err:
        raise ReportError(f"{path} is not valid JSON: {err}") from err
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "dependencies" in data:
        return data["dependencies"]
    raise ReportError(
        f"{path} is not a pip-audit report: expected a list or an object "
        f"with a 'dependencies' key, found {type(data).__name__}"
    )


def build_sarif(dependencies: list, manifest: str) -> dict:
    rules: dict = {}
    results: list = []
    seen: set = set()
    for dep in dependencies:
        name = dep.get("name", "unknown")
        version = dep.get("version", "unknown")
        for vuln in dep.get("vulns", []):
            vuln_id = vuln.get("id", "UNKNOWN")
            # pip-audit queries more than one vulnerability service and
            # reports the same id once per service: jinja2 3.1.2 comes back
            # with 10 records over 5 ids. One alert per vulnerability needs
            # one result per (package, version, id).
            fingerprint = f"{name}:{version}:{vuln_id}"
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            description = vuln.get("description") or vuln_id
            fixes = ", ".join(vuln.get("fix_versions", [])) or "no fix available"
            aliases = [a for a in vuln.get("aliases", []) if a.startswith("CVE-")]
            if vuln_id not in rules:
                rules[vuln_id] = {
                    "id": vuln_id,
                    "name": vuln_id,
                    "shortDescription": {"text": f"{vuln_id} in {name}"},
                    "fullDescription": {"text": description[:1000]},
                    "helpUri": f"https://osv.dev/vulnerability/{vuln_id}",
                    "help": {"text": description[:1000]},
                    "properties": {"tags": ["security", "dependency"]},
                }
            title = f"{name} {version} is affected by {vuln_id}"
            if aliases:
                title += f" ({', '.join(aliases)})"
            results.append(
                {
                    "ruleId": vuln_id,
                    "level": "error",
                    "message": {"text": f"{title}. Fix: {fixes}."},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": manifest},
                                "region": {"startLine": 1},
                            }
                        }
                    ],
                    "partialFingerprints": {"pipAuditVuln": fingerprint},
                }
            )
    return {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "pip-audit",
                        "informationUri": "https://github.com/pypa/pip-audit",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="pip-audit JSON report")
    parser.add_argument("--output", required=True, help="SARIF file to write")
    parser.add_argument(
        "--root", default=".", help="Repository root, to find the dependency file"
    )
    args = parser.parse_args()

    try:
        dependencies = load_dependencies(pathlib.Path(args.input))
    except ReportError as err:
        # Write nothing. An empty report reads as "no vulnerability found".
        sys.stderr.write(f"pip-audit report unusable, no SARIF written: {err}\n")
        raise SystemExit(2)
    manifest = find_manifest(pathlib.Path(args.root))
    sarif = build_sarif(dependencies, manifest)
    with open(args.output, "w") as handle:
        json.dump(sarif, handle, indent=2)

    run = sarif["runs"][0]
    print(
        f"SARIF written to {args.output}: {len(run['results'])} result(s), "
        f"{len(run['tool']['driver']['rules'])} rule(s), location {manifest}"
    )


if __name__ == "__main__":
    main()
