#!/usr/bin/env python3
"""Format a TTS-intelligibility pytest json-report into a markdown table.

The per-plugin end2end test prints one ``::TTS-INTELLIGIBILITY:: {json}`` marker
per scored run (a JSON-encoded ``IntelligibilityReport.to_dict()``). This script
scrapes those markers from the captured stdout of a pytest ``--json-report`` file
(and, as a fallback, from a raw log), then renders a per-(voice, lang) WER/CER
table to an output file for posting to the OVOS PR Checks comment.

It never raises on missing/garbled input — a placeholder section is written so
the PR comment step always has something to post.

Usage:
    format_tts_intel.py --json /tmp/tts-results.json --out /tmp/tts-section.md \
        [--log /tmp/tts-stdout.txt] [--max-wer 1.0]
"""

import argparse
import ast
import json
import re
import sys
from typing import List, Optional

MARKER = "::TTS-INTELLIGIBILITY::"
MARKER_RE = re.compile(re.escape(MARKER) + r"\s*(\{.*\})")


def _parse_marker(blob: str) -> Optional[dict]:
    """Parse a marker payload as JSON, falling back to a Python dict literal.

    Older test files emitted ``str(report.to_dict())`` (a Python repr with single
    quotes / ``None`` / ``True``) which is not valid JSON, so ``ast.literal_eval``
    is used as a fallback to keep their scores visible.
    """
    try:
        obj = json.loads(blob)
    except (ValueError, TypeError):
        try:
            obj = ast.literal_eval(blob)
        except (ValueError, SyntaxError, TypeError):
            return None
    return obj if isinstance(obj, dict) else None


def _scrape_text(text: str) -> List[dict]:
    """Extract all marker-tagged report dicts from a blob of text."""
    reports = []
    for line in text.splitlines():
        m = MARKER_RE.search(line)
        if not m:
            continue
        obj = _parse_marker(m.group(1))
        if obj is not None:
            reports.append(obj)
    return reports


def _iter_test_stdout(data: dict) -> str:
    """Concatenate captured stdout/longrepr across all tests in a json-report."""
    chunks = []
    for t in data.get("tests", []):
        for phase in ("setup", "call", "teardown"):
            sect = t.get(phase)
            if isinstance(sect, dict):
                for key in ("stdout", "longrepr", "stderr"):
                    val = sect.get(key)
                    if isinstance(val, str):
                        chunks.append(val)
        # pytest-json-report may also stash captured output here
        for key in ("stdout", "stderr"):
            val = t.get(key)
            if isinstance(val, str):
                chunks.append(val)
    return "\n".join(chunks)


def collect_reports(json_path: Optional[str],
                    log_path: Optional[str]) -> "tuple[List[dict], Optional[dict]]":
    """Collect intelligibility report dicts and the json summary, if any."""
    reports: List[dict] = []
    summary = None

    if json_path:
        try:
            with open(json_path) as f:
                data = json.load(f)
            summary = data.get("summary")
            reports.extend(_scrape_text(_iter_test_stdout(data)))
            # The json-report top-level may also carry captured stdout.
            top = data.get("stdout") or data.get("captured_stdout")
            if isinstance(top, str):
                reports.extend(_scrape_text(top))
        except (FileNotFoundError, ValueError):
            pass

    if log_path:
        try:
            with open(log_path) as f:
                reports.extend(_scrape_text(f.read()))
        except FileNotFoundError:
            pass

    # Deduplicate on (voice, lang, mode, n) — markers may appear in both sources.
    seen = set()
    unique = []
    for r in reports:
        key = (r.get("voice"), r.get("lang"), r.get("mode"), r.get("n_utterances"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return unique, summary


def render(reports: List[dict], summary: Optional[dict], max_wer: float) -> str:
    """Render the markdown section."""
    lines: List[str] = []

    if summary:
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        errored = summary.get("error", 0)
        skipped = summary.get("skipped", 0)
        all_ok = failed == 0 and errored == 0
        icon = "✅" if all_ok else "❌"
        parts = [f"**{passed}/{total}** passed"]
        if failed:
            parts.append(f"**{failed}** failed")
        if errored:
            parts.append(f"**{errored}** error{'s' if errored != 1 else ''}")
        if skipped:
            parts.append(f"{skipped} skipped")
        lines.append(f"{icon} {', '.join(parts)}")
        lines.append("")

    if not reports:
        lines.append("⚠️ No intelligibility scores reported "
                     f"(looked for `{MARKER}` markers).")
        return "\n".join(lines)

    lines.append(f"Reference STT: faster-whisper `tiny`. "
                 f"Report-only threshold `TTS_MAX_WER={max_wer:g}`. "
                 "Lower WER/CER is better.")
    lines.append("")
    lines.append("| Voice | Lang | Mean WER | Mean CER | Utterances |")
    lines.append("|-------|------|----------|----------|------------|")

    worst = 0.0
    for r in sorted(reports, key=lambda x: (str(x.get("voice")), str(x.get("lang")))):
        voice = r.get("voice") or "default"
        lang = r.get("lang", "?")
        wer = float(r.get("mean_wer", 0.0))
        cer = float(r.get("mean_cer", 0.0))
        n = r.get("n_utterances", len(r.get("scores", [])))
        worst = max(worst, wer)
        flag = " ⚠️" if wer > max_wer else ""
        lines.append(f"| {voice} | {lang} | {wer:.3f}{flag} | {cer:.3f} | {n} |")

    lines.append("")
    if worst > max_wer:
        lines.append(f"⚠️ Worst mean WER `{worst:.3f}` exceeds `TTS_MAX_WER={max_wer:g}`.")
    else:
        lines.append(f"✅ All voices within `TTS_MAX_WER={max_wer:g}` "
                     f"(worst mean WER `{worst:.3f}`).")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", dest="json_path", default=None,
                    help="Path to the pytest --json-report file")
    ap.add_argument("--log", dest="log_path", default=None,
                    help="Optional raw stdout log to scrape markers from")
    ap.add_argument("--out", required=True, help="Output markdown file")
    ap.add_argument("--max-wer", type=float, default=1.0,
                    help="Report-only WER threshold for flagging (default 1.0)")
    args = ap.parse_args(argv)

    reports, summary = collect_reports(args.json_path, args.log_path)
    md = render(reports, summary, args.max_wer)
    with open(args.out, "w") as f:
        f.write(md)
    print(f"Wrote {args.out} ({len(reports)} report(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
