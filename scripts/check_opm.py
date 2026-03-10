#!/usr/bin/env python3
"""
Verify that a package is correctly detected by ovos-plugin-manager.

Supports auto-detection of plugin type from pyproject.toml or setup.py entry points.
Can validate any OVOS plugin type (skill, tts, stt, wake_word, etc).

Usage:
    python check_opm.py --plugin-type auto --output-json /tmp/opm.json
    python check_opm.py --plugin-type skill --entry-point "ovos-skill-confucius-quotes"
    python check_opm.py --plugin-type tts (auto-detects from entry_points)
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Mapping of plugin type names to ovos-plugin-manager finder functions
PLUGIN_TYPE_FINDERS = {
    "skill": "ovos_plugin_manager.skills:find_skill_plugins",
    "tts": "ovos_plugin_manager.tts:find_tts_plugins",
    "stt": "ovos_plugin_manager.stt:find_stt_plugins",
    "wake_word": "ovos_plugin_manager.wakewords:find_wake_word_plugins",
    "vad": "ovos_plugin_manager.vad:find_vad_plugins",
    "phal": "ovos_plugin_manager.phal:find_phal_plugins",
    "pipeline": "ovos_plugin_manager.pipeline:find_pipeline_plugins",
    "utterance_transformer": "ovos_plugin_manager.transformers:find_utterance_transformer_plugins",
    "tts_transformer": "ovos_plugin_manager.transformers:find_tts_transformer_plugins",
}


def auto_detect_plugin_types() -> List[str]:
    """
    Auto-detect plugin types by scanning pyproject.toml or setup.py entry points.

    Returns list of detected OVOS plugin types (e.g., ['opm.skill', 'opm.tts']).
    """
    detected = []

    # Try pyproject.toml first
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
            entry_points = config.get("project", {}).get("entry-points", {})
            for group in entry_points.keys():
                if group.startswith("opm."):
                    detected.append(group)
        except Exception as e:
            print(f"Warning: Could not parse pyproject.toml: {e}", file=sys.stderr)

    # Try setup.py as fallback
    if not detected:
        setup_py = Path("setup.py")
        if setup_py.exists():
            try:
                import ast
                with open(setup_py) as f:
                    tree = ast.parse(f.read())

                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Look for setup(...) or setuptools.setup(...)
                        if hasattr(node.func, "id") and node.func.id == "setup":
                            # Find entry_points keyword argument
                            for keyword in node.keywords:
                                if keyword.arg == "entry_points":
                                    # Parse the dict
                                    if isinstance(keyword.value, ast.Dict):
                                        for k in keyword.value.keys:
                                            if isinstance(k, ast.Constant):
                                                if str(k.value).startswith("opm."):
                                                    detected.append(str(k.value))
            except Exception as e:
                print(f"Warning: Could not parse setup.py: {e}", file=sys.stderr)

    return detected


def find_plugin_class(plugin_type: str, entry_point_name: str) -> Optional[str]:
    """
    Extract the plugin class name from an entry point string.
    E.g., 'my-tts-plugin = mypackage.tts:MyTTSPlugin' -> 'MyTTSPlugin'
    """
    if ":" in entry_point_name:
        return entry_point_name.split(":")[-1].split(",")[0].strip()
    return None


def check_opm(
    plugin_type: str = "auto",
    entry_point: Optional[str] = None,
    output_json: Optional[str] = None,
) -> int:
    """
    Check if a package is detected by ovos-plugin-manager.

    Args:
        plugin_type: "auto" to auto-detect, or specific type (skill, tts, stt, etc)
        entry_point: Expected entry point ID (legacy mode, for skills)
        output_json: Path to write JSON results

    Returns:
        0 if detected, 1 if not detected or error
    """
    result = {
        "detected_types": [],
        "entry_points": {},
        "opm_found": {},
        "plugin_classes": {},
        "is_ovos_plugin": False,
        "summary": "",
    }

    # Step 1: Auto-detect plugin types if requested
    if plugin_type == "auto":
        result["detected_types"] = auto_detect_plugin_types()
        if not result["detected_types"]:
            result["summary"] = "Not an OVOS plugin — no opm.* entry points found"
            result["is_ovos_plugin"] = False

            if output_json:
                with open(output_json, "w") as f:
                    json.dump(result, f, indent=2)
            print(result["summary"])
            return 0  # Not an error, just not a plugin

        plugin_types_to_check = [t.replace("opm.", "") for t in result["detected_types"]]
    else:
        plugin_types_to_check = [plugin_type]

    # Step 2: Load entry points from pyproject.toml/setup.py
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
            entry_points = config.get("project", {}).get("entry-points", {})
            for group, entries in entry_points.items():
                if group.startswith("opm."):
                    result["entry_points"][group] = list(entries.keys()) if isinstance(entries, dict) else entries
        except Exception:
            pass

    # Step 3: Check if OPM can find each plugin type
    try:
        import ovos_plugin_manager
    except ImportError:
        result["summary"] = "❌ ovos-plugin-manager not installed"
        if output_json:
            with open(output_json, "w") as f:
                json.dump(result, f, indent=2)
        print(result["summary"])
        return 1

    found_any = False
    for ptype in plugin_types_to_check:
        full_type = f"opm.{ptype}" if not ptype.startswith("opm.") else ptype
        short_type = ptype.replace("opm.", "")

        try:
            # Dynamically import the finder function
            module_path, func_name = PLUGIN_TYPE_FINDERS.get(short_type, "").split(":")
            if not module_path:
                print(f"⚠️  Unknown plugin type: {short_type}", file=sys.stderr)
                continue

            module = __import__(module_path, fromlist=[func_name])
            finder = getattr(module, func_name)
            plugins = finder()

            result["opm_found"][full_type] = bool(plugins)
            found_any = bool(plugins) or found_any

            # Extract first plugin class if available
            if plugins:
                first_plugin = list(plugins.items())[0] if plugins else None
                if first_plugin and len(first_plugin) > 1:
                    result["plugin_classes"][full_type] = first_plugin[1].__class__.__name__
        except Exception as e:
            print(f"⚠️  Error checking {short_type}: {e}", file=sys.stderr)
            result["opm_found"][full_type] = False

    # Step 4: Legacy entry_point support (backward compatibility)
    if entry_point:
        try:
            from ovos_plugin_manager.skills import find_skill_plugins
            plugins = find_skill_plugins()
            if entry_point in plugins:
                print(f"✅ Skill '{entry_point}' detected by ovos-plugin-manager.")
                result["is_ovos_plugin"] = True
                result["summary"] = f"Skill: {entry_point} (found by OPM)"
                if output_json:
                    with open(output_json, "w") as f:
                        json.dump(result, f, indent=2)
                return 0
            else:
                print(f"❌ Skill '{entry_point}' NOT detected by ovos-plugin-manager.")
                if output_json:
                    with open(output_json, "w") as f:
                        json.dump(result, f, indent=2)
                return 1
        except Exception:
            pass

    # Step 5: Summarize results
    if result["detected_types"]:
        result["is_ovos_plugin"] = True
        types_summary = ", ".join([t.replace("opm.", "") for t in result["detected_types"]])
        result["summary"] = f"✅ OVOS plugin detected: {types_summary}"
        exit_code = 0
    elif found_any:
        result["is_ovos_plugin"] = True
        found_types = [t for t, found in result["opm_found"].items() if found]
        result["summary"] = f"✅ OVOS plugin(s) found by OPM: {', '.join(found_types)}"
        exit_code = 0
    else:
        result["is_ovos_plugin"] = False
        result["summary"] = "ℹ️ Not an OVOS plugin or detection failed"
        exit_code = 1 if entry_point else 0

    print(result["summary"])

    # Step 6: Write JSON output
    if output_json:
        with open(output_json, "w") as f:
            json.dump(result, f, indent=2)

    return exit_code


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--plugin-type",
        default="auto",
        help="Plugin type to check (auto, skill, tts, stt, wake_word, vad, phal, pipeline, etc). Default: auto-detect"
    )
    parser.add_argument(
        "--entry-point",
        default="",
        help="[Legacy] Expected skill entry point ID for backward compatibility"
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Path to write JSON results for workflow consumption"
    )
    args = parser.parse_args()

    sys.exit(check_opm(
        plugin_type=args.plugin_type,
        entry_point=args.entry_point,
        output_json=args.output_json or None,
    ))


if __name__ == "__main__":
    main()
