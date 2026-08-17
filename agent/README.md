# victoria-agent

Personal admin agent — Lambda MCP server + wiki over S3. See `docs/DESIGN.md`
at the repo root for the full design.

## Building the Lambda package

```
./scripts/build_lambda.sh
```

Produces `dist/victoria.zip`: dependencies resolved for Lambda's
`linux/arm64` runtime via `uv` (no Docker needed — see
[Astral's uv + AWS Lambda guide](https://docs.astral.sh/uv/guides/integration/aws-lambda/))
plus `src/victoria` at the zip root.

Re-run this before any `terraform apply` (from `infra/`) that changes
`agent/` code or dependencies — `infra/terraform.tfvars`'s
`lambda_package_path` points at this script's output, and Terraform only
redeploys the Lambda's code when that file's hash changes.
