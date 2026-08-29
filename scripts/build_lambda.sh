#!/usr/bin/env bash
# Builds dist/victoria-<target>.zip for one workspace member: its third-party
# dependencies (resolved for Lambda's linux/arm64 runtime via uv, no Docker
# needed) + the first-party src for that member and victoria-core.
# See Astral's uv + AWS Lambda guide:
# https://docs.astral.sh/uv/guides/integration/aws-lambda/
#
# Usage: build_lambda.sh mcp | viewer
#
# Reproducible: every file's mtime is normalized before zipping, and -X
# strips extra fields (extended timestamps, uid/gid) that would otherwise
# still leak the real build time. Without this, source_code_hash changes
# on every rebuild even when nothing actually changed, causing Terraform
# to see drift.
set -euo pipefail

target="${1:-}"
case "$target" in
  mcp)    member=victoria-mcp;    src_members=(victoria-core victoria-mcp) ;;
  viewer) member=victoria-viewer; src_members=(victoria-core victoria-viewer) ;;
  *) echo "usage: $0 mcp|viewer" >&2; exit 2 ;;
esac

cd "$(dirname "$0")/../agent"

zip_path="dist/victoria-${target}.zip"
rm -rf build "$zip_path"
mkdir -p build/app build/package dist

uv export -q --frozen --no-dev --no-editable --no-emit-workspace \
  --package "$member" -o build/requirements.txt

uv pip install -q \
  --no-installer-metadata \
  --no-compile-bytecode \
  --python-platform aarch64-manylinux2014 \
  --python 3.13 \
  --target build/package \
  -r build/requirements.txt

for m in "${src_members[@]}"; do
  rsync -a --exclude='*.pyc' --exclude='__pycache__' --exclude='*.swp' \
    "packages/${m}/src/victoria" build/app/
done

find build -exec touch -t 202001010000.00 {} +

# Zip app code into a *fresh* archive first, then append dependencies.
# zip's -x excludes only reliably apply when creating an archive, not when
# appending to an existing one (observed with Apple's bundled Info-ZIP 3.0).
(cd build/app && zip -Xrq "../../${zip_path}" victoria)
(cd build/package && zip -Xrq "../../${zip_path}" .)

rm -rf build

echo "Built $(pwd)/${zip_path}"
