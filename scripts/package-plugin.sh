#!/usr/bin/env bash
set -Eeuo pipefail
root=$(cd -- "$(dirname -- "$0")/.." && pwd -P)
cd -- "$root"
test -f dist/index.js || { echo 'run pnpm build first' >&2; exit 1; }
test -d runtime || { echo 'runtime assets are produced by GitHub Actions' >&2; exit 1; }
if find runtime -type f -name 'dlssnr.bin' -print -quit | grep -q .; then
  echo 'refusing to package NVIDIA model data' >&2; exit 1
fi
mkdir -p release
version=$(node -p "require('./package.json').version")
python3 - "$root" "release/decky-dlssnr-manager-v$version.zip" <<'PY'
import os, sys, zipfile
root, output = map(os.path.abspath, sys.argv[1:])
include = ('dist', 'runtime', 'main.py', 'plugin.json', 'package.json', 'README.md', 'LICENSE', 'THIRD_PARTY.md')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for item in include:
        path = os.path.join(root, item)
        if os.path.isfile(path):
            archive.write(path, item)
        else:
            for directory, _, files in os.walk(path):
                for filename in sorted(files):
                    full = os.path.join(directory, filename)
                    archive.write(full, os.path.relpath(full, root))
PY
