"""
Prove that a test suite imported the installed package and not the source tree.

``build-tests.yml`` builds a wheel, installs it non-editable, and runs the
``pytest`` console script so the repository root is not on ``sys.path``. That is
necessary and not sufficient, as the step's own comment says. pytest's prepend
import mode puts the rootdir back whenever the collected tests are a package or
a root ``conftest.py`` exists, so the tree is reachable again and a stale or
incomplete wheel is never missed. The job stays green.

Measured on ``hivemind-websocket-client`` at 7c1c5f6 (T-6677), one arm per
workflow, wheel installed non-editable in both:

  with the ``e2e`` extra      the package resolves to site-packages
  with the ``test`` extra     the package resolves to the SOURCE TREE

The only difference is that ``e2e`` installs ``hivescope``, whose ``node.py``
imports the package at plugin load and fills ``sys.modules`` from site-packages
before any test module is imported. The first arm is green by luck, not by
construction: the shadow is pre-empted, and it returns the moment that
dependency is dropped or stops importing the package at module level.

So the green needs a control, and it takes two arms, because "did the suite read
the wheel" and "is the wheel complete" are different questions:

  RESOLUTION    after collection, no top-level name the wheel ships may resolve
                to the source-tree copy. This is what catches the reading above.
                A rename control cannot: hiding the tree lets the import fall
                back to a complete wheel and collection succeeds either way, so
                the tree read passes unseen.

  COMPLETENESS  with the tree copy hidden, the suite must still collect. This
                catches a module left out of the wheel, a missing dependency or
                missing package data -- the defect the tree read conceals.

Hiding is a rename inside the repository root, restored in a ``finally``, so a
crash in the middle leaves no renamed tree behind.

A baseline that does not collect proves nothing about packaging, so it is
reported as inconclusive and never as a pass.

Failing either arm is not always a defect: a caller whose suite has not migrated
off a root ``conftest.py`` reads red on resolution while its wheel is fine. So
this is a warning by default and a failure only when the caller asks for one
with ``packaging_strict``.

Usage:
    python packaging_control.py --test-path "test/" [--root .] [--wheel x.whl]
        [--pytest-args="..."] [--strict] [--summary "$GITHUB_STEP_SUMMARY"]

Exit status: 0 when both arms pass, when the baseline is inconclusive, or when
an arm fails without ``--strict``. 1 when an arm fails and ``--strict`` is set.
2 on a usage error.
"""
import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile

HIDDEN_SUFFIX = ".packaging-control-hidden"

# Runs inside the pytest interpreter, which is the only one that can answer
# where an import resolved. Observes sys.modules after collection rather than
# importing anything itself: an import here would resolve by this plugin's own
# position on sys.path and not by the test modules', and would answer the wrong
# question.
PROBE = '''
import json, os, sys, sysconfig

def pytest_sessionfinish(session, exitstatus):
    names = json.loads(os.environ["PACKAGING_CONTROL_NAMES"])
    repo = os.path.realpath(os.environ["PACKAGING_CONTROL_REPO"])
    # "Is it the tree copy", not "is it under site-packages". The second reads
    # the same in the common case and is wrong in two: a virtualenv that lives
    # inside the repository (.venv) has its site-packages UNDER the repo root,
    # and an install elsewhere (user site, a conda layout, a .pth redirect) is
    # not under purelib at all. So the site paths are used only to rescue a
    # path that is under the repo root because the venv is.
    site = []
    for key in ("purelib", "platlib"):
        path = sysconfig.get_paths().get(key)
        if path:
            site.append(os.path.realpath(path))
    out = {}
    for name in names:
        mod = sys.modules.get(name)
        found = getattr(mod, "__file__", None)
        if found is None:
            out[name] = {"file": None, "in_tree": None}
            continue
        real = os.path.realpath(found)
        under_repo = real.startswith(repo + os.sep)
        under_site = any(real.startswith(s + os.sep) for s in site)
        out[name] = {"file": real, "in_tree": under_repo and not under_site}
    with open(os.environ["PACKAGING_CONTROL_OUT"], "w") as fh:
        json.dump({"modules": out, "site": site, "repo": repo}, fh)
'''


def top_level_names(wheel):
    """Top-level importable names the wheel ships, from its own entries.

    Read from the archive rather than from installed metadata: ``top_level.txt``
    is optional and absent from wheels built by several backends, while the
    entry list is always there.
    """
    names = set()
    with zipfile.ZipFile(wheel) as zf:
        for entry in zf.namelist():
            head = entry.split("/")[0]
            if head.endswith(".dist-info") or head.endswith(".data"):
                continue
            if "/" in entry:
                if head:
                    names.add(head)
            elif head.endswith(".py"):
                names.add(head[:-3])
    return sorted(names)


def tree_paths(root, names):
    """The source-tree path for each name that actually exists at the root."""
    found = []
    for name in names:
        pkg = os.path.join(root, name)
        mod = os.path.join(root, name + ".py")
        if os.path.isdir(pkg):
            found.append(pkg)
        elif os.path.isfile(mod):
            found.append(mod)
    return found


def collect(test_path, pytest_args, root, names=None, probe_dir=None):
    """Run a collect-only pass. Returns (ok, count, output, probe or None)."""
    cmd = ["pytest", "--collect-only", "-q"]
    env = dict(os.environ)
    out_path = None
    if names is not None and probe_dir is not None:
        plugin = os.path.join(probe_dir, "packaging_control_probe.py")
        with open(plugin, "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        out_path = os.path.join(probe_dir, "probe.json")
        # Never leave an empty entry on PYTHONPATH: python reads "" as the
        # current directory, which is the repository root here, and that puts
        # the source tree back on sys.path. The probe would then report the tree
        # for a suite that reads the wheel -- the instrument manufacturing the
        # very defect it measures. Measured on hivemind-websocket-client at
        # 7c1c5f6: a trailing os.pathsep alone flips the arm from site-packages
        # to the tree.
        inherited = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            probe_dir + os.pathsep + inherited if inherited else probe_dir
        )
        env["PACKAGING_CONTROL_NAMES"] = json.dumps(names)
        env["PACKAGING_CONTROL_OUT"] = out_path
        env["PACKAGING_CONTROL_REPO"] = root
        cmd += ["-p", "packaging_control_probe"]
    cmd += shlex.split(test_path)
    cmd += shlex.split(pytest_args or "")
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, env=env)
    text = (proc.stdout or "") + (proc.stderr or "")
    hit = re.search(r"(\d+) tests? collected", text)
    count = int(hit.group(1)) if hit else 0
    probe = None
    if out_path and os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as fh:
                probe = json.load(fh)
        except (OSError, ValueError):
            probe = None
    return proc.returncode == 0, count, text, probe


def write_summary(path, lines):
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        print(f"could not write the step summary: {exc}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test-path", required=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--wheel", default="")
    ap.add_argument("--pytest-args", default="")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--summary", default=os.environ.get("GITHUB_STEP_SUMMARY", ""))
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    wheel = args.wheel
    if not wheel:
        found = sorted(glob.glob(os.path.join(root, "dist", "*.whl")))
        if not found:
            print("::warning title=Packaging control::no wheel in dist/, so the "
                  "control did not run", file=sys.stderr)
            write_summary(args.summary,
                          ["### Packaging control", "",
                           "Skipped: no wheel in `dist/`."])
            return 0
        wheel = found[0]

    names = top_level_names(wheel)
    hide = tree_paths(root, names)
    # N in, N out: the wheel's names against the ones that exist in the tree.
    print(f"wheel {os.path.basename(wheel)} ships {len(names)} top-level "
          f"name(s): {', '.join(names) or '(none)'}")
    print(f"{len(hide)} of them also exist in the source tree: "
          f"{', '.join(os.path.basename(p) for p in hide) or '(none)'}")

    probe_dir = tempfile.mkdtemp(prefix="packaging-control-")
    base_ok, base_n, base_out, probe = collect(
        args.test_path, args.pytest_args, root, names=names, probe_dir=probe_dir)
    if not base_ok:
        print(base_out, file=sys.stderr)
        print("::warning title=Packaging control::the suite does not collect with "
              "the source tree present, so this run proves nothing about packaging "
              "(inconclusive, not a pass)", file=sys.stderr)
        write_summary(args.summary, [
            "### Packaging control", "",
            "**Inconclusive.** The suite does not collect even with the source "
            "tree in place, so neither arm would say anything about packaging. "
            "Fix the baseline collection error first.",
        ])
        return 0

    # --- arm 1, resolution -------------------------------------------------
    tree_read, unknown = [], []
    if probe is None:
        print("::warning title=Packaging control::the resolution probe wrote no "
              "result, so the resolution arm did not run", file=sys.stderr)
    else:
        for name, info in sorted(probe.get("modules", {}).items()):
            if info.get("file") is None:
                unknown.append(name)
            elif info.get("in_tree"):
                tree_read.append((name, info["file"]))
    for name, path in tree_read:
        print(f"resolution: {name} resolved to {path}, which is the source "
              f"tree copy and not the installed one")
    if unknown:
        print(f"resolution: {len(unknown)} name(s) never imported during "
              f"collection, so resolution is unknown for them: "
              f"{', '.join(unknown)}")

    # --- arm 2, completeness ----------------------------------------------
    pois_ok, pois_n, pois_out = True, base_n, ""
    if hide:
        renamed = []
        try:
            for path in hide:
                dest = path + HIDDEN_SUFFIX
                os.rename(path, dest)
                renamed.append((dest, path))
            pois_ok, pois_n, pois_out, _ = collect(
                args.test_path, args.pytest_args, root)
        finally:
            for dest, path in renamed:
                try:
                    os.rename(dest, path)
                except OSError as exc:
                    print(f"::error title=Packaging control::could not restore "
                          f"{path}: {exc}", file=sys.stderr)
    else:
        print("completeness: no top-level name the wheel ships exists at the "
              "repository root, so the tree cannot shadow the installed package")

    complete = pois_ok and pois_n == base_n
    problems = []
    if tree_read:
        problems.append(
            "the suite imported the SOURCE TREE for " +
            ", ".join(f"`{n}`" for n, _ in tree_read) +
            ", not the installed wheel, so a stale or incomplete wheel would "
            "not be noticed here")
    if not complete:
        if pois_ok:
            problems.append(
                f"the suite collects {base_n} test(s) with the source tree "
                f"present and {pois_n} with it hidden, so {base_n - pois_n} "
                "were read from the tree")
        else:
            problems.append(
                f"the suite does not collect with the source tree hidden "
                f"({base_n} test(s) collected with it present), so the wheel is "
                "missing something the tree supplies")

    if not problems:
        print(f"control passed: every name resolved to the installed copy and "
              f"the suite collects {pois_n} test(s) with the tree hidden")
        write_summary(args.summary, [
            "### Packaging control", "",
            f"Passed. The suite imported the installed wheel, and it still "
            f"collects {pois_n} test(s) with the source tree hidden.",
        ])
        return 0

    short = [ln for ln in pois_out.splitlines()
             if "ModuleNotFoundError" in ln or "ImportError" in ln][:20]
    level = "error" if args.strict else "warning"
    for problem in problems:
        print(f"::{level} title=Packaging control::"
              f"{problem.replace('`', '')}", file=sys.stderr)
    write_summary(args.summary, [
        "### Packaging control", "",
        f"**{'Failed' if args.strict else 'Warning'}.**", "",
    ] + [f"- {p}" for p in problems] + [
        "",
        "The wheel is installed non-editable and the console script adds no "
        "`sys.path` entry, so the tree is reached through pytest's prepend "
        "import mode (a test package, or a root `conftest.py`) or through a "
        "dependency that imports the package at plugin load. Remove the test "
        "package's `__init__.py`, or pass "
        "`pytest_args: --import-mode=importlib`.",
    ] + ([""] + ["```"] + short + ["```"] if short else []))
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
