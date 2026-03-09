#!/usr/bin/env python3
"""
Analyse a checked-out OVOS skill repository for locale structure, language
coverage, skill.json validity, and gitlocalize readiness.

Outputs a JSON report. Exit code is always 0; callers decide pass/fail.

Usage:
    check_skill.py [--repo-root .] [--locale-dir ""] [--output-json /tmp/skill-report.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_setup_files(repo_root: str) -> list[str]:
    """Return paths of setup.py / pyproject.toml / setup.cfg under repo_root."""
    found = []
    for name in ("setup.py", "pyproject.toml", "setup.cfg"):
        candidate = os.path.join(repo_root, name)
        if os.path.isfile(candidate):
            found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def is_skill_repo(repo_root: str) -> bool:
    """Return True if repo_root is an OVOS skill (contains 'ovos.plugin.skill' entry point)."""
    for path in _find_setup_files(repo_root):
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
            if "ovos.plugin.skill" in content:
                return True
        except OSError:
            continue
    return False


def find_locale_dir(repo_root: str, override: str = "") -> str | None:
    """Auto-detect the locale directory.

    Preference order:
    1. *override* if provided and valid.
    2. Shallowest ``locale/`` directory containing an ``en-us`` sub-directory.
    3. Any directory named ``locale/`` containing sub-directories with
       ``*.intent`` or ``*.voc`` files.

    Returns None if nothing is found.
    """
    if override:
        candidate = override if os.path.isabs(override) else os.path.join(repo_root, override)
        if os.path.isdir(candidate):
            return candidate

    candidates: list[tuple[int, str]] = []  # (depth, path)

    for dirpath, dirnames, _filenames in os.walk(repo_root):
        # Skip hidden dirs and common non-source dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__")]
        if os.path.basename(dirpath) == "locale":
            depth = dirpath.count(os.sep)
            en_us = os.path.join(dirpath, "en-us")
            if os.path.isdir(en_us):
                candidates.append((depth, dirpath))
            else:
                # Fallback: any sub-dir with .intent/.voc files
                for sub in os.listdir(dirpath):
                    sub_path = os.path.join(dirpath, sub)
                    if not os.path.isdir(sub_path):
                        continue
                    for _, _, fnames in os.walk(sub_path):
                        if any(f.endswith((".intent", ".voc")) for f in fnames):
                            candidates.append((depth, dirpath))
                            break
                    else:
                        continue
                    break

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def count_locale_files(lang_dir: str) -> dict[str, int]:
    """Count locale files by extension under *lang_dir* (recursive).

    Returns dict with keys: intent, voc, dialog, rx, entity, total.
    """
    counts: dict[str, int] = {"intent": 0, "voc": 0, "dialog": 0, "rx": 0, "entity": 0, "total": 0}
    ext_map = {".intent": "intent", ".voc": "voc", ".dialog": "dialog", ".rx": "rx", ".entity": "entity"}
    for dirpath, _dirs, fnames in os.walk(lang_dir):
        for fname in fnames:
            if fname == "skill.json":
                continue
            ext = os.path.splitext(fname)[1].lower()
            key = ext_map.get(ext)
            if key:
                counts[key] += 1
                counts["total"] += 1
    return counts


def get_en_us_file_set(locale_dir: str) -> set[str]:
    """Return relative paths of all files under locale_dir/en-us/ (excluding skill.json)."""
    en_us_dir = os.path.join(locale_dir, "en-us")
    if not os.path.isdir(en_us_dir):
        return set()
    result: set[str] = set()
    for dirpath, _dirs, fnames in os.walk(en_us_dir):
        for fname in fnames:
            if fname == "skill.json":
                continue
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, en_us_dir)
            result.add(rel)
    return result


def check_skill_json(lang_dir: str) -> dict:
    """Check skill.json presence and validity in *lang_dir*.

    Returns dict with: exists, valid_json, missing_fields, skill_id.
    Required fields: skill_id, name, description, examples, tags.
    """
    required_fields = {"skill_id", "name", "description", "examples", "tags"}
    path = os.path.join(lang_dir, "skill.json")
    if not os.path.isfile(path):
        return {"exists": False, "valid_json": False, "missing_fields": list(required_fields), "skill_id": None}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        missing = sorted(required_fields - set(data.keys()))
        return {
            "exists": True,
            "valid_json": True,
            "missing_fields": missing,
            "skill_id": data.get("skill_id"),
        }
    except json.JSONDecodeError as exc:
        return {"exists": True, "valid_json": False, "missing_fields": sorted(required_fields), "skill_id": None, "error": str(exc)}


def check_translation_completeness(locale_dir: str, en_us_files: set[str]) -> list[dict]:
    """Check translation coverage for each non-en-us language directory.

    Returns list of dicts: {lang, total, present, pct}, sorted by lang.
    """
    if not en_us_files:
        return []
    results: list[dict] = []
    try:
        langs = [d for d in os.listdir(locale_dir)
                 if os.path.isdir(os.path.join(locale_dir, d)) and d != "en-us"]
    except OSError:
        return []
    for lang in sorted(langs):
        lang_dir = os.path.join(locale_dir, lang)
        present = 0
        for rel_path in en_us_files:
            candidate = os.path.join(lang_dir, rel_path)
            if os.path.isfile(candidate):
                present += 1
        total = len(en_us_files)
        pct = round(present / total * 100, 1) if total > 0 else 0.0
        results.append({"lang": lang, "total": total, "present": present, "pct": pct})
    return results


def check_gitlocalize_readiness(repo_root: str) -> dict:
    """Check gitlocalize integration readiness.

    Returns dict with:
      sync_script_exists, translations_dir_exists,
      sync_workflow_exists, sync_workflow_file.
    """
    sync_script = os.path.join(repo_root, "scripts", "sync_translations.py")
    translations_dir = os.path.join(repo_root, "translations")
    workflows_dir = os.path.join(repo_root, ".github", "workflows")

    sync_workflow_exists = False
    sync_workflow_file: str | None = None

    if os.path.isdir(workflows_dir):
        for fname in os.listdir(workflows_dir):
            if not fname.endswith((".yml", ".yaml")):
                continue
            fpath = os.path.join(workflows_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    content = fh.read()
                if "sync-translations.yml" in content:
                    sync_workflow_exists = True
                    sync_workflow_file = fname
                    break
            except OSError:
                continue

    return {
        "sync_script_exists": os.path.isfile(sync_script),
        "translations_dir_exists": os.path.isdir(translations_dir),
        "sync_workflow_exists": sync_workflow_exists,
        "sync_workflow_file": sync_workflow_file,
    }


def run_checks(repo_root: str, locale_dir_override: str = "") -> dict:
    """Run all skill checks and return the full report dict."""
    repo_root = os.path.abspath(repo_root)

    report: dict = {
        "repo_root": repo_root,
        "is_skill": is_skill_repo(repo_root),
        "locale_dir": None,
        "has_en_us": False,
        "en_us_counts": {},
        "skill_json": {},
        "languages": 0,
        "translations": [],
        "gitlocalize": {},
        "skill_id": None,
    }

    locale_dir = find_locale_dir(repo_root, locale_dir_override)
    if locale_dir is None:
        return report

    report["locale_dir"] = locale_dir
    en_us_dir = os.path.join(locale_dir, "en-us")
    report["has_en_us"] = os.path.isdir(en_us_dir)

    if report["has_en_us"]:
        report["en_us_counts"] = count_locale_files(en_us_dir)
        report["skill_json"] = check_skill_json(en_us_dir)
        report["skill_id"] = report["skill_json"].get("skill_id")

    en_us_files = get_en_us_file_set(locale_dir)
    translations = check_translation_completeness(locale_dir, en_us_files)
    report["translations"] = translations
    # Count non-en-us language dirs
    try:
        all_langs = [d for d in os.listdir(locale_dir) if os.path.isdir(os.path.join(locale_dir, d))]
    except OSError:
        all_langs = []
    report["languages"] = len(all_langs)

    report["gitlocalize"] = check_gitlocalize_readiness(repo_root)

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=".", help="Root of the skill repository (default: .)")
    parser.add_argument("--locale-dir", default="", help="Override locale directory path (empty = auto-detect)")
    parser.add_argument("--output-json", default="/tmp/skill-report.json", help="Output JSON report path")
    args = parser.parse_args()

    report = run_checks(args.repo_root, args.locale_dir)

    with open(args.output_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    print(json.dumps(report, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
