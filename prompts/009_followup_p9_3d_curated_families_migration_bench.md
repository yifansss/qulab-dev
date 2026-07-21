# Prompt 009-followup P9.3D: Curated Sequence Families + Migration + Bench Worker

下面这份 prompt 可以直接交给新的 AI worker。目标是在P9.3A/B/C公共contract稳定后，把Phase E从framework demo推进到实验台可用：硬化Rabi family，增加Ramsey与Hahn Echo family，提供existing sequence/template迁移工具，并新增严格安全门控的mock/bench配置与完整provenance验证。

---

## /goal

交付一套可复用、可记录、可上实验台分级验证的curated sequence family体系：

- Operator在GUI选择Rabi/Ramsey/Hahn Echo并调整有物理意义的参数；
- 不编辑generator source；
- 不手写manifest/bundle/workflow plumbing；
- 每个family通过同一A provider contract和B transform/model工具；
- legacy sequence可导入为generic template plan；
- mock dry-run和bench scope/ASG+NI验证分层，默认tests不触发hardware；
- run可重建family/plan/template/generated bundle/selected sequence/data coords。

---

## 硬依赖

P9.3A、P9.3B、P9.3C必须完成并通过full suite。开始前确认公共contract稳定：

- provider spec/registry；
- plan schema/sampling/materializer/compiler；
- generic ASG model/transform/preview；
- Sequence Sweep GUI；
- generation provenance。

本worker不得为了一个family修改公共contract造成其他provider回归。确需修bug时先加contract regression tests，并最小修改。

---

## 必须先阅读

1. `docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md`
2. `docs/EXPERIMENT_BENCH_BRINGUP_GUIDE.md`
3. `docs/BENCH_TEST_CONFIGS.md`
4. `docs/HARDWARE_SYNC.md`
5. `docs/ADAPTER_REQUIREMENTS.md`
6. `docs/DATA_MODEL.md`
7. `workers/experiment_template_worker.md`
8. `workers/adapter_worker.md`
9. `workers/sync_worker.md`
10. `workers/storage_worker.md`
11. `workers/qa_worker.md`
12. P9.3A/B/C实现和tests
13. current bench 03/05/07/09 templates
14. current pycontrol ASG/NI adapters和vendored drivers
15. standalone sequence editor JSON format

---

## 严格范围

### 必须实现

- production-quality Rabi family；
- Ramsey family；
- Hahn Echo family；
- shared family timing helpers built onB model/constraints；
- family parameter specs/units/ranges/metadata/preview；
- legacy concrete sequence -> generic plan migration CLI/API；
- optional offline bundle -> authoring-plan inspection/import assistance；
- mock configs for each family；
- bench generation/scope/ASG+NI templates；
- safety and preflight checks；
- provenance reconstruction tests；
- operator/bench docs。

### 不实现

- 不实现任意新pulse language；
- 不修改executor scan engine；
- 不实现全局Phase F scan editor；
- 不实现closed-loop/adaptive generation；
- 不默认打开MW/ASG/NI AO output；
- 不在default pytest连接hardware；
- 不声称未上台验证的timing已物理验证；
- 不批量添加未经定义和测试的几十个family。

---

## 推荐文件

Provider可放built-in或project-local，但选择一个canonical import路径并记录source identity：

```text
analysis_modules/sequence_generators/
  __init__.py
  common.py
  rabi.py
  ramsey.py
  hahn_echo.py
```

如果`analysis_modules`当前不是installable/import-safe package，可使用：

```text
src/qulab/sequence_generation/providers/experiments/
```

不要同时维护两份production family。examples可以thin wrapper引用canonical provider。

迁移工具：

```text
src/qulab/sequence_generation/migration.py
src/qulab/scripts/sequence_plan_from_template.py
```

建议tests：

```text
tests/unit/test_rabi_sequence_family.py
tests/unit/test_ramsey_sequence_family.py
tests/unit/test_hahn_echo_sequence_family.py
tests/unit/test_sequence_family_invariants.py
tests/unit/test_sequence_plan_migration.py
tests/integration/test_curated_family_dry_runs.py
tests/integration/test_curated_family_provenance.py
tests/integration/test_curated_family_gui_contract.py
tests/hardware/test_generated_sequence_bench.py
```

---

## Family Design Rule

Curated family不是独立手写bundle generator。每个family必须：

1. 实现A的provider contract。
2. 尽量复用B的headless ASG model/transform/constraint。
3. `describe()`声明参数、单位、default、min/max、sweepable和role。
4. 只接收完整point参数，返回concrete bytes/metadata。
5. 不写manifest、不枚举grid、不连接hardware。
6. 同输入产生deterministic bytes/hash。
7. preview和generate共用timing model。
8. 将实验物理假设写入provider docstring和docs，不隐藏在magic constants。

所有时间参数framework boundary使用seconds。Channel assignment应可配置但有安全默认，不把实验室接线写死进核心算法。

---

## Rabi Family Contract

至少参数：

```text
laser_init_s       fixed/sweepable policy explicit
laser_to_mw_s
tau_s              sweepable primary coordinate
mw_to_readout_s
readout_s
trigger_offset_s
sequence_period_s  fixed or derived, policy explicit
```

可配置channel roles：

```text
laser_channel
mw_gate_channel
readout_gate_channel
daq_trigger_channel
```

要求：

- `tau_s`改变时dependent readout/trigger通过anchor graph重算；
- 可选择fixed total period或grow-with-tau policy，不能隐式混用；
- total period不足时preflight error；
- metadata可靠提供duration/output/trigger/readout window；
- 0/负tau、过小resolution、channel collision报错；
- GUI只显示有物理意义参数和read-only dependency summary。

如果laser/readout由同一channel不同pulse表示，target aliases必须清楚。

---

## Ramsey Family Contract

至少参数：

```text
laser_init_s
pi2_1_s
free_evolution_s   sweepable primary coordinate
pi2_2_s
phase_2_deg        fixed or optional explicit sweep if ASG format supports
mw_to_readout_s
readout_s
trigger_offset_s
sequence_period_s
```

要求：

- second pi/2 start anchor to first pi/2 end + free_evolution_s；
- readout/trigger anchor to second pulse；
- phase unsupported bycurrentASG format时parameter不得伪装可用；应明确omit/warn或delegate AWG future provider；
- free evolution变化不累计shift；
- metadata和preview标出两个MW pulse和free evolution区间。

---

## Hahn Echo Family Contract

至少参数：

```text
laser_init_s
pi2_1_s
tau_s              define clearly as half-evolution or full delay
pi_s
pi2_2_s
mw_to_readout_s
readout_s
trigger_offset_s
sequence_period_s
```

必须在label/docs/metadata清楚定义`tau_s`：推荐定义为每个free-evolution arm，total free evolution为`2*tau_s`。不得让GUI和data coords含义模糊。

anchors：

```text
pi.start     = pi2_1.end + tau_s
pi2_2.start  = pi.end + tau_s
readout      = pi2_2.end + mw_to_readout_s
```

要求同Rabi/Ramsey的duration/period/channel/resolution验证。

---

## Shared Invariants

所有family tests必须检查：

- starts/durations finite positive；
- no unintended same-channel overlap；
- trigger channel存在且与sync template一致；
- required acquisition window合理；
- output channels metadata完整；
- fixed/growing period policy；
- parameter boundary/min/max；
- unit conversion；
- point output deterministic；
- each point从immutable base/model生成；
- preview timing等于serialized timing；
- provider version/source identity变化进入plan hash。

不要以“JSON能写出”为验收。

---

## Migration API and CLI

目标：把已有single concrete ASG sequence变成generic template plan起点，不自动猜实验物理意义。

推荐CLI：

```bash
python -m qulab.scripts.sequence_plan_from_template \
  configs/sequences/existing.json \
  --resource asg \
  --plan-id imported_sequence \
  --output configs/experiments/imported_sequence_plan.yaml
```

输出应包含：

- generic provider；
- project-relative template path；
- inspected channel/pulse summary；
- optional target aliases chosen viaCLI args或interactive GUI later；
- fixed parameter placeholders only whenexplicit；
- `sequence_sweep` macro skeleton或safe single-point plan；
- warnings/TODO metadata for unbound pulses。

规则：

- 不覆盖source template；
- output存在时需`--force`，默认fail；
- path使用project-relative helper；
- 不猜“Channel 1一定是MW”或“Pulse 0一定是tau”；
- malformed template报清楚error；
- generated YAML可load/save/Prepare；
- migration result不包含absolute cache path。

可选bundle inspection：读取existing manifest并生成一个只读migration report，指出coordinate names、provider provenance和能否映射到generic plan。不能从concrete bundle可靠反推transform时必须明确说不可逆，不伪造plan。

---

## GUI Integration Contract

P9.3C应自动发现三个family。验证：

- provider selector列出Rabi/Ramsey/Hahn Echo；
- parameter labels/units/modes正确；
- dependency summary清楚；
- first/current/last preview正确；
- range修改使plan stale并需Prepare；
- imported generic plan可打开；
- family config save/reload无损；
- production family不要求显示rawtarget editor，除非用户显式switch generic。

本worker只做family注册和必要小型GUI contract修复，不重构P9.3C layout。

---

## Mock Experiment Configs

新增：

```text
configs/experiments/dry_run_rabi_sequence_family.yaml
configs/experiments/dry_run_ramsey_sequence_family.yaml
configs/experiments/dry_run_hahn_echo_sequence_family.yaml
```

要求：

- point数小；
- 使用mock ASG/DAQ；
- authoring config只含sequence plan/macro，不含手写generated plumbing；
- dry-run产生正确coords、SequenceSelected和data；
- RunStore provenance可重建。

---

## Bench Test Ladder

不要直接跳到完整低温/激光/MW Rabi。新增分层template，编号遵循现有bench文档且不覆盖旧配置：

### Stage 1: Generation only

- real provider parameters，mock resources；
- Prepare/materialize/preflight；
- inspect manifest/hash/preview；
- no connect/output。

### Stage 2: ASG scope generated sequence

- pycontrol ASG；
- generated family bundle选first/middle/last points；
- oscilloscope观察laser/MW/readout/trigger channel；
- explicit `allow_output`；
- NI不参与或只读；
- operator逐点记录expected/measured timing。

### Stage 3: ASG -> NI triggered acquisition

- 复用已验证Bench05 wiring；
- NI先arm，ASG后start；
- generated trigger channel与PFI一致；
- acquisition window覆盖readout；
- scope同时看ASG trigger和detector/AI；
- timeout/route错误保留真实DAQmx信息。

### Stage 4: Low-power Rabi family plan

- MW output必须显式授权；
- 默认低功率、安全frequency/power placeholder；
- operator必须根据实际连接修改port/device/PFI/channel；
- cleanup关闭ASG/MW/DAQ；
- 第一次只运行3-5个tau点；
- scope和RunStore同时验证point->sequence。

Hardware config使用`.template.yaml`，禁止默认pytest执行。hardware test加`@pytest.mark.hardware`和显式environment/flag gate。

---

## Hardware Safety

- generation/preview/Prepare不得connect；
- ASG start、MW output、NI AO仍遵循现有authorization；
- family metadata不能自动启用output；
- missing cleanup/preflight error；
- real config默认`simulation: false`但必须template且需要explicit flags；
- no silent mock fallback for hardware adapter；
- channel mapping和PFI由operator确认；
- static preflight不声称证明physical route；
- generator failure或stale plan阻止connect/output。

---

## Provenance Reconstruction Acceptance

对每个family run，test/reader必须能回答：

1. family/provider/version/source hash是什么？
2. normalized plan和parameter definitions是什么？
3. template/model/channel role配置是什么？
4. scan coordinate和loop order是什么？
5. generated manifest/hash是什么？
6. 每个point加载哪个entry/file/hash？
7. raw DataPoint.coords与sequence coordinate是否一致？
8. cache hit是否影响run artifacts？答案应为不影响可重建性。

增加helper/report如有必要，但不要复制RunReader体系。

---

## Tests

至少覆盖：

1. 三family describe/schema/defaults。
2. Rabi timing/anchors/period policies。
3. Ramsey two-pulse/free-evolution timing。
4. Hahn Echo tau定义和three-pulse timing。
5. min/max/resolution/channel collisions。
6. deterministic hashes。
7. preview/serialized timing一致。
8. metadata trigger/output/acquisition fields。
9. each family 1D dry-run。
10. at least one family 2D dry-run。
11. GUI registry/parameter contract。
12. migration valid template。
13. migration malformed/source-preserved/output-force。
14. migration YAML Prepare成功。
15. full provenance reconstruction。
16. old offline bundle andgeneric provider不回归。
17. bench templates parse without hardware。
18. default tests不connect/import unavailable SDK。
19. hardware tests only run explicit marker/flag。
20. full suite通过。

---

## Documentation

更新：

```text
docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md
docs/CONFIG_SCHEMA.md
docs/OPERATOR_UI.md
docs/DATA_MODEL.md
docs/BENCH_TEST_CONFIGS.md
docs/EXPERIMENT_BENCH_BRINGUP_GUIDE.md
docs/IMPLEMENTATION_ORDER.md
```

文档分别标记`implemented in mock/dry-run`、`bench template ready`、`physically verified`。没有上硬件就不得写physically verified。

---

## 验收命令

```bash
python -m pytest tests/unit/test_rabi_sequence_family.py
python -m pytest tests/unit/test_ramsey_sequence_family.py
python -m pytest tests/unit/test_hahn_echo_sequence_family.py
python -m pytest tests/unit/test_sequence_family_invariants.py
python -m pytest tests/unit/test_sequence_plan_migration.py
python -m pytest tests/integration/test_curated_family_dry_runs.py
python -m pytest tests/integration/test_curated_family_provenance.py
python -m pytest tests/integration/test_curated_family_gui_contract.py
python -m pytest tests/integration/test_bench_templates_parse.py
python -m pytest
```

Hardware test只在用户明确授权和仪器连接确认后：

```bash
python -m pytest tests/hardware/test_generated_sequence_bench.py -m hardware
```

未运行hardware时最终报告必须明确。

---

## 完成定义

- Rabi/Ramsey/Hahn family可从GUI/YAML调整并Prepare；
- 不编辑generator source或generated plumbing；
- legacy sequence可安全导入generic plan；
- mock configs和provenance完整；
- bench ladder/template可操作且默认安全；
- public Phase E contract无family-specific破坏；
- default full suite通过；
- hardware状态如实记录。

---

## 最终汇报

1. 修改文件和provider import paths。
2. 每个family参数与tau定义。
3. migration CLI示例/result。
4. GUI discovery/preview情况。
5. mock dry-run coordinate/entry结果。
6. provenance reconstruction结果。
7. bench templates、安全门和实际硬件测试状态。
8. tests pass/skip。
9. remaining physical validation和Phase F/P10后续。

