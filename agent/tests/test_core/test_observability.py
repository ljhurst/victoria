from unittest.mock import patch

import pytest

from victoria.core import observability


def test_timed_logs_one_finished_line_with_duration_and_extra_fields():
    with (
        patch.object(observability, "logger") as logger,
        observability.timed("work", path="a.md") as extra,
    ):
        extra["tokens"] = 7

    (finished,) = logger.info.call_args_list
    assert finished.args == ("stage finished",)
    assert finished.kwargs["stage"] == "work"
    assert finished.kwargs["path"] == "a.md"
    assert finished.kwargs["tokens"] == 7
    assert isinstance(finished.kwargs["duration_ms"], int)
    logger.error.assert_not_called()


def test_timed_logs_failure_with_error_name_and_reraises():
    with (
        patch.object(observability, "logger") as logger,
        pytest.raises(ValueError, match="boom"),
        observability.timed("work") as extra,
    ):
        extra["partial"] = True
        raise ValueError("boom")

    logger.info.assert_not_called()
    (failed,) = logger.error.call_args_list
    assert failed.args == ("stage failed",)
    assert failed.kwargs["stage"] == "work"
    assert failed.kwargs["error"] == "ValueError"
    assert failed.kwargs["partial"] is True
    assert isinstance(failed.kwargs["duration_ms"], int)


def test_timed_works_as_a_decorator_and_logs_every_call():
    @observability.timed("work", kind="decorated")
    def double(x: int) -> int:
        return x * 2

    with patch.object(observability, "logger") as logger:
        assert [double(2), double(3)] == [4, 6]

    finished = [c.kwargs for c in logger.info.call_args_list if c.args == ("stage finished",)]
    assert [f["stage"] for f in finished] == ["work", "work"]
    assert all(f["kind"] == "decorated" for f in finished)
