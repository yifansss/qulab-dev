# Config Schema

实验 config 使用 YAML。目标是人能读、GUI 能生成、AI 能编辑、CLI 能执行。

## 1. 顶层字段

```yaml
schema_version: 1
name: example
description: optional text
tags: [odmr, nv]

resources: {}
sequence_bundles: {}
sync: {}
setup: []
procedure: []
cleanup: []
plot: []
storage: {}
operator_parameters: []
```

## 2. Resources

```yaml
resources:
  mw:
    adapter: pycontrol_lmx
    capabilities: [microwave_source]
    port: COM5
    simulation: false

  asg:
    adapter: pycontrol_asg
    capabilities: [pulse_sequencer, trigger_source]
    address: auto
    sequence_file: configs/sequences/rabi.seq
    simulation: false
```

要求：

- resource key 使用 snake_case。
- adapter 使用 snake_case。
- capabilities 必须是已知 capability。
- hardware-only 参数保留在 resource 自己下面。
- ASG/AWG 等 sequence-capable resource 可以声明 `sequence_file`、`sequence_params`、`trigger_mode` 等资源级默认配置；主 procedure 仍通过 `load_sequence`、`set_sequence_param`、`arm`、`start` 等步骤表达运行逻辑。

### 2.1 多个同类仪器

同一类仪器可以出现多次，用 resource name 区分角色。实验流程依赖 resource name，不依赖“只能有一个 mw”。

例如两个微波源：

```yaml
resources:
  mw_drive:
    adapter: mock_microwave
    capabilities: [microwave_source]
    simulation: true

  mw_probe:
    adapter: mock_microwave
    capabilities: [microwave_source]
    simulation: true
```

一个固定、一个扫描：

```yaml
setup:
  - call: mw_drive.set_frequency
    args: { freq_hz: 2.87e9 }
  - call: mw_drive.set_power
    args: { power_dbm: -10 }

procedure:
  - scan:
      name: probe_freq_hz
      values: { start: 2.86e9, stop: 2.88e9, points: 101 }
      body:
        - call: mw_probe.set_frequency
          args: { freq_hz: ${probe_freq_hz} }
        - measurement:
            name: point
            body:
              - run:
                  name: readout
                  steps:
                    - call: daq.read_counts
                      save_as: counts
```

两个都扫描：

```yaml
procedure:
  - scan:
      name: drive_freq_hz
      values: { start: 2.86e9, stop: 2.88e9, points: 51 }
      body:
        - call: mw_drive.set_frequency
          args: { freq_hz: ${drive_freq_hz} }
        - scan:
            name: probe_freq_hz
            values: { start: 2.80e9, stop: 2.95e9, points: 151 }
            body:
              - call: mw_probe.set_frequency
                args: { freq_hz: ${probe_freq_hz} }
              - measurement:
                  name: point
                  body:
                    - run:
                        name: readout
                        steps:
                          - call: daq.read_counts
                            save_as: counts
```

GUI 和 storage 应显示/保存两个坐标：`drive_freq_hz` 和 `probe_freq_hz`。实时图可以先选择一个主 x 轴，完整数据仍按 point record 保存所有坐标。

当前可运行示例是 `configs/experiments/dry_run_two_mw_scan.yaml`。它默认使用两个 `mock_microwave` resource，因此可在无硬件机器上 parse 和 dry-run。真实硬件时保持 `mw_drive`、`mw_probe` 这类角色名不变，只把对应 resource 的 adapter 改为 `pycontrol_lmx`，补充 `port`、`baudrate`、`output_type`、`simulation: false`。Qulab 默认从项目内 `drivers/pycontrol` 导入驱动；只有需要覆盖默认驱动树时才写 `pycontrol_path`。

硬件模板：

- `configs/setups/real_nv_setup.template.yaml`：只描述真实资源和 sync，不执行输出动作。
- `configs/experiments/hardware_odmr.template.yaml`：低风险 ODMR 模板，可 parse/preflight；默认不包含 `mw.output_on` 或 `asg.start`。

## 3. Call Step

```yaml
- call: mw.set_frequency
  args:
    freq_hz: ${mw_freq}
```

要求：

- `call` 格式为 `<resource>.<method>`。
- 参数引用使用 `${param_name}`。
- 不允许在 YAML 内写任意 Python 表达式。

所有 step 都支持可选顶层 `enabled` 字段：

```yaml
- enabled: false
  call: mw.output_on
```

默认 `enabled: true`。Parser 会把该字段映射到 core `Step.enabled`，executor 会跳过 disabled step。GUI 保存时允许显式写出 `enabled: true/false`，后续 serializer 可以选择省略默认 true。

## 4. Scan Step

```yaml
- scan:
    name: mw_freq
    values:
      start: 2.86e9
      stop: 2.88e9
      points: 101
    body: []
```

支持 values：

- explicit list：`values: [1, 2, 3]`
- linspace：`{start, stop, points}`
- range：`{start, stop, step}`

## 5. Average Step

```yaml
- average:
    name: avg
    count: 100
    reducer: mean
    body: []
```

MVP reducers：

- `mean`
- `sum`
- `none`

## 6. Run Step

```yaml
- run:
    name: pulse_readout
    timeout_s: 10
    steps:
      - call: daq.arm
      - call: asg.arm
      - call: asg.start
      - call: daq.read_counts
        save_as: counts
```

`run` 表示一个硬件同步执行单元。后续 sync validator 会检查 run 内的 arm/start/read 顺序。

## 6.1 Wait Step

```yaml
- wait:
    name: mw_settle
    duration_s: 0.05
    reason: wait for microwave source settling
```

也可以简写为：

```yaml
- wait: 0.05
```

`wait` 表示宏观流程中的等待或 settling 时间。dry-run 执行时只发出 step 事件，不实际 sleep；非 dry-run 执行时会等待 `duration_s` 秒。精密脉冲时序仍应由 ASG/AWG/DAQ 硬件完成，不应靠 `wait` 对齐纳秒或微秒级事件。

## 6.2 Measurement Step

`measurement` 表示一个扫描点内部的完整测量子流程。它可以包含多个 `call`、`average`、`run`、`save`、`analyze` step。

示例：

```yaml
- measurement:
    name: rabi_point
    save_raw: true
    snapshots: [asg, daq, mw]
    body:
      - call: mw.set_frequency
        args: { freq_hz: ${mw_freq_hz} }
      - call: asg.set_sequence_param
        args: { name: tau_s, value: ${tau_s} }
      - average:
          count: ${averages}
          reducer: mean
          body:
            - run:
                name: pulse_readout
                timeout_s: 10
                steps:
                  - call: daq.arm
                  - call: asg.arm
                  - call: asg.start
                  - call: daq.read_counts
                    save_as: photon_bins
                  - call: daq.read_analog
                    save_as: analog_trace
      - analyze:
          method: summarize_counts
          inputs: [photon_bins]
          outputs: [counts_mean, counts_std]
```

要求：

- 每个 `measurement` 执行时生成唯一 `point_id`。
- `save_raw: true` 时保存单点内部的原始数组或 shot records。
- `snapshots` 指定该点需要记录哪些仪器状态。
- `analyze` 只做轻量单点处理，复杂离线分析放到 analysis pipeline。

高维扫描示例：

```yaml
procedure:
  - scan:
      name: magnetic_field_v
      values: { start: -1.0, stop: 1.0, points: 21 }
      body:
        - call: coil.set_voltage
          args: { voltage: ${magnetic_field_v} }
        - scan:
            name: mw_freq_hz
            values: { start: 2.86e9, stop: 2.88e9, points: 101 }
            body:
              - scan:
                  name: tau_s
                  values: { start: 20e-9, stop: 2e-6, points: 100 }
                  body:
                    - measurement:
                        name: full_point_record
                        save_raw: true
                        body:
                          - call: mw.set_frequency
                            args: { freq_hz: ${mw_freq_hz} }
                          - call: asg.set_sequence_param
                            args: { name: tau_s, value: ${tau_s} }
                          - run:
                              name: pulse_and_acquire
                              steps:
                                - call: daq.arm
                                - call: asg.arm
                                - call: asg.start
                                - call: daq.read_counts
                                  save_as: photon_bins
```

## 7. Sync

```yaml
sync:
  master: asg
  triggers:
    - source: asg.ch5
      target: daq.PFI0
      edge: rising
      purpose: readout_gate
  order:
    configure: [mw, asg, daq]
    arm: [daq, asg]
    start: [asg]
    read: [daq]
```

## 8. Plot

```yaml
plot:
  - type: line
    x: mw_freq
    y: counts

  - type: heatmap
    x: mw_freq
    y: tau
    z: counts
```

## 9. Operator Parameters

`operator_parameters` 是给 GUI operator parameters submode 使用的可选声明。它不改变实验语义，只描述哪些 config/procedure 字段应集中显示给操作者快速修改。

```yaml
operator_parameters:
  - name: tau_start_s
    label: Tau start
    unit: s
    source: procedure.scan[tau_s].values.start
    widget: number
    min: 0

  - name: averages
    label: Averages
    source: procedure.average[avg].count
    widget: integer
    min: 1

  - name: sequence_file
    label: ASG sequence
    source: resources.asg.sequence_file
    widget: file_picker
```

要求：

- `name` 使用 snake_case。
- `source` 指向 YAML/config model 中的字段路径。
- `operator_parameters` 只影响 GUI 呈现和快速编辑，不允许隐藏真实 procedure/config。
- GUI 修改 operator parameter 后必须同步更新 workflow model 和保存后的 YAML。
- 如果未声明 `operator_parameters`，GUI 可以从 scan、average、常见 call args、resource sequence_file 和 storage backend 自动提取常用参数。
- 危险硬件动作不应通过 operator parameter 暗中触发；输出类动作应放入 Direct Control submode 并接受 safety gate。

当前 PyQt Operator Console 支持的 `source` MVP：

- `procedure.scan[<name>].values.start|stop|points|step`
- `procedure.scan[<name>].values`
- `procedure.average[<name>].count`
- `setup.call[<resource.method>].args.<arg>`
- `procedure.call[<resource.method>].args.<arg>`
- `cleanup.call[<resource.method>].args.<arg>`
- `resources.<name>.sequence_file`
- `storage.backend`
- `storage.backends`

显式声明优先按 YAML 顺序显示，自动发现会补充未重复的 source。source 当前不存在但可创建时，GUI 显示 warning，并在用户 apply 后写入同一份 raw config。

ASG sequence 的 canonical quick-edit source 是 `resources.<name>.sequence_file`。`asg.load_sequence` 仍可以保留在 workflow 中表达宏观动作，但自动发现 Operator Parameters 时应跳过 `asg.load_sequence` 的 `sequence`/`path`/`sequence_file` call arg，避免和 resource-level sequence file 出现两个现场设置入口。

## 10. ASG Sequence File and Parameter Binding

ASG sequence 文件属于 resource/instrument panel 管理，主 procedure 只引用它。常见配置：

```yaml
resources:
  asg:
    adapter: pycontrol_asg
    capabilities: [pulse_sequencer, trigger_source]
    sequence_file: configs/sequences/rabi.seq
    sequence_params:
      tau_s: ${tau_s}
      laser_width_s: 3e-6
    trigger_mode: external_or_software
```

procedure 中仍建议显式表达单点测量动作：

```yaml
procedure:
  - scan:
      name: tau_s
      values: { start: 20e-9, stop: 2e-6, points: 101 }
      body:
        - measurement:
            name: rabi_point
            body:
              - call: asg.load_sequence
                args:
                  sequence_file: configs/sequences/rabi_readout.json
              - call: asg.set_sequence_param
                args: { name: tau_s, value: ${tau_s} }
              - run:
                  name: pulse_readout
                  steps:
                    - call: daq.arm
                    - call: asg.arm
                    - call: asg.start
                    - call: daq.read_counts
                      save_as: counts
```

规则：

- Qulab 不在主 workflow tree 中展开 sequence 内部的纳秒/微秒 pulse。
- GUI ASG 子面板应能打开 standalone sequence editor、刷新 sequence hash 和可扫描参数。
- 一次实验可以多次调用 `asg.load_sequence`。resource-level `resources.asg.sequence_file` 是默认 sequence；每个 workflow `asg.load_sequence` step 可以用 `args.sequence_file`、`args.path` 或 `args.sequence_path` 绑定自己的点内脉冲文件。
- Operator Parameters 应为每个 `asg.load_sequence` occurrence 提供独立 file picker，同时避免把旧的 `args.sequence` 字符串当作 sequence 文件入口。
- 运行数据应记录每个 sequence reference 的 source path、artifact copy、hash、mtime、参数绑定和必要的 channel/trigger snapshot。
- 当前 bridge 只负责 import-safe 文件检查、sha256、简单 `${param}`/channel 检测和外部 editor wrapper；无法估算 duration 时会在 preflight snapshot 中显示 warning。
- 左侧 resource 区显示 sequence preview；`sequence_file` 的选择和编辑应通过 `Operator Parameters` 或 `Builder Workflow` 设置区域写入 resource config。

## 11. Sequence Bundle Runtime (P9.1 + P9.2)

当前 parser 支持可选顶层 `sequence_bundles`，executor 支持显式
`resource.load_sequence_from_bundle` workflow action。扫描执行语义仍只由
`procedure.scan` 表达；bundle action 消费当前 point coordinate，选择 concrete entry，
然后委托 resource 已有的 `load_sequence(sequence_file=...)`。

```yaml
sequence_bundles:
  rabi_tau:
    manifest: configs/sequences/examples/rabi_tau_bundle/manifest.yaml
    resource: asg
    match:
      mode: nearest
      tolerance: {tau_s: 1e-15}
```

规则：

- `sequence_bundles` 缺省、`null` 或 `{}` 时旧配置行为不变。
- mapping key 必须与 manifest `id` 一致；可选 `resource` 必须与 manifest `resource` 一致。
- resource 必须存在；显式声明 capability 时必须包含 `pulse_sequencer`。
- manifest path 按 project-relative 规则解析，不依赖启动 cwd。
- `match.mode` 只允许 `exact`、`nearest`、`id`；`nearest` 的每个 numeric coordinate 都必须声明 finite、non-negative tolerance。

Manifest schema version 1：

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
      output_channels: [ch1, ch6]
generator:
  tool: standalone_sequence_editor
```

Entry sequence path 相对 manifest 目录解析。loader 对 manifest 原始 bytes 和 concrete sequence 原始 bytes 计算 SHA-256；entry 声明 `sha256` 时不一致会 fail closed。未知 top-level、entry-level 和 metadata 字段会保留，供后续 provenance 使用。

公共离线 API 位于 `qulab.sequence_bundles`：`load_sequence_bundle()`、`SequenceBundle.resolve()`、`validate_bundle_coverage()`。`ParsedExperiment.sequence_bundles` 暴露加载后的显式模型；`config` 和 `resolved_config` 中仍只保留可 YAML 序列化的原始声明。

Canonical workflow：

```yaml
procedure:
  - scan:
      name: tau_s
      values: [20e-9, 40e-9, 60e-9]
      body:
        - measurement:
            name: rabi_point
            body:
              - call: asg.load_sequence_from_bundle
                args:
                  bundle: rabi_tau
                  coordinates: {tau_s: "${tau_s}"}
              - call: asg.compile_sequence
              - run:
                  steps:
                    - call: daq.arm
                    - call: asg.arm
                    - call: asg.start
                    - call: daq.read_counts
                      save_as: counts
```

`bundle` 必须是顶层 registry 中的 id，action resource 必须等于 manifest resource。
`coordinates` 在 action 执行时通过当前 `ExperimentContext` 解析。成功调用 adapter
的 `load_sequence` 后才发出 `SequenceSelected`；不需要 `save_as` 才能记录 provenance。

Prepare/preflight 会静态枚举 action 外层、且被 coordinates 引用的 scan 维度，并检查：

- `bundle_unknown`、`bundle_resource_mismatch`；
- `bundle_coverage_missing`、`bundle_coverage_ambiguous`；
- `bundle_trigger_channel_mismatch`；
- `bundle_trigger_route_mismatch`、`bundle_trigger_edge_mismatch`；
- `bundle_acquisition_window_short`。

Entry metadata 中 acquisition duration 的优先级为
`required_acquisition_s`、`readout_window_s`、`duration_s`。缺少 optional trigger 或
duration metadata 只产生 warning。静态 preflight 只验证配置与 metadata 一致性，不能
证明物理接线或 NI 型号实际支持某条 route。

主程序/Operator 面板可以直接打开
`configs/experiments/dry_run_rabi_sequence_bundle.yaml`，点击 Prepare 后再 Start。当前面板
尚没有自动创建 scan/bundle 的专用控件；需要在 Builder/YAML 中写出上述 canonical
workflow。Phase E 将用 `Sequence Sweep` submode 和 `sequence_sweep` compiler 消除这些
手写步骤。旧 `resources.asg.sequence_file` 和直接 `asg.load_sequence` 继续受支持。

离线生成示例：

```bash
PYTHONPATH=src python examples/generate_rabi_sequence_bundle.py /path/to/rabi_bundle --tau-ns 20 40 60
```

PowerShell：

```powershell
$env:PYTHONPATH = "src"
python examples/generate_rabi_sequence_bundle.py C:\data\rabi_bundle --tau-ns 20 40 60
```

脚本先写 concrete ASG JSON 和 manifest；随后把 experiment config 的 `manifest` 指向生成
的 `manifest.yaml` 即可。它是当前兼容用的离线脚本，不是规划中的 Phase E Sequence
Family / Sweep Generator。

规划文档：

```text
docs/PARAMETERIZED_EXPERIMENT_ARCHITECTURE_PLAN.md
docs/SEQUENCE_FAMILY_GENERATOR_PHASE_E_PLAN.md
```

### 11.1 Planned Phase E Authoring Schema

Phase E 将增加一个 source-of-truth `sequence_plans`，由 GUI 或 YAML 描述 provider、模板、
固定参数、扫描参数和 pulse 联动规则。框架负责生成 concrete sequence、manifest、
`sequence_bundles` runtime 声明和 canonical workflow，用户不再维护四份重复信息。

Curated Rabi 示例：

```yaml
sequence_plans:
  rabi_main:
    resource: asg
    family:
      provider: analysis_modules.sequence_generators.rabi
      version: "1"
    parameters:
      laser_init_s: {mode: fixed, value: 3e-6}
      tau_s:
        mode: linspace
        start: 20e-9
        stop: 2e-6
        points: 101
      readout_s: {mode: fixed, value: 2e-6}
    sampling:
      mode: cartesian
      order: [tau_s]

procedure:
  - sequence_sweep:
      plan: rabi_main
      body:
        - measurement:
            name: rabi_point
            body: []
```

`sequence_sweep` 是 authoring macro。Prepare/compiler 必须把它展开为现有 `scan` 和
`resource.load_sequence_from_bundle`；executor 不增加第二套 scan engine。原始
`config.yaml` 保留 authoring plan，`resolved_config.yaml` 保存生成后的 bundle declaration
和 canonical workflow。

通用 template provider 还可声明结构化 `targets`、`transform`、`propagation` 和
`constraints`。YAML 不允许任意 Python 表达式；依赖关系使用可验证的 anchor/offset schema。

计划中的其他可选顶层字段包括：

```yaml
parameters: {}
scans: {}
bindings: []
sequence_plans: {}
```

P9.1/P9.2 已启用 bundle loader、runtime、preflight 和 provenance；`parameters`、
`scans`、`bindings` 和 `sequence_plans` 仍作为后续 authoring/metadata 扩展逐步启用。

后续 runtime 实现仍必须满足：

- 旧 config 继续有效。
- `procedure.scan` 仍是 canonical execution semantics。
- P9.1/P9.2 不创建隐藏扫描引擎。Phase E compiler 生成显式 canonical workflow，但 executor
  仍只运行现有 `procedure.scan`。
- ASG sequence-dependent 参数通过 bundle coordinate 绑定，例如 `sequence_bundle.rabi_tau.coordinate.tau_s`。
- 每个 point 解析为 concrete sequence file，再由 `asg.load_sequence` 加载；Qulab core 不负责通用 pulse compiler。
- 运行 metadata 记录参数定义、binding、bundle manifest hash、selected entry id、sequence source/artifact/hash 和 point coordinates。

## 12. Planned Extension: Live Compute and Derived Data

## 11.1 Sequence Generation Authoring (implemented)

`sequence_plans` declares provider-owned SI parameters and `sequence_sweep`
references one plan. Supported value modes are `fixed`, inclusive `linspace`,
inclusive `range` (same semantics as `ScanValues.range`), and ordered
`explicit`; `sampling.order` is Cartesian outer-to-inner order.

```yaml
sequence_plans:
  rabi:
    resource: asg
    family: {provider: rabi, version: "2"}
    parameters:
      tau_s: {mode: linspace, start: 20e-9, stop: 2e-6, points: 101, unit: s}
    sampling: {mode: cartesian, order: [tau_s]}
procedure:
  - sequence_sweep:
      plan: rabi
      body:
        - measurement: {name: rabi_point, body: []}
```

Prepare generates concrete files, manifest, `sequence_bundles`, nested scans,
and the bundle load action. These generated fields are not saved back into the
authoring YAML. Generic `asg_template` plans additionally accept `template`,
`targets`, `groups`, structured `constraints`, and parameter `transform`
blocks. Direct parsing of an unprepared macro is rejected with guidance to use
the preparation API.

当前 schema 已支持可选实时计算/派生量配置；没有 `analysis` 的旧配置保持原行为。

规划文档：

```text
docs/LIVE_COMPUTE_DERIVED_DATA_PLAN.md
docs/SEQUENCE_LIVE_COMPUTE_GUI_INTEGRATION_PLAN.md
```

可选顶层字段：

```yaml
analysis:
  live:
    enabled: true
    fail_policy: warn        # warn | skip | fail
    save_outputs: true
    emit_events: true
    execution: sync          # sync | async (P10.5)
    queue_size: 64           # async only
    backpressure: skip_newest
    drain_on_close: true
    drain_timeout_s: 10
    worker_count: 1
    status_interval_s: 0.5

  modules:
    - name: trace_summary
      module: analysis_modules.trace_window_mean
      class: TraceWindowMean
      enabled: true
      run_live: true
      run_post: false
      show: true
      save: true
      fail_policy: warn
      inputs: [pse_ai1_trace]
      outputs: [signal_mean, baseline_mean, contrast]
      args: {}
```

这些字段已由 parser/preflight、runner 和 OperatorController 使用。`execution` 默认 `sync`；async 当前严格要求 `worker_count: 1`，queue policy 只允许 `skip_newest|skip_oldest|latest|disable_module|fail`。

- Qulab core 只规定模块接口和数据流，不写死具体实验公式。
- 用户计算模块优先放在项目内 `analysis_modules/`。
- raw data 不被 derived data 覆盖。
- derived outputs 可作为单独 data keys 存储。
- P10.2 使用显式 `DerivedData` 与 `AnalysisStatus`，不通过普通 `DataPoint` key name 猜测数据来源。
- `show` 控制 Live View 默认显示，`save` 控制 RunStore 持久化；live-only output 不写入 completed run。
- Live View 只选择和显示 raw/derived keys，不包含公式逻辑。
- Live Run 同时只读显示 P9 sequence plan/bundle/entry/hash context；Sequence Sweep authoring 仍在 Control page。
- RunStore 记录 module name、version、inputs、outputs、args、show/save/fail policy。
- P10.4 post-run recompute 写入版本化 `analysis/<result_id>/` group，不覆盖 raw 或 live-derived data。
- P10.5 async queue 必须有界，backpressure/drop/lag 可见且 raw storage 优先。
