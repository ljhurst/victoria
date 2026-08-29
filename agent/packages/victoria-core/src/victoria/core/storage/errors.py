class ConditionalWriteFailedError(Exception):
    """An If-Match conditional write lost a race (DESIGN §6 concurrency)."""

    def __init__(self, key: str) -> None:
        super().__init__(f"conditional write to {key!r} failed: object changed underneath it")
        self.key = key
