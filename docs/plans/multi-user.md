# Multi-user Victoria

Give each friend their own private wiki under `users/<sub>/` in the existing
bucket, keyed by the `sub` claim of their Lasso token. Cap what they can spend
on the shared Anthropic key. Three PRs; the first changes nothing for the
current single user.

## Decision for Luke

Can Lasso create accounts for friends (open sign-up, invite, or manual)? PR 3
depends on the answer; PRs 1 and 2 do not.

## Today

- `handlers.py` passes one global `wiki_bucket` string into every `wiki.*` and
  `search_index.*` call; there is no notion of whose wiki it is.
- `LassoTokenValidator` already verifies tokens and returns `sub`, but nothing
  reads it.
- The Anthropic API key is a single SSM parameter shared by `remember` and
  `consolidate`.
- The viewer reads the bucket root.

## Design

- **Identity** comes only from the verified token's `sub`, read inside the
  handler. Never from a tool argument or model output.
- **Tenant-scoped type.** `Wiki(bucket, prefix)` replaces the bare `bucket: str`
  threaded through `core`. Keys inside `core` stay relative
  (`wiki/house/x.md`); the prefix is applied in one place. Paths containing
  `..` or starting with `/` are rejected at that boundary.
- **Layout.** `users/<sub>/{CONVENTIONS.md,index.md,log.md,search.db,wiki/}`.
  `search.db` and conditional writes already work per object, so they work per
  user unchanged.
- **First use.** An unknown `sub` gets `seed/` copied into its prefix.
- **Isolation level.** App-level prefix enforcement. IAM-level isolation
  (per-request STS session tags) is deferred until Victoria is opened beyond
  people Luke knows.
- **Cost.** Allowlist of subs, a spend limit on the Anthropic workspace, and a
  per-user daily cap on `remember` and `consolidate` (`consolidate` is the
  multi-step loop and the one to watch).
- **Privacy.** The operator can read all buckets; friends are told so.

## PRs

### 1. Tenant-scoped storage (behaviour-preserving)

- Add `Wiki` to `core/storage`; migrate `wiki.py`, `search_index.py`,
  `remember.py`, `consolidate.py`, and `pages/` helpers to take it.
- Handlers build `Wiki` from a single `current_wiki()` that, for now, returns
  the existing root with an empty prefix.
- Tests: path-traversal rejection; every operation under a non-empty prefix
  writes and reads only inside it (including the `remember` branch that links
  into a non-empty index, and `search.db`).

### 2. Per-user wikis

- `current_wiki()` derives the prefix from the token `sub`; reject tokens
  without one.
- Bootstrap from `seed/` on first use; one-off `aws s3 mv` moves the existing
  wiki to Luke's prefix.
- Viewer maps its session's `sub` to the same prefix.
- Tests: two subs cannot see each other's pages through list, get, search, or
  the viewer.

### 3. Quotas and onboarding

- Allowlist and per-user daily caps on LLM-backed tools; counter in S3 or
  DynamoDB.
- Onboarding doc: Lasso account, connector URL, privacy note.
- Depends on the Lasso answer above.

## Rollout safety

- PR 1 ships with an empty prefix, so production keys are unchanged.
- Before PR 2 deploys, copy the bucket (versioning is on, plus a manual
  `s3 sync` backup) and run the move in a window when no one is using it.
- Roll back PR 2 by redeploying PR 1's Lambda and moving the prefix back.
