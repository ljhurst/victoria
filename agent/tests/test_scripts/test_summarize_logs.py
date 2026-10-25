import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parents[2] / "scripts" / "summarize_logs.py"
_spec = importlib.util.spec_from_file_location("summarize_logs", _SCRIPT)
summarize_logs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summarize_logs)


def _json(message: str, level: str = "INFO", **fields) -> str:
    return json.dumps({"level": level, "message": message, **fields})


def _export(tmp_path: Path, messages: list[str], name: str = "mcp") -> Path:
    events = [
        {"timestamp": 1_760_000_000_000 + i * 1000, "message": m} for i, m in enumerate(messages)
    ]
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"events": events}))
    return path


def _render(tmp_path: Path, messages: list[str], name: str = "mcp") -> str:
    return summarize_logs.render(summarize_logs.load(_export(tmp_path, messages, name)))


def _stage(stage: str, ms: int, **fields) -> str:
    return _json("stage finished", stage=stage, duration_ms=ms, **fields)


def _report(request_id: str, ms: float, memory: int = 150) -> str:
    return (
        f"REPORT RequestId: {request_id}\tDuration: {ms} ms\tBilled Duration: {int(ms) + 1} ms\t"
        f"Memory Size: 512 MB\tMax Memory Used: {memory} MB\n"
    )


def test_stats_use_nearest_rank_percentiles():
    stats = summarize_logs._stats([40, 10, 100, 20, 30])

    assert (stats.count, stats.p50, stats.p95, stats.max) == (5, 30, 100, 100)


def test_stats_of_one_sample_and_of_none():
    assert summarize_logs._stats([7]) == summarize_logs.Stats(1, 7, 7, 7)
    assert summarize_logs._stats([]) == summarize_logs.Stats(0, 0, 0, 0)


def test_errors_and_warnings_are_grouped_with_reason_and_counted(tmp_path):
    reason = "old_str matched 0 times"
    retry = _json("edits rejected, retrying", level="WARNING", reason=reason)
    output = _render(tmp_path, [retry, retry, _json("boom", level="ERROR")])

    assert "2x WARNING edits rejected, retrying" in output
    assert f"reason: {reason}" in output
    assert "1x ERROR boom" in output
    assert "remember edit retries: 2 (remember failed: 0)" in output


def test_invocations_cold_starts_and_slow_reports(tmp_path):
    messages = [
        "INIT_START Runtime Version: python:3.13",
        "START RequestId: a Version: $LATEST",
        _report("a", 6000.0, memory=200),
        "END RequestId: a",
        "START RequestId: b Version: $LATEST",
        _report("b", 40),
    ]
    output = _render(tmp_path, messages)

    assert "events: 6 (" in output
    assert "invocations: 2, cold starts: 1 (50%)" in output
    assert "max memory used: 200 MB" in output
    assert "invocations over 5000 ms: 1" in output
    assert "6000 ms request a" in output


def test_plain_text_warnings_are_listed_separately_from_json(tmp_path):
    plain = "[WARNING]\t2026-10-25T01:40:35.128Z\tabc\tLasso token rejected: ExpiredSignatureError"
    output = _render(tmp_path, [plain, plain])

    assert "plain-text lines (not JSON):" in output
    assert "2x Lasso token rejected: ExpiredSignatureError" in output


def test_stage_started_lines_are_ignored_and_tool_calls_counted_once(tmp_path):
    started = _json("stage started", stage="tool_call", tool="remember")
    finished = _stage("tool_call", 1200, tool="remember", tool_error=False)
    output = _render(tmp_path, [started, finished, started, finished])

    assert "remember: 2 calls" in output
    assert "0 errors" in output


def test_tool_errors_are_counted(tmp_path):
    failed = _json("stage failed", level="ERROR", stage="tool_call", tool="remember", duration_ms=5)
    output = _render(tmp_path, [_stage("tool_call", 100, tool="remember", tool_error=True), failed])

    assert "remember: 2 calls" in output
    assert "2 errors" in output


def test_slow_requests_are_listed_with_cold_start_flag(tmp_path):
    messages = [
        _stage("request", 20, method="GET", path="/browse/a.md", status=200, cold_start=False),
        _stage("request", 1500, method="GET", path="/browse/b.md", status=307, cold_start=True),
    ]
    output = _render(tmp_path, messages, name="viewer")

    assert "/browse 200: 1" in output
    assert "/browse 307: 1" in output
    assert "/browse/b.md 307 1500 ms cold_start=True" in output
    assert "/browse/a.md 200 20" not in output


def test_empty_export_reports_no_events(tmp_path):
    assert "no events" in _render(tmp_path, [])


@pytest.mark.parametrize("content", ["not json", '{"nope": []}'])
def test_malformed_export_exits_with_a_clear_message(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content)

    with pytest.raises(SystemExit, match="filter-log-events"):
        summarize_logs.load(path)


def test_missing_file_exits_with_a_clear_message(tmp_path):
    with pytest.raises(SystemExit, match="no such file"):
        summarize_logs.load(tmp_path / "missing.json")
