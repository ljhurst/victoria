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

A learning project: a hosted, always-available agent that acts as admin for
two domains — house (tool inventory, "can I do this project," manuals) and
business/LLC (tax categories, hours worked, filings). Reachable from
anywhere via Claude mobile app as an MCP server; low cost is a hard
constraint throughout. See [`docs/DESIGN.md`](docs/DESIGN.md) for the full
design.

## Repo structure

- [`docs/`](docs/)
  - [`docs/DESIGN.md`](docs/DESIGN.md) — architecture and design decisions
  - [`docs/USE_CASES.md`](docs/USE_CASES.md) — the user stories the design is built around
- [`agent/`](agent/) — the Python Lambda package (MCP server + wiki logic)
- [`infra/`](infra/) — Terraform for the AWS resources (S3, Lambda, IAM, SSM)
- [`seed/`](seed/) — bootstrap content uploaded to the wiki root on first deploy

## Requirements

- [`uv`](https://docs.astral.sh/uv/) — Python dependency management and the Lambda build
- [`pre-commit`](https://pre-commit.com/) — run `pre-commit install` once; hooks cover ruff, yamllint, and terraform fmt/validate
