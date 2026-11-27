"""Count the OpenVoiceOS repos that call each reusable workflow; write docs/img/callers.csv.

Needs an authenticated gh CLI. GitHub code search indexes default branches only
and returns at most 1000 files, so the counts are a lower bound.
"""
import collections
import csv
import json
import pathlib
import re
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
USES = re.compile(r"gh-automations/\.github/workflows/([\w-]+\.yml)")

reusable = []
for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
    on = yaml.safe_load(path.read_text())[True]
    if isinstance(on, dict) and "workflow_call" in on:
        reusable.append(path.name)

out = subprocess.run(
    ["gh", "search", "code", "--owner", "OpenVoiceOS", "--limit", "1000",
     "--json", "repository,textMatches", "OpenVoiceOS/gh-automations/.github/workflows"],
    check=True, capture_output=True, text=True).stdout
hits = json.loads(out)
repos = collections.defaultdict(set)
for hit in hits:
    repo = hit["repository"]["nameWithOwner"]
    if repo == "OpenVoiceOS/gh-automations":
        continue
    for match in hit["textMatches"]:
        for name in USES.findall(match["fragment"]):
            repos[name].add(repo)

rows = sorted(((n, len(repos[n])) for n in reusable), key=lambda r: (-r[1], r[0]))
with open(ROOT / "docs/img/callers.csv", "w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["workflow", "caller_repos"])
    writer.writerows(rows)
print(f"{len(hits)} caller files in, {len(rows)} workflow rows out")
