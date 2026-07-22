# Prompt 011-followup P11.3A: Capability Action Schema Registry Worker

这份 prompt 可直接交给 adapter/core worker。目标是建立 import-safe、机器可读、可验证的仪器 action 描述合同，让 GUI、config validation、Direct Control 和文档都从同一份 schema 知道“有哪些功能、需要哪些参数、单位/范围是什么、返回什么、应处于哪个阶段、是否危险”。

## /goal

实现公共 descriptor registry，但不改变 executor 的 canonical `resource.method` 调用语义：

- capability 定义 canonical actions；
- adapter 声明自己实现哪些 action specs；
- GUI 可离线列举 resource 可用 actions；
- config validator 可检查 method/args/type/ref；
- action phase/safety/ordering 可供 P11.3B completeness validator 使用；
- descriptor discovery 不连接硬件、不导入厂商 DLL、不依赖 Windows。

## 必须先阅读

- `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
- `docs/ADAPTER_REQUIREMENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/CONFIG_SCHEMA.md`
- `src/qulab/instruments/base.py`
- `src/qulab/instruments/capabilities.py`
- `src/qulab/instruments/registry.py`
- mock and pycontrol adapters
- executor ActionStep resolution
- sequence runtime actions
- sync validators
- Direct Control planning
- P11.1 diagnostic contract/handoff

## Public models

推荐 Qt-free dataclasses：

```python
@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    dtype: str
    required: bool = False
    default: Any = MISSING
    unit: str | None = None
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[Any, ...] | None = None
    allow_reference: bool = True
    widget: str | None = None
    description: str | None = None

@dataclass(frozen=True)
class ReturnSpec:
    data_kind: str
    unit: str | None = None
    fields: tuple[DataFieldSpec, ...] = ()
    save_recommended: bool = False

@dataclass(frozen=True)
class ActionSpec:
    id: str
    method: str
    label: str
    capability: str
    arguments: tuple[ArgumentSpec, ...]
    returns: ReturnSpec | None
    phase: str
    safety_class: str
    requires_connected: bool
    requires_states: tuple[str, ...] = ()
    provides_states: tuple[str, ...] = ()
    invalidates_states: tuple[str, ...] = ()
    allowed_sections: tuple[str, ...] = ("setup", "procedure", "cleanup")
    description: str | None = None
```

补充 `CapabilitySpec`、`AdapterSpec`、registry/query result。所有 models 可序列化，stable id/version 明确。

## Canonical action coverage

至少为当前 capabilities 描述：

- MicrowaveSource: set_frequency, set_power, output_on/off；
- PulseSequencer: load_sequence, load_sequence_from_bundle, set_sequence_param, compile_sequence, configure_trigger, arm, start, stop；
- DAQCounter: configure_counter/configure_point_readout where public, arm, read/read_counts/read_counts_binned, stop；
- AnalogInput: configure_ai/configure_point_readout, arm/read_analog/read where public, stop；
- AnalogOutput: set_voltage/set_ao_static, set_waveform；
- TriggerSource/Receiver；
- WaveformGenerator: upload/play/stop；
- wait remains workflow structural action, not adapter action。

Adapter aliases may map to canonical actions but GUI must display actual callable method used in YAML. Do not claim a method exists unless adapter implements it.

## Descriptor location and imports

Descriptors must be loadable before adapter instance creation. Recommended:

- capability canonical specs live in `instruments/action_specs.py`；
- adapter registry registration includes `AdapterSpec` or a lazy descriptor factory；
- pycontrol descriptor module must not import driver packages；
- runtime factory remains lazy and unchanged；
- project-local adapter registration can supply specs explicitly。

Do not use broad filesystem scanning. Do not instantiate adapter to discover methods. `inspect.signature()` may be used only in tests to detect descriptor drift.

## Validation

Provide APIs such as：

```python
registry.list_adapters()
registry.describe_adapter(name)
registry.list_actions(adapter_name, capabilities=None)
registry.resolve_action(adapter_name, method)
validate_action_call(spec, args, available_refs)
```

Validation returns P11.1 `ConfigDiagnostic` or an adapter-independent issue converted by P11.1.

Checks：

- action exists and callable contract declared；
- required/unknown args；
- literal dtype；
- numeric range/choice；
- unit representation where supported；
- `${ref}` allowed and available；
- `save_as` recommendation/return kind；
- section/safety warning；
- descriptor/runtime signature drift in tests。

Do not reject adapter `**kwargs` advanced calls by guessing. Such actions must explicitly declare an advanced mapping argument or be marked schema-incomplete with `unknown` safety and warning.

## Lifecycle state tokens

Define a small generic vocabulary, not vendor-specific state explosion：

```text
configured
sequence_loaded
compiled
armed
running
acquiring
output_enabled
```

Action specs state requirements are advisory/validation metadata; executor behavior remains unchanged in P11.3A. Device-specific exceptions may add namespaced tokens.

## Safety

Use existing planned classes：

```text
read_only
connect
configure_no_output
output
analog_output
unknown
```

No action with `output|analog_output|unknown` may be mislabeled safer just to expose it in GUI. P11.3A does not enable Direct Control actions.

## Docs generation

Provide a deterministic function/CLI that renders action catalog Markdown or JSON for inspection. Generated docs are optional to commit; contract tests must ensure deterministic output. GUI tooltips should consume descriptors directly, not scrape Markdown/docstrings.

## Tests

- registry lists all built-in adapters without vendor imports；
- every declared capability/action has unique stable id；
- specs JSON serialization deterministic；
- mock and pycontrol adapter public methods agree with specs；
- required/default/range/choice/ref validation；
- data-producing returns and save recommendation；
- lifecycle and safety fields present；
- unknown adapter/action diagnostics；
- importing descriptors with pycontrol/nidaqmx absent works；
- no hardware connect/driver constructor during discovery；
- project-local adapter registration；
- P11.1 integration checks workflow calls；
- all existing configs either validate or have intentional documented warning, with no surprise mass breakage。

## Non-goals

- 不做 Workflow Composer UI；
- 不执行 action；
- 不做硬件自动探测；
- 不把所有 vendor private methods 暴露给 experiment；
- 不从 docstring 自动生成权威 schema；
- 不改变 sequence provider parameter contract。

## Definition of Done

- GUI/headless code可离线列举 adapters/capabilities/actions/args；
- schemas 包含 unit/default/range/return/phase/safety/order；
- P11.1 能使用 schema 验证 call；
- descriptor discovery 无 vendor/hardware side effect；
- runtime signature drift 有 tests；
- built-in adapters 覆盖完整且没有虚假 action；
- docs 和 examples 更新；
- full tests/portability pass。

建议 commits：

```text
feat(instruments): add capability action schemas
feat(config): validate workflow calls from action specs
test(instruments): detect adapter descriptor drift
docs(adapters): publish action catalog contract
```

最终 handoff 给出 public API、覆盖 action 表、schema-incomplete actions、safety decisions、tests，并确认 discovery 未连接硬件。
