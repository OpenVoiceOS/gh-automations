#!/usr/bin/env python3
"""
Aggregate Python version compatibility results from multiple matrix jobs.

Reads a directory of result files (one per Python version and mode) and produces
a Markdown table for the PR comment.

Expected result files:
    results/3.8-regular.txt  -> "success", "failure", or "opm_failure"
    results/3.11-editable.txt -> "success", "failure", or "opm_failure"

Usage:
    python aggregate_python_results.py --results-dir ./results --output /tmp/report.md
"""
import argparse
import os
import sys

# Mapping status -> status icon
ICONS = {
    "success": "✅",
    "failure": "❌",
    "opm_failure": "🔶",  # OPM detection failed but install succeeded
    "skipped": "⚪",
    "unknown": "❓"
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, help="Directory containing result files")
    parser.add_argument("--output", required=True, help="Path to write the Markdown report")
    parser.add_argument("--versions", default="3.8,3.9,3.10,3.11,3.12", help="Comma-separated list of expected versions")
    parser.add_argument("--modes", default="regular,editable", help="Comma-separated list of expected modes")
    args = parser.parse_args()

    expected_versions = [v.strip() for v in args.versions.split(",")]
    expected_modes = [m.strip() for v in args.modes.split(",") for m in [v]] # fix splitting logic
    # Re-eval splitting logic for modes
    expected_modes = [m.strip() for m in args.modes.split(",")]
    
    results = {}

    if not os.path.exists(args.results_dir):
        print(f"Results directory '{args.results_dir}' not found.", file=sys.stderr)
        with open(args.output, "w") as f:
            f.write("⚠️ Python compatibility data unavailable.")
        return

    for version in expected_versions:
        for mode in expected_modes:
            key = f"{version}-{mode}"
            path = os.path.join(args.results_dir, f"{key}.txt")
            if os.path.exists(path):
                with open(path, "r") as f:
                    results[key] = f.read().strip().lower()
            else:
                # Try subdirs (artifact download pattern)
                sub_path = os.path.join(args.results_dir, f"python-result-{key}", f"{key}.txt")
                if os.path.exists(sub_path):
                    with open(sub_path, "r") as f:
                        results[key] = f.read().strip().lower()
                else:
                    results[key] = "unknown"

    # Format the report
    lines = []
    lines.append("🐍 **Python Support Matrix**")
    lines.append("")
    
    # Table header: | Mode | 3.8 | 3.9 | 3.10 | 3.11 | 3.12 |
    header = "| Mode | " + " | ".join(expected_versions) + " |"
    lines.append(header)
    
    separator = "|:---| " + " | ".join([":-:"] * len(expected_versions)) + " |"
    lines.append(separator)
    
    for mode in expected_modes:
        mode_label = mode.capitalize()
        row_icons = []
        for version in expected_versions:
            status = results.get(f"{version}-{mode}", "unknown")
            row_icons.append(ICONS.get(status, ICONS["unknown"]))
        lines.append(f"| {mode_label} | " + " | ".join(row_icons) + " |")
    
    lines.append("")
    
    # Legend/Notes
    has_failure = any(r == "failure" for r in results.values())
    has_opm_failure = any(r == "opm_failure" for r in results.values())
    
    if has_failure or has_opm_failure:
        lines.append("---")
        if has_failure:
            lines.append("❌ Installation failed.")
        if has_opm_failure:
            lines.append("🔶 Installation succeeded, but `ovos-plugin-manager` did not detect the entry point.")
        lines.append("Check job logs for details.")

    with open(args.output, "w") as f:
        f.write("\n".join(lines))

    print(f"Report written to {args.output}")

if __name__ == "__main__":
    main()
