#!/usr/bin/env bash
# Builds dist/victoria-mcp.zip: the MCP server's third-party dependencies
# (resolved for Lambda's linux/arm64 runtime via uv, no Docker needed) + the
# first-party src for victoria-mcp and victoria-core.
# See Astral's uv + AWS Lambda guide:
# https://docs.astral.sh/uv/guides/integration/aws-lambda/
#
# Reproducible: every file's mtime is normalized before zipping, and -X
# strips extra fields (extended timestamps, uid/gid) that would otherwise
# still leak the real build time. Without this, source_code_hash changes
# on every rebuild even when nothing actually changed, causing Terraform
# to see drift.
set -euo pipefail

cd "$(dirname "$0")/.."

zip_path="dist/victoria-mcp.zip"
rm -rf build "$zip_path"
mkdir -p build/app build/package dist

uv export -q --frozen --no-dev --no-editable --no-emit-workspace \
  --package victoria-mcp -o build/requirements.txt

uv pip install -q \
  --no-installer-metadata \
  --no-compile-bytecode \
  --python-platform aarch64-manylinux2014 \
  --python 3.13 \
  --target build/package \
  -r build/requirements.txt

for member in victoria-core victoria-mcp; do
  rsync -a --exclude='*.pyc' --exclude='__pycache__' --exclude='*.swp' \
    "packages/${member}/src/victoria" build/app/
done

find build -exec touch -t 202001010000.00 {} +

# Zip app code into a *fresh* archive first, then append dependencies.
# zip's -x excludes only reliably apply when creating an archive, not when
# appending to an existing one (observed with Apple's bundled Info-ZIP 3.0).
(cd build/app && zip -Xrq "../../${zip_path}" victoria)
(cd build/package && zip -Xrq "../../${zip_path}" .)

rm -rf build

echo "Built $(pwd)/${zip_path}"
