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
import random
import re
import sys
import time
import urllib.request
import urllib.error

# Invisible HTML comment used to identify the aggregated PR checks comment.
COMMENT_MARKER = "<!-- ovos-pr-checks -->"
SIG_MARKER = "<!-- ovos-sig-start -->"

GREETINGS = [
    "Hello! I've finished running some automated checks on this PR. 👋",
    "Beep boop! Here's the latest status of your PR checks. 🤖",
    "Greetings! I've analyzed your changes and have some results to share. 🖖",
    "Checking in! Here's how the automated tests are looking. 🧐",
    "At your service! I've gathered all the check results for you. 🫡",
    "Reporting for duty! The automated checks have completed. 🎖️",
]

SIGNATURES = [
    "Generated with ❤️ by OVOS Automations",
    "Your friendly neighborhood bot 🕷️",
    "Beep boop, I'm just a script 🤖",
    "Keeping the code clean, one PR at a time ✨",
    "Automating the boring stuff so you don't have to! 🚀",
]

FLAVOR_TEXTS = {
    "coverage": [
        "I've been crunching the numbers! Here's how the test coverage changed. 📈",
        "Let's see how much of the code is actually being tested... 🧐",
        "I've mapped out the test coverage for you! 🗺️",
        "Coverage report incoming! Every line counts. 🎯",
    ],
    "build": [
        "I tried building your changes, and here's what happened! 🔨",
        "Build test complete! Let's see if everything fits together. 🧩",
        "I've put your code through the build grinder. ☕",
        "Checking if the gears are still turning smoothly... ⚙️",
    ],
    "skill": [
        "I've given your skill a thorough inspection! 🕵️",
        "Skill structure analysis complete! 🧠",
        "I've checked the skill's DNA. Here's what I found! 🔬",
        "Is it a bird? Is it a plane? No, it's a skill check result! 🦸",
    ],
    "security": [
        "I've scanned the dependencies for any hidden surprises. 🔍",
        "Security check! Are we safe from vulnerabilities? 🛡️",
        "I've audited the packages. Safety first! 🦺",
        "Checking for any digital cooties in your dependencies... 👾",
    ],
    "license": [
        "Legal eagle here! Checking those licenses. ⚖️",
        "Are we all good on the legal front? Let's find out! 📑",
        "I've verified the license compliance for your changes. ✅",
        "Keeping the lawyers happy, one file at a time. 👔",
    ],
    "health": [
        "A quick checkup for the repository! 🩺",
        "How's the repo's pulse? Let's take a look. 💓",
        "I've performed a health check on the project. 🏥",
        "Keeping the project in tip-top shape! 🏃",
    ],
    "python_support": [
        "Testing across the Python multiverse! 🐍",
        "Checking if your code plays well with different Python versions. 🎭",
        "Compatibility check! No version left behind. 🌍",
        "I've tested your changes against multiple Python interpreters. 🧪",
    ],
    "release": [
        "A sneak peek into the future! 🔮",
        "Here's what the next release might look like! 🚀",
        "I've generated a preview of the upcoming changes. 🎬",
        "Coming soon to a stable branch near you! 📽️",
    ],
    "welcome": [
        "Welcome to the community! 🥳",
        "A new contributor! This is exciting! ✨",
        "Thanks for joining us! 🤝",
        "We're glad to have you here! 🌈",
    ],
    "generic": [
        "I've got some results for you! 📝",
        "Here's the latest update on this check. 🗞️",
        "Analysis complete! Check out the details below. 📊",
        "Another piece of the puzzle! 🧩",
    ]
}


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
    # Choose a random flavor text from the appropriate pool
    pool = FLAVOR_TEXTS.get(section_id, FLAVOR_TEXTS["generic"])
    flavor = random.choice(pool)
    
    return (
        f"<!-- section:{section_id} -->\n"
        f"### {title}\n\n"
        f"{flavor}\n\n"
        f"{content.strip()}\n"
        f"<!-- /section:{section_id} -->"
    )


def insert_or_replace_section(body: str, section_id: str, title: str, content: str) -> str:
    """Replace an existing section, or append it if not present."""
    new_section = build_section(section_id, title, content)
    start_tag = f"<!-- section:{section_id} -->"
    end_tag = f"<!-- /section:{section_id} -->"
    
    if start_tag in body:
        # Surgical replacement using index to avoid regex greedy pitfalls
        start_idx = body.find(start_tag)
        end_idx = body.find(end_tag) + len(end_tag)
        if end_idx < start_idx: # Should not happen with well-formed comments
             return body.rstrip() + "\n\n" + new_section + "\n"
        return body[:start_idx] + new_section + body[end_idx:]
    
    # If adding the first section, ensure we don't just append to the signature
    if SIG_MARKER in body:
        parts = body.split(SIG_MARKER, 1)
        return parts[0].rstrip() + "\n\n" + new_section + "\n\n" + SIG_MARKER + parts[1]
        
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
        content = fh.read().strip()

    # Initial check for existing comment
    comment_id, body = find_ovos_comment(args.repo, args.pr)

    if comment_id is None:
        # Race condition mitigation: sleep a random amount and re-check
        # This helps break ties if multiple workflows start at the exact same time.
        wait_time = random.uniform(1.0, 10.0)
        print(f"No existing comment found. Waiting {wait_time:.2f}s to mitigate race conditions...")
        time.sleep(wait_time)
        comment_id, body = find_ovos_comment(args.repo, args.pr)

    if comment_id is None:
        # Still none? Create it.
        greeting = random.choice(GREETINGS)
        signature = random.choice(SIGNATURES)
        
        new_body = (
            f"{COMMENT_MARKER}\n"
            f"## {greeting}\n\n"
            f"I've aggregated the results of the automated checks for this PR below.\n\n"
            + build_section(args.section_id, args.title, content) + "\n\n"
            f"{SIG_MARKER}\n"
            f"---\n"
            f"_{signature}_"
        )
        github_api("POST", f"/repos/{args.repo}/issues/{args.pr}/comments", data={"body": new_body})
        print(f"Created new OVOS PR Checks comment with section '{args.section_id}'")
    else:
        new_body = insert_or_replace_section(body, args.section_id, args.title, content)
        if new_body.strip() == body.strip():
            print(f"Section '{args.section_id}' content unchanged — skipping update")
            return
        github_api("PATCH", f"/repos/{args.repo}/issues/comments/{comment_id}", data={"body": new_body})
        print(f"Updated section '{args.section_id}' in existing OVOS PR Checks comment #{comment_id}")


if __name__ == "__main__":
    main()
