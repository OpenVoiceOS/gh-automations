"""publish-alpha.yml under two runs on one repository (T-2782).

Two runs that merge within a minute used to compute the same next alpha,
push into each other, and then build or tag whatever the branch head was
by the time the later jobs ran. The bump step now pushes in a loop that
re-reads the branch on a rejected push, and every later job checks out the
commit the bump step reports. The loops are executed here under bash
against a local bare remote whose pre-receive hook rejects the first push
of every ref, the way GitHub rejects a push behind the head."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github/workflows/publish-alpha.yml"

# rejects the first push it sees for each ref, then accepts
PRE_RECEIVE = """#!/usr/bin/env bash
while read -r old new ref; do
  marker="$GIT_DIR/rejected-once-${ref//\\//_}"
  if [ ! -e "$marker" ]; then
    touch "$marker"
    echo "simulated: another run moved $ref first" >&2
    exit 1
  fi
done
exit 0
"""


VERSION_PY = """# START_VERSION_BLOCK
VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_BUILD = 0
VERSION_ALPHA = {alpha}
# END_VERSION_BLOCK
"""


def load():
    return yaml.safe_load(WORKFLOW.read_text())


def step(job: str, name: str) -> dict:
    steps = load()["jobs"][job]["steps"]
    return next(s for s in steps if s.get("name") == name)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def remote(tmp_path: Path):
    """A bare remote with one commit on dev and a version.py at 0.1.0."""
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "dev", str(bare)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", "-q", str(bare), str(seed)], check=True)
    git(seed, "checkout", "-q", "-b", "dev")
    (seed / "version.py").write_text(
        VERSION_PY.format(alpha=0))
    (seed / "CHANGELOG.md").write_text("# Changelog\n")
    git(seed, "add", ".")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", "origin", "dev")
    hook = bare / "hooks" / "pre-receive"
    hook.write_text(PRE_RECEIVE)
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    return bare


def package_checkout(tmp_path: Path, remote: Path, ref: str = "dev") -> Path:
    pkg = tmp_path / "action" / "package"
    pkg.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--depth=1", "-b", "dev", str(remote), str(pkg)], check=True)
    if ref != "dev":
        git(pkg, "checkout", "-q", ref)
    return pkg


def run_bash(script: str, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    out = cwd / "gh_output"
    out.touch()
    # the workflow calls `python`; on a runner that is setup-python's interpreter
    pybin = str(Path(sys.executable).parent)
    full = dict(os.environ, GITHUB_OUTPUT=str(out), RUNNER_TEMP=str(cwd),
                PATH=f"{pybin}:{os.environ['PATH']}", **env)
    r = subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=full, capture_output=True, text=True)
    r.outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return r


class TestBumpLoop:
    def test_rejected_push_rereads_the_head(self, tmp_path, remote):
        pkg = package_checkout(tmp_path, remote)
        # another run lands 0.1.0a1 after our checkout and before our push
        other = tmp_path / "other"
        subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
        (other / "version.py").write_text(
            VERSION_PY.format(alpha=1))
        git(other, "commit", "-q", "-am", "Increment Version to 0.1.0a1")
        with pytest.raises(subprocess.CalledProcessError):
            git(other, "push", "-q", "origin", "dev")  # the hook rejects the first push
        git(other, "push", "-q", "origin", "dev")
        for m in remote.glob("rejected-once-*"):
            m.unlink()  # arm the hook again for the loop under test
        s = step("bump_version", "Increment Version and push")["run"]
        r = run_bash(s, pkg, {"PART": "alpha", "BRANCH": "dev", "VERSION_FILE": "version.py",
                              "SCRIPTS": str(ROOT / "scripts")})
        assert r.returncode == 0, r.stdout + r.stderr
        # attempt 1 reads 0.1.0a1, bumps to 0.1.0a2, is rejected by the hook;
        # attempt 2 reads the head again and lands 0.1.0a2 on top of it
        assert "rejected on attempt 1" in r.stdout
        assert "on attempt 2" in r.stdout
        assert r.outputs["version"] == "0.1.0a2"
        head = git(pkg, "rev-parse", "HEAD")
        assert r.outputs["sha"] == head
        assert git(pkg, "ls-remote", str(remote), "refs/heads/dev").split()[0] == head
        assert git(pkg, "log", "-1", "--format=%s") == "Increment Version to 0.1.0a2"
        assert git(pkg, "log", "-2", "--format=%s").splitlines()[1] == "Increment Version to 0.1.0a1"

    def test_clean_push_lands_on_the_first_attempt(self, tmp_path, remote):
        (remote / "hooks" / "pre-receive").unlink()
        pkg = package_checkout(tmp_path, remote)
        s = step("bump_version", "Increment Version and push")["run"]
        r = run_bash(s, pkg, {"PART": "alpha", "BRANCH": "dev", "VERSION_FILE": "version.py",
                              "SCRIPTS": str(ROOT / "scripts")})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "on attempt 1" in r.stdout and "rejected" not in r.stdout
        assert r.outputs["version"] == "0.1.1a1"  # alpha after a released 0.1.0, per update_version.py


class TestChangelogLoop:
    def test_generated_file_survives_a_rejected_push(self, tmp_path, remote):
        pkg = package_checkout(tmp_path, remote)
        bump = git(pkg, "rev-parse", "HEAD")
        (pkg / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0a1\n- a fix\n")
        s = step("update_changelog", "Push Changelog")["run"]
        r = run_bash(s, pkg, {"BRANCH": "dev", "CHANGELOG": "CHANGELOG.md", "BUMP_SHA": bump})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "rejected on attempt 1" in r.stdout and "pushed at" in r.stdout
        assert r.outputs["sha"] == git(pkg, "rev-parse", "HEAD")
        assert "- a fix" in git(pkg, "show", "origin/dev:CHANGELOG.md")

    def test_unchanged_changelog_reports_the_bump_sha(self, tmp_path, remote):
        pkg = package_checkout(tmp_path, remote)
        bump = git(pkg, "rev-parse", "HEAD")
        s = step("update_changelog", "Push Changelog")["run"]
        r = run_bash(s, pkg, {"BRANCH": "dev", "CHANGELOG": "CHANGELOG.md", "BUMP_SHA": bump})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "unchanged" in r.stdout
        assert r.outputs["sha"] == bump


class TestLaterJobsPinTheBumpCommit:
    """No later job checks out `inputs.branch`: that head belongs to whichever run pushed last."""

    def test_bump_version_exports_sha(self):
        assert load()["jobs"]["bump_version"]["outputs"]["sha"] == "${{ steps.version.outputs.sha }}"

    @pytest.mark.parametrize("job", ["update_changelog", "tag_prerelease", "publish_pypi"])
    def test_checkout_ref_is_the_bump_sha(self, job):
        ref = step(job, "Checkout Repository")["with"]["ref"]
        assert ref == "${{ needs.bump_version.outputs.sha }}", (job, ref)

    def test_propose_release_starts_at_this_runs_commits(self):
        ref = step("propose_release", "Checkout Repository")["with"]["ref"]
        assert ref == "${{ needs.update_changelog.outputs.sha || needs.bump_version.outputs.sha }}"

    def test_prerelease_tags_the_bump_commit(self):
        assert step("tag_prerelease", "Create Pre-release")["with"]["commit"] == "${{ needs.bump_version.outputs.sha }}"

    def test_no_later_job_reads_the_branch_head(self):
        jobs = load()["jobs"]
        for job in ("update_changelog", "tag_prerelease", "propose_release", "publish_pypi"):
            for s in jobs[job]["steps"]:
                if "checkout" in str(s.get("uses", "")):
                    assert s["with"]["ref"] != "${{ inputs.branch }}", job
