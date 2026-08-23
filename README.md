# Victoria

```text
             /\
            /  \
           /____\
      /\   |    |
     /  \  | [] |
    /____\ |    |
    |    | |____|
    | [] |_|  []|
    |____|_|____|
    |  | .|  |[]|
    |__|__|__|__|
```

A personal knowledge base, inspired by my home.

## Table of Contents

- [Features](#features)
- [Repo Structure](#repo-structure)
- [Connect](#connect)
- [Requirements](#requirements)
- [Deployment](#deployment)

## Features

- Remember important information about your home or anything else
 - What tools are in my workshop?
 - What plants are in my garden?
- Search memories for highest quality context
- Consolidate, prune, clean, and organize memories

See the example [use cases](docs/USE_CASES.md).

## Repo structure

- [`docs/`](docs/) - Technical documentation
- [`agent/`](agent/) — the Python Lambda package (MCP server + wiki logic)
- [`infra/`](infra/) — Terraform for the AWS resources (S3, Lambda, IAM, SSM)
- [`seed/`](seed/) — bootstrap content uploaded to the wiki root on first deploy

## Connect

The MCP server is an AWS Lambda that lives at

```text
https://diozeathy56roah5fxesmhji640ugrkn.lambda-url.us-east-1.on.aws/mcp
```

You can connect with the [MCP Inspector](https://modelcontextprotocol.io/docs/2026-07-28/tools/inspector)

```bash
npx @modelcontextprotocol/inspector@latest
```

Auth is provided by [Lasso](https://github.com/ljhurst/lasso), my self hosted SSO.

Simply set the Client ID under OAuth Settings and the OAuth dance will take care of the rest

```text
mcp-inspector
```

You'll see these available tools

- `list_files`: List all raw files under a prefix 
- `get_file`: Get raw file content
- `search_wiki`: Retrieve relevant snippets
- `remember`: Store a fact in the knowledge base
- `consolidate`: Combine, split, and prune memories

## Architecture

This project want's to make a useful, dynamic knowledge base for the lowest possible
cost. To do that it

- Runs an MCP server as a stateless Lambda
- Stores the knowledge base raw files in S3
- Does searches on the fly, no long running vector database

See the full [design](DESIGN.md) for details.

## Requirements

- [`uv`](https://docs.astral.sh/uv/) — Python dependency management and the Lambda build
- [`pre-commit`](https://pre-commit.com/) — run `pre-commit install` once; hooks cover ruff, yamllint, and terraform fmt/validate
- [`awscli`](https://aws.amazon.com/cli/) - Run AWS commands
- [`terraform`](https://developer.hashicorp.com/terraform/install) - Manage infrastructure

## Deployment

We use Lambda zip + [Terraform](https://developer.hashicorp.com/terraform) to manage infra. First create the Lambda src zip

```bash
./agent/scripts/build_lambda.sh
```

Log in via AWS SSO and assume the `victoria-deploy` role

```bash
aws sso login --profile victoria-deploy
```

Set the AWS profile

```bash
export AWS_PROFILE=victoria-deploy
```

Then from `infra/`

```bash
terraform plan
```

And

```bash
terraform apply
```
