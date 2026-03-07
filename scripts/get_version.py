"""Read version string from version.py file (START_VERSION_BLOCK/END_VERSION_BLOCK format)"""
import argparse


def get_version(version_file):
    VERSION_MAJOR = 0
    VERSION_MINOR = 0
    VERSION_BUILD = 0
    VERSION_ALPHA = 0

    with open(version_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith("# END_VERSION_BLOCK"):
                break
            if line.startswith("VERSION_MAJOR"):
                VERSION_MAJOR = int(line.split("=")[-1].strip())
            elif line.startswith("VERSION_MINOR"):
                VERSION_MINOR = int(line.split("=")[-1].strip())
            elif line.startswith("VERSION_BUILD"):
                VERSION_BUILD = int(line.split("=")[-1].strip())
            elif line.startswith("VERSION_ALPHA"):
                VERSION_ALPHA = int(line.split("=")[-1].strip())

    version = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"
    if VERSION_ALPHA:
        version += f"a{VERSION_ALPHA}"
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get version string from version.py file')
    parser.add_argument('--version-file', required=True, help='Path to version.py file')
    args = parser.parse_args()
    print(get_version(args.version_file))