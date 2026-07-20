"""
SEMA: daily prompt-cache report.

Reads the structured `agent_run` log lines the agent already emits (obs.py) and
rolls them up PER DAY into a prompt-cache scorecard: how many request tokens
were served from cache vs. freshly written, the cache hit rate, and the
estimated $ saved by caching the big static prefix (system prompt + tool
schemas). It parses logs -- it does NOT call the API or the DB -- so it's safe
to run anywhere the logs are.

Prompt caching in one line (for the analyst reading this): Anthropic lets us
mark the large, identical prefix of every request so the model re-reads it at
~0.1x input cost instead of full price. `cache_creation_input_tokens` is the
one-time write (the "miss", billed at ~1.25x); `cache_read_input_tokens` is
every later reuse (the "hit", ~0.1x); `input_tokens` is the genuinely dynamic
suffix (the user's question, SQL results) that was never cacheable.

Usage (logs are JSON lines on stderr, so capture them to a file first):

    .venv\\Scripts\\python.exe -m sema_core.cache_report var\\sema.log
    ... | .venv\\Scripts\\python.exe -m sema_core.cache_report      # or stdin
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

# Rough Anthropic per-million-token input/output rates -- EDIT to your plan.
# Same ballpark constants as evals/run_evals.py; not a billing source of truth.
USD_PER_M_INPUT_TOKENS = 3.00
USD_PER_M_OUTPUT_TOKENS = 15.00
# Cache multipliers relative to the normal input rate: a cache READ is ~0.1x
# (the whole point), a cache WRITE (creation) carries a ~1.25x one-time premium.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass
class DayTotals:
    """One day's summed token counters across all agent_run events."""

    requests: int = 0
    input_tokens: int = 0  # dynamic suffix, never cacheable
    cache_read_tokens: int = 0  # prefix served from cache (~0.1x) -- the "hit"
    cache_write_tokens: int = 0  # prefix written to cache (~1.25x) -- the "miss"
    output_tokens: int = 0

    def add(self, ev: dict) -> None:
        self.requests += 1
        self.input_tokens += int(ev.get("input_tokens") or 0)
        self.cache_read_tokens += int(ev.get("cache_read_tokens") or 0)
        self.cache_write_tokens += int(ev.get("cache_write_tokens") or 0)
        self.output_tokens += int(ev.get("output_tokens") or 0)

    @property
    def cache_hit_rate(self) -> float:
        """Share of the cacheable PREFIX that was served from cache rather than
        re-written: read / (read + write). ~0 means a silent cache invalidator
        (a per-request value leaked into the static prefix); high is healthy."""
        cacheable = self.cache_read_tokens + self.cache_write_tokens
        return self.cache_read_tokens / cacheable if cacheable else 0.0

    @property
    def cost_with_cache(self) -> float:
        """What these requests actually cost, given caching."""
        in_rate = USD_PER_M_INPUT_TOKENS / 1_000_000
        return (
            self.input_tokens * in_rate
            + self.cache_read_tokens * in_rate * CACHE_READ_MULTIPLIER
            + self.cache_write_tokens * in_rate * CACHE_WRITE_MULTIPLIER
            + self.output_tokens * (USD_PER_M_OUTPUT_TOKENS / 1_000_000)
        )

    @property
    def cost_without_cache(self) -> float:
        """What they WOULD have cost with no caching: every cached-read and
        cached-write token would instead have been a full-price input token,
        re-sent on every round."""
        in_rate = USD_PER_M_INPUT_TOKENS / 1_000_000
        all_input = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        return all_input * in_rate + self.output_tokens * (USD_PER_M_OUTPUT_TOKENS / 1_000_000)

    @property
    def savings(self) -> float:
        return self.cost_without_cache - self.cost_with_cache


def _day_of(ev: dict) -> str | None:
    """The YYYY-MM-DD date from an event's `ts`, or None if absent/malformed."""
    ts = ev.get("ts")
    if not isinstance(ts, str) or len(ts) < 10:
        return None
    return ts[:10]


def summarize(events: Iterable[dict]) -> dict[str, DayTotals]:
    """Roll `agent_run` events up into {date: DayTotals}. Non-agent_run events
    and events without a usable `ts` are ignored."""
    by_day: dict[str, DayTotals] = defaultdict(DayTotals)
    for ev in events:
        if ev.get("event") != "agent_run":
            continue
        day = _day_of(ev)
        if day is None:
            continue
        by_day[day].add(ev)
    return dict(by_day)


def parse_log_lines(lines: Iterable[str]) -> Iterable[dict]:
    """Yield the JSON object from each structured log line, skipping any line
    that isn't JSON (human-readable tracebacks are interleaved on the same
    stream, so tolerate them)."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj


def format_report(by_day: dict[str, DayTotals]) -> str:
    """Human-readable per-day scorecard, oldest day first, with a grand total."""
    if not by_day:
        return "No agent_run events with timestamps found."

    out: list[str] = ["SEMA prompt-cache report", "=" * 60]
    grand = DayTotals()
    for day in sorted(by_day):
        t = by_day[day]
        grand.requests += t.requests
        grand.input_tokens += t.input_tokens
        grand.cache_read_tokens += t.cache_read_tokens
        grand.cache_write_tokens += t.cache_write_tokens
        grand.output_tokens += t.output_tokens
        out.append(
            f"{day}  {t.requests:>4} req  "
            f"hit {t.cache_hit_rate * 100:5.1f}%  "
            f"read {t.cache_read_tokens:>9,}  write {t.cache_write_tokens:>8,}  "
            f"uncached {t.input_tokens:>8,}  "
            f"saved ${t.savings:8.2f}"
        )
    out.append("=" * 60)
    out.append(
        f"TOTAL {grand.requests:>4} req  "
        f"hit {grand.cache_hit_rate * 100:5.1f}%  "
        f"cost ${grand.cost_with_cache:.2f} "
        f"(vs ${grand.cost_without_cache:.2f} uncached) -> "
        f"saved ${grand.savings:.2f}"
    )
    out.append(
        f"rates: ${USD_PER_M_INPUT_TOKENS}/M in, ${USD_PER_M_OUTPUT_TOKENS}/M out; "
        f"cache read {CACHE_READ_MULTIPLIER}x, write {CACHE_WRITE_MULTIPLIER}x "
        f"(edit at top of sema_core/cache_report.py)"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily SEMA prompt-cache report from agent_run logs.")
    parser.add_argument(
        "logfile",
        nargs="?",
        help="Path to a file of JSON log lines. Omit to read from stdin.",
    )
    args = parser.parse_args(argv)

    if args.logfile:
        with open(args.logfile, encoding="utf-8") as f:
            by_day = summarize(parse_log_lines(f))
    else:
        by_day = summarize(parse_log_lines(sys.stdin))

    print(format_report(by_day))
    return 0


if __name__ == "__main__":
    sys.exit(main())
