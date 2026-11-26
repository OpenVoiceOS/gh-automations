"""Unit tests for scripts/format_ovoscope_results.py.

The shapes here are taken from a real pytest run of a unittest suite that uses
``self.subTest``, with ``pytest-subtests``, ``pytest-xdist`` (-n 2) and
``pytest-json-report`` installed, which is what the ovoscope workflow runs.

Runs without any external dependencies beyond the Python standard library.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from format_ovoscope_results import (  # noqa: E402
    main,
    parse_subfailures,
    render,
)

# The worker banner is the whole longrepr a collided subtest report keeps.
BANNER = "[gw0] linux -- Python 3.11.16 /opt/hostedtoolcache/Python/3.11.16/x64/bin/python"


def _report(tests, summary, exitcode=0):
    return {"exitcode": exitcode, "summary": summary, "tests": tests}


def _test_entry(nodeid, outcome, longrepr=""):
    return {
        "nodeid": nodeid,
        "outcome": outcome,
        "setup": {"outcome": "passed"},
        "call": {"outcome": "passed", "longrepr": longrepr},
        "teardown": {"outcome": "passed"},
    }


GREEN = _report(
    [
        _test_entry("test/end2end/test_a.py::TestA::test_subs",
                    "subtests passed", BANNER),
        _test_entry("test/end2end/test_a.py::TestA::test_plain", "passed", BANNER),
    ],
    {"subtests passed": 1, "passed": 1, "total": 2, "collected": 2},
    exitcode=0,
)


class TestSubtestsPassedIsAPass:
    def test_all_green_reads_green(self):
        md = render(GREEN, [], outcome="success")
        assert md.startswith("✅ **2/2** passed")
        assert "❌" not in md

    def test_class_line_counts_the_subtest_test(self):
        md = render(GREEN, [], outcome="success")
        assert "✅ **TestA** — 2/2" in md

    def test_no_details_block_when_green(self):
        md = render(GREEN, [], outcome="success")
        assert "<details>" not in md

    def test_worker_banner_is_never_a_failure_body(self):
        md = render(GREEN, [], outcome="success")
        assert "gw0" not in md


class TestRealFailuresStillRead:
    def test_a_failed_test_is_red(self):
        data = _report(
            [_test_entry("test/end2end/test_a.py::TestA::test_x", "failed",
                         BANNER + "\nE   AssertionError: no match")],
            {"failed": 1, "total": 1, "collected": 1},
            exitcode=1,
        )
        md = render(data, [], outcome="failure")
        assert md.startswith("❌ **0/1** passed, **1** failed")
        assert "AssertionError: no match" in md
        # the banner line is stripped, the assertion text is kept
        assert "gw0" not in md

    def test_a_failing_subtest_is_named_and_counted(self):
        data = _report(
            [_test_entry("test/end2end/test_a.py::TestA::test_subs",
                         "subtests passed", BANNER)],
            {"subtests passed": 1, "total": 1, "collected": 1},
            exitcode=1,
        )
        subs = [{
            "nodeid": "test/end2end/test_a.py::TestA::test_subs",
            "sub": "(utt='hello')",
            "msg": "AssertionError: ovos.intent.unmatched",
            "kind": "failed",
        }]
        md = render(data, subs, outcome="failure")
        assert md.startswith("❌ **0/1** passed, **1** subtest failed")
        assert "❌ **TestA** — 0/1, 1 subtest failed" in md
        assert "test_subs(utt='hello')" in md
        assert "AssertionError: ovos.intent.unmatched" in md

    def test_exit_code_alone_still_reports_red(self):
        data = _report(
            [_test_entry("test/end2end/test_a.py::TestA::test_subs",
                         "subtests passed", BANNER)],
            {"subtests passed": 1, "total": 1, "collected": 1},
            exitcode=1,
        )
        md = render(data, [], outcome="failure")
        assert md.startswith("❌")
        assert "names no failing test" in md

    def test_skipped_is_not_a_failure(self):
        data = _report(
            [_test_entry("test/end2end/test_a.py::TestA::test_s", "skipped")],
            {"skipped": 1, "total": 1, "collected": 1},
            exitcode=0,
        )
        md = render(data, [], outcome="success")
        assert "1 skipped" in md


class TestParseSubfailures:
    def test_reads_the_short_summary_lines(self, tmp_path):
        log = tmp_path / "pytest.log"
        log.write_text(
            "=========== short test summary info ===========\n"
            "SUBFAILED(i='1') test/end2end/test_b.py::TestB::test_y"
            " - AssertionError: 1 == 1\n"
            "SUBERROR(i='2') test/end2end/test_b.py::TestB::test_y - KeyError: 'lang'\n"
            "1 failed, 3 passed, 7 subtests passed in 0.51s\n"
        )
        subs = parse_subfailures(str(log))
        assert len(subs) == 2
        assert subs[0]["nodeid"] == "test/end2end/test_b.py::TestB::test_y"
        assert subs[0]["sub"] == "(i='1')"
        assert subs[0]["msg"] == "AssertionError: 1 == 1"
        assert subs[0]["kind"] == "failed"
        assert subs[1]["kind"] == "error"

    def test_reads_a_labelled_subtest_line(self, tmp_path):
        log = tmp_path / "pytest.log"
        log.write_text(
            "SUBFAILED[case] (i=1) gen/test_g.py::test_lab - AssertionError: boom\n"
        )
        subs = parse_subfailures(str(log))
        assert subs == [{
            "nodeid": "gen/test_g.py::test_lab",
            "sub": "[case] (i=1)",
            "msg": "AssertionError: boom",
            "kind": "failed",
        }]

    def test_reads_a_label_without_parameters(self, tmp_path):
        log = tmp_path / "pytest.log"
        log.write_text(
            "SUBFAILED[solo] gen/test_g.py::test_msgonly - AssertionError: boom\n"
        )
        subs = parse_subfailures(str(log))
        assert len(subs) == 1
        assert subs[0]["nodeid"] == "gen/test_g.py::test_msgonly"
        assert subs[0]["sub"] == "[solo]"

    def test_reads_an_unlabelled_subtest_line(self, tmp_path):
        log = tmp_path / "pytest.log"
        log.write_text(
            "SUBFAILED(i=1) gen/test_g.py::test_nolab - AssertionError: boom\n"
        )
        subs = parse_subfailures(str(log))
        assert subs == [{
            "nodeid": "gen/test_g.py::test_nolab",
            "sub": "(i=1)",
            "msg": "AssertionError: boom",
            "kind": "failed",
        }]

    def test_a_repeated_line_counts_once(self, tmp_path):
        log = tmp_path / "pytest.log"
        line = "SUBFAILED(i='1') test/t.py::T::test_y - boom\n"
        log.write_text(line * 3)
        assert len(parse_subfailures(str(log))) == 1

    def test_a_plain_failed_line_is_not_a_subfailure(self, tmp_path):
        log = tmp_path / "pytest.log"
        log.write_text("FAILED test/t.py::T::test_y - boom\n")
        assert parse_subfailures(str(log)) == []

    def test_no_log_is_not_an_error(self):
        assert parse_subfailures(None) == []
        assert parse_subfailures("/nonexistent/pytest.log") == []


class TestMain:
    def test_missing_json_writes_a_placeholder(self, tmp_path):
        out = tmp_path / "section.md"
        rc = main(["--json", str(tmp_path / "nope.json"), "--out", str(out)])
        assert rc == 0
        assert "Test results unavailable" in out.read_text()

    def test_end_to_end_green(self, tmp_path):
        js = tmp_path / "results.json"
        js.write_text(json.dumps(GREEN))
        out = tmp_path / "section.md"
        rc = main(["--json", str(js), "--out", str(out), "--outcome", "success"])
        assert rc == 0
        assert out.read_text().startswith("✅ **2/2** passed")
