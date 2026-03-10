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
import ast
import importlib
import json
import sys
import time
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]  # Python < 3.11
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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

# Mapping of plugin types to their abstract base classes
ABSTRACT_BASES = {
    "skill": ("ovos_workshop.skills.ovos", "OVOSSkill"),
    "tts": ("ovos_plugin_manager.templates.tts", "TTS"),
    "stt": ("ovos_plugin_manager.templates.stt", "STT"),
    "wake_word": ("ovos_plugin_manager.templates.hotwords", "HotWordEngine"),
    "vad": ("ovos_plugin_manager.templates.vad", "VADEngine"),
    "phal": ("ovos_plugin_manager.templates.phal", "PHALPlugin"),
    "pipeline": ("ovos_plugin_manager.templates.pipeline", "IntentHandlerPlugin"),
    "utterance_transformer": ("ovos_plugin_manager.templates.transformers", "UtteranceTransformer"),
    "tts_transformer": ("ovos_plugin_manager.templates.transformers", "TTSTransformer"),
}


def extract_metadata() -> Dict[str, Any]:
    """
    Extract plugin metadata from pyproject.toml or setup.py.

    Returns dict with keys: name, version, authors, description, homepage, requires_python.
    Missing values are set to None or empty list.
    """
    metadata = {
        "name": None,
        "version": None,
        "authors": [],
        "description": None,
        "homepage": None,
        "requires_python": None,
    }

    # Try pyproject.toml first
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
            project = config.get("project", {})
            metadata["name"] = project.get("name")
            metadata["version"] = project.get("version")
            metadata["description"] = project.get("description")
            metadata["requires_python"] = project.get("requires-python")

            # Extract authors
            authors_list = project.get("authors", [])
            if isinstance(authors_list, list):
                metadata["authors"] = authors_list

            # Extract homepage from URLs
            urls = project.get("urls", {})
            if isinstance(urls, dict):
                metadata["homepage"] = urls.get("homepage") or urls.get("Homepage")

            return metadata
        except Exception:
            pass

    # Try setup.py as fallback
    setup_py = Path("setup.py")
    if setup_py.exists():
        try:
            with open(setup_py) as f:
                content = f.read()
            # Simple extraction using regex (limited fallback)
            import re
            name_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
            if name_match:
                metadata["name"] = name_match.group(1)
            version_match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if version_match:
                metadata["version"] = version_match.group(1)
        except Exception:
            pass

    return metadata


def extract_system_deps() -> List[str]:
    """
    Extract system dependencies from [tool.ovos.build] section in pyproject.toml.

    Returns list of system dependency package names.
    """
    deps = []
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        try:
            with open(pyproject, "rb") as f:
                config = tomllib.load(f)
            tool = config.get("tool", {})
            ovos = tool.get("ovos", {})
            build = ovos.get("build", {})
            deps = build.get("system-dependencies", [])
        except Exception:
            pass
    return deps


def validate_plugin_import(module_path: str, class_name: str) -> Tuple[Optional[bool], Optional[int], Optional[str]]:
    """
    Test if plugin class can be imported and measure import time.

    Returns (ok, time_ms, error):
    - ok: True if import successful, False if failed, None if untested
    - time_ms: import time in milliseconds
    - error: error message if import failed, None otherwise
    """
    try:
        start = time.perf_counter()
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        elapsed = time.perf_counter() - start
        return (True, int(elapsed * 1000), None)
    except ImportError as e:
        return (False, None, f"ImportError: {str(e)}")
    except AttributeError as e:
        return (False, None, f"AttributeError: {str(e)}")
    except Exception as e:
        return (False, None, f"{type(e).__name__}: {str(e)}")


def check_plugin_interface(plugin_cls: Any, short_type: str) -> Tuple[Optional[bool], Optional[str], Optional[str]]:
    """
    Check if plugin class inherits from the correct abstract base.

    Returns (ok, abstract_base_name, error):
    - ok: True if correct, False if incorrect, None if ABC not available
    - abstract_base_name: name of the abstract base (e.g. "OVOSSkill")
    - error: error message if validation couldn't be performed
    """
    if short_type not in ABSTRACT_BASES:
        return (None, None, f"Unknown plugin type: {short_type}")

    module_path, class_name = ABSTRACT_BASES[short_type]
    try:
        abc_module = importlib.import_module(module_path)
        abc_class = getattr(abc_module, class_name)
        is_subclass = issubclass(plugin_cls, abc_class)
        return (is_subclass, class_name, None)
    except (ImportError, AttributeError):
        return (None, class_name, f"Abstract base not available: {module_path}.{class_name}")
    except TypeError as e:
        return (False, class_name, f"TypeError: {str(e)}")


def validate_config_docs(repo_root: str = ".") -> Tuple[bool, List[str], Optional[str]]:
    """
    Check for settingsmeta.json and extract config keys.

    Returns (has_config_docs, config_keys, error):
    - has_config_docs: True if settingsmeta.json found
    - config_keys: list of config key names extracted
    - error: error message if parsing failed
    """
    repo_path = Path(repo_root)
    try:
        # Search for settingsmeta.json anywhere in the repo
        for settingsmeta_path in repo_path.rglob("settingsmeta.json"):
            try:
                with open(settingsmeta_path) as f:
                    config = json.load(f)

                keys = []
                # Try sections.fields format
                sections = config.get("sections", [])
                if sections and isinstance(sections, list):
                    for section in sections:
                        fields = section.get("fields", [])
                        if isinstance(fields, list):
                            for field in fields:
                                if isinstance(field, dict) and "name" in field:
                                    keys.append(field["name"])

                # Try flat fields format
                fields = config.get("fields", [])
                if isinstance(fields, list):
                    for field in fields:
                        if isinstance(field, dict) and "name" in field:
                            keys.append(field["name"])

                if keys or sections or fields:
                    return (True, list(set(keys)), None)  # deduplicate
            except json.JSONDecodeError as e:
                return (True, [], f"JSON parse error in {settingsmeta_path}: {str(e)}")

        return (False, [], None)
    except Exception as e:
        return (False, [], f"Error scanning for settingsmeta.json: {str(e)}")


def collect_issues(result: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Collect validation issues from OPM check result.

    Returns list of dicts with keys: severity, message, check.
    Severity is one of: "error", "warning", "info".
    """
    issues = []

    # Check if OPM found the plugin
    opm_found = result.get("opm_found", {})
    for plugin_type, found in opm_found.items():
        if not found:
            issues.append({
                "severity": "error",
                "message": f"OPM could not detect {plugin_type}",
                "check": "opm_detection"
            })

    # Check import times and results
    validation = result.get("validation", {})
    import_ok = validation.get("import_ok", {})
    import_time_ms = validation.get("import_time_ms", {})

    for plugin_type, ok in import_ok.items():
        if ok is False:
            issues.append({
                "severity": "error",
                "message": f"Could not import plugin class for {plugin_type}",
                "check": "plugin_import"
            })
        elif ok is True and plugin_type in import_time_ms:
            time_val = import_time_ms[plugin_type]
            if time_val and time_val > 500:
                issues.append({
                    "severity": "error",
                    "message": f"Import time for {plugin_type} exceeds 500ms ({time_val}ms)",
                    "check": "import_perf"
                })
            elif time_val and time_val > 200:
                issues.append({
                    "severity": "warning",
                    "message": f"Import time for {plugin_type} is slow ({time_val}ms)",
                    "check": "import_perf"
                })

    # Check interface compliance
    interface_ok = validation.get("interface_ok", {})
    for plugin_type, ok in interface_ok.items():
        if ok is False:
            abstract_base = validation.get("abstract_base", {}).get(plugin_type)
            issues.append({
                "severity": "error",
                "message": f"Plugin for {plugin_type} does not inherit from {abstract_base}",
                "check": "interface_compliance"
            })

    # Check config docs
    if not validation.get("has_config_docs"):
        issues.append({
            "severity": "warning",
            "message": "No settingsmeta.json found",
            "check": "config_docs"
        })

    return issues


def compute_status(issues: List[Dict[str, str]]) -> str:
    """
    Compute overall status from issues list.

    Returns "pass", "warning", or "fail".
    """
    if not issues:
        return "pass"
    has_error = any(issue["severity"] == "error" for issue in issues)
    if has_error:
        return "fail"
    return "warning"


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
    validate_interface: bool = True,
    test_import: bool = True,
    perf_threshold_ms: int = 500,
) -> int:
    """
    Check if a package is detected by ovos-plugin-manager.

    Args:
        plugin_type: "auto" to auto-detect, or specific type (skill, tts, stt, etc)
        entry_point: Expected entry point ID (legacy mode, for skills)
        output_json: Path to write JSON results
        validate_interface: Check that plugin class inherits from correct abstract base
        test_import: Test plugin class importability and measure time
        perf_threshold_ms: Import time threshold for warnings (ms)

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
        "metadata": extract_metadata(),
        "system_deps": extract_system_deps(),
        "validation": {
            "import_ok": {},
            "import_time_ms": {},
            "interface_ok": {},
            "abstract_base": {},
            "has_config_docs": False,
            "config_keys": [],
        },
        "issues": [],
        "status": "pass",
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

    # Step 3b: Check configuration docs
    has_config_docs, config_keys, _ = validate_config_docs()
    result["validation"]["has_config_docs"] = has_config_docs
    result["validation"]["config_keys"] = config_keys

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

    # Step 3c: Validate declared entry points (import test + interface check)
    if test_import or validate_interface:
        pyproject = Path("pyproject.toml")
        if pyproject.exists():
            try:
                with open(pyproject, "rb") as f:
                    config = tomllib.load(f)
                entry_points_cfg = config.get("project", {}).get("entry-points", {})

                for ep_group, entries in entry_points_cfg.items():
                    if not ep_group.startswith("opm."):
                        continue

                    short_type = ep_group.replace("opm.", "")
                    if isinstance(entries, dict):
                        for ep_name, ep_value in entries.items():
                            if ":" not in ep_value:
                                continue
                            module_path, class_name = ep_value.split(":", 1)
                            module_path = module_path.strip()
                            class_name = class_name.split(",")[0].strip()

                            # Test import
                            if test_import:
                                ok, time_ms, error = validate_plugin_import(module_path, class_name)
                                result["validation"]["import_ok"][short_type] = ok
                                if time_ms is not None:
                                    result["validation"]["import_time_ms"][short_type] = time_ms
                                if error and ok is False:
                                    print(f"⚠️  Import failed for {short_type}: {error}", file=sys.stderr)

                                # Validate interface if import was successful
                                if ok and validate_interface:
                                    try:
                                        plugin_cls = getattr(importlib.import_module(module_path), class_name)
                                        iface_ok, abc_name, iface_error = check_plugin_interface(plugin_cls, short_type)
                                        result["validation"]["interface_ok"][short_type] = iface_ok
                                        if abc_name:
                                            result["validation"]["abstract_base"][short_type] = abc_name
                                        if iface_error and iface_ok is not None:
                                            print(f"⚠️  Interface check result for {short_type}: {iface_error}", file=sys.stderr)
                                    except Exception as e:
                                        print(f"⚠️  Could not validate interface for {short_type}: {e}", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Error extracting entry points for validation: {e}", file=sys.stderr)

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

    # Step 5: Collect issues and compute status
    result["issues"] = collect_issues(result)
    result["status"] = compute_status(result["issues"])

    # Step 6: Summarize results
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

    # Step 7: Write JSON output
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
    parser.add_argument(
        "--validate-interface",
        action="store_true",
        default=True,
        help="Check that plugin class inherits from correct abstract base (default: true)"
    )
    parser.add_argument(
        "--no-validate-interface",
        action="store_false",
        dest="validate_interface",
        help="Skip interface compliance check"
    )
    parser.add_argument(
        "--test-import",
        action="store_true",
        default=True,
        help="Test that plugin class is importable (default: true)"
    )
    parser.add_argument(
        "--no-test-import",
        action="store_false",
        dest="test_import",
        help="Skip import test"
    )
    parser.add_argument(
        "--perf-threshold-ms",
        type=int,
        default=500,
        help="Import time threshold for warnings (ms). Default: 500"
    )
    args = parser.parse_args()

    sys.exit(check_opm(
        plugin_type=args.plugin_type,
        entry_point=args.entry_point,
        output_json=args.output_json or None,
        validate_interface=args.validate_interface,
        test_import=args.test_import,
        perf_threshold_ms=args.perf_threshold_ms,
    ))


if __name__ == "__main__":
    main()
