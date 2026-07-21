# Prompt 009-followup P9.3A: Sequence Generation Foundation Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是实现 Phase E 的公共基础：provider contract、`sequence_plans` schema、参数 sampling、framework-owned materializer、`sequence_sweep` compiler、Prepare pipeline、generation provenance，以及一个 headless Rabi provider/example。此 worker不实现通用 pulse target/shift engine，也不实现 GUI。

---

## /goal

让用户只修改一份结构化 authoring config 就能生成并运行 Rabi sequence scan：

```text
sequence_plans + sequence_sweep
  -> provider parameter validation
  -> fixed/linspace/range/explicit sampling
  -> concrete sequence files
  -> framework writes manifest/hash
  -> P9.1 load/validate
  -> authoring macro compiles to existing scan/load action
  -> P9.2 preflight/runtime/RunStore
```

用户不得再手写 manifest entries、generated `sequence_bundles` block 或重复的 `load_sequence_from_bundle` action。旧 concrete bundle YAML 必须继续工作。

---

## 硬依赖与开始条件

开始前确认 P9.1/P9.2 已完成并通过：

```text
qulab.sequence_bundles
qulab.sequence_runtime
qulab.sequence_preflight
SequenceSelected
RunStore sequence bundle provenance
```

必须实际运行现有 sequence bundle focused tests。不得复制或替换 P9.1/P9.2 loader/runtime。

---

## 必须先阅读

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/CONFIG_SCHEMA.md`
4. `docs/DATA_MODEL.md`
5. `docs/IMPLEMENTATION_ORDER.md` P9
6. `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
7. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
8. `workers/core_worker.md`
9. `workers/storage_worker.md`
10. `workers/sync_worker.md`
11. `workers/qa_worker.md`

检查当前实现：

```text
src/qulab/config/parser.py
src/qulab/config/runner.py
src/qulab/core/context.py
src/qulab/core/executor.py
src/qulab/sequence_bundles.py
src/qulab/sequence_runtime.py
src/qulab/sequence_preflight.py
src/qulab/storage/run_store.py
src/qulab/gui/controller.py
examples/generate_rabi_sequence_bundle.py
configs/experiments/dry_run_rabi_sequence_bundle.yaml
```

---

## 严格任务范围

### 必须实现

- typed generator/provider/spec/plan/result models；
- explicit provider registry/import；
- `sequence_plans` schema parsing/normalization；
- fixed/linspace/range/explicit sampling；
- deterministic Cartesian grid and loop order；
- framework-owned concrete file/manifest packaging；
- atomic immutable cache keyed by plan hash；
- `sequence_sweep` authoring macro compiler；
- preparation API used by CLI runner and OperatorController；
- generated bundle loading through P9.1；
- existing P9.2 preflight/runtime integration；
- generation/parameter provenance passed to RunStore；
- headless built-in Rabi provider and dry-run config；
- tests and docs。

### 明确不实现

- 不实现 channel/pulse picker；
- 不实现 generic start/duration/end transform；
- 不实现 following/group shift 或 anchor graph；
- 不实现 Qt GUI；
- 不实现 Ramsey/Hahn Echo production families；
- 不实现 zip/table/adaptive sampling；
- 不改变 executor scan semantics；
- 不在 generation/Prepare 阶段连接任何硬件；
- 不允许 provider 自己写 manifest 或调用 ASG。

---

## 推荐模块

```text
src/qulab/sequence_generation/
  __init__.py
  models.py
  errors.py
  registry.py
  sampling.py
  compiler.py
  materializer.py
  preparation.py
  providers/
    __init__.py
    rabi.py
```

可根据现有项目风格合并小文件，但公共职责必须保持清楚。不要创建与 `qulab.sequence_bundles` 重复的 manifest model。

建议测试：

```text
tests/unit/test_sequence_generation_models.py
tests/unit/test_sequence_generation_sampling.py
tests/unit/test_sequence_generation_registry.py
tests/unit/test_sequence_generation_compiler.py
tests/unit/test_sequence_generation_materializer.py
tests/unit/test_sequence_generation_preparation.py
tests/integration/test_generated_rabi_dry_run.py
tests/integration/test_generated_sequence_provenance.py
```

---

## 公共类型契约

至少提供等价类型：

```python
@dataclass(frozen=True)
class SourceIdentity:
    provider: str
    version: str
    source_path: str | None
    source_sha256: str | None

@dataclass(frozen=True)
class SequenceParameterSpec:
    name: str
    label: str
    dtype: str
    unit: str | None
    default: object
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[object, ...] | None = None
    sweepable: bool = True
    role: str = "sequence_parameter"
    safety_class: str = "configure_no_output"

@dataclass(frozen=True)
class SequenceFamilySpec:
    id: str
    version: str
    label: str
    output_format: str
    parameters: tuple[SequenceParameterSpec, ...]
    resource_capability: str = "pulse_sequencer"
    supports_preview: bool = False
    source_identity: SourceIdentity | None = None

@dataclass(frozen=True)
class GeneratedSequencePoint:
    sequence_bytes: bytes
    extension: str
    metadata: Mapping[str, Any]

@dataclass(frozen=True)
class SequenceSweepPlan:
    id: str
    resource: str
    provider: str
    provider_version: str | None
    parameters: Mapping[str, ParameterValuePlan]
    sampling_mode: str
    sampling_order: tuple[str, ...]
    template: Path | None
    materialize: MaterializePolicy
```

所有 model 提供 JSON/YAML-safe `to_dict()`。Path、tuple、bytes 不得直接泄漏到 metadata/config serialization；sequence bytes 只交给 materializer。

---

## Provider Contract

推荐 protocol：

```python
class SequenceGeneratorProvider(Protocol):
    def describe(self) -> SequenceFamilySpec: ...

    def validate_plan(self, plan: SequenceSweepPlan) -> SequencePlanValidationResult: ...

    def generate_point(
        self,
        parameters: Mapping[str, Any],
        *,
        template: Path | None,
    ) -> GeneratedSequencePoint: ...

    def preview_point(...): ...  # optional; A 可返回 None
```

规则：

1. `describe()` 和 `generate_point()` 不连接硬件。
2. provider 返回 concrete bytes，不写 manifest。
3. provider 不枚举 scan grid。
4. provider 不决定 entry id、filename、hash 或 cache path。
5. unknown/missing parameter 必须报结构化 validation issue。
6. provider version request 与 `describe().version` 不一致时 fail closed。
7. provider source identity/hash 可追溯。
8. module import error 包装为稳定 `SequenceGenerationError`，保留 cause。
9. 本阶段允许可信本地代码同进程运行；如果实现 helper process，必须有 JSON-safe request/result、timeout 和 clean cancellation，但不要扩大成安全 sandbox 项目。

Provider registry 只加载显式 dotted path或显式 built-in id，不扫描并 import 任意目录中的所有 Python 文件。

---

## Authoring Config Schema

必须支持：

```yaml
sequence_plans:
  rabi_main:
    resource: asg
    family:
      provider: qulab.sequence_generation.providers.rabi
      version: "1"
    parameters:
      laser_init_s:
        mode: fixed
        value: 3e-6
      tau_s:
        mode: linspace
        start: 20e-9
        stop: 2e-6
        points: 101
      readout_s:
        mode: fixed
        value: 2e-6
    sampling:
      mode: cartesian
      order: [tau_s]
    materialize:
      cache: true
      max_points: 10000
```

规则：

- plan id、parameter name 使用稳定 identifier；
- resource 必须存在并支持 `pulse_sequencer`；
- config 参数必须出现在 family spec；
- spec required/default 规则必须明确；
- canonical framework unit 使用 SI；
- fixed parameter 不进入 scan coords；
- swept parameter必须 `sweepable: true`；
- `sampling.order` 恰好包含所有 swept parameters，每个一次；
- initial `sampling.mode` 只允许 `cartesian`；
- empty/non-finite/invalid values 报错；bool 不当作 number；
- point count 在生成前计算；超过 `max_points` fail closed；
- plan exported coordinate 默认等于 parameter name；如支持 `expose_as`，必须检查 collision。

Preparation/compiler必须在compiled config生成统一parameter definitions，例如：

```yaml
parameters:
  laser_init_s:
    value: 3e-6
    unit: s
    role: sequence_parameter
    plan: rabi_main
  tau_s:
    unit: s
    role: sequence_coordinate
    plan: rabi_main
```

`parse_experiment_config()`应在构建context时把literal fixed `parameters.<name>.value`初始化为
`ExperimentContext.parameters`；swept参数仍由现有`ScanStep`逐点写入。这样普通workflow
call可安全使用`${laser_init_s}`，且sequence参数与其他仪器共享同一parameter context。
同名existing scan、existing fixed parameter或多个plan参数若unit/meaning/value不一致，
Prepare必须报`sequence_plan_name_collision`，不能按后加载覆盖。

旧 config 缺少 `sequence_plans` 时不触发 generation，结果保持不变。

---

## Sampling Semantics

实现纯函数：

```python
normalize_parameter_values(spec, raw_plan) -> tuple[Any, ...]
enumerate_plan_points(plan, family_spec) -> Iterable[PlanPoint]
estimate_point_count(plan) -> int
```

模式：

- `fixed`: `value`；
- `linspace`: inclusive `start/stop/points`，`points >= 1`；
- `range`: 明确定义 stop inclusive/exclusive，必须与现有 `ScanValues.range` 一致并有 boundary tests；
- `explicit`: non-empty ordered `values`。

Cartesian nesting以 `sampling.order` 从外到内。生成 entry coordinate mapping 只含 swept parameters，参数完整 mapping 同时包含 fixed + current swept values。

禁止使用集合导致顺序不稳定。浮点值序列必须与 compiled workflow 使用同一 normalized list，不能一边 numpy、一边 Python 重新计算导致 bundle coverage mismatch。

---

## Materializer Contract

推荐 API：

```python
materialize_sequence_plan(
    plan: SequenceSweepPlan,
    provider: SequenceGeneratorProvider,
    *,
    cache_root: Path,
) -> MaterializedSequenceBundle
```

职责：

1. 对 normalized points 逐点调用 provider。
2. 验证 result bytes 非空、extension 安全、metadata JSON-safe。
3. framework 生成稳定 entry id和无冲突 filename。
4. 写 concrete file并计算 SHA-256。
5. framework 生成 schema v1 manifest。
6. manifest generator metadata包含 provider/version/source hash、plan hash、template hash。
7. 用 P9.1 `load_sequence_bundle()` 重新读取并验证。
8. coverage 必须与 normalized point list 完全匹配。
9. 生成到 temporary sibling目录，全部成功后 atomic rename。
10. 失败清理 temp，不覆盖已有 valid cache。

默认 cache：

```text
.qulab/cache/sequence_bundles/<plan_id>/<plan_hash>/
```

tests 必须传 `tmp_path`，不得污染项目 cache或 `runs/`。

`plan_hash` 至少包含 normalized plan、ordered values、provider id/version/source hash、template bytes hash、generation schema version。相同输入 cache hit；任一输入变化 cache miss。cache hit仍通过 manifest/file hash validation，不能信任损坏 cache。

不要把 `output_dir` 暴露为普通 provider 参数。框架控制写入位置。

---

## `sequence_sweep` Compiler Contract

Authoring macro：

```yaml
procedure:
  - sequence_sweep:
      plan: rabi_main
      body:
        - measurement:
            name: rabi_point
            body:
              - call: daq.configure_counter
                args: {...}
              - run: {...}
```

MVP 约束：

- macro `body` 必须包含且只包含一个顶层 `measurement`；否则给清楚 compiler error；
- compiler 按 `sampling.order` 生成 nested existing `scan` nodes；
- scan values直接使用 materializer 的 normalized explicit values，避免数值漂移；
- 在 measurement body 最前插入：

```yaml
- call: asg.load_sequence_from_bundle
  args:
    bundle: generated_rabi_main
    coordinates:
      tau_s: "${tau_s}"
```

- bundle id稳定、可从 plan id推导且 collision checked；
- fixed parameters写入compiled top-level `parameters`并由parser初始化到context；不得创建假 scan；
- authoring `config.yaml` 不被 in-place mutation；
- compiled `resolved_config` 包含 generated `sequence_bundles` declaration和 canonical workflow；
- executor继续只看到现有 `scan/measurement/call/run`。

多维例子必须测试外/内 loop order和 point坐标顺序。

---

## Preparation API and Existing Integration

不要把有文件写入副作用的 generation偷偷塞进低层 `parse_experiment_config()`。

推荐 API：

```python
prepare_sequence_config(
    config: Mapping[str, Any],
    *,
    cache_root: Path | None = None,
) -> SequencePreparationResult

prepare_and_parse_experiment_config(...) -> ParsedExperiment
```

`SequencePreparationResult` 至少包含：

- untouched/deep-copied authoring config；
- compiled/resolved config；
- normalized plans；
- generated bundle registry或 manifest declarations；
- generation records/provenance；
- validation issues；
- cache root/cache hit信息。

Integration：

- `run_dry_config()` 识别 Phase E authoring config并调用 preparation；
- `OperatorController.prepare()` 调用 preparation并显示统一 issues；
- `OperatorController.start_run()` 必须使用最近一次成功 Prepare 的 frozen result，配置改变后失效；
- hardware connect发生在 Prepare成功之后；
- legacy config 走轻量 no-op preparation；
- direct `parse_experiment_config()` 对 legacy/compiled config保持当前行为；若收到未prepared macro，给明确错误并指向 preparation API，不要静默忽略。

不得在 Prepare 中 import/连接 pycontrol vendor SDK。

---

## Rabi Provider

新增一个 headless、无模板依赖的最小 provider用于固定 contract：

```text
qulab.sequence_generation.providers.rabi
```

至少参数：

- `laser_init_s` fixed；
- `tau_s` sweepable；
- `readout_s` fixed；
- 可选 `mw_start_s`、`trigger_delay_s`，如加入必须有清楚约束。

输出必须是当前 pycontrol ASG JSON compatible concrete bytes，单位转换明确。metadata 至少包含：

- `duration_s`；
- `required_acquisition_s` 或 `readout_window_s`；
- `trigger_channels`；
- `output_channels`；
- parameter snapshot。

此 provider是 contract fixture，不在 A 中声称覆盖所有实验 Rabi timing。

---

## Provenance Contract

扩展 RunStore输入/metadata，不破坏现有 sequence bundle字段：

```text
artifacts/sequence_generation/<plan_id>/sequence_plan.yaml
artifacts/sequence_generation/<plan_id>/provider_identity.json
artifacts/sequence_generation/<plan_id>/generation_log.txt
```

metadata compact summary：

```json
{
  "experiment_parameters": {
    "tau_s": {"unit":"s","mode":"linspace","role":"sequence_coordinate","plan":"rabi_main"}
  },
  "sequence_generation": [{
    "plan_id":"rabi_main",
    "plan_hash":"...",
    "provider":"...rabi",
    "provider_version":"1",
    "provider_source_hash":"...",
    "template_sha256":null,
    "bundle_id":"generated_rabi_main",
    "manifest_sha256":"...",
    "point_count":101,
    "cache_hit":false,
    "status":"generated"
  }]
}
```

完整 plan/values放 artifact和 `resolved_config.yaml`，不向 metadata复制大 grid。DataPoint coords和 SequenceSelected继续由 compiled workflow/P9.2产生。

---

## Error/Issue Codes

至少稳定支持：

```text
sequence_provider_not_found
sequence_provider_import_failed
sequence_provider_version_mismatch
sequence_parameter_unknown
sequence_parameter_missing
sequence_parameter_invalid
sequence_parameter_unit_invalid
sequence_sweep_empty
sequence_sweep_too_large
sequence_plan_name_collision
sequence_generation_failed
sequence_output_invalid
sequence_cache_invalid
sequence_macro_invalid
```

配置/Prepare错误必须在 hardware connection前出现。不要只依赖整段异常字符串；tests断言 code和关键上下文。

---

## 测试矩阵

至少覆盖：

1. provider describe和source identity。
2. unknown provider/import failure/version mismatch。
3. fixed、linspace、range、explicit values。
4. invalid/empty/non-finite/unknown parameter。
5. deterministic Cartesian 2D order。
6. max_points在 generation前阻止。
7. same input得到same plan hash/cache hit。
8. parameter/provider/template变化导致cache miss。
9. partial generation不留下final bundle。
10. invalid provider bytes/metadata被拒绝。
11. generated manifest可被P9.1加载并全coverage。
12. compiler生成正确nested scans和bundle action。
13. load action位于measurement内，SequenceSelected具有point_id。
14. authoring config未被in-place mutation。
15. old bundle config preparation no-op且行为不变。
16. `run_dry_config()`运行generated Rabi成功。
17. 2D coords顺序与SequenceSelected entry一致。
18. RunStore保存plan/provider/generation provenance。
19. generation failure不connect mock/real resources。
20. tests不需要Qt、hardware或vendor SDK。

---

## 示例与文档

新增：

```text
configs/experiments/dry_run_rabi_sequence_plan.yaml
```

它只能包含authoring plan和`sequence_sweep`，不能提交预生成的大bundle到git。

更新：

```text
docs/CONFIG_SCHEMA.md
docs/DATA_MODEL.md
docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md
docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md
docs/IMPLEMENTATION_ORDER.md
```

只标记E1/E2完成；E3/E4/E5保持planned。

---

## 验收命令

```bash
python -m pytest tests/unit/test_sequence_generation_models.py
python -m pytest tests/unit/test_sequence_generation_sampling.py
python -m pytest tests/unit/test_sequence_generation_registry.py
python -m pytest tests/unit/test_sequence_generation_compiler.py
python -m pytest tests/unit/test_sequence_generation_materializer.py
python -m pytest tests/unit/test_sequence_generation_preparation.py
python -m pytest tests/integration/test_generated_rabi_dry_run.py
python -m pytest tests/integration/test_generated_sequence_provenance.py
python -m pytest
```

执行两次同一dry-run，报告第一次generation和第二次cache hit；tests使用temp cache/run root。

---

## 完成定义

- 改YAML中的Rabi `tau_s`范围即可生成新的bundle；
- 无需手写manifest、bundle block或load action；
- compiled workflow只使用现有scan/runtime；
- generation/validation先于hardware connect；
- generated config可dry-run，old config不回归；
- parameter/plan/provider/bundle/point provenance完整；
- E3 generic transform和E4 GUI未混入本worker；
- focused和全量tests通过。

---

## 最终汇报格式

1. 修改文件。
2. 最终公共API/import path。
3. authoring YAML与compiled YAML摘要。
4. plan hash/cache规则。
5. Prepare与hardware安全顺序。
6. Rabi dry-run point/entry结果。
7. provenance文件/metadata字段。
8. 测试命令和结果。
9. 给P9.3B/P9.3C的handoff与未实现项。
