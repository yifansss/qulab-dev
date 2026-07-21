> **面向量子传感 / NV / 固态自旋实验的轻量化实验编排与数据框架。**
> 驱动层兼容已有 `pycontrol`，流程层像 Python for-loop 一样直观，配置层像 LabVIEW block diagram / Scratch 一样可视，数据层像 QCoDeS 一样可追溯，但整体比 LabVIEW 更轻、更适合版本管理、更容易扩展。

------

**价值判断**

这个事情非常有价值，但要分阶段。

内部价值很高。你们以后一定会遇到这些问题：二维/三维扫描、平均、暂停恢复、实验参数记录、不同仪器组合、不同 setup 切换、重复实验复现、数据追踪、多人使用。现在不抽象，后面每个实验都会长出一份“半复制半改”的脚本和面板，维护成本会迅速爆炸。

外部价值也有，但门槛更高。想真正“对标并超越 LabVIEW / labscript / QCoDeS”，不是靠功能堆满，而是靠一个非常清晰的使用模型：

1. 新人能 10 分钟跑一个 ODMR / Rabi / Ramsey。
2. 熟练用户能用 Python 写复杂流程。
3. 面板用户能用图形化流程块搭实验。
4. 每次实验自动保存完整 provenance：参数、仪器状态、驱动版本、代码版本、数据、图、日志。
5. 换仪器时只换 adapter，不改实验逻辑。

如果做到这些，在 NV / 量子传感这个垂直领域是很有竞争力的。

------

**工作量评估**

AI 帮忙会明显降低工程实现成本，但不会消除“实验模型设计”和“硬件联调”的成本。

粗略估计：

| 阶段                         | 目标                                                         | AI 辅助后工作量 |
| ---------------------------- | ------------------------------------------------------------ | --------------- |
| MVP                          | 支持已有 3-4 类仪器、单参数/二维扫描、HDF5/SQLite 存储、实时绘图、Python API | 3-6 周          |
| 可用版 v0.2                  | GUI 流程编辑、仪器子面板、实验模板、暂停/停止/异常恢复、配置校验 | 2-3 个月        |
| 稳定版 v0.5                  | 插件化驱动、模拟器、批量实验、数据浏览器、分析 pipeline、文档教程 | 4-8 个月        |
| 对外发布版 v1.0              | 跨实验室可安装、完善文档、示例实验、测试体系、硬件兼容层     | 8-12 个月       |
| 真正挑战 LabVIEW/QCoDeS 生态 | 社区、插件、标准化、长期维护                                 | 1-2 年以上      |

如果只为你们组内部好用，**3 个月可以做出非常有用的版本**。
如果要变成“广大研究者都能迁移使用”的框架，至少要按 **半年到一年** 规划。

------

**核心建议：不要强行统一所有仪器，而是统一“能力”**

你担心“不同类型、不同厂商仪器做统一接口困难”，这个担心非常正确。

不要设计这种接口：

```
instrument.set(value)
instrument.run()
instrument.read()
```

这会过度抽象，最后什么都表达不了。

应该设计成 **Capability-based Interface**，也就是仪器声明自己具备哪些能力：

```
MicrowaveSource:
    set_frequency()
    set_power()
    output_on()
    output_off()

PulseSequencer:
    load_sequence()
    arm()
    start()
    stop()

DAQCounter:
    configure_counter()
    arm()
    read_counts()

AnalogOutput:
    set_voltage()
    sweep_voltage()

WaveformGenerator:
    upload_waveform()
    play_sequence()
```

一个真实仪器可以实现多个 capability。例如 NI 板卡可以同时是：

```
AnalogInput
AnalogOutput
CounterInput
TriggerReceiver
ClockSource
```

国仪 ASG 可以是：

```
PulseSequencer
DigitalOutput
TriggerSource
ClockParticipant
```

这样实验流程只依赖能力，不依赖具体型号。

------

**推荐整体架构**

我建议分成 7 层，保持强大但不臃肿：

```
qulab/
  core/
    parameter.py       # 参数、单位、扫描范围、依赖关系
    procedure.py       # Step / Loop / Scan / Average / Branch
    executor.py        # 实验执行引擎
    context.py         # 实验上下文、当前参数、资源句柄
    events.py          # 数据点、日志、状态、异常事件

  instruments/
    base.py            # Instrument, Capability, Adapter
    registry.py        # 仪器注册表
    profiles.py        # setup 配置和连接信息
    adapters/
      pycontrol_asg.py
      pycontrol_ni.py
      pycontrol_lmx.py
      pycontrol_awg.py

  sync/
    trigger_plan.py    # 触发、时钟、arm/start/read 的协调计划
    timing_model.py    # 不做复杂编译器，但描述同步关系
    validators.py      # 检查触发线、采样率、等待时间是否合法

  storage/
    run_store.py       # 每次实验 run 的数据写入
    metadata.py        # 参数、仪器状态、版本、日志
    formats.py         # HDF5 / Zarr / SQLite index

  plotting/
    live_plot.py       # 实时曲线、二维 heatmap
    subscribers.py     # 监听 executor 事件
    analysis.py        # ODMR/Rabi/Ramsey fit 可后加

  gui/
    main_window.py
    instrument_panels/
    sequence_editor_bridge.py
    procedure_editor.py
    data_browser.py

  experiments/
    odmr.py
    rabi.py
    ramsey.py
    pulsed_odmr.py
```

核心思想：

```
驱动只负责“怎么和仪器说话”
adapter 负责“把具体仪器翻译成能力”
procedure 负责“实验逻辑”
executor 负责“按顺序、可停止、可记录地执行”
storage 负责“所有东西都能复现”
GUI 只是 procedure/config 的编辑器，不直接写死实验逻辑
```

------

**实验流程 DSL 的样子**

你说的“像 for 循环嵌套两层”非常关键。这个框架应该同时支持 Python API 和 YAML/JSON config。

Python 版本可以这样：

```
exp = Experiment("rabi_2d_scan")

mw = exp.resource("mw")
asg = exp.resource("asg")
daq = exp.resource("daq")

exp.setup(
    mw.set_power(-10),
    asg.load_sequence("rabi.seq"),
    daq.configure_counter(sample_rate=1e5, samples=1000),
)

with exp.scan("mw_freq", linspace(2.86e9, 2.88e9, 101)):
    mw.set_frequency(P("mw_freq"))

    with exp.scan("tau", linspace(20e-9, 2e-6, 100)):
        asg.set_sequence_param("tau", P("tau"))

        with exp.average(100):
            exp.run_once(
                asg.arm(),
                daq.arm(),
                asg.start(),
                data=daq.read_counts(name="counts"),
            )

exp.plot.heatmap(x="mw_freq", y="tau", z="counts")
```

Config 版本可以这样：

```
name: rabi_2d_scan

resources:
  mw:
    type: microwave_source
    driver: pycontrol.lmx2572
    port: COM5

  asg:
    type: pulse_sequencer
    driver: pycontrol.asg24100
    sequence: rabi.seq

  daq:
    type: daq_counter
    driver: pycontrol.ni
    device: Dev2

setup:
  - mw.set_power: -10
  - mw.output_on: true
  - asg.load_sequence: rabi.seq
  - daq.configure_counter:
      sample_rate: 100000
      samples: 1000

procedure:
  - scan:
      name: mw_freq
      values: { start: 2.86e9, stop: 2.88e9, points: 101 }
      body:
        - mw.set_frequency: ${mw_freq}

        - scan:
            name: tau
            values: { start: 20e-9, stop: 2e-6, points: 100 }
            body:
              - asg.set_param:
                  tau: ${tau}

              - average:
                  count: 100
                  body:
                    - run:
                        steps:
                          - asg.arm
                          - daq.arm
                          - asg.start
                          - daq.read_counts:
                              save_as: counts

plot:
  - heatmap:
      x: mw_freq
      y: tau
      z: counts
```

这就是你说的“面向对象但直观”的实验语言。GUI 以后可以直接编辑这个结构。

------

**关于仪器子面板怎么放**

你的直觉也是对的：**具体仪器的复杂设置应该放在仪器自己的子面板里**，不要塞进主实验流程。

例如：

国仪 ASG 子面板负责：

```
通道映射
脉冲序列编辑
触发方式
loop 次数
输出电平
sequence 参数列表：tau, laser_width, mw_width, readout_delay...
```

微波源子面板负责：

```
频率
功率
开关
参考时钟
扫频能力声明
```

NI 子面板负责：

```
AI/AO/Counter 通道
采样率
采样点数
触发源
内部路由
计数模式
```

实验流程只关心：

```
set mw frequency
set sequence parameter tau
arm daq
start pulse
read counts
save counts
```

这样主流程不会被每个厂商的细节污染。

------

**硬件同步必须做到的东西**

你们的核心架构应该以 **国仪 ASG + NI DAQ** 为中心。

最低要求：

1. ASG 作为主触发源，发 TTL 给 NI。
2. NI 在外部触发或门控下采集，不靠 Python sleep 对齐。
3. 所有需要同步的设备都要有 `arm -> trigger/start -> read` 三阶段模型。
4. 实验执行器必须区分“配置阶段”和“运行阶段”。
5. 每个 step 要能声明自己是否阻塞、是否硬件定时、是否软件定时。
6. 运行前做 preflight：触发线、采样率、采样窗口、序列周期、平均次数是否匹配。
7. 记录 sync plan：哪个设备触发哪个设备，触发边沿、线缆、通道、时钟源是什么。
8. 出错时必须安全关断：微波关、激光关、ASG stop、DAQ task close。

建议内部模型：

```
SyncPlan(
    master="asg",
    trigger_edges=[
        Trigger(source="asg.ch5", target="ni.PFI0", edge="rising"),
    ],
    participants=["asg", "daq"],
    order=["configure", "arm_daq", "arm_asg", "start_asg", "read_daq"],
)
```

不需要一开始做复杂 timing compiler，但一定要有这个 `SyncPlan`，否则之后联调会乱。

------

**数据存储建议**

不要只用数据库，也不要只用一堆 CSV。

推荐：

```
每次实验一个 run folder
大数组数据：HDF5 或 Zarr
索引/查询：SQLite
配置快照：YAML/JSON
日志：text/jsonl
图：png/html
```

结构：

```
data/
  2026-06-26/
    20260626_153012_rabi_2d/
      config.yaml
      resolved_config.yaml
      data.h5
      metadata.json
      events.jsonl
      preview.png
      notebook.ipynb
```

必须保存：

```
实验名
开始/结束时间
用户
完整 config
扫描参数
每个仪器连接信息
每个仪器关键状态
驱动版本
git commit hash
sequence 文件快照
错误日志
实时数据点
最终数据
```

这点是“超越 LabVIEW”的关键之一：**复现能力和数据治理**。

------

**Outstanding Features 可以这样设计**

真正有辨识度的功能，我建议做这些：

1. **Readable Experiment Config**
   实验可以用 YAML 表达，也可以用 Python API 生成。
2. **Procedure Graph / Loop Blocks**
   支持 `setup / scan / average / run / cleanup / on_error`，以后 GUI 可以变成类 Scratch 的块编辑器。
3. **Capability-based Instrument Adapter**
   不统一厂商接口，统一“能力”。这会比传统 driver abstraction 更现实。
4. **Preflight Check**
   实验开始前检查参数范围、仪器连接、触发关系、采样窗口、数据 shape。
5. **Dry Run / Simulation Mode**
   不接硬件也能跑完整流程，生成假数据，方便写实验和教学。
6. **Full Provenance Data Store**
   每个数据点都知道来自哪个参数、哪个 config、哪个序列、哪个仪器状态。
7. **Live Plot as Subscriber**
   绘图不嵌死在实验逻辑里，而是订阅 executor 的数据事件。
8. **Pause / Stop / Resume**
   长时间二维扫描必须能中断、保存、继续。
9. **Template Experiments**
   ODMR、Rabi、Ramsey、Hahn Echo、T1、Pulsed ODMR 作为模板。
10. **Instrument Subpanel Auto-generation**
       每个 adapter 提供参数 schema，GUI 自动生成基础控制面板。

------

**和几个系统的对标**

LabVIEW 强在图形化和硬件集成，但版本管理差、复杂实验容易变成难维护的大图。你们可以在“文本 config + GUI 编辑 + Git 可追踪”上超过它。

Labscript 强在时序实验编译和 shot-based control，但对你们来说可能太偏“时序编译系统”。你们应该吸收它的 run manager / connection table 思想，而不是复制它。

QCoDeS 强在 parameter、dataset、measurement loop 和仪器驱动生态，但对 NV 这类强触发、强时序、强 GUI 的实验不够开箱即用。你们可以在“量子传感实验模板 + ASG/NI 同步 + 轻 GUI”上形成优势。

PyMeasure 轻量好用，但流程表达能力和复杂数据 provenance 不够强。你们可以吸收它的 Procedure/Worker 思想。

------

**我建议的开发路线**

第一阶段不要做大而全，先做一个最小闭环：

```
已有 pycontrol adapter
Experiment / Scan / Average / RunOnce
HDF5 + metadata
实时 matplotlib/pyqtgraph plot
一个 ODMR 示例
一个 Rabi 示例
```

第二阶段再做 GUI：

```
仪器连接页
仪器子面板
流程树编辑器
扫描参数编辑器
实时图
数据浏览
```

第三阶段才做：

```
插件系统
图形化 block editor
远程控制
批量任务队列
分析 pipeline
外部发布文档
```

最重要的一句话：

> 这个框架的灵魂不是“统一所有仪器”，而是“统一实验意图”：setup、scan、average、trigger、read、save、plot、resume。

只要这个模型立住，国仪 ASG、NI 板卡、微波源、AWG 都只是能力提供者。这样架构会很强，但不会一开始就臃肿。