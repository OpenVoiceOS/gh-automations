#!/usr/bin/env python3
"""
Update a named section in the aggregated 'OVOS PR Checks' comment on a PR.

If the comment does not exist, it is created.
If the named section does not exist in the comment, it is appended.
If the named section exists, only that section is replaced.

This lets multiple independent workflows each manage their own section
of a single sticky PR comment without overwriting each other's content.

Usage:
    python update_pr_comment.py \\
        --repo OpenVoiceOS/ovos-core \\
        --pr 123 \\
        --section-id coverage \\
        --title "📊 Coverage" \\
        --content-file /tmp/coverage-section.md

Environment:
    GITHUB_TOKEN   Required. Personal access token or GITHUB_TOKEN from Actions.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error

# Invisible HTML comment used to identify the aggregated PR checks comment.
COMMENT_MARKER = "<!-- ovos-pr-checks -->"


def github_api(method: str, path: str, data: dict = None) -> dict | list:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise EnvironmentError("GITHUB_TOKEN environment variable is not set")
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"GitHub API {method} {path} failed with HTTP {exc.code}: {detail}", file=sys.stderr)
        raise


def find_ovos_comment(repo: str, pr_number: int) -> tuple[int | None, str | None]:
    """Return (comment_id, body) for the existing OVOS PR Checks comment, or (None, None)."""
    page = 1
    while True:
        comments = github_api("GET", f"/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}")
        if not comments:
            break
        for comment in comments:
            if COMMENT_MARKER in comment.get("body", ""):
                return comment["id"], comment["body"]
        if len(comments) < 100:
            break
        page += 1
    return None, None


def build_section(section_id: str, title: str, content: str) -> str:
    return (
        f"<!-- section:{section_id} -->\n"
        f"### {title}\n\n"
        f"{content.strip()}\n"
        f"<!-- /section:{section_id} -->"
    )


def insert_or_replace_section(body: str, section_id: str, title: str, content: str) -> str:
    """Replace an existing section, or append it if not present."""
    new_section = build_section(section_id, title, content)
    start = re.escape(f"<!-- section:{section_id} -->")
    end = re.escape(f"<!-- /section:{section_id} -->")
    pattern = rf"{start}.*?{end}"
    if re.search(pattern, body, re.DOTALL):
        return re.sub(pattern, new_section, body, flags=re.DOTALL)
    return body.rstrip() + "\n\n" + new_section + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="owner/repo (e.g. OpenVoiceOS/ovos-core)")
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument("--section-id", required=True, help="Unique section identifier (e.g. 'coverage')")
    parser.add_argument("--title", required=True, help="Section heading text (e.g. '📊 Coverage')")
    parser.add_argument("--content-file", required=True, help="File containing the markdown content for this section")
    args = parser.parse_args()

    with open(args.content_file, encoding="utf-8") as fh:
        content = fh.read()

    comment_id, body = find_ovos_comment(args.repo, args.pr)

    if comment_id is None:
        new_body = (
            f"{COMMENT_MARKER}\n"
            f"## OVOS PR Checks\n\n"
            + build_section(args.section_id, args.title, content) + "\n"
        )
        github_api("POST", f"/repos/{args.repo}/issues/{args.pr}/comments", data={"body": new_body})
        print(f"Created new OVOS PR Checks comment with section '{args.section_id}'")
    else:
        new_body = insert_or_replace_section(body, args.section_id, args.title, content)
        if new_body == body:
            print(f"Section '{args.section_id}' content unchanged — skipping update")
            return
        github_api("PATCH", f"/repos/{args.repo}/issues/comments/{comment_id}", data={"body": new_body})
        print(f"Updated section '{args.section_id}' in existing OVOS PR Checks comment #{comment_id}")


if __name__ == "__main__":
    main()
