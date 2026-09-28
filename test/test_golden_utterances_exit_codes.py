"""golden-utterances.yml's summary step and ovoscope golden's exit codes.

ovoscope#214 added exit 5: the run could not boot, which covers the preset
check before the run and the MiniCroft boot itself, with or without a preset
(ovoscope/golden_minicroft.py, EXIT_PRESET, and both PresetUnavailable
returns). Exit 5 is never exit 1, because exit 1 is a corpus miss and a boot
that failed measured no row at all.

The step is driven here with a stub ``ovoscope`` on PATH, one per exit code,
so what is asserted is the step's behaviour and not the text of the file: the
job stays red on 5, and the summary says the run could not boot and carries
the reason ovoscope printed.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/golden-utterances.yml"
STEP = "Run the golden corpus"


def step_script() -> str:
    """The step's run script, with the one matrix expression filled in.

    A workflow expression is the runner's substitution, not bash's, so it is
    replaced here rather than left for the shell to mangle.
    """
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["golden"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    script = script.replace("${{ matrix.python-version }}", "3.11")
    assert "${{" not in script, script
    return script


def write_stub(bin_dir: Path, code: int, log: str) -> None:
    """A stub ``ovoscope`` that prints *log* and exits *code*."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "ovoscope"
    stub.write_text("#!/usr/bin/env bash\ncat <<'LOG'\n" + log + "\nLOG\nexit "
                    + str(code) + "\n")
    stub.chmod(0o755)


def run_step(tmp_path: Path, code: int, log: str, pipeline: str = "repo") -> tuple[int, str, str]:
    """Run the step with the stub in place. Returns (rc, summary, output)."""
    work = tmp_path / "checkout"
    work.mkdir(exist_ok=True)
    bin_dir = tmp_path / "bin"
    write_stub(bin_dir, code, log)
    summary = tmp_path / "step_summary"
    summary.write_text("")
    out = tmp_path / "github_output"
    out.write_text("")
    env = dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        ROWS="test/end2end/golden_utterances*.jsonl",
        SKILL_ID="ovos-skill-parrot.openvoiceos",
        LOCALES="",
        PIPELINE=pipeline,
        UTT_TIMEOUT="20",
        GITHUB_STEP_SUMMARY=str(summary),
        GITHUB_OUTPUT=str(out),
    )
    r = subprocess.run(["bash", "-c", step_script()], cwd=work,
                       capture_output=True, text=True, env=env)
    return r.returncode, summary.read_text(), out.read_text()


PRESET_LOG = ("pipeline: m2v-prototype\n"
              "PRESET UNAVAILABLE: preset 'm2v-prototype' could not boot for "
              "en-us: ModuleNotFoundError: No module named 'model2vec'")


def test_exit_5_keeps_the_job_red(tmp_path: Path) -> None:
    """A boot failure fails the step. It is not softened to a warning."""
    rc, _, output = run_step(tmp_path, 5, PRESET_LOG)
    assert rc == 5, output
    assert "rc=5" in output


def test_exit_5_summary_says_the_run_could_not_boot(tmp_path: Path) -> None:
    rc, summary, _ = run_step(tmp_path, 5, PRESET_LOG)
    assert rc == 5
    assert "could not boot" in summary, summary
    assert "no row was measured" in summary, summary


def test_exit_5_summary_carries_the_reason_ovoscope_printed(tmp_path: Path) -> None:
    """The PRESET UNAVAILABLE line is the reason, and it reaches the summary.

    Without it a reader sees a red job, no counts and no cause, and has to
    open the artifact to learn the boot failed.
    """
    _, summary, _ = run_step(tmp_path, 5, PRESET_LOG)
    assert "No module named 'model2vec'" in summary, summary


def test_exit_5_with_no_reason_in_the_log_says_where_to_look(tmp_path: Path) -> None:
    """A boot failure whose log carries no PRESET UNAVAILABLE line still
    explains itself, rather than leaving the section empty."""
    _, summary, _ = run_step(tmp_path, 5, "pipeline: repo\nkilled")
    assert "read golden-results.log in the artifact" in summary, summary


def test_the_legend_names_every_code_the_command_can_return(tmp_path: Path) -> None:
    """0 to 5, with 5 named. The legend is what a reader of a red job reads."""
    _, summary, _ = run_step(tmp_path, 5, PRESET_LOG)
    legend = [ln for ln in summary.splitlines() if ln.startswith("exit codes:")]
    assert len(legend) == 1, summary
    for code in ("0 ", "1 ", "2 ", "3 ", "4 ", "5 "):
        assert code in legend[0], legend[0]
    assert "could not boot" in legend[0]


def test_a_boot_failure_is_not_reported_as_a_miss(tmp_path: Path) -> None:
    """Exit 1 and exit 5 do not read the same. A miss measured rows; a boot
    failure measured none, and the summary must not imply otherwise."""
    _, five, _ = run_step(tmp_path, 5, PRESET_LOG)
    _, one, _ = run_step(tmp_path, 1, "12 rows, 11 matched, 1 failed")
    # "no row was measured" marks the boot section. The legend line names
    # every code in both summaries, so it cannot be the marker.
    assert "no row was measured" in five, five
    assert "no row was measured" not in one, one
    assert "PRESET UNAVAILABLE" not in one, one
    assert "12 rows, 11 matched, 1 failed" in one


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4])
def test_the_other_codes_are_unchanged(tmp_path: Path, code: int) -> None:
    """The boot section belongs to 5 alone, and every code still propagates."""
    rc, summary, output = run_step(tmp_path, code, "3 rows, 3 matched")
    assert rc == code, output
    assert f"rc={code}" in output
    assert "no row was measured" not in summary, summary
