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

Exit code is always 0. A report that cannot be read is itself a finding:
the section says so and one warning annotation is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    """[(name, version, vuln dict)] for every vulnerability in the report."""
    out = []
    for dep in deps:
        for vuln in dep.get("vulns") or []:
            if isinstance(vuln, dict):
                out.append((dep.get("name", "?"), dep.get("version", "?"), vuln))
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
        findings = findings_of(deps)
        total = args.total_packages or len(deps)
        if findings:
            body = render_table(findings, total)
            warnings = [annotation(n, v, x) for n, v, x in findings]
        else:
            body = f"✅ No known vulnerabilities found ({total} packages scanned)."
            warnings = []

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
