#!/usr/bin/env bash
# Builds agent/dist/victoria.zip: dependencies (resolved for Lambda's
# linux/arm64 runtime via uv, no Docker needed) + src/victoria app code.
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

rm -rf build dist
mkdir -p build/app build/package dist

uv export -q --frozen --no-dev --no-editable --no-emit-project -o build/requirements.txt

uv pip install -q \
  --no-installer-metadata \
  --no-compile-bytecode \
  --python-platform aarch64-manylinux2014 \
  --python 3.13 \
  --target build/package \
  -r build/requirements.txt

rsync -a --exclude='*.pyc' --exclude='__pycache__' --exclude='*.swp' src/victoria build/app/

find build -exec touch -t 202001010000.00 {} +

# Zip app code into a *fresh* archive first, then append dependencies.
# zip's -x excludes only reliably apply when creating an archive, not when
# appending to an existing one (observed with Apple's bundled Info-ZIP 3.0).
(cd build/app && zip -Xrq ../../dist/victoria.zip victoria)
(cd build/package && zip -Xrq ../../dist/victoria.zip .)

rm -rf build

echo "Built $(cd dist && pwd)/victoria.zip"
