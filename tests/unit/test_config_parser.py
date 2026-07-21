from qulab.config import load_experiment_config, parse_experiment_config
from qulab.config.refs import resolve_parameter_refs
from qulab.core import ActionStep, AverageStep, MeasurementStep, P, ParameterRef, RunStep, ScanStep, WaitStep


def test_load_experiment_config_converts_numeric_strings() -> None:
    config = load_experiment_config(
        """
        schema_version: 1
        name: numeric
        resources: {}
        procedure:
          - scan:
              name: freq
              values: {start: "2.86e9", stop: "2.88e9", points: "3"}
              body: []
        """
    )

    values = config["procedure"][0]["scan"]["values"]
    assert values["start"] == 2.86e9
    assert values["points"] == 3


def test_parameter_refs_are_recursive_and_strict() -> None:
    resolved = resolve_parameter_refs({"outer": [{"value": "${tau_s}"}]})

    assert isinstance(resolved["outer"][0]["value"], ParameterRef)
    assert resolved["outer"][0]["value"] == P("tau_s")


def test_parse_yaml_steps_to_core_procedure() -> None:
    parsed = parse_experiment_config(
        {
            "schema_version": 1,
            "name": "parser_test",
            "resources": {
                "mw": {"adapter": "mock_microwave"},
                "asg": {"adapter": "mock_asg"},
                "daq": {"adapter": "mock_daq"},
            },
            "sync": {
                "master": "asg",
                "triggers": [{"source": "asg.ch5", "target": "daq.PFI0"}],
                "order": {"arm": ["daq", "asg"], "start": ["asg"], "read": ["daq"]},
            },
            "setup": [{"call": "mw.set_power", "args": {"power_dbm": -10}}],
            "procedure": [
                {
                    "scan": {
                        "name": "tau_s",
                        "values": {"start": 1.0, "stop": 3.0, "step": 1.0},
                        "body": [
                            {
                                "measurement": {
                                    "name": "point",
                                    "body": [
                                        {
                                            "average": {
                                                "name": "avg",
                                                "count": 2,
                                                "body": [
                                                    {
                                                        "run": {
                                                            "name": "readout",
                                                            "steps": [
                                                                {
                                                                    "call": "daq.read_counts",
                                                                    "save_as": "counts",
                                                                }
                                                            ],
                                                        }
                                                    }
                                                ],
                                            }
                                        }
                                    ],
                                }
                            }
                        ],
                    }
                }
            ],
            "cleanup": [{"call": "mw.output_off"}],
        }
    )

    assert parsed.validation.ok
    assert set(parsed.context.resources) == {"mw", "asg", "daq"}
    assert isinstance(parsed.procedure.setup[0], ActionStep)
    scan = parsed.procedure.body[0]
    assert isinstance(scan, ScanStep)
    assert list(scan.values) == [1.0, 2.0, 3.0]
    measurement = scan.body[0]
    assert isinstance(measurement, MeasurementStep)
    average = measurement.body[0]
    assert isinstance(average, AverageStep)
    run = average.body[0]
    assert isinstance(run, RunStep)
    action = run.body[0]
    assert isinstance(action, ActionStep)
    assert action.action == "daq.read_counts"
    assert action.save_as == "counts"


def test_parse_wait_step() -> None:
    parsed = parse_experiment_config(
        {
            "schema_version": 1,
            "name": "wait_test",
            "resources": {},
            "procedure": [{"wait": {"name": "settle", "duration_s": 0.25, "reason": "mw settle"}}],
        }
    )

    wait = parsed.procedure.body[0]
    assert isinstance(wait, WaitStep)
    assert wait.duration_s == 0.25
    assert wait.reason == "mw settle"
