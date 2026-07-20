"""
Unit tests for the daily prompt-cache report (sema_core/cache_report.py).

Pure aggregation over structured log dicts -- no DB, no API, no files -- so the
hit-rate and savings math is verified in ordinary CI.
"""

from __future__ import annotations

from sema_core import cache_report as cr


def _event(day: str, **over) -> dict:
    ev = {
        "event": "agent_run",
        "ts": f"{day}T12:00:00+00:00",
        "input_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 0,
    }
    ev.update(over)
    return ev


def test_summarize_buckets_by_day_and_sums():
    events = [
        _event("2026-07-19", cache_read_tokens=1000, cache_write_tokens=100),
        _event("2026-07-19", cache_read_tokens=500, input_tokens=200),
        _event("2026-07-20", cache_write_tokens=800),
    ]
    by_day = cr.summarize(events)
    assert set(by_day) == {"2026-07-19", "2026-07-20"}
    d19 = by_day["2026-07-19"]
    assert d19.requests == 2
    assert d19.cache_read_tokens == 1500
    assert d19.cache_write_tokens == 100
    assert d19.input_tokens == 200


def test_ignores_non_agent_run_and_missing_ts():
    events = [
        {"event": "response_mode", "ts": "2026-07-19T00:00:00", "cache_read_tokens": 999},
        _event("2026-07-19", cache_read_tokens=10),
        {"event": "agent_run", "cache_read_tokens": 5},  # no ts -> skipped
    ]
    by_day = cr.summarize(events)
    assert list(by_day) == ["2026-07-19"]
    assert by_day["2026-07-19"].cache_read_tokens == 10  # the response_mode line was not counted


def test_hit_rate_and_savings_math():
    # 9000 read (hits) + 1000 write (miss) -> 90% prefix hit rate.
    (t,) = cr.summarize([_event("2026-07-19", cache_read_tokens=9000, cache_write_tokens=1000)]).values()
    assert abs(t.cache_hit_rate - 0.9) < 1e-9

    # Caching must be cheaper here: 9000 tokens at 0.1x + 1000 at 1.25x is far
    # less than 10000 at full price.
    assert t.cost_with_cache < t.cost_without_cache
    assert t.savings > 0
    # Savings identity: without - with, computed independently.
    assert abs(t.savings - (t.cost_without_cache - t.cost_with_cache)) < 1e-12


def test_hit_rate_zero_when_no_cache_activity():
    (t,) = cr.summarize([_event("2026-07-19", input_tokens=500)]).values()
    assert t.cache_hit_rate == 0.0  # no divide-by-zero


def test_parse_log_lines_tolerates_non_json():
    lines = [
        '{"event": "agent_run", "ts": "2026-07-19T00:00:00", "cache_read_tokens": 7}',
        "Traceback (most recent call last):",  # human-readable line on same stream
        "",
    ]
    objs = list(cr.parse_log_lines(lines))
    assert len(objs) == 1 and objs[0]["cache_read_tokens"] == 7


def test_format_report_empty():
    assert "No agent_run events" in cr.format_report({})
