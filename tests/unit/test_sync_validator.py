from qulab.core import ActionStep, AverageStep, Procedure, RunStep, ScanStep, ScanValues
from qulab.instruments import build_context_from_resources
from qulab.sync import ExecutionOrder, SyncPlan, SyncValidator, TriggerEdge


def test_sync_validator_accepts_valid_mock_plan() -> None:
    context = build_context_from_resources({"asg": {"adapter": "mock_asg"}, "daq": {"adapter": "mock_daq"}})
    plan = SyncPlan(
        master="asg",
        triggers=[TriggerEdge(source="asg.ch5", target="daq.PFI0")],
        order=ExecutionOrder(arm=["daq", "asg"], start=["asg"], read=["daq"]),
    )
    procedure = Procedure(name="ok", body=[ScanStep(name="x", values=ScanValues.explicit([1]), body=[])])

    result = SyncValidator().validate(plan, context, procedure)

    assert result.ok


def test_sync_validator_reports_unknown_resource_and_bad_order() -> None:
    context = build_context_from_resources({"asg": {"adapter": "mock_asg"}, "daq": {"adapter": "mock_daq"}})
    plan = SyncPlan(
        master="missing",
        triggers=[TriggerEdge(source="asg.ch5", target="daq.PFI0", edge="sideways")],
        order=ExecutionOrder(arm=["asg", "daq"], start=["asg"], read=["missing"]),
    )

    result = SyncValidator().validate(plan, context, Procedure(name="bad"))

    assert not result.ok
    codes = {issue.code for issue in result.errors}
    assert {"unknown_master", "invalid_edge", "unknown_order_resource", "receiver_arm_order"} <= codes


def test_sync_validator_checks_average_and_scan_values() -> None:
    result = SyncValidator().validate(
        None,
        build_context_from_resources({}),
        Procedure(
            name="bad_steps",
            body=[
                ScanStep(name="empty", values=ScanValues.explicit([]), body=[]),
                AverageStep(name="avg", count=0, body=[]),
            ],
        ),
    )

    assert {issue.code for issue in result.errors} == {"empty_scan", "invalid_average"}


def test_sync_validator_rejects_procedure_order_that_contradicts_plan() -> None:
    context = build_context_from_resources({"asg": {"adapter": "mock_asg"}, "daq": {"adapter": "mock_daq"}})
    plan = SyncPlan(
        master="asg",
        triggers=[TriggerEdge(source="asg.ch1", target="daq.PFI1")],
        order=ExecutionOrder(arm=["daq", "asg"], start=["asg"], read=["daq"]),
    )
    procedure = Procedure(name="bad_runtime_order", body=[RunStep(name="point", body=[
        ActionStep(name="asg arm", action="asg.arm"),
        ActionStep(name="daq arm", action="daq.arm"),
        ActionStep(name="start", action="asg.start"),
        ActionStep(name="read", action="daq.read_analog_traces"),
    ])])

    result = SyncValidator().validate(plan, context, procedure)

    assert "procedure_sync_order_mismatch" in {issue.code for issue in result.errors}
