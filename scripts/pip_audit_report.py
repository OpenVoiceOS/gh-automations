#!/usr/bin/env python3
"""Turn a pip-audit JSON report into the three places a person reads it.

The pip-audit job warns and never fails (Miro, 2026-09-18, on
gh-automations#126). So every finding must be visible without a red check:

- one ``::warning`` annotation per vulnerability, on the job and on the
  pull request's Checks tab;
- a Markdown table in the job summary;
- the same table in the shared PR comment section.

Usage:
    pip_audit_report.py --input /tmp/pip-audit-results.json \
        --section /tmp/security-section.md [--summary "$GITHUB_STEP_SUMMARY"] \
        [--annotations] [--outcome success|failure] [--total-packages N]

Exit code is always 0. A report that cannot be read is itself a finding, and
so is a package that pip-audit left unaudited: the section says so and one
warning annotation is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pip_audit_sarif import skipped_packages


def load_dependencies(path: Path):
    """The dependency list of a pip-audit JSON report, or None when the file
    is absent, truncated, or not a pip-audit report. Both shapes pip-audit
    has written are accepted: a list, or {"dependencies": [...]}."""
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if isinstance(data, list):
        deps = data
    elif isinstance(data, dict) and isinstance(data.get("dependencies"), list):
        deps = data["dependencies"]
    else:
        return None
    if not all(isinstance(d, dict) for d in deps):
        return None
    return deps


def one_line(text: str, limit: int = 120) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def findings_of(deps):
    """[(name, version, vuln dict)] for every vulnerability in the report,
    one per (package, version, id). pip-audit queries more than one
    vulnerability service and reports the same id once per service (jinja2
    3.1.2 comes back with 10 records over 5 ids), the same dedupe as
    pip_audit_sarif.build_sarif. GitHub keeps at most 10 annotations per
    step, so a duplicate would push a real finding off the list."""
    out = []
    seen = set()
    for dep in deps:
        name, version = dep.get("name", "?"), dep.get("version", "?")
        for vuln in dep.get("vulns") or []:
            if not isinstance(vuln, dict):
                continue
            fingerprint = (name, version, vuln.get("id", "?"))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            out.append((name, version, vuln))
    return out


def render_table(findings, total_packages: int) -> str:
    pkg_note = f" ({total_packages} packages scanned)" if total_packages > 0 else ""
    packages = {name for name, _, _ in findings}
    lines = [
        f"⚠️ **{len(findings)} known vulnerabilit{'y' if len(findings) == 1 else 'ies'}** "
        f"in {len(packages)} package{'s' if len(packages) != 1 else ''}{pkg_note}. "
        "This job warns and does not fail; update the affected packages.",
        "",
        "| Package | Version | ID | Description | Fix |",
        "|---------|---------|-----|-------------|-----|",
    ]
    for name, version, vuln in findings:
        vid = vuln.get("id", "?")
        cve = next((a for a in vuln.get("aliases") or [] if str(a).startswith("CVE-")), "")
        id_cell = f"[{vid}](https://osv.dev/vulnerability/{vid})" + (f" / {cve}" if cve else "")
        desc = one_line(vuln.get("description", "")).replace("|", "\\|")
        fixes = ", ".join(vuln.get("fix_versions") or []) or "no fix available"
        lines.append(f"| `{name}` | `{version}` | {id_cell} | {desc} | {fixes} |")
    return "\n".join(lines)


def render_gaps(gaps) -> str:
    """The packages pip-audit left out, named with the reason it gave.

    A reader who sees no vulnerability must also see what was not audited.
    pip-audit says nothing outside its report about a package it skipped."""
    plural = len(gaps) != 1
    lines = [
        f"⚠️ **{len(gaps)} package{'s' if plural else ''} "
        f"{'were' if plural else 'was'} not audited.** "
        f"pip-audit could not resolve a version, so this report says nothing "
        f"about {'them' if plural else 'it'}. The job uploads no SARIF for an "
        "incomplete audit, and the Security tab keeps its last complete analysis.",
        "",
        "| Package | Not audited because |",
        "|---------|---------------------|",
    ]
    for name, reason in gaps:
        reason_cell = one_line(reason).replace("|", "\\|")
        lines.append(f"| `{name}` | {reason_cell} |")
    return "\n".join(lines)


def gap_annotation(name, reason) -> str:
    return f"::warning title=pip-audit skipped {name}::{one_line(reason, 200)}"


def annotation(name, version, vuln) -> str:
    vid = vuln.get("id", "?")
    fixes = ", ".join(vuln.get("fix_versions") or []) or "no fix available"
    desc = one_line(vuln.get("description", ""), 200)
    # a newline or a colon-colon would end the annotation early
    desc = desc.replace("::", ": :")
    return f"::warning title=pip-audit {name} {version} {vid}::{desc} (fix: {fixes})"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--section", required=True, type=Path, help="Markdown file for the PR comment section")
    ap.add_argument("--summary", type=Path, default=None, help="job summary file to append the table to")
    ap.add_argument("--annotations", action="store_true", help="print one ::warning per vulnerability")
    ap.add_argument("--outcome", default="", help="outcome of the audit step, for the unreadable-report case")
    ap.add_argument("--total-packages", type=int, default=0)
    args = ap.parse_args(argv)

    deps = load_dependencies(args.input)
    if deps is None:
        body = ("⚠️ pip-audit wrote no readable report" +
                (f" (audit step outcome: {args.outcome})" if args.outcome else "") +
                ". The job warns and does not fail; read the job log.")
        warnings = ["::warning title=pip-audit::the audit wrote no readable report; read the job log"]
    else:
        gaps = skipped_packages(deps)
        findings = findings_of([d for d in deps if not d.get("skip_reason")])
        scanned = (args.total_packages or len(deps)) - len(gaps)
        # The gap warning explains why the SARIF upload was withheld; it must
        # come before the finding warnings, or a long finding list pushes it
        # off GitHub's 10-annotation render limit (findings_of's own comment).
        warnings = [gap_annotation(n, r) for n, r in gaps]
        warnings += [annotation(n, v, x) for n, v, x in findings]
        if not findings and args.outcome not in ("", "success"):
            # A readable, clean report and a failed audit step contradict
            # each other: the report does not describe the run that wrote
            # it. pip_audit_sarif.py already refuses this input.
            body = ("⚠️ the audit step failed and the report lists no vulnerability"
                     f" (audit step outcome: {args.outcome})"
                     ". The job warns and does not fail; read the job log.")
            if not gaps:
                warnings.append(
                    "::warning title=pip-audit::the audit step failed and the "
                    "report lists no vulnerability; read the job log"
                )
        elif findings:
            body = render_table(findings, scanned)
        elif not gaps:
            body = f"✅ No known vulnerabilities found ({scanned} packages scanned)."
        else:
            body = (f"pip-audit audited {scanned} "
                    f"package{'s' if scanned != 1 else ''} and found no vulnerability.")
        if gaps:
            body += "\n\n" + render_gaps(gaps)

    args.section.write_text(body)
    if args.summary is not None:
        with open(args.summary, "a") as fh:
            fh.write("## 🔒 Security (pip-audit)\n\n" + body + "\n\n")
    if args.annotations:
        for line in warnings:
            print(line)
    print(f"pip-audit report: {len(warnings)} warning(s), section written to {args.section}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
