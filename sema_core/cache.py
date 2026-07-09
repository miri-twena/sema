"""
SEMA: framework-neutral TTL caching.

Replaces @st.cache_data so the core backend no longer depends on Streamlit
(FastAPI imports these modules too). Same idea as a BI extract refresh: keep
the computed result for `ttl` seconds, then recompute on the next call.

Built on cachetools.TTLCache (already a dependency) plus a lock so concurrent
FastAPI worker threads can share one cache safely.

The `vary_on` hook exists for functions whose result depends on hidden context
rather than their arguments -- e.g. queries.py report functions take no args
but read the ACTIVE CLIENT inside. Passing vary_on=active_client_id folds the
client into the cache key, so client A's cached report is never served to
client B (the same tenant-bleed family as the schema-cache bug).
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
        lock = threading.Lock()

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (vary_on() if vary_on else None, args, tuple(sorted(kwargs.items())))
            with lock:
                if key in store:
                    return store[key]
            result = func(*args, **kwargs)
            with lock:
                store[key] = result
            return result

        # Expose for tests / manual invalidation (mirrors st.cache_data.clear()).
        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator
