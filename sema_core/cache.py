"""
SEMA: framework-neutral TTL caching.

Replaces @st.cache_data so the core backend no longer depends on Streamlit
(FastAPI imports these modules too). Same idea as a BI extract refresh: keep
the computed result for `ttl` seconds, then recompute on the next call.

Built on cachetools.TTLCache (already a dependency) plus locking so concurrent
FastAPI worker threads can share one cache safely.

The `vary_on` hook exists for functions whose result depends on hidden context
rather than their arguments -- e.g. queries.py report functions take no args
but read the ACTIVE CLIENT inside. Passing vary_on=active_client_id folds the
client into the cache key, so client A's cached report is never served to
client B (the same tenant-bleed family as the schema-cache bug).

Single-flight (backend_qa_prompt.md item 4 follow-up): a cold key must be
computed by exactly ONE caller at a time, with every other concurrent caller
for that SAME key waiting on that result instead of independently repeating
the work. The original version only locked the CHECK, not the compute --
under N concurrent requests racing a cold cache (every process restart, or
every TTL expiry under real traffic), all N would fall through and each run
the underlying (often DB-hitting) function itself. That "thundering herd" is
what was actually exhausting the Postgres connection pool under concurrent
/api/chat load, not the pool size being too small per se -- 20 concurrent
requests could mean 20 simultaneous, fully redundant queries for data that's
identical across all 20. Fixed here so a burst of concurrent callers costs
ONE real query, not N.
"""

from __future__ import annotations

import threading
from functools import wraps
from typing import Callable

from cachetools import TTLCache


def ttl_cache(ttl: int, maxsize: int = 128, vary_on: Callable[[], object] | None = None):
    """Decorator: cache the function's result for `ttl` seconds.

    The cache key is (vary_on(), *args, **kwargs). Arguments must be hashable
    (they are simple strings/ints everywhere we use this).
    """

    def decorator(func):
        store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        store_lock = threading.Lock()
        # One lock per in-flight cold key, created on demand. Distinct keys
        # (different clients, different args) never block each other --
        # only concurrent callers computing the SAME cold key serialize.
        key_locks: dict[object, threading.Lock] = {}
        key_locks_lock = threading.Lock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (vary_on() if vary_on else None, args, tuple(sorted(kwargs.items())))
            with store_lock:
                if key in store:
                    return store[key]

            with key_locks_lock:
                key_lock = key_locks.setdefault(key, threading.Lock())
            with key_lock:
                # Re-check: whoever held key_lock first may have already
                # populated the cache while we were waiting for it.
                with store_lock:
                    if key in store:
                        return store[key]
                result = func(*args, **kwargs)
                with store_lock:
                    store[key] = result
            with key_locks_lock:
                key_locks.pop(key, None)
            return result

        # Expose for tests / manual invalidation (mirrors st.cache_data.clear()).
        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator
