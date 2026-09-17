#!/usr/bin/env bash
# Build espeak-ng from source at a pinned tag into a prefix and print the
# prefix. Usage: build_espeak_ng.sh <version> <prefix>
set -euo pipefail
version="${1:?espeak-ng version, e.g. 1.52.0}"; prefix="${2:?install prefix}"
src="$(mktemp -d)"
git clone -q --depth 1 -b "$version" https://github.com/espeak-ng/espeak-ng.git "$src/espeak-ng"
cd "$src/espeak-ng"
./autogen.sh >/dev/null
./configure --prefix="$prefix" --with-klatt=no --with-speechplayer=no --with-mbrola=no --with-sonic=no --with-async=no >/dev/null
make -j"$(nproc)" >/dev/null
make install >/dev/null
"$prefix/bin/espeak-ng" --version
