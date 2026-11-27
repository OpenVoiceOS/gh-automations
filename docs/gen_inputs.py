"""Rewrite each generated inputs table in docs/workflow-reference.md from its workflow_call block.

A table sits between `<!-- inputs:<name>.yml -->` and `<!-- /inputs -->`.
With --check, exit 1 when a table differs from the workflow file.
"""
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/workflow-reference.md"
BLOCK = re.compile(r"(<!-- inputs:([\w-]+\.yml) -->\n).*?(<!-- /inputs -->)", re.S)


def default(spec):
    if spec.get("required"):
        return "required"
    value = spec.get("default", "")
    if isinstance(value, bool):
        value = str(value).lower()
    return f"`{value}`" if value != "" else '`""`'


def table(name):
    on = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())[True]
    rows = ["| Input | Type | Default | Description |", "|---|---|---|---|"]
    for key, spec in on["workflow_call"]["inputs"].items():
        text = " ".join(str(spec.get("description", "")).split()).replace("|", "\\|")
        rows.append(f"| `{key}` | {spec['type']} | {default(spec)} | {text} |")
    return "\n".join(rows) + "\n"


def render(doc):
    return BLOCK.sub(lambda m: m.group(1) + table(m.group(2)) + m.group(3), doc)


if __name__ == "__main__":
    old = DOC.read_text()
    new = render(old)
    if "--check" in sys.argv:
        sys.exit(0 if new == old else 1)
    DOC.write_text(new)
    print(f"{len(BLOCK.findall(old))} tables in, {len(BLOCK.findall(new))} tables out")
