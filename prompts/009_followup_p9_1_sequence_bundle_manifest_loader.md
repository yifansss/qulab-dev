# Prompt 009-followup P9.1: Sequence Bundle Manifest Model + Loader Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是完成 P9 的第一个小目标：实现完全离线、与硬件无关的 sequence bundle manifest 数据模型、配置解析、路径解析、hash、entry 匹配与 coverage 校验。这个 worker 只完成 P9 Phase A + Phase B，不接入 executor，不加载 ASG，不修改 GUI。

---

## /goal

在当前 `qulab` 项目中实现稳定、可测试、向后兼容的 Sequence Bundle 基础层，使 Qulab 能够：

1. 从实验 YAML 顶层可选 `sequence_bundles` 声明加载 manifest。
2. 解析 manifest 中的 bundle、coordinate、entry、sequence file 和可选 metadata。
3. 正确解析项目相对路径和 manifest 相对路径。
4. 计算 manifest 与 concrete sequence 文件的 SHA-256。
5. 使用 `exact`、`nearest` 或 `id` 策略，在纯 Python 中把 coordinate 映射到唯一 entry。
6. 对给定 point coordinate 集合执行 coverage 校验。
7. 在缺失 manifest、缺失 sequence 文件、重复 coordinate、非法 tolerance 或无法匹配时给出稳定、清楚、可测试的错误。
8. 保证旧实验 YAML、单一 `resources.asg.sequence_file` 和现有 sequence editor bridge 行为完全不变。

本目标完成后，项目应具备一个可靠的离线 bundle 基础库，但实验运行时仍不会自动选择或加载 bundle entry。运行时接入属于后续 `P9.2`。

---

## 必须先阅读

开始修改前必须完整阅读：

1. `PROJECT_BLUEPRINT.md`
2. `docs/ARCHITECTURE.md`
3. `docs/IMPLEMENTATION_ORDER.md` 中 P9
4. `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
5. `docs/CONFIG_SCHEMA.md`
6. `docs/NAMING_AND_GIT.md`
7. `workers/core_worker.md`
8. `workers/sync_worker.md`
9. `workers/qa_worker.md`

同时检查当前实现，不要凭 prompt 假设接口仍未变化：

```text
src/qulab/paths.py
src/qulab/sequence_files.py
src/qulab/config/loader.py
src/qulab/config/parser.py
src/qulab/config/errors.py
src/qulab/core/context.py
src/qulab/instruments/profiles.py
tests/unit/test_project_paths.py
tests/unit/test_config_parser.py
tests/unit/test_sequence_artifacts.py
tests/integration/test_bench_templates_parse.py
```

执行 `rg` 确认是否已经存在 sequence bundle 代码。如果已存在部分实现，应在现有实现上补齐，不得创建第二套平行模型。

---

## 当前事实与兼容边界

当前项目已经支持：

- workflow `scan` 和 `${parameter}` 引用；
- 单个 `resources.<asg>.sequence_file`；
- workflow 中的 `asg.load_sequence(sequence_file=...)`；
- 项目根目录相对路径解析；
- sequence 文件 snapshot/hash 和 RunStore artifact；
- standalone sequence editor bridge。

本 worker 必须保持：

- workflow `scan` 是唯一执行语义；
- `sequence_bundles` 是可选配置；
- 没有 `sequence_bundles` 的旧 YAML 解析结果和 dry-run 行为不变；
- Qulab 不解析、改写或编译 pulse internals；
- manifest loader 不连接任何硬件，也不 import vendor SDK；
- sequence 文件仍是 concrete file，不在 core 中抽象成 pulse entity。

---

## 严格任务范围

### 必须实现

- manifest dataclass/model；
- manifest loader；
- config 顶层 `sequence_bundles` 解析；
- project-relative 与 manifest-relative path 规则；
- manifest/sequence SHA-256；
- entry 唯一性和 coordinate 校验；
- `exact`、`nearest`、`id` 纯函数解析；
- coverage report；
- 完整 unit/integration tests；
- schema/architecture 文档同步。

### 明确不实现

- 不修改 `ExperimentExecutor` 的执行行为；
- 不调用 `asg.load_sequence`；
- 不新增 GUI 控件；
- 不实现 fixed/linspace/range 自动生成 workflow scan；
- 不实现 pre-run generator hook；
- 不修改 standalone sequence editor 文件格式；
- 不做真实硬件测试；
- 不把 bundle 的全部 sequence 文件预先复制进 RunStore。

如果发现这些需求确实需要后续处理，只在最终 handoff 中记录，不要扩张本 worker 范围。

---

## 推荐文件布局

优先使用一个清晰、无 Qt、无硬件依赖的模块：

```text
src/qulab/sequence_bundles.py
```

如实现规模明确需要 package，也可使用：

```text
src/qulab/sequences/__init__.py
src/qulab/sequences/bundles.py
```

二者只选一种。不得同时保留两个公共入口。已有 `src/qulab/sequence_files.py` 继续负责单文件 snapshot/artifact，不要把其职责全部搬走。

建议新增测试：

```text
tests/unit/test_sequence_bundle_manifest.py
tests/unit/test_sequence_bundle_resolution.py
tests/unit/test_sequence_bundle_coverage.py
tests/integration/test_sequence_bundle_config_parse.py
```

建议新增一个可读的小型示例 bundle：

```text
configs/sequences/examples/rabi_tau_bundle/manifest.yaml
configs/sequences/examples/rabi_tau_bundle/sequences/tau_20ns.json
configs/sequences/examples/rabi_tau_bundle/sequences/tau_40ns.json
configs/sequences/examples/rabi_tau_bundle/sequences/tau_60ns.json
```

示例 sequence 必须是当前 Qulab/pycontrol ASG JSON 能读取的 concrete 文件。不要引入另一种虚构格式。

---

## Manifest Schema Contract

必须支持 schema version 1：

```yaml
schema_version: 1
kind: sequence_bundle
id: rabi_tau
resource: asg
format: pycontrol_asg_json

coordinates:
  tau_s:
    unit: s
    values: [20e-9, 40e-9, 60e-9]

entries:
  - id: tau_20ns
    coordinates: {tau_s: 20e-9}
    sequence_file: sequences/tau_20ns.json
    metadata:
      duration_s: 8e-6
      trigger_channels: [ch6]
      output_channels: [ch1, ch2, ch6]
```

必填字段：

- `kind`，值必须为 `sequence_bundle`；
- `id`，非空 snake_case 或稳定 identifier；
- `resource`，非空 resource name；
- `entries`，非空 list；
- 每个 entry 的 `id`；
- 每个 entry 的 `coordinates`；
- 每个 entry 的 `sequence_file`。

可选字段：

- `schema_version`，缺省可按 version 1 处理，但未知大版本必须报错；
- `format`；
- `coordinates.<name>.unit`；
- `coordinates.<name>.values`；
- `entries[].metadata.duration_s`；
- `entries[].metadata.trigger_channels`；
- `entries[].metadata.output_channels`；
- `entries[].sha256`；
- `generator`，本 worker 只保留并序列化 metadata，不执行。

不得把未知可选 metadata 静默丢弃。可以放入 `extra`/`metadata` mapping，以便 provenance 后续使用。

---

## Experiment Config Contract

实验 YAML 顶层支持可选 mapping：

```yaml
sequence_bundles:
  rabi_tau:
    manifest: configs/sequences/examples/rabi_tau_bundle/manifest.yaml
    resource: asg
    match:
      mode: nearest
      tolerance:
        tau_s: 1e-15
```

规则：

1. key `rabi_tau` 是 config 中引用 bundle 的稳定 ID。
2. manifest 内 `id` 必须与 config key 一致；不一致时必须报清楚错误，不能静默重命名。
3. config `resource` 如果存在，必须与 manifest `resource` 一致。
4. resource 必须存在于 `resources`，且具有 `pulse_sequencer` capability；无法确认 capability 时至少检查 resource 存在，并提供明确 issue。
5. `match.mode` 只允许 `exact|nearest|id`。
6. `nearest` 必须为每个参与近邻匹配的 numeric coordinate 提供非负有限 tolerance；不得默认无限 nearest。
7. `sequence_bundles` 缺省、`null` 或空 mapping 均不得破坏旧 config。

将结果暴露在 `ParsedExperiment` 的显式字段中，例如：

```python
sequence_bundles: dict[str, SequenceBundle]
```

不要把运行时对象写回 `config` 或 `resolved_config`，两者必须继续可 YAML 序列化。

---

## 数据模型与公共 API

推荐提供不可变或受控 dataclass：

```python
@dataclass(frozen=True)
class SequenceBundleEntry:
    id: str
    coordinates: Mapping[str, Any]
    sequence_file: Path
    sha256: str
    metadata: Mapping[str, Any]

@dataclass(frozen=True)
class SequenceBundleSelection:
    bundle_id: str
    resource: str
    entry_id: str
    requested_coordinates: Mapping[str, Any]
    entry_coordinates: Mapping[str, Any]
    sequence_file: Path
    sequence_sha256: str
    manifest_path: Path
    manifest_sha256: str
    metadata: Mapping[str, Any]

@dataclass(frozen=True)
class BundleCoverageIssue:
    code: str
    message: str
    coordinates: Mapping[str, Any] | None = None

@dataclass(frozen=True)
class BundleCoverageReport:
    ok: bool
    matched: int
    requested: int
    issues: tuple[BundleCoverageIssue, ...]
```

公共 API 至少应表达以下能力；命名可根据现有风格微调，但必须保持同等清晰度：

```python
load_sequence_bundle(
    manifest: str | Path,
    *,
    declared_id: str | None = None,
    declared_resource: str | None = None,
    match: Mapping[str, Any] | None = None,
    validate_files: bool = True,
) -> SequenceBundle

bundle.resolve(
    coordinates: Mapping[str, Any] | None = None,
    *,
    entry_id: str | None = None,
    mode: str | None = None,
    tolerance: Mapping[str, float] | None = None,
) -> SequenceBundleSelection

validate_bundle_coverage(
    bundle: SequenceBundle,
    points: Iterable[Mapping[str, Any]],
) -> BundleCoverageReport
```

不要返回松散的多层 dict 作为唯一公共接口。需要 YAML/JSON 输出时，为 model 提供 `to_dict()`，并确保 Path 转为稳定字符串。

---

## 路径与 Hash 规则

路径处理必须遵守现有 `src/qulab/paths.py`：

1. experiment config 中的 manifest path 按 project-relative 解析；
2. manifest 内 `entries[].sequence_file` 优先相对 manifest 所在目录解析；
3. absolute path 可读取，但 provenance 必须保留明确 source path；
4. 不允许依赖启动时 cwd；
5. Windows 和 macOS/Linux 路径测试都不能写死平台分隔符；
6. missing file 的错误必须包含 bundle id、entry id 和解析后的 path；
7. SHA-256 对原始文件 bytes 计算，不对 YAML re-dump 后的内容计算；
8. entry 声明了 `sha256` 时，必须与实际文件一致，否则 fail closed；
9. 同一 loader 调用内可避免重复 hash，但不要引入全局陈旧 cache。

---

## Entry 校验与匹配语义

### Structural validation

- entry id 在 bundle 内唯一；
- coordinate name 非空且稳定；
- 每个 entry 的 coordinate key 集合必须一致；
- 如果 manifest 声明 `coordinates.<name>.values`，entry 值必须被该集合覆盖；
- 同一 coordinate tuple 不得指向两个 entry；
- bool 不得被误当作 numeric coordinate；
- numeric values 必须有限，拒绝 NaN/Inf；
- `duration_s` 如存在必须为有限正数；
- channel metadata 如存在必须为非空字符串 list。

### `exact`

- 请求必须给出 bundle 所需全部 coordinate；
- 数字 exact 使用值相等，不暗含 tolerance；
- 0 个匹配报 `no_match`；
- 多个匹配报 `ambiguous_match`，虽然 structural validation 应尽量提前阻止。

### `nearest`

- 仅 numeric coordinate 可做 nearest；
- 每个 numeric coordinate 必须有显式 tolerance；
- 所有维度都在 tolerance 内才是 candidate；
- 选择归一化距离最小的唯一 candidate；建议使用 `abs(delta) / tolerance` 的平方和；
- tolerance 为 0 时等价于该维 exact；
- 最近距离并列必须报 `ambiguous_match`，不能按文件顺序选一个；
- string/enum coordinate 必须 exact match。

### `id`

- 必须显式提供 `entry_id`，或从定义清楚的单一参数获取；
- entry id 不存在时报包含 bundle id 和 entry id 的错误；
- 不得把 coordinate 字符串猜测成 entry id。

定义稳定的异常层次，例如：

```text
SequenceBundleError
  SequenceBundleManifestError
  SequenceBundleValidationError
  SequenceBundleResolutionError
```

配置 parser 应把 bundle 配置/manifest 错误转换或包装为当前项目使用的 `ConfigLoadError`，并保留原始原因链。

---

## Coverage Contract

`validate_bundle_coverage()` 是纯离线函数：

- 输入是预计运行的 point coordinate mapping iterable；
- 每个 point 使用 bundle 的 configured match policy；
- 返回匹配数量和逐点 issue；
- 不因为第一个 miss 就停止，尽量汇总所有 miss；
- issue 必须包含请求 coordinate；
- duplicate requested points 可以匹配，但 report 应可保留 requested count；
- coverage 函数不得连接 ASG 或复制文件。

本 worker 不要求自动从任意复杂 workflow 提取 Cartesian points。可以在 tests 中直接提供 point list。workflow-aware preflight 属于 P9.2。

---

## 测试矩阵

至少覆盖：

1. 三个 `tau_s` entry 的有效 manifest 可加载。
2. manifest path 使用 project-relative path。
3. sequence path 使用 manifest-relative path。
4. manifest 和每个 sequence 的 hash 正确且稳定。
5. experiment config 缺少 `sequence_bundles` 时旧解析行为不变。
6. experiment config bundle id/resource mismatch 报清楚错误。
7. missing manifest 报错。
8. missing sequence file 报错并包含 entry id/path。
9. duplicate entry id 报错。
10. duplicate coordinate tuple 报错。
11. coordinate key 不一致报错。
12. declared SHA-256 mismatch 报错。
13. `exact` 正确匹配和 no-match。
14. `nearest` 在 tolerance 内正确匹配。
15. `nearest` 超 tolerance 报错。
16. `nearest` 距离并列报 ambiguous。
17. `id` 正确匹配和 missing id。
18. coverage 同时报告多个缺失点。
19. optional metadata 被保留并可序列化。
20. Windows 风格输入或 Path 对象不会因 cwd 不同而失效。

tests 必须只使用临时目录或项目内无害示例文件，不得 import NI/ASG vendor SDK，不得要求 Qt。

---

## 文档更新

实现完成后同步更新：

```text
docs/CONFIG_SCHEMA.md
docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md
docs/IMPLEMENTATION_ORDER.md
```

只把 P9 Phase A/B 标记为已完成；P9 Phase C/D/E/F 保持 planned。文档必须明确：bundle 基础层已存在，但运行时尚未自动加载 bundle entry。

---

## 验收命令

worker 必须实际执行并报告：

```bash
python -m pytest tests/unit/test_sequence_bundle_manifest.py
python -m pytest tests/unit/test_sequence_bundle_resolution.py
python -m pytest tests/unit/test_sequence_bundle_coverage.py
python -m pytest tests/integration/test_sequence_bundle_config_parse.py
python -m pytest
```

如果文件名根据现有布局调整，应执行等价的 focused tests。不得只报告“代码看起来正确”。

还应执行一个无硬件 smoke：

```bash
python -c "from qulab.sequence_bundles import load_sequence_bundle; print(load_sequence_bundle('configs/sequences/examples/rabi_tau_bundle/manifest.yaml').id)"
```

若最终公共 import path 不同，应使用实际路径给出等价命令。

---

## 完成定义

只有同时满足以下条件才可宣告完成：

- schema v1 manifest 可稳定加载；
- concrete sequence path 与 hash 正确；
- 三种匹配策略定义明确并有测试；
- coverage 可离线验证多个 point；
- `ParsedExperiment` 可访问 bundle models；
- 旧 YAML 和全量 tests 不回归；
- 没有引入 executor、GUI、hardware side effect；
- 文档准确标记 Phase A/B 完成、P9.2 待完成。

---

## 最终汇报格式

worker 最终回答必须包含：

1. 实际新增/修改的文件。
2. 最终公共 API 和 manifest schema 的简短说明。
3. 路径、hash、match、coverage 的关键语义。
4. 向后兼容情况。
5. 实际运行的测试命令与结果。
6. 明确列出未实现项：runtime load、preflight/RunStore provenance、generator hook、GUI scan authoring。
7. 给 P9.2 worker 的具体 handoff，包括公共类型/import path 和任何需注意的限制。

