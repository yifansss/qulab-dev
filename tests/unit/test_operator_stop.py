from threading import Event, Thread

from qulab.core import ActionStep, ExperimentContext, ExperimentExecutor, Procedure
from qulab.gui.controller import OperatorController


def test_controller_stop_unblocks_resource_read_and_cancels_executor(tmp_path) -> None:
    class BlockingResource:
        def __init__(self) -> None:
            self.read_started = Event()
            self.stopped = Event()

        def read(self):
            self.read_started.set()
            self.stopped.wait(2)
            raise RuntimeError("task stopped")

        def stop(self):
            self.stopped.set()

    resource = BlockingResource()
    executor = ExperimentExecutor(
        Procedure(name="blocking", body=[ActionStep(name="read", action="daq.read")]),
        ExperimentContext(resources={"daq": resource}),
        dry_run=False,
    )
    controller = OperatorController(tmp_path / "runs")
    controller._active_executor = executor
    controller._active_resources = {"daq": resource}
    thread = Thread(target=executor.run)
    thread.start()
    assert resource.read_started.wait(1)

    assert controller.stop_run() is True
    thread.join(2)

    assert not thread.is_alive()
    assert executor.state == "cancelled"
    assert resource.stopped.is_set()
