import threading

from qulab.core import DataPoint, EventBus


def test_subscribers_are_never_called_concurrently():
    bus = EventBus(); active = 0; concurrent = False; guard = threading.Lock(); barrier = threading.Barrier(3)
    def subscriber(event):
        nonlocal active, concurrent
        with guard:
            active += 1; concurrent = concurrent or active > 1
        for _ in range(10000): pass
        with guard: active -= 1
    bus.subscribe(subscriber)
    def emit(value): barrier.wait(); bus.emit(DataPoint(point_id=str(value), data={"x": value}))
    threads = [threading.Thread(target=emit, args=(value,)) for value in (1, 2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(2)
    assert not concurrent and len(bus.events) == 2 and all(not thread.is_alive() for thread in threads)
