# Prompt 009-followup P9.3B: Generic ASG Template Sweep Provider Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是基于P9.3A公共provider/plan/materializer contract，实现无Qt、无硬件依赖的通用ASG template sweep provider：选择pulse target和start/duration/end/gap等属性，支持多参数、多维Cartesian扫描、following/group propagation与anchor constraints，并生成P9.1可加载的concrete sequence。

---

## /goal

实现比旧MATLAB `SweepSEQ`更通用且确定性的模板扫描：

```text
immutable ASG template
 + point parameters
 + target/property transforms
 + propagation/anchor constraints
 -> validated concrete ASG JSON
```

普通用户之后可通过GUI选择通道、pulse、属性和联动方式，无需为每个Rabi-like实验写Python generator。每个point必须从原模板重算，不能基于上一个point累积修改。

---

## 硬依赖

P9.3A必须已完成且tests通过。开始前读取实际公共接口，不得复制：

- provider protocol；
- `SequenceFamilySpec` / plan/result model；
- sampling/materializer/compiler；
- registry；
- generation error/issue模型。

如果A的接口与prompt示例不同，适配实际接口并在handoff说明，不创建平行体系。

---

## 必须先阅读

1. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
2. `docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md`
3. `docs/CONFIG_SCHEMA.md`
4. `docs/OPERATOR_UI.md`
5. `docs/HARDWARE_SYNC.md`
6. `workers/core_worker.md`
7. `workers/qa_worker.md`
8. P9.3A实现和tests
9. `tools/sequence_editor/sequence_editor.py`
10. `src/qulab/gui/sequence_bridge.py`
11. `src/qulab/sequence_files.py`
12. `drivers/pycontrol/PulseGenerator/`相关ASG loader/driver代码
13. 当前ASG JSON examples和bench configs

重点理解现有JSON字段：`channel_name`、`pulses`、`start_time`、`time_on`、`rise`、`d`、`pbn`、`delay_off`，但不得凭字段名猜语义；用现有editor/driver行为和tests确定单位、结束时间、重复pulse语义。

---

## 严格范围

### 必须实现

- headless ASG JSON load/normalize/serialize model；
- legacy sequence adaptation（如现有格式需要）；
- target alias、selector和template fingerprint；
- start/duration/end/shift/gap transform；
- same-channel/all-channel/named-group propagation；
- structured anchor dependency graph；
- conflict/cycle/stale target/timing validation；
- provider describe/validate/generate/preview-data接口；
- provider metadata用于P9.2 trigger/window preflight；
- 1D/2D/3D point generation tests；
- standalone editor兼容性tests；
- docs。

### 不实现

- 不实现Qt widget或GUI；
- 不修改P9.3A sampling/compiler contract，除非发现明确bug并加regression test；
- 不实现任意Python表达式或字符串eval；
- 不做通用vendor-independent pulse compiler；
- 不连接ASG/NI/MW；
- 不让provider写manifest；
- 不实现adaptive scan；
- 不把Qulab-only pulse ID写入vendor output，除非已验证driver安全接受。

---

## 推荐模块

```text
src/qulab/sequence_generation/providers/asg_template.py
src/qulab/sequence_generation/providers/asg_model.py
src/qulab/sequence_generation/providers/asg_transforms.py
```

如果P9.3A已有providers布局，遵循它。纯model/transform模块不能import Qt或vendor SDK。

建议tests：

```text
tests/unit/test_asg_sequence_model.py
tests/unit/test_asg_template_targets.py
tests/unit/test_asg_template_transforms.py
tests/unit/test_asg_template_propagation.py
tests/unit/test_asg_template_constraints.py
tests/unit/test_asg_template_provider.py
tests/integration/test_generic_asg_template_bundle.py
tests/integration/test_sequence_editor_template_compatibility.py
```

---

## Generic Plan Schema

必须支持等价schema：

```yaml
sequence_plans:
  custom_rabi:
    resource: asg
    family:
      provider: qulab.sequence_generation.providers.asg_template
      version: "1"
    template: configs/sequences/rabi_base.json

    targets:
      mw_pulse:
        channel: Channel 1
        pulse: 0
        fingerprint: optional_saved_fingerprint
      readout_gate:
        channel: Channel 6
        pulse: 0

    groups:
      readout_related: [readout_gate, trigger_pulse]

    parameters:
      tau_s:
        mode: linspace
        start: 20e-9
        stop: 2e-6
        points: 101
        transform:
          target: mw_pulse
          property: duration
          propagation:
            mode: shift_after
            scope: all_channels
            boundary: target_end

    constraints:
      - type: anchor
        target: readout_gate.start
        reference: mw_pulse.end
        offset_s: 1e-6

    sampling:
      mode: cartesian
      order: [tau_s]
```

Unknown target/property/mode/scope必须在Prepare validation时报结构化error。

---

## Headless ASG Model

建立typed或受控model，至少表达：

- logical channel name/index/pbn；
- pulse index和可选alias；
- canonical start/duration/end in seconds；
- format-specific raw fields；
- serialization back tocurrent pycontrol editor/driver JSON。

要求：

1. 输入template绝不in-place修改。
2. parse->serialize未变更模板时保持语义等价；合理保留未知字段。
3. 单位转换集中在model/provider boundary，不散落在transform代码。
4. bool/NaN/Inf/negative timing明确拒绝。
5. raw字段无法无损映射时给warning/error，不静默猜测。
6. channel和pulse顺序稳定。
7. concrete output不包含Path、dataclass或Qulab-only sidecar对象。

对于`rise/d/time_on`的duration/end定义，必须由现有editor/driver contract验证并写入代码注释/tests。不要假定`end = start + time_on`适用于所有重复pulse。

---

## Target Identity and Fingerprint

MVP selector：

```python
PulseSelector(channel="Channel 1", pulse_index=0)
```

同时计算稳定fingerprint，至少包含：

- template SHA-256；
- normalized channel identity；
- pulse index；
- pulse关键结构摘要（不含正在扫描的值或允许masked fields）。

规则：

- alias在plan内唯一；
- channel大小写/`Channel 1`与`ch1` normalization规则清楚且tested；
- selector 0 match -> `sequence_target_missing`；
- multiple match -> `sequence_target_ambiguous`；
- saved fingerprint与当前模板不符 -> `sequence_target_stale`；
- 不因为模板变化自动选择“最像的pulse”；
- future sidecar persistent ID可扩展，但本worker不要求修改vendor JSON。

提供纯查询API给P9.3C GUI：

```python
inspect_template(path) -> TemplateInspection
list_channels(inspection) -> ...
list_pulses(channel) -> ...
build_target_selector(...) -> PulseTargetSpec
```

结果必须JSON-safe且包含display label、start/duration/end和fingerprint。

---

## Transform Semantics

Canonical property names：

- `start` -> set absolute start；
- `duration` -> set high/active duration where format supports；
- `end` -> keep start, derive duration；
- `shift` -> add delta to start；
- `gap_after` -> set target end to next/reference start gap，必须有明确reference/target；
- optional `repeat_count` / `spacing` 仅当ASG model可可靠表达。

所有parameter values使用SI seconds/count。Provider负责转成ASG JSON单位。

Direct transform顺序：

1. clone immutable base；
2. resolve all targets；
3. compute proposed direct writes from completepoint parameters；
4. reject two transforms writing same `(target, property)` unless有显式tested composition；
5. apply independent writes；
6. calculate changed edge deltas；
7. apply propagation/constraints；
8. validate/serialize。

多参数结果不能依赖dict iteration order。声明顺序仅用于display，语义由dependency graph决定。

---

## Propagation Semantics

支持：

```text
mode: none
mode: shift_after, scope: same_channel
mode: shift_after, scope: all_channels
mode: shift_group, group: <name>
mode: constraints
```

`shift_after`：

- threshold基于base template中target boundary；
- delta基于修改后boundary - base boundary；
- `same_channel`只平移同channel、在threshold之后的pulse；
- `all_channels`平移所有channel中在threshold之后的pulse；
- target本身不能被重复平移；
- boundary inclusivity必须明确定义并有相同start time测试；
- protected/anchored pulse冲突时error，不静默覆盖。

`shift_group`：

- group成员由target aliases显式列出；
- missing/duplicate member error；
- group平移同一delta；
- 一个pulse被两个propagation写入时conflict error，除非deltas相同且明确允许去重。

这部分应复现现有standalone editor的“本通道后续/所有通道后续”能力，但headless语义必须比UI checkbox更严格。

---

## Anchor Constraint Graph

Schema：

```yaml
constraints:
  - type: anchor
    target: readout_gate.start
    reference: mw_pulse.end
    offset_s: 1e-6
```

支持anchor points：`start`、`end`，必要时`center`可后置。

规则：

- 构建directed dependency graph；
- topological evaluation；
- cycle -> `sequence_constraint_cycle`并列出cycle；
- multiple writers -> `sequence_transform_conflict`；
- reference/target missing -> target error；
- target start更新时duration默认保持，除非constraint明确写end；
- fixed offset使用SI且finite；
- constraints结果再次进行non-negative/overlap/format validation。

YAML不允许`readout.start = mw.end + gap`表达式字符串；只能结构化字段。

---

## Timing Validation

至少检查：

- start >= 0；
- duration > 0；
- end finite且不早于start；
- provider/ASG支持的min resolution/alignment；
- same channel overlap policy（默认error，若硬件/format允许需显式policy）；
- repeat count/spacing有效；
- generated total duration；
- declared trigger/output channels存在；
- maximum sequence duration/point count若可从driver contract获得则验证，否则warning。

稳定issue codes至少：

```text
sequence_template_invalid
sequence_target_missing
sequence_target_ambiguous
sequence_target_stale
sequence_property_unsupported
sequence_transform_conflict
sequence_constraint_cycle
sequence_timing_negative
sequence_duration_invalid
sequence_overlap
sequence_resolution_invalid
```

---

## Provider Metadata

每个GeneratedSequencePoint metadata至少返回：

- `duration_s`；
- `required_acquisition_s`或`readout_window_s`，只有能可靠推导时；
- `trigger_channels`；
- `output_channels`；
- normalized parameter snapshot；
- target/transform summary；
- template SHA-256；
- provider version。

不要伪造readout window。未知时省略并让P9.2 warning。

---

## Preview Data Contract

给GUI提供无Qt preview data，而不是Matplotlib widget：

```python
@dataclass(frozen=True)
class SequencePreview:
    channels: tuple[PreviewChannel, ...]
    total_duration_s: float
    warnings: tuple[ValidationIssue, ...]
```

每个preview pulse包含alias/selector/start/end/level/label。P9.3C决定如何绘图。

Preview和generate必须使用同一transform engine；不能存在“预览看起来对但生成文件不同”的第二套逻辑。

---

## Tests

至少覆盖：

1. current editor ASG JSON parse/serialize语义等价。
2. unknown fields保留。
3. legacy format adaptation。
4. channel normalization和pulse listing。
5. target fingerprint stable/stale/missing/ambiguous。
6. set_start、set_duration、set_end、shift。
7. same-channel following shift。
8. all-channel following shift。
9. equal-threshold boundary行为。
10. named group shift。
11. transform conflict。
12. anchor chain topological evaluation。
13. anchor cycle/multiple writer。
14. negative timing/zero duration/overlap。
15. each point starts from immutable template。
16. 2D parameter order不改变同坐标output hash。
17. preview与generated model timing一致。
18. metadata duration/channels正确。
19. framework materializer生成P9.1-valid bundle。
20. P9.2 coverage/trigger/window preflight可消费metadata。
21. standalone editor保存的fixture可作为template。
22. 无Qt、无hardware、无vendor SDK tests通过。

property/propagation tests要断言具体pulse timing，不只断言“文件生成成功”。

---

## 示例

新增小型template/config：

```text
configs/sequences/examples/generic_rabi_base.json
configs/experiments/dry_run_generic_asg_template_sweep.yaml
```

示例至少二维：`tau_s`修改MW duration，`readout_delay_s`通过anchor或target移动readout。保持point数很小，不提交大型generated cache/bundle。

---

## 文档更新

更新Phase E文档、CONFIG_SCHEMA和OPERATOR_UI target/propagation术语。只标记E3完成；E4 GUI/E5 families仍planned。

---

## 验收命令

```bash
python -m pytest tests/unit/test_asg_sequence_model.py
python -m pytest tests/unit/test_asg_template_targets.py
python -m pytest tests/unit/test_asg_template_transforms.py
python -m pytest tests/unit/test_asg_template_propagation.py
python -m pytest tests/unit/test_asg_template_constraints.py
python -m pytest tests/unit/test_asg_template_provider.py
python -m pytest tests/integration/test_generic_asg_template_bundle.py
python -m pytest tests/integration/test_sequence_editor_template_compatibility.py
python -m pytest
```

---

## 完成定义

- 任意兼容ASG template可列出channel/pulse并建立稳定target；
- 1D/ND pulse property scan无需写custom generator；
- following/group/anchor联动确定且可验证；
- 每点从immutable template重建；
- output兼容editor/driver并被P9.1/P9.2消费；
- GUI未混入provider/model；
- focused与全量tests通过。

---

## 最终汇报

1. 修改文件和公共API。
2. ASG字段/单位语义。
3. target fingerprint规则。
4. transform/propagation/anchor规则。
5. 2D示例坐标到具体timing/hash结果。
6. metadata/preflight集成。
7. tests结果。
8. 给P9.3C GUI的inspection/preview API handoff。

