"""Summarize CloudWatch log exports from the victoria Lambdas.

Usage: python3 -I summarize_logs.py <filter-log-events.json> [<more.json> ...]

Each input is the output of `aws logs filter-log-events --output json`. The
log group name is taken from the file name.
"""

import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SLOW_INVOCATION_MS = 5000
SLOW_REQUEST_MS = 1000

_REPORT = re.compile(
    r"REPORT RequestId: (?P<id>\S+)\s+Duration: (?P<duration>[\d.]+) ms"
    r".*?Max Memory Used: (?P<memory>\d+) MB"
)
_PLAIN_LEVEL = re.compile(r"^\[(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\]\t")


@dataclass(frozen=True)
class Event:
    time: datetime
    level: str
    message: str
    request_id: str | None
    fields: dict[str, Any]


@dataclass(frozen=True)
class Report:
    time: datetime
    request_id: str
    duration_ms: float
    memory_mb: int


@dataclass(frozen=True)
class PlainLine:
    time: datetime
    level: str
    text: str


@dataclass(frozen=True)
class Export:
    name: str
    events: list[Event]
    reports: list[Report]
    plain_lines: list[PlainLine]
    event_count: int
    starts: int
    inits: int
    total_bytes: int


@dataclass(frozen=True)
class Stats:
    count: int
    p50: float
    p95: float
    max: float


def main(paths: list[str]) -> None:
    if not paths:
        raise SystemExit("usage: summarize_logs.py <filter-log-events.json> [...]")
    for path in paths:
        print(render(load(Path(path))))


def load(path: Path) -> Export:
    try:
        raw = json.loads(path.read_text())
        raw_events = raw["events"]
    except FileNotFoundError:
        raise SystemExit(f"{path}: no such file") from None
    except (json.JSONDecodeError, KeyError, TypeError):
        raise SystemExit(f"{path}: not the JSON output of `aws logs filter-log-events`") from None

    events: list[Event] = []
    reports: list[Report] = []
    plain_lines: list[PlainLine] = []
    starts = inits = total_bytes = 0
    for raw_event in raw_events:
        message = raw_event["message"].rstrip("\n")
        time = datetime.fromtimestamp(raw_event["timestamp"] / 1000, tz=UTC)
        total_bytes += len(message)
        if message.startswith("START RequestId"):
            starts += 1
        elif message.startswith("INIT_START"):
            inits += 1
        elif report := _REPORT.match(message):
            reports.append(
                Report(time, report["id"], float(report["duration"]), int(report["memory"]))
            )
        elif message.startswith("{") and (event := _parse_json_event(message, time)):
            events.append(event)
        elif not message.startswith("END RequestId"):
            plain_lines.append(_plain_line(message, time))
    return Export(
        path.stem, events, reports, plain_lines, len(raw_events), starts, inits, total_bytes
    )


def render(export: Export) -> str:
    sections = [
        _overview(export),
        _problems(export),
        _stages(export),
        _tool_calls(export),
        _requests(export),
        _lambda_reports(export),
    ]
    return "\n\n".join(section for section in sections if section)


def _parse_json_event(message: str, time: datetime) -> Event | None:
    try:
        fields = json.loads(message)
    except json.JSONDecodeError:
        return None
    if not isinstance(fields, dict) or "message" not in fields:
        return None
    return Event(
        time=time,
        level=str(fields.get("level", "")),
        message=str(fields["message"]),
        request_id=fields.get("function_request_id"),
        fields=fields,
    )


def _plain_line(message: str, time: datetime) -> PlainLine:
    match = _PLAIN_LEVEL.match(message)
    return PlainLine(time, match["level"] if match else "", message)


def _overview(export: Export) -> str:
    times = [e.time for e in export.events] + [r.time for r in export.reports]
    lines = [f"== {export.name}"]
    if not times:
        return "\n".join([*lines, "no events"])
    invocations = export.starts or len(export.reports)
    lines.append(f"window: {_stamp(min(times))} to {_stamp(max(times))} UTC")
    lines.append(
        f"events: {export.event_count}"
        f" ({export.total_bytes} bytes, {export.total_bytes // max(invocations, 1)} per invocation)"
    )
    cold = f"{export.inits / invocations:.0%}" if invocations else "n/a"
    lines.append(f"invocations: {invocations}, cold starts: {export.inits} ({cold})")
    return "\n".join(lines)


def _problems(export: Export) -> str:
    grouped: dict[tuple[str, str, str, str, str], list[Event]] = defaultdict(list)
    for event in export.events:
        if event.level in ("ERROR", "WARNING", "CRITICAL"):
            key = (
                event.level,
                event.message,
                str(event.fields.get("stage", "")),
                str(event.fields.get("error", "")),
                str(event.fields.get("reason", ""))[:200],
            )
            grouped[key].append(event)

    lines = ["errors and warnings:"]
    for (level, message, stage, error, reason), events in sorted(
        grouped.items(), key=lambda item: -len(item[1])
    ):
        detail = " ".join(
            f"{name}={value}" for name, value in (("stage", stage), ("error", error)) if value
        )
        lines.append(f"  {len(events):>3}x {level} {message} {detail}".rstrip())
        if reason:
            lines.append(f"       reason: {reason}")
        lines.append(
            f"       {_stamp(events[0].time)} to {_stamp(events[-1].time)},"
            f" e.g. request {events[0].request_id}"
        )

    problem_lines = [p for p in export.plain_lines if p.level in ("WARNING", "ERROR", "CRITICAL")]
    if problem_lines:
        lines.append("  plain-text lines (not JSON):")
        counts = Counter(_plain_summary(p) for p in problem_lines)
        lines.extend(f"    {n:>3}x {text}" for text, n in counts.most_common())

    retries = sum(1 for e in export.events if e.message == "edits rejected, retrying")
    failed = sum(
        1 for e in export.events if e.fields.get("stage") == "remember" and e.level == "ERROR"
    )
    if retries:
        lines.append(f"  remember edit retries: {retries} (remember failed: {failed})")

    return "\n".join(lines) if len(lines) > 1 else "errors and warnings: none"


def _stages(export: Export) -> str:
    durations = _stage_durations(export.events)
    if not durations:
        return ""
    lines = ["stage durations (ms):", f"  {'stage':<24}{'n':>5}{'p50':>8}{'p95':>8}{'max':>8}"]
    for stage, values in sorted(durations.items()):
        stats = _stats(values)
        lines.append(
            f"  {stage:<24}{stats.count:>5}{stats.p50:>8.0f}{stats.p95:>8.0f}{stats.max:>8.0f}"
        )
    return "\n".join(lines)


def _tool_calls(export: Export) -> str:
    calls = [
        e
        for e in export.events
        if e.fields.get("stage") == "tool_call"
        and "tool" in e.fields
        and e.message in ("stage finished", "stage failed")
    ]
    if not calls:
        return ""
    lines = ["tool calls:"]
    for tool in sorted({str(c.fields["tool"]) for c in calls}):
        mine = [c for c in calls if c.fields["tool"] == tool]
        errors = sum(1 for c in mine if c.message == "stage failed" or c.fields.get("tool_error"))
        stats = _stats([float(c.fields["duration_ms"]) for c in mine])
        lines.append(
            f"  {tool}: {len(mine)} calls, p50 {stats.p50:.0f} ms, max {stats.max:.0f} ms,"
            f" {errors} errors"
        )
    return "\n".join(lines)


def _requests(export: Export) -> str:
    requests = [
        e
        for e in export.events
        if e.fields.get("stage") == "request" and e.message == "stage finished"
    ]
    if not requests:
        return ""
    by_status = Counter(
        (_path_prefix(str(r.fields.get("path", ""))), r.fields.get("status")) for r in requests
    )
    lines = ["http requests:"]
    lines.extend(f"  {prefix} {status}: {n}" for (prefix, status), n in sorted(by_status.items()))
    slow = [r for r in requests if float(r.fields["duration_ms"]) > SLOW_REQUEST_MS]
    for r in slow:
        lines.append(
            f"  slow: {_stamp(r.time)} {r.fields.get('path')} {r.fields.get('status')}"
            f" {r.fields['duration_ms']} ms cold_start={r.fields.get('cold_start')}"
        )
    return "\n".join(lines)


def _lambda_reports(export: Export) -> str:
    if not export.reports:
        return ""
    stats = _stats([r.duration_ms for r in export.reports])
    memory = max(r.memory_mb for r in export.reports)
    lines = [
        "lambda reports:",
        f"  duration ms: p50 {stats.p50:.0f}, p95 {stats.p95:.0f}, max {stats.max:.0f}",
        f"  max memory used: {memory} MB",
    ]
    slow = [r for r in export.reports if r.duration_ms > SLOW_INVOCATION_MS]
    if slow:
        lines.append(f"  invocations over {SLOW_INVOCATION_MS} ms: {len(slow)}")
        lines.extend(
            f"    {_stamp(r.time)} {r.duration_ms:.0f} ms request {r.request_id}" for r in slow
        )
    return "\n".join(lines)


def _stage_durations(events: list[Event]) -> dict[str, list[float]]:
    durations: dict[str, list[float]] = defaultdict(list)
    for event in events:
        if event.message == "stage finished" and "duration_ms" in event.fields:
            durations[str(event.fields.get("stage", ""))].append(float(event.fields["duration_ms"]))
    return durations


def _stats(values: list[float]) -> Stats:
    if not values:
        return Stats(0, 0, 0, 0)
    ordered = sorted(values)
    return Stats(len(ordered), _percentile(ordered, 50), _percentile(ordered, 95), ordered[-1])


def _percentile(ordered: list[float], percent: int) -> float:
    return ordered[max(0, math.ceil(percent / 100 * len(ordered)) - 1)]


def _path_prefix(path: str) -> str:
    return "/" + path.strip("/").split("/")[0] if path.strip("/") else "/"


def _plain_summary(line: PlainLine) -> str:
    parts = line.text.split("\t")
    return parts[-1] if len(parts) >= 4 else line.text


def _stamp(time: datetime) -> str:
    return time.strftime("%m-%d %H:%M:%S")


if __name__ == "__main__":
    main(sys.argv[1:])
