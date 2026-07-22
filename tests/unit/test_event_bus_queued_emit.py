from qulab.core import DataPoint, DerivedData, EventBus


def test_nested_emit_is_fifo_after_all_raw_subscribers():
    bus = EventBus()
    order = []
    bus.subscribe(lambda event: order.append(("a", event.type)))

    def nested(event):
        order.append(("b", event.type))
        if isinstance(event, DataPoint):
            bus.emit(DerivedData(point_id="p1", data={"y": 2}))

    bus.subscribe(nested)
    bus.subscribe(lambda event: order.append(("c", event.type)))
    bus.emit(DataPoint(point_id="p1", data={"x": 1}))
    assert order == [("a", "DataPoint"), ("b", "DataPoint"), ("c", "DataPoint"),
                     ("a", "DerivedData"), ("b", "DerivedData"), ("c", "DerivedData")]
    assert [event.type for event in bus.events] == ["DataPoint", "DerivedData"]
