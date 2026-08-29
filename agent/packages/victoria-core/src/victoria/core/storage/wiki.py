"""S3 primitives for the wiki (DESIGN §7): list_files, get_file, put_file.

Text helpers (get_file/put_file) are for markdown pages. Byte helpers
(get_bytes/put_bytes) are for search.db, which is binary.
"""

from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from .errors import ConditionalWriteFailedError
from .models import ListFilesResult, PageContent, PageVersion, RawContent


def list_files(bucket: str, prefix: str) -> ListFilesResult:
    return ListFilesResult(paths=_list_keys(bucket, prefix))


def list_pages(bucket: str) -> ListFilesResult:
    """Every markdown page in the wiki. Filters out the binary search.db
    sidecar first — it isn't a WikiPath, so building the result without
    dropping it would fail validation."""
    keys = [key for key in _list_keys(bucket, "") if key.endswith(".md")]

    return ListFilesResult(paths=keys)


def file_exists(bucket: str, key: str) -> bool:
    try:
        _client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return False

        raise


def get_file(bucket: str, key: str) -> PageContent:
    raw = get_bytes(bucket, key)

    return PageContent(path=key, content=raw.content.decode("utf-8"))


def get_file_with_etag(bucket: str, key: str) -> PageVersion:
    raw = get_bytes(bucket, key)

    return PageVersion(path=key, content=raw.content.decode("utf-8"), etag=raw.etag)


def get_bytes(bucket: str, key: str) -> RawContent:
    obj = _client().get_object(Bucket=bucket, Key=key)

    return RawContent(content=obj["Body"].read(), etag=obj["ETag"])


def put_file(bucket: str, key: str, content: str, *, if_match: str | None = None) -> str:
    return put_bytes(
        bucket,
        key,
        content.encode("utf-8"),
        if_match=if_match,
        content_type="text/markdown",
    )


def put_bytes(
    bucket: str,
    key: str,
    content: bytes,
    *,
    if_match: str | None = None,
    content_type: str = "application/octet-stream",
) -> str:
    """Write content to key. If if_match is given, the write only succeeds
    if the object's current ETag matches (S3 conditional writes) — this is
    how a lost update (e.g. a racing remember/consolidate call) fails loudly
    instead of silently corrupting state (DESIGN §6)."""
    kwargs: dict = {
        "Bucket": bucket,
        "Key": key,
        "Body": content,
        "ContentType": content_type,
    }

    if if_match is not None:
        kwargs["IfMatch"] = if_match

    try:
        resp = _client().put_object(**kwargs)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("PreconditionFailed", "412"):
            raise ConditionalWriteFailedError(key) from e

        raise

    return resp["ETag"]


def _list_keys(bucket: str, prefix: str) -> list[str]:
    paginator = _client().get_paginator("list_objects_v2")
    keys: list[str] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])

    return keys


@lru_cache(maxsize=1)
def _client():
    # Lazy + cached: constructing this at import time would bind it to
    # whatever credentials/mocks exist at import, before tests (moto) or
    # Lambda's execution environment are actually ready.
    return boto3.client("s3")
