import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from check_docs_standard import check

HINT = "<!-- agent-hint\ncovers: x\nsource: y\ngenerated: no\nverify: true\nsee: z\n-->\n"
FOOT = "\n---\n[Home](index.md)\n"


def write(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


def test_clean_repo_has_no_finding(tmp_path):
    write(tmp_path, {"README.md": f"# r\n\n{HINT}\n[Try it](https://huggingface.co/spaces/O/r) · [docs](docs/index.md)\n",
                     "docs/index.md": f"# i\n{HINT}[a](a.md)\n",
                     "docs/a.md": f"# a\n{HINT}text{FOOT}"})
    assert check(tmp_path, "O/r") == ([], 3)


def test_each_rule_fires(tmp_path):
    write(tmp_path, {"README.md": "# r\n" + "line\n" * 90 + "[x](missing.md)\n```\n[y](fenced.md)\n```\n",
                     "docs/a.md": "# a\n" + HINT.replace("see: z\n", "") + "no footer\n",
                     "TODO.md": ""})
    findings, files = check(tmp_path, "O/r")
    assert files == 2
    assert sorted((r, w) for r, w, _ in findings) == [
        ("DS-11", "TODO.md"), ("DS-12", "README.md"), ("DS-6", "README.md"), ("DS-6a", "README.md"),
        ("DS-8", "docs/a.md"), ("DS-9", "README.md"), ("DS-9", "docs/a.md")]


def test_exit_code(tmp_path):
    write(tmp_path, {"README.md": "# r\n"})
    run = subprocess.run([sys.executable, str(ROOT / "scripts/check_docs_standard.py"), "--root", str(tmp_path)],
                         capture_output=True, text=True)
    assert run.returncode == 1 and run.stdout.endswith("files checked: 1, findings: 1\n")


def test_nested_page_footer_links_parent_index(tmp_path):
    write(tmp_path, {"docs/lang/pt.md": f"# pt\n{HINT}text\n---\n[Home](../index.md)\n", "docs/index.md": f"# i\n{HINT}"})
    assert check(tmp_path) == ([], 2)


def test_link_forms_that_resolve(tmp_path):
    write(tmp_path, {"docs/index.md": f"# i\n{HINT}", "docs/a.md":
        f"# a\n{HINT}`[ic](gone.md)` [r](/docs/index.md) [q](index.md?plain=1) [u](HTTPS://x.org){FOOT}"})
    assert check(tmp_path) == ([], 2)


def test_non_utf8_page_is_a_finding(tmp_path):
    write(tmp_path, {"docs/index.md": f"# i\n{HINT}"})
    (tmp_path / "docs/b.md").write_bytes(b"# b\n\xff\xfe")
    assert check(tmp_path) == ([("DS-12", "docs/b.md", "not UTF-8, not checked")], 2)
