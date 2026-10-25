import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from aws_lambda_powertools import Logger

logger = Logger(child=True)


@contextmanager
def timed(stage: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Log a stage's duration, as a `with` block or a decorator on a sync
    function (an async function would time only creating the coroutine).
    The yielded dict collects fields only known once the stage has run, and is
    attached to the closing line."""
    start = time.perf_counter()
    extra: dict[str, Any] = {}
    try:
        yield extra
    except Exception as e:
        logger.error(
            "stage failed",
            stage=stage,
            duration_ms=_elapsed_ms(start),
            error=type(e).__name__,
            **fields,
            **extra,
        )
        raise
    logger.info("stage finished", stage=stage, duration_ms=_elapsed_ms(start), **fields, **extra)


def _elapsed_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)
