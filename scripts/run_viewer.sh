#!/usr/bin/env bash
# Run the wiki viewer locally against the real S3 wiki. Needs AWS creds with
# read access to the bucket (e.g. `aws sso login --profile victoria-deploy`
# then `export AWS_PROFILE=victoria-deploy`).
#
# The Lasso `victoria-viewer` client must have http://localhost:8000/auth/callback
# registered as a redirect URI, and your Lasso user needs the victoria:read role.
set -euo pipefail

cd "$(dirname "$0")/../agent"

export WIKI_BUCKET="${WIKI_BUCKET:-lj-victoria-wiki}"
export LASSO_ISSUER_URL="${LASSO_ISSUER_URL:-https://zzspanxrc7v4tvou4acvdq36oi0yjdrz.lambda-url.us-east-1.on.aws/}"
export VIEWER_BASE_URL="${VIEWER_BASE_URL:-http://localhost:8000}"
# Local redirect stays on localhost, but the token is audience-bound to the
# deployed viewer URL — the resource indicator actually registered in Lasso.
export VIEWER_RESOURCE_URL="${VIEWER_RESOURCE_URL:-https://s4wndhtrbjoflmoqeb4zvvmeim0cyodv.lambda-url.us-east-1.on.aws/}"
export VIEWER_SESSION_SECRET="${VIEWER_SESSION_SECRET:-local-dev-not-secret}"

exec uv run --package victoria-viewer uvicorn victoria.viewer.app:build_app \
  --factory --reload --port 8000
