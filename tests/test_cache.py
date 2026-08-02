"""
sema_core.cache.ttl_cache: single-flight TTL caching.

Follow-up to backend_qa_prompt.md's QA sweep: the original implementation
only locked the cache CHECK, not the compute -- under concurrent callers
racing a cold key, every one of them fell through and independently ran the
(sometimes DB-hitting) underlying function, a "thundering herd" that turned
out to be the real cause of the connection-pool exhaustion the sweep found
under concurrent /api/chat load, not the pool size alone. These tests prove
a cold key is computed exactly once no matter how many concurrent callers
race it, while distinct keys never block each other.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sema_core.cache import ttl_cache


def test_basic_hit_avoids_a_second_call():
    calls = []

    @ttl_cache(ttl=60)
    def compute(x):
        calls.append(x)
        return x * 2

    assert compute(3) == 6
    assert compute(3) == 6
    assert calls == [3]  # second call was a cache hit, not a recompute


def test_ttl_expiry_recomputes():
    calls = []

    @ttl_cache(ttl=0.05)
    def compute():
        calls.append(1)
        return "v"

    compute()
    time.sleep(0.1)
    compute()
    assert len(calls) == 2


def test_vary_on_keys_separately():
    calls = []
    current_client = ["ecommerce"]

    @ttl_cache(ttl=60, vary_on=lambda: current_client[0])
    def compute():
        calls.append(current_client[0])
        return current_client[0]

    assert compute() == "ecommerce"
    current_client[0] = "insurance"
    assert compute() == "insurance"  # different vary_on() -> not the cached ecommerce result
    assert calls == ["ecommerce", "insurance"]


def test_concurrent_cold_callers_compute_exactly_once():
    """The core regression test: N threads racing a COLD key must result in
    the underlying function running ONCE, with every thread getting the
    SAME result -- not N independent (redundant, possibly DB-hitting) runs."""
    call_count = 0
    call_lock = threading.Lock()
    ready = threading.Barrier(20)

    @ttl_cache(ttl=60)
    def slow_compute():
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.2)  # long enough that every thread is genuinely in-flight together
        return "the answer"

    def worker():
        ready.wait()  # line every thread up so they hit the cold cache together
        return slow_compute()

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(lambda _: worker(), range(20)))

    assert call_count == 1, f"expected exactly 1 real computation, got {call_count}"
    assert results == ["the answer"] * 20


def test_concurrent_callers_for_different_keys_do_not_block_each_other():
    """Two DIFFERENT cold keys computing concurrently must not serialize on
    each other -- only same-key contention should wait."""
    order: list[str] = []
    order_lock = threading.Lock()
    both_started = threading.Barrier(2)

    @ttl_cache(ttl=60)
    def slow_compute(key: str):
        with order_lock:
            order.append(f"{key}-start")
        both_started.wait(timeout=2)  # both must be mid-flight simultaneously
        with order_lock:
            order.append(f"{key}-end")
        return key

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(slow_compute, ["a", "b"]))

    assert set(results) == {"a", "b"}
    # If key "b" had waited for key "a"'s lock, both_started.wait() would
    # have timed out (only one thread could ever reach it at a time).
    assert {"a-start", "b-start"} <= set(order[:2])


def test_a_slow_first_caller_does_not_duplicate_work_for_a_late_arrival():
    """A caller that arrives WHILE another is already computing the same
    cold key must wait and reuse that result, not start its own second
    computation."""
    call_count = 0
    started = threading.Event()
    finish = threading.Event()

    @ttl_cache(ttl=60)
    def compute():
        nonlocal call_count
        call_count += 1
        started.set()
        finish.wait(timeout=2)
        return "result"

    first = threading.Thread(target=compute)
    first.start()
    started.wait(timeout=2)  # first caller is now mid-computation

    second_result = []
    second = threading.Thread(target=lambda: second_result.append(compute()))
    second.start()
    time.sleep(0.05)  # give the second caller a chance to (wrongly) start its own call
    finish.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert call_count == 1
    assert second_result == ["result"]
