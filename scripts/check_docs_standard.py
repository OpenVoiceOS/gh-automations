#!/usr/bin/env python3
"""Check a repository's README and docs/ against the OVOS docs standard.

    check_docs_standard.py [--root DIR] [--hf-space OWNER/NAME] [--json FILE]

Rule IDs are those of the docs standard:
  DS-6   README of at most README_MAX lines
  DS-6a  README links its Hugging Face Space (only with --hf-space)
  DS-8   each docs page except the index ends with `---` and a footer that links the index
  DS-9   README and each docs page have an agent-hint comment right after the H1,
         with the keys covers, source, generated, verify and see
  DS-11  no agent scratch files at the root
  DS-12  each relative link resolves to a file

Prints one line per finding and the counts. Exits 1 when a finding exists.
"""
import argparse
import json
import re
import sys
from pathlib import Path

README_MAX = 80
HINT_KEYS = ("covers", "source", "generated", "verify", "see")
NOISE = ("AUDIT.md", "HANDOFF.md", "FINDINGS.md", "NOTES.md", "STATUS.md", "TODO.md", "PLAN.md",
         "CLAUDE.md", "llms.txt")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
CODE = re.compile(r"`[^`\n]*`")
SCHEME = re.compile(r"[a-z][a-z0-9+.-]*:", re.I)


def hint_findings(path, text):
    lines = text.splitlines()
    h1 = next((i for i, l in enumerate(lines) if l.startswith("# ")), None)
    if h1 is None:
        return [("DS-9", path, "no H1")]
    rest = [l for l in lines[h1 + 1:] if l.strip()]
    if not rest or not rest[0].startswith("<!-- agent-hint"):
        return [("DS-9", path, "no agent-hint comment right after the H1")]
    block = text[text.index("<!-- agent-hint"):]
    block = block.split("-->")[0]
    missing = [k for k in HINT_KEYS if not re.search(rf"^{k}:", block, re.M)]
    return [("DS-9", path, f"agent-hint misses {', '.join(missing)}")] if missing else []


def footer_findings(path, text):
    tail = [l.strip() for l in text.splitlines() if l.strip()][-2:]
    if len(tail) < 2 or tail[0] != "---" or not re.search(r"\]\((\.\./)*index\.md\)", tail[1]):
        return [("DS-8", path, "no `---` and footer line that links index.md at the end")]
    return []


def link_findings(root, path, text):
    out = []
    for target in LINK.findall(CODE.sub("", FENCE.sub("", text))):
        if SCHEME.match(target) or target.startswith("#"):
            continue
        file = re.split(r"[#?]", target)[0]
        base = root if file.startswith("/") else path.parent
        if file and not (base / file.lstrip("/")).resolve().exists():
            out.append(("DS-12", path.relative_to(root), f"broken link {target}"))
    return out


def read(root, path, findings):
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        findings.append(("DS-12", path.relative_to(root), "not UTF-8, not checked"))


def check(root, hf_space=None):
    findings = []
    readme = root / "README.md"
    pages = sorted((root / "docs").rglob("*.md")) if (root / "docs").is_dir() else []
    text = read(root, readme, findings) if readme.is_file() else None
    if text is not None:
        n = len(text.splitlines())
        if n > README_MAX:
            findings.append(("DS-6", "README.md", f"{n} lines, more than {README_MAX}"))
        if hf_space and f"huggingface.co/spaces/{hf_space}".lower() not in text.lower():
            findings.append(("DS-6a", "README.md", f"no link to https://huggingface.co/spaces/{hf_space}"))
        findings += hint_findings("README.md", text)
        findings += link_findings(root, readme, text)
    for page in pages:
        text = read(root, page, findings)
        if text is None:
            continue
        rel = page.relative_to(root)
        findings += hint_findings(rel, text)
        if page.name != "index.md":
            findings += footer_findings(rel, text)
        findings += link_findings(root, page, text)
    findings += [("DS-11", name, "agent scratch file") for name in NOISE if (root / name).exists()]
    return [(rule, str(where), what) for rule, where, what in findings], 1 + len(pages) if readme.is_file() else len(pages)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--hf-space", default="")
    ap.add_argument("--json")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    findings, files = check(root, args.hf_space.strip() or None)
    for rule, where, what in findings:
        print(f"{rule}\t{where}\t{what}")
    print(f"files checked: {files}, findings: {len(findings)}")
    if args.json:
        Path(args.json).write_text(json.dumps({"files": files, "findings": findings}))
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
