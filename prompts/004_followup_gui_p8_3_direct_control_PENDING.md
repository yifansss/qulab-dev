# Prompt 004-followup P8.3: Direct Control Submode Worker - PENDING

P8.3 Direct Control Submode 的详细 worker prompt 后续再给出。

原因：

- Direct Control 会涉及真实硬件手动控制、安全分级、授权门槛和 bench commissioning workflow。
- 该 prompt 需要和 `prompts/006_bench_commissioning_worker.md`、hardware safety policy、真实实验台联调流程对齐后再写。
- 不应和 P8.1 ASG Sequence Bridge 或 P8.2 Operator Parameters 混在同一个 worker 里。

后续 prompt 应覆盖：

- Direct Control submode UI。
- resource/action display model。
- safety class：`read_only`、`connect`、`configure_no_output`、`output`、`analog_output`、`unknown`。
- 默认禁用危险动作。
- ASG channel constant-on / start / stop 的授权门槛。
- NI AO 写入授权门槛。
- MW output 和 AWG play 授权门槛。
- 与 bench workflow / event logging 的关系。
- 无硬件默认测试和 import safety。
