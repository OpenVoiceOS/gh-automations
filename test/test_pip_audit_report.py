"""scripts/pip_audit_report.py and the pip-audit workflow around it: the job
warns and never fails (Miro, 2026-09-18). A finding is one ::warning per
vulnerability, a job summary table and a PR comment section; a clean run
writes none; an unreadable report is itself a warning. The workflow has no
step that exits non-zero on a finding."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pip_audit_report import main  # noqa: E402

yaml = pytest.importorskip("yaml")

VULN_REPORT = {
    "dependencies": [
        {"name": "certifi", "version": "2026.7.22", "vulns": []},
        {"name": "urllib3", "version": "1.26.5", "vulns": [
            {"id": "PYSEC-2026-1995", "description": "Proxy-Authorization leak.",
             "fix_versions": ["1.26.19", "2.2.2"], "aliases": ["CVE-2024-37891", "GHSA-34jh-p97f-mpxf"]},
            {"id": "PYSEC-2026-1999", "description": "Redirect handling | with a pipe.\nand a newline.",
             "fix_versions": [], "aliases": []},
        ]},
        {"name": "requests", "version": "2.20.0", "vulns": [
            {"id": "PYSEC-2026-1995", "description": "Proxy-Authorization leak.",
             "fix_versions": ["2.34.2"], "aliases": ["CVE-2024-37891"]},
        ]},
    ]
}


def run(tmp_path, report, capsys, **extra):
    inp = tmp_path / "results.json"
    if report is not None:
        inp.write_text(report if isinstance(report, str) else json.dumps(report))
    section = tmp_path / "section.md"
    summary = tmp_path / "summary.md"
    summary.write_text("earlier content\n")
    argv = ["--input", str(inp), "--section", str(section), "--summary", str(summary), "--annotations"]
    for k, v in extra.items():
        argv += [f"--{k.replace('_', '-')}", str(v)]
    rc = main(argv)
    out = capsys.readouterr().out
    return rc, out, section.read_text(), summary.read_text()


def test_findings_give_one_warning_each_and_the_table(tmp_path, capsys):
    rc, out, section, summary = run(tmp_path, VULN_REPORT, capsys)
    assert rc == 0
    warnings = [l for l in out.splitlines() if l.startswith("::warning ")]
    assert len(warnings) == 3
    assert warnings[0] == ("::warning title=pip-audit urllib3 1.26.5 PYSEC-2026-1995::"
                           "Proxy-Authorization leak. (fix: 1.26.19, 2.2.2)")
    assert "(fix: no fix available)" in warnings[1]
    assert "\n" not in warnings[1]
    assert "**3 known vulnerabilities** in 2 packages (3 packages scanned)" in section
    assert "This job warns and does not fail" in section
    assert "| `urllib3` | `1.26.5` | [PYSEC-2026-1995](https://osv.dev/vulnerability/PYSEC-2026-1995) / CVE-2024-37891 | Proxy-Authorization leak. | 1.26.19, 2.2.2 |" in section
    assert "Redirect handling \\| with a pipe. and a newline." in section
    assert summary.startswith("earlier content\n## 🔒 Security (pip-audit)\n\n")
    assert section in summary


def test_clean_report_writes_no_warning(tmp_path, capsys):
    rc, out, section, summary = run(tmp_path, {"dependencies": [{"name": "a", "version": "1", "vulns": []}]}, capsys)
    assert rc == 0
    assert "::warning" not in out
    assert section == "✅ No known vulnerabilities found (1 packages scanned)."
    assert section in summary


def test_list_shape_and_total_packages_override(tmp_path, capsys):
    rc, out, section, _ = run(tmp_path, VULN_REPORT["dependencies"], capsys, total_packages=40)
    assert rc == 0
    assert "(40 packages scanned)" in section


@pytest.mark.parametrize("report", [None, "{not json", '{"other": 1}', "[1, 2]"])
def test_unreadable_report_is_one_warning_not_a_failure(tmp_path, capsys, report):
    rc, out, section, summary = run(tmp_path, report, capsys, outcome="failure")
    assert rc == 0
    assert out.count("::warning") == 1
    assert "wrote no readable report (audit step outcome: failure)" in section
    assert section in summary


def test_duplicate_records_give_one_warning_per_id(tmp_path, capsys):
    """pip-audit reports one record per vulnerability service: jinja2 3.1.2
    comes back with 10 records over 5 ids. GitHub keeps 10 annotations per
    step, so a duplicate would push a real finding off the list."""
    v = {"id": "GHSA-1", "description": "d", "fix_versions": ["2"]}
    rep = {"dependencies": [
        {"name": "jinja2", "version": "3.1.2", "vulns": [v, dict(v), {"id": "GHSA-2", "description": "e"}]},
        {"name": "jinja2", "version": "3.1.3", "vulns": [v]},  # another version is another finding
    ]}
    _, out, section, _ = run(tmp_path, rep, capsys)
    assert out.count("::warning") == 3
    assert "**3 known vulnerabilities** in 1 package" in section
    assert section.count("GHSA-1") == 4  # two rows, each with the id in the link text and the url


def test_a_single_vulnerability_reads_singular(tmp_path, capsys):
    rep = {"dependencies": [{"name": "x", "version": "1", "vulns": [{"id": "V-1", "description": "d"}]}]}
    _, _, section, _ = run(tmp_path, rep, capsys)
    assert "**1 known vulnerability** in 1 package" in section


class TestWorkflowNeverFails:
    """pip-audit.yml has no step that turns a finding into a red job."""

    @pytest.fixture
    def wf(self):
        return yaml.safe_load((ROOT / ".github/workflows/pip-audit.yml").read_text())

    def steps(self, wf):
        return wf["jobs"]["pip_audit"]["steps"]

    def test_no_step_exits_nonzero_on_the_audit_outcome(self, wf):
        for s in self.steps(wf):
            if "pip_audit_check.outcome" in str(s.get("if", "")):
                assert "exit 1" not in s.get("run", ""), s["name"]
        assert not [s for s in self.steps(wf) if s.get("name", "").startswith("Fail job")]

    def test_audit_and_sarif_steps_never_fail_the_job(self, wf):
        by_id = {s.get("id"): s for s in self.steps(wf)}
        assert by_id["pip_audit_check"]["continue-on-error"] is True
        assert by_id["sarif_report"]["continue-on-error"] is True

    def test_report_step_runs_whenever_the_audit_ran(self, wf):
        step = next(s for s in self.steps(wf) if s.get("name") == "Report findings")
        assert "always()" in step["if"] and "pip_audit_check.outcome != 'skipped'" in step["if"]
        assert "--annotations" in step["run"] and '--summary "$GITHUB_STEP_SUMMARY"' in step["run"]

    def test_scripts_checkout_is_unconditional(self, wf):
        step = next(s for s in self.steps(wf) if s.get("name") == "Checkout gh-automations scripts")
        assert "if" not in step

    def test_warn_only_is_kept_and_documented_as_moot(self, wf):
        inp = wf[True]["workflow_call"]["inputs"]["warn_only"]  # yaml reads the `on` key as True
        assert inp["default"] is True
        assert "never fails" in inp["description"]

    @pytest.mark.parametrize("category, section_id, title", [
        ("pip-audit", "security", "🔒 Security (pip-audit)"),
        ("pip-audit-all", "security-pip-audit-all", "🔒 Security (pip-audit: pip-audit-all)"),
        ("extras/gui x", "security-extras-gui-x", "🔒 Security (pip-audit: extras/gui x)"),
    ])
    def test_comment_section_is_keyed_on_sarif_category(self, wf, tmp_path, category, section_id, title):
        """Two calls on one pull request must not share a section, or the
        clean call overwrites the vulnerable call's table (hello-world#143,
        comment 5723386358)."""
        import os
        import subprocess
        step = next(s for s in self.steps(wf) if s.get("name") == "Post security section to PR comment")
        script = step["run"]
        for k, v in (("github.repository", "o/r"), ("github.event.pull_request.number", "7")):
            script = script.replace("${{ %s }}" % k, v)
        assert "${{" not in script
        fake = tmp_path / "_gh_automations" / "scripts"
        fake.mkdir(parents=True)
        (fake / "update_pr_comment.py").write_text("import sys; print(' '.join(sys.argv[1:]))")
        r = subprocess.run(["bash", "-e", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                           env=dict(os.environ, CATEGORY=category))
        assert r.returncode == 0, r.stderr
        assert f"--section-id {section_id} --title {title} " in r.stdout

    def test_self_check_has_no_job_that_must_fail(self):
        sc = yaml.safe_load((ROOT / ".github/workflows/self-check-pip-audit.yml").read_text())
        assert set(sc["jobs"]) == {"clean_environment_passes", "vulnerable_environment_warns"}
        for job in sc["jobs"].values():
            assert "if" not in job
