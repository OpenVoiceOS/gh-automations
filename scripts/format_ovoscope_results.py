#!/usr/bin/env python3
"""Format an ovoscope pytest json-report into the OVOS PR Checks section.

pytest-subtests gives a test that runs ``self.subTest`` the outcome
``"subtests passed"``, not ``"passed"`` (T-6656). pytest-json-report keys its
test list on the nodeid, so the subtest reports and the test report collide:
the last one wins, the per-subtest failure reports are dropped, and the
``longrepr`` kept under pytest-xdist is the worker banner alone
(``[gw0] linux -- Python 3.11.16 ...``). A reader that counts only ``passed``
therefore reports every subtest-using test as a failure with no assertion
text, and a real subtest failure reads the same as a pass.

This script reads ``"subtests passed"`` as a pass, takes the red/green verdict
from the run exit code instead of the test list, and names the failing
subtests from the ``SUBFAILED`` lines of the captured pytest log, which is the
only place they survive.

It never raises on missing/garbled input — a placeholder section is written so
the PR comment step always has something to post.

Usage:
    format_ovoscope_results.py --json /tmp/ovoscope-results.json \
        --out /tmp/ovoscope-section.md [--log /tmp/ovoscope-pytest.log] \
        [--outcome success]
"""

import argparse
import json
import re
import sys
from typing import Dict, List, Optional, Tuple

# pytest-subtests reports a test whose subtests all passed with this outcome.
SUBTESTS_PASSED = "subtests passed"
PASS_OUTCOMES = ("passed", SUBTESTS_PASSED)

# "SUBFAILED(i='1') test/end2end/test_x.py::TestX::test_y - AssertionError: ..."
SUBFAILED_RE = re.compile(
    r"^SUB(?P<kind>FAILED|ERROR)(?P<sub>\(.*?\))?\s+(?P<nodeid>\S+)(?:\s+-\s+(?P<msg>.*))?$"
)
# The pytest-xdist worker banner, the only longrepr a collided report keeps.
WORKER_BANNER_RE = re.compile(r"^\[gw\d+\]\s")


def _is_pass(outcome: str) -> bool:
    return outcome in PASS_OUTCOMES


def _clean_longrepr(text: str) -> str:
    """Drop a longrepr that is the xdist worker banner and nothing else."""
    if not text:
        return ""
    body = [ln for ln in text.splitlines() if not WORKER_BANNER_RE.match(ln)]
    return "\n".join(body).strip()


def parse_subfailures(log_path: Optional[str]) -> List[Dict[str, str]]:
    """Read the failing subtests from a captured pytest log.

    The short test summary names one ``SUBFAILED``/``SUBERROR`` line per failing
    subtest. The json-report keeps none of them.
    """
    if not log_path:
        return []
    try:
        with open(log_path, errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    out: List[Dict[str, str]] = []
    seen = set()
    for line in text.splitlines():
        m = SUBFAILED_RE.match(line.strip())
        if not m:
            continue
        key = (m.group("nodeid"), m.group("sub") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "nodeid": m.group("nodeid"),
            "sub": (m.group("sub") or "").strip(),
            "msg": (m.group("msg") or "").strip(),
            "kind": m.group("kind").lower(),
        })
    return out


def load(json_path: Optional[str]) -> Optional[dict]:
    if not json_path:
        return None
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _counts(summary: dict) -> Tuple[int, int, int, int, int]:
    total = summary.get("total", 0)
    passed = summary.get("passed", 0) + summary.get(SUBTESTS_PASSED, 0)
    failed = summary.get("failed", 0)
    errored = summary.get("error", 0)
    skipped = summary.get("skipped", 0)
    return total, passed, failed, errored, skipped


def render(data: Optional[dict], subfailures: List[Dict[str, str]],
           outcome: str = "") -> str:
    lines: List[str] = []

    if data is None:
        lines.append("⚠️ Test results unavailable — check the job log.")
        return "\n".join(lines)

    summary = data.get("summary", {}) or {}
    total, passed, failed, errored, skipped = _counts(summary)
    exitcode = data.get("exitcode", 0)
    # A test with a failing subtest still reports "subtests passed": take it
    # back out of the passed count.
    sub_nodes = {sf["nodeid"] for sf in subfailures}
    passed = max(0, passed - len(sub_nodes))

    # The test list cannot be trusted for the verdict: a dropped subtest
    # failure leaves no failed entry. The exit code always records it.
    red = bool(failed or errored or subfailures or exitcode
               or outcome == "failure")
    icon = "❌" if red else "✅"
    parts = [f"**{passed}/{total}** passed"]
    if failed:
        parts.append(f"**{failed}** failed")
    if errored:
        parts.append(f"**{errored}** error{'s' if errored != 1 else ''}")
    if subfailures:
        parts.append(f"**{len(subfailures)}** subtest"
                     f"{'s' if len(subfailures) != 1 else ''} failed")
    if skipped:
        parts.append(f"{skipped} skipped")
    lines.append(f"{icon} {', '.join(parts)}")

    if red and not (failed or errored or subfailures):
        lines.append("")
        lines.append(f"⚠️ The suite exited `{exitcode}` and the report names no "
                     "failing test — check the job log.")

    tests = data.get("tests", []) or []
    if tests:
        by_class: Dict[str, List[dict]] = {}
        for t in tests:
            node = t.get("nodeid", "")
            parts_node = node.split("::")
            cls = parts_node[1] if len(parts_node) >= 2 else "Other"
            by_class.setdefault(cls, []).append(t)

        # A failing subtest is dropped from its test entry, so mark the class
        # from the log as well.
        sub_by_node: Dict[str, List[Dict[str, str]]] = {}
        for sf in subfailures:
            sub_by_node.setdefault(sf["nodeid"], []).append(sf)

        lines.append("")
        for cls, cls_tests in sorted(by_class.items()):
            cls_passed = sum(1 for t in cls_tests
                             if _is_pass(t.get("outcome", ""))
                             and t.get("nodeid", "") not in sub_nodes)
            cls_total = len(cls_tests)
            cls_subs = [sf for t in cls_tests
                        for sf in sub_by_node.get(t.get("nodeid", ""), [])]
            failing = [t for t in cls_tests if not _is_pass(t.get("outcome", ""))]
            cls_ok = not failing and not cls_subs
            cls_icon = "✅" if cls_ok else "❌"
            summary_line = f"{cls_icon} **{cls}** — {cls_passed}/{cls_total}"
            if cls_subs:
                summary_line += (f", {len(cls_subs)} subtest"
                                 f"{'s' if len(cls_subs) != 1 else ''} failed")

            if cls_ok:
                lines.append(summary_line)
                continue

            lines.append(f"<details><summary>{summary_line}</summary>")
            lines.append("")
            lines.append("| Test | Result |")
            lines.append("|------|--------|")
            for t in cls_tests:
                name = t.get("nodeid", "?").split("::")[-1]
                t_outcome = t.get("outcome", "?")
                subs = sub_by_node.get(t.get("nodeid", ""), [])
                if subs:
                    t_icon = "❌"
                    t_outcome = (f"{len(subs)} subtest"
                                 f"{'s' if len(subs) != 1 else ''} failed")
                elif _is_pass(t_outcome):
                    t_icon = "✅"
                elif t_outcome == "skipped":
                    t_icon = "⚠️"
                else:
                    t_icon = "❌"
                lines.append(f"| `{name}` | {t_icon} {t_outcome} |")
            lines.append("")
            for sf in cls_subs[:5]:
                name = sf["nodeid"].split("::")[-1]
                msg = sf["msg"] or "see the job log"
                lines.append(f"**`{name}{sf['sub']}` {sf['kind']}:**")
                lines.append(f"```\n{msg}\n```")
            for t in failing[:3]:
                name = t.get("nodeid", "?").split("::")[-1]
                call = t.get("call", {})
                longrepr = call.get("longrepr", "") if isinstance(call, dict) else ""
                longrepr = _clean_longrepr(longrepr)
                if longrepr:
                    truncated = longrepr[-800:] if len(longrepr) > 800 else longrepr
                    lines.append(f"**`{name}` failure:**")
                    lines.append(f"```\n{truncated.strip()}\n```")
            lines.append("</details>")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", dest="json_path", default=None,
                    help="Path to the pytest --json-report file")
    ap.add_argument("--log", dest="log_path", default=None,
                    help="Captured pytest output, read for SUBFAILED lines")
    ap.add_argument("--out", required=True, help="Output markdown file")
    ap.add_argument("--outcome", default="",
                    help="Outcome of the pytest step (success | failure)")
    args = ap.parse_args(argv)

    data = load(args.json_path)
    subfailures = parse_subfailures(args.log_path)
    md = render(data, subfailures, args.outcome)
    with open(args.out, "w") as f:
        f.write(md)
    n_tests = len((data or {}).get("tests", []) or [])
    print(f"Wrote {args.out}: {n_tests} test(s) in, "
          f"{len(subfailures)} failing subtest(s) named")
    return 0


if __name__ == "__main__":
    sys.exit(main())
