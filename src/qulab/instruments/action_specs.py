"""Import-safe action descriptors shared by validation and authoring UIs."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass
from typing import Any

class _Missing:
    def __repr__(self) -> str: return "MISSING"
MISSING = _Missing()

@dataclass(frozen=True)
class ArgumentSpec:
    name: str; dtype: str; required: bool = False; default: Any = MISSING
    unit: str | None = None; minimum: float | None = None; maximum: float | None = None
    choices: tuple[Any, ...] | None = None; allow_reference: bool = True
    widget: str | None = None; description: str | None = None

@dataclass(frozen=True)
class DataFieldSpec:
    name: str; dtype: str = "any"; unit: str | None = None

@dataclass(frozen=True)
class ReturnSpec:
    data_kind: str; unit: str | None = None; fields: tuple[DataFieldSpec, ...] = (); save_recommended: bool = False

@dataclass(frozen=True)
class ActionSpec:
    id: str; method: str; label: str; capability: str; arguments: tuple[ArgumentSpec, ...] = ()
    returns: ReturnSpec | None = None; phase: str = "configure"; safety_class: str = "unknown"
    requires_connected: bool = False; requires_states: tuple[str, ...] = (); provides_states: tuple[str, ...] = ()
    invalidates_states: tuple[str, ...] = (); allowed_sections: tuple[str, ...] = ("setup", "procedure", "cleanup")
    description: str | None = None; allow_unknown_arguments: bool = False

@dataclass(frozen=True)
class CapabilitySpec:
    id: str; label: str; version: int = 1

@dataclass(frozen=True)
class AdapterSpec:
    id: str; capabilities: tuple[str, ...]; actions: tuple[ActionSpec, ...]; version: int = 1

@dataclass(frozen=True)
class ActionValidationIssue:
    severity: str; code: str; message: str; argument: str | None = None

class ActionSpecRegistry:
    def __init__(self) -> None: self._adapters: dict[str, AdapterSpec] = {}
    def register(self, spec: AdapterSpec) -> None:
        if spec.id in self._adapters: raise ValueError(f"duplicate adapter spec: {spec.id}")
        if len({a.id for a in spec.actions}) != len(spec.actions): raise ValueError(f"duplicate action id: {spec.id}")
        self._adapters[spec.id] = spec
    def list_adapters(self) -> tuple[str, ...]: return tuple(sorted(self._adapters))
    def describe_adapter(self, name: str) -> AdapterSpec | None: return self._adapters.get(name)
    def list_actions(self, adapter_name: str, capabilities: set[str] | None = None) -> tuple[ActionSpec, ...]:
        spec = self._adapters.get(adapter_name)
        return () if spec is None else tuple(a for a in spec.actions if capabilities is None or a.capability in capabilities)
    def resolve_action(self, adapter_name: str, method: str) -> ActionSpec | None:
        return next((a for a in self.list_actions(adapter_name) if a.method == method), None)
    def to_json(self) -> str:
        return json.dumps({n: _jsonable(asdict(self._adapters[n])) for n in sorted(self._adapters)}, sort_keys=True, separators=(",", ":"))

def validate_action_call(spec: ActionSpec, args: dict[str, Any], available_refs: set[str] | None = None) -> tuple[ActionValidationIssue, ...]:
    issues: list[ActionValidationIssue] = []; declared = {a.name: a for a in spec.arguments}
    for arg in spec.arguments:
        if arg.required and arg.default is MISSING and arg.name not in args:
            issues.append(ActionValidationIssue("error", "action_argument_missing", f"Missing required argument '{arg.name}'.", arg.name))
    if not spec.allow_unknown_arguments:
        for name in args:
            if name not in declared: issues.append(ActionValidationIssue("error", "action_argument_unknown", f"Unknown argument '{name}' for {spec.method}.", name))
    for name, value in args.items():
        arg = declared.get(name)
        if arg is None: continue
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            ref = value[2:-1]
            if not arg.allow_reference: issues.append(ActionValidationIssue("error", "action_argument_type", f"Argument '{name}' does not allow references.", name))
            elif available_refs is not None and ref not in available_refs: issues.append(ActionValidationIssue("error", "parameter_reference_unresolved", f"Unknown reference '{ref}'.", name))
            continue
        if not _matches(value, arg.dtype): issues.append(ActionValidationIssue("error", "action_argument_type", f"Argument '{name}' must be {arg.dtype}.", name)); continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if arg.minimum is not None and value < arg.minimum: issues.append(ActionValidationIssue("error", "action_argument_range", f"Argument '{name}' must be >= {arg.minimum}.", name))
            if arg.maximum is not None and value > arg.maximum: issues.append(ActionValidationIssue("error", "action_argument_range", f"Argument '{name}' must be <= {arg.maximum}.", name))
        if arg.choices is not None and value not in arg.choices: issues.append(ActionValidationIssue("error", "action_argument_choice", f"Argument '{name}' must be one of {arg.choices}.", name))
    return tuple(issues)

def _matches(value: Any, dtype: str) -> bool:
    if dtype in {"any", "object"}: return True
    if dtype in {"number", "float"}: return isinstance(value, (int, float)) and not isinstance(value, bool)
    if dtype in {"integer", "int"}: return isinstance(value, int) and not isinstance(value, bool)
    if dtype in {"string", "path", "channel", "terminal"}: return isinstance(value, str)
    if dtype == "boolean": return isinstance(value, bool)
    if dtype == "list": return isinstance(value, list)
    if dtype == "mapping": return isinstance(value, dict)
    return True

def _jsonable(value: Any) -> Any:
    if value is MISSING or isinstance(value, _Missing): return {"missing": True}
    if isinstance(value, dict): return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_jsonable(v) for v in value]
    return value

def _a(method: str, capability: str, *, arguments: tuple[ArgumentSpec, ...] = (), returns: ReturnSpec | None = None, phase: str = "configure", safety: str = "configure_no_output", requires: tuple[str, ...] = (), provides: tuple[str, ...] = (), invalidates: tuple[str, ...] = (), sections: tuple[str, ...] = ("setup", "procedure", "cleanup"), connected: bool = False, unknown: bool = False) -> ActionSpec:
    return ActionSpec(f"{capability}.{method}", method, method.replace("_", " ").title(), capability, arguments, returns, phase, safety, connected, requires, provides, invalidates, sections, allow_unknown_arguments=unknown)
def N(name: str, **kw: Any) -> ArgumentSpec: return ArgumentSpec(name, "number", **kw)
def I(name: str, **kw: Any) -> ArgumentSpec: return ArgumentSpec(name, "integer", **kw)
def S(name: str, **kw: Any) -> ArgumentSpec: return ArgumentSpec(name, "string", **kw)
def A(name: str, **kw: Any) -> ArgumentSpec: return ArgumentSpec(name, "any", **kw)

MW = (_a("set_frequency", "microwave_source", arguments=(N("freq_hz", required=True, unit="Hz", minimum=0),)), _a("set_power", "microwave_source", arguments=(N("power_dbm", required=True, unit="dBm"),)), _a("output_on", "microwave_source", phase="start", safety="output", provides=("output_enabled",), sections=("setup", "procedure")), _a("output_off", "microwave_source", phase="cleanup", safety="output", invalidates=("output_enabled",), sections=("cleanup", "procedure")))
PULSE = (_a("load_sequence", "pulse_sequencer", arguments=(S("path"), S("sequence_file"), A("sequence"), S("code")), provides=("sequence_loaded",)), _a("set_sequence_param", "pulse_sequencer", arguments=(S("name", required=True), A("value", required=True))), _a("compile_sequence", "pulse_sequencer", requires=("sequence_loaded",), provides=("compiled",)), _a("configure_trigger", "trigger_source", unknown=True), _a("configure_trigger_output", "trigger_source", arguments=(S("channel", required=True), S("mode", required=True), S("edge"), A("level"))), _a("arm", "pulse_sequencer", phase="arm", safety="output", requires=("sequence_loaded",), provides=("armed",), connected=True), _a("start", "pulse_sequencer", phase="start", safety="output", requires=("armed",), provides=("running",), invalidates=("armed",), connected=True), _a("stop", "pulse_sequencer", phase="cleanup", safety="output", invalidates=("running", "armed")))
PULSE += (_a("load_sequence_from_bundle", "pulse_sequencer", arguments=(S("bundle", required=True),), provides=("sequence_loaded",), unknown=True),)
DAQ = (_a("configure_counter", "daq_counter", arguments=(N("sample_rate"), I("samples", minimum=1), S("source"), S("trigger")), provides=("configured",)), _a("configure_ai", "analog_input", arguments=(A("channels", required=True), N("sample_rate"), I("samples", minimum=1), S("terminal_config")), provides=("configured",)), _a("arm", "trigger_receiver", phase="arm", requires=("configured",), provides=("armed",), connected=True), _a("read_counts", "daq_counter", arguments=(N("timeout"),), returns=ReturnSpec("mapping", fields=(DataFieldSpec("counts_mean", "number"), DataFieldSpec("photon_bins", "list")), save_recommended=True), phase="read", safety="read_only", requires=("armed",), connected=True), _a("read_counts_binned", "daq_counter", arguments=(I("bins", default=4, minimum=1), N("timeout")), returns=ReturnSpec("array", save_recommended=True), phase="read", safety="read_only"), _a("read_counts_trace", "daq_counter", arguments=(I("bins", default=4, minimum=1),), returns=ReturnSpec("mapping", save_recommended=True), phase="read", safety="read_only"), _a("read_analog", "analog_input", arguments=(N("timeout"),), returns=ReturnSpec("array", unit="V", save_recommended=True), phase="read", safety="read_only"), _a("read", "analog_input", arguments=(N("timeout"),), returns=ReturnSpec("any", save_recommended=True), phase="read", safety="read_only"), _a("set_voltage", "analog_output", arguments=(S("channel", required=True), N("voltage", required=True, unit="V")), safety="analog_output"), _a("set_ao_static", "analog_output", arguments=(S("channel", required=True), N("voltage", required=True, unit="V")), safety="analog_output"), _a("set_waveform", "analog_output", arguments=(S("channel", required=True), ArgumentSpec("waveform", "list", required=True), N("sample_rate")), safety="analog_output"), _a("stop", "daq_counter", phase="cleanup", invalidates=("armed", "acquiring")))

DEFAULT_ACTION_REGISTRY = ActionSpecRegistry()
for name in ("mock_microwave", "mock_microwave_source", "pycontrol_lmx"): DEFAULT_ACTION_REGISTRY.register(AdapterSpec(name, ("microwave_source",), MW))
for name in ("mock_pulse_sequencer", "mock_asg", "pycontrol_asg"): DEFAULT_ACTION_REGISTRY.register(AdapterSpec(name, ("pulse_sequencer", "trigger_source"), PULSE))
for name in ("mock_daq_counter", "mock_daq"): DEFAULT_ACTION_REGISTRY.register(AdapterSpec(name, ("daq_counter", "analog_input", "trigger_receiver"), DAQ))
DEFAULT_ACTION_REGISTRY.register(AdapterSpec("mock_analog_io", ("analog_input", "analog_output"), tuple(a for a in DAQ if a.method in {"configure_ai", "read_analog", "set_voltage", "set_waveform"})))
ni_extra = tuple(_a(n, "daq_counter", unknown=True, provides=("configured",)) for n in ("configure_counter_external_clock", "configure_ai_external_trigger", "configure_ao_ai_sync", "configure_ao_ai_step_and_sample", "configure_point_readout")) + (_a("wait_settle", "analog_output", arguments=(N("seconds", required=True, minimum=0),)),)
DEFAULT_ACTION_REGISTRY.register(AdapterSpec("pycontrol_ni", ("daq_counter", "analog_input", "analog_output", "trigger_receiver"), DAQ + ni_extra))
DEFAULT_ACTION_REGISTRY.register(AdapterSpec("pycontrol_awg", ("waveform_generator", "trigger_receiver"), (_a("upload_waveform", "waveform_generator", arguments=(S("name", required=True), A("data", required=True), N("sample_rate")), provides=("sequence_loaded",)), _a("play", "waveform_generator", arguments=(S("name", required=True),), phase="start", safety="output", provides=("running",), connected=True), _a("stop", "waveform_generator", phase="cleanup", safety="output", invalidates=("running",)), _a("configure_trigger_input", "trigger_receiver", arguments=(S("channel", required=True), ArgumentSpec("edge", "string", default="rising", choices=("rising", "falling"))), provides=("configured",)), _a("arm", "trigger_receiver", phase="arm", requires=("configured",), provides=("armed",), connected=True))))

def render_action_catalog_markdown(registry: ActionSpecRegistry = DEFAULT_ACTION_REGISTRY) -> str:
    lines = ["# Instrument Action Catalog", ""]
    for adapter in registry.list_adapters():
        lines += [f"## `{adapter}`", "", "| Method | Capability | Phase | Safety |", "|---|---|---|---|"]
        lines += [f"| `{a.method}` | `{a.capability}` | `{a.phase}` | `{a.safety_class}` |" for a in registry.list_actions(adapter)]
        lines.append("")
    return "\n".join(lines)
