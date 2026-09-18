"""locale-lint.yml's "Lint locale directories" step: with spec_scope=changed a
finding blocks only when its file is one the pull request changed. The step is
run under bash against a scratch git repository and a fake ovos-spec-lint that
prints fixed finding lines, so the path filter is what is under test.

CodeRabbit on gh-automations#113 (:108): `grep -F -f changed.txt` was a
substring match, so a finding in `locale/en-us/foo.dialog.bak` blocked when
the PR changed `locale/en-us/foo.dialog`. The filter compares the finding's
path field with each changed path exactly."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/locale-lint.yml"
STEP = "Lint locale directories"

FAKE_LINT = """#!/usr/bin/env bash
# one finding in the changed file, one in a file whose path merely contains it
echo "locale/en-us/foo.dialog:1: error: unbalanced parenthesis"
echo "locale/en-us/foo.dialog.bak:1: error: unbalanced parenthesis"
echo "./locale/en-us/other.intent:3: warning: empty line"
exit 1
"""


def step_script() -> str:
    wf = yaml.safe_load(WORKFLOW.read_text())
    steps = wf["jobs"]["spec"]["steps"]
    script = next(s for s in steps if s.get("name") == STEP)["run"]
    assert "${{" not in script, script
    return script


def git(repo: Path, *args: str) -> str:
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
    r = subprocess.run(["git", "-C", str(repo), *args], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "skill"
    (repo / "locale/en-us").mkdir(parents=True)
    for name in ("foo.dialog", "foo.dialog.bak", "other.intent"):
        (repo / "locale/en-us" / name).write_text("(a|b\n")
    git(repo, "init", "-q", "-b", "dev")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "base")
    # a remote named origin whose dev is the base, as the runner sees it
    git(repo, "remote", "add", "origin", str(repo))
    git(repo, "fetch", "-q", "origin", "dev")
    git(repo, "checkout", "-q", "-b", "pr")
    (repo / "locale/en-us/foo.dialog").write_text("(a|b|c\n")
    git(repo, "commit", "-q", "-am", "pr: change foo.dialog only")
    return repo


def run_step(tmp_path: Path, repo: Path, scope: str = "changed") -> subprocess.CompletedProcess:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    fake = bindir / "ovos-spec-lint"
    fake.write_text(FAKE_LINT)
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{bindir}:{os.environ['PATH']}", LOCALE_PATHS="locale",
               SPEC_SCOPE=scope, BASE_REF="dev")
    return subprocess.run(["bash", "-e", "-c", step_script()], cwd=repo, env=env,
                          capture_output=True, text=True)


def test_a_finding_in_a_file_whose_path_contains_a_changed_path_does_not_block(tmp_path):
    repo = make_repo(tmp_path)
    r = run_step(tmp_path, repo)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "3 findings, 1 in files this pull request touches" in r.stdout, r.stdout
    blocking = (repo / "blocking.txt").read_text().splitlines()
    assert blocking == ["locale/en-us/foo.dialog:1: error: unbalanced parenthesis"], blocking


def test_a_dot_slash_prefix_on_the_finding_still_matches_the_changed_path(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "locale/en-us/other.intent").write_text("(a|b|c\n")
    git(repo, "commit", "-q", "-am", "pr: change other.intent too")
    r = run_step(tmp_path, repo)
    assert r.returncode == 1
    blocking = (repo / "blocking.txt").read_text().splitlines()
    assert blocking == ["locale/en-us/foo.dialog:1: error: unbalanced parenthesis",
                        "./locale/en-us/other.intent:3: warning: empty line"], blocking


def test_scope_all_blocks_on_every_finding(tmp_path):
    repo = make_repo(tmp_path)
    r = run_step(tmp_path, repo, scope="all")
    assert r.returncode == 1
    assert "3 findings, 3 in files this pull request touches" in r.stdout, r.stdout
