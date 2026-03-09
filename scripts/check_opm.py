#!/usr/bin/env python3
"""
Verify that the skill is correctly detected by ovos-plugin-manager.

Usage:
    python check_opm.py --entry-point "ovos-skill-confucius-quotes.openvoiceos"
"""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-point", required=True, help="The expected skill entry point ID")
    args = parser.parse_args()

    try:
        from ovos_plugin_manager.skills import find_skill_plugins
        plugins = find_skill_plugins()
        if args.entry_point in plugins:
            print(f"✅ Skill '{args.entry_point}' detected by ovos-plugin-manager.")
            sys.exit(0)
        else:
            print(f"❌ Skill '{args.entry_point}' NOT detected by ovos-plugin-manager.")
            print(f"Available plugins: {list(plugins.keys())}")
            sys.exit(1)
    except ImportError:
        print("❌ ovos-plugin-manager not installed.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error checking ovos-plugin-manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
