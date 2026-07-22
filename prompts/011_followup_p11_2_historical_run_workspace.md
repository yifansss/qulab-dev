# Prompt 011-followup P11.2: Historical Run Workspace and Event Replay Worker

这份 prompt 可直接交给 storage/GUI worker。目标是让用户从历史 run 打开一个完整、只读、可解释的实验现场，而不只是查看单个 dataset。必须诚实区分 recorded、reconstructed、partial 和 unavailable；绝不自动恢复旧硬件输出。

## Dependencies

依赖 P11.1 的 diagnostic contract。可与 P11.3A 并行，但不得同时修改同一 GUI/controller 文件。开始前确认当前 branch/handoff。

## /goal

在现有 Operator Console 内加入 Historical Workspace：

- 选择 run folder；
- 查看 recorded authoring/resolved workflow；
- 查看参数、resources、sync、sequence、analysis provenance；
- 查看 raw/derived/recomputed data；
- 查看 logs/errors/event timeline；
- 将 recorded events 以只读方式 replay 到 Live View/sequence/module status；
- 显示每类信息的 fidelity；
- 支持 `Clone as new experiment`，生成安全的新 draft；
- 不连接、配置或启动硬件，不修改原 run。

## 必须先阅读

- `docs/EXPERIMENT_AUTHORING_DIAGNOSTICS_REPLAY_PLAN.md`
- `docs/DATA_MODEL.md`
- `docs/DATA_VIEWER_REQUIREMENTS.md`
- `docs/OPERATOR_UI.md`
- `src/qulab/storage/run_store.py`
- `src/qulab/storage/run_reader.py`
- `src/qulab/storage/index.py`
- `src/qulab/storage/metadata.py`
- `src/qulab/storage/events.py`
- `src/qulab/gui/controller.py`
- `src/qulab/gui/pyqt_views.py`
- `src/qulab/viewer/pyqt_viewer_app.py`
- live catalog/plot/status/sequence context models
- sequence artifact/provenance and analysis recompute code
- storage/viewer/live integration tests

## Historical fidelity contract

推荐：

```python
class Fidelity(str, Enum):
    RECORDED = "recorded"
    RECONSTRUCTED = "reconstructed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    MISMATCH = "mismatch"

@dataclass(frozen=True)
class HistoricalSectionStatus:
    section: str
    fidelity: Fidelity
    message: str
    artifacts: tuple[str, ...] = ()
```

至少报告 config、resolved config、resources, sync、sequence、analysis、events、points、data、logs。缺文件不能使整个 workspace 崩溃；对应 section 标为 partial/unavailable。

## Reader/model

新增 Qt-free `HistoricalRunWorkspace` 或等价模型：

- 验证所选目录是 Qulab run；
- 路径 containment，拒绝 artifact path traversal；
- 读取 metadata/config/resolved config；
- 读取 sequence generation/snapshots/selections 并校验 hash；
- 列出 analysis result groups；
- 以 streaming iterator 读取 events/logs，不一次加载超大文件；
- 提供 timeline summary/filter；
- 提供 replay events iterator；
- 提供 config/workflow snapshots；
- 提供 clone plan 和 fidelity report；
- 对旧 schema 做向后兼容或清楚标记 unsupported。

不要让 model import Qt。不要通过当前机器 adapter 实例来“补全”历史状态。

## Event replay

Replay 只重放 recorded events 到只读 presentation models：

- DataPoint/DerivedData -> historical live plots；
- AnalysisStatus -> module status；
- SequenceSelected -> sequence context；
- StepStarted/Completed、Measurement、ErrorRaised、LogMessage -> timeline/log；
- RunStarted/Completed -> replay status。

要求：

- play/pause/step；
- speed 0.25x/1x/4x/max；
- seek by event index，若高效时间 seek 暂不可做则明确限制；
- reset 后 deterministic；
- 不 publish 到 hardware EventBus；
- 不写 RunStore；
- malformed event 隔离并报告 line/index；
- live-only DerivedData 若没有被 RunStore 记录，必须标 unavailable，不能伪造；
- replay completion 保留最终 plot。

可以重用 Live View canvas/model，但必须增加 `Historical / Read-only` mode，禁止 start/prepare/control actions。

## Qt workspace

在现有主窗口加入 History/Open Run 入口，推荐页面/子页：

```text
Overview | Workflow | Parameters & Resources | Sequence | Timeline & Logs | Data
```

要求：

- 顶部持续显示 `Historical / Read-only`、run id、status、start/end；
- Workflow 显示 authoring 与 resolved 两种 snapshot，不能编辑；
- Parameters 展示 config/operator/sequence coordinates；
- Resources 展示 declared config 和实际 recorded snapshot；没有 snapshot 显示 unavailable；
- Sequence 展示 plan/provider/template/manifest/entry/hash/artifact；hash mismatch 红色 error；
- Timeline 支持 event type/severity/point filter；
- Data 直接复用现有 Data Viewer；
- 打开历史 run 不覆盖当前 active experiment；
- 从 History 返回 Control 后 active draft 不变。

## Clone as new experiment

Clone 是显式 command，不是“恢复硬件现场”。

要求：

1. 默认来源为 recorded `config.yaml`；允许用户选择 resolved snapshot，但 UI 必须解释区别。
2. 输出到用户选择的 project-relative config path。
3. 原 run folder 永不修改。
4. 对 copied sequence artifacts 建立明确的新引用策略：优先复制到项目 artifact/import 目录并保留 hash，不让新 config 永久依赖旧 run 的易变绝对路径。
5. 清除/关闭 `allow_output`、physical verification 或同等危险授权。
6. 增加 provenance 注释/metadata：source run id/path/hash，但不得写开发机器绝对路径进 portable YAML；使用 project-relative 或可选 external reference。
7. 运行 P11.1 candidate validation。
8. clone 结果先进入 draft，不自动 Prepare/Start。
9. missing artifact、provider version mismatch、adapter unavailable 都作为 diagnostics。

## Storage improvements

只添加历史重建确实需要且当前未记录的通用 metadata。不得破坏旧 run：

- adapter/resource snapshots 应在安全时间点记录，且不要求 connect 才能写 declared state；
- git commit、Qulab version、machine、config hashes；
- event schema version；
- artifact relative paths/hashes；
- final diagnostic/preflight summary。

对当前 metadata 中始终为空的字段不要假装已经记录。新增字段必须 optional、backward-compatible。

## Tests

Headless：

- complete run fidelity recorded/reconstructed；
- missing config/events/log/data/sequence artifact；
- malformed JSONL line isolation；
- sequence hash mismatch；
- event replay deterministic；
- replay feeds raw/derived/sequence/status models；
- large events streaming；
- path traversal rejected；
- old run backward compatibility；
- clone leaves source byte-identical；
- clone resets safety gates；
- clone path rewriting/hash/provenance；
- clone diagnostics on missing dependencies；
- opening history never calls adapters。

Qt：

- open run from Data Viewer/history action；
- visible read-only marker；
- active draft remains unchanged；
- workflow cannot be edited；
- play/pause/step updates plots/timeline；
- incomplete run shows partial instead of crash；
- clone action produces draft and invokes diagnostics。

Integration：

- create dry-run with sequence and derived data；
- reopen as historical workspace；
- compare config/data/event/sequence summary；
- replay to final state；
- clone and parse/dry-run new config with mock resources where safe。

## Non-goals

- 不自动 reconnect hardware；
- 不恢复旧电压、MW output、ASG running state；
- 不保证未记录状态；
- 不修改 historical data；
- 不用 replay 重新执行 analysis formula；recompute 使用现有 explicit recompute path；
- 不复制实现 Data Viewer。

## Definition of Done

- 历史 run 可作为完整只读 workspace 打开；
- fidelity per section 准确；
- recorded events 可控 replay；
- Data Viewer、sequence、logs、workflow/provenance 集成；
- active experiment 不被覆盖；
- clone 安全、portable、可诊断且不修改 source；
- incomplete/old/malformed runs fail soft；
- 自动 tests 证明无 adapter action/hardware side effect；
- docs 明确“软件现场恢复”不等于“硬件状态恢复”。

建议 commits：

```text
feat(storage): add historical run workspace model
feat(gui): add read-only run replay workspace
feat(gui): clone historical run as safe draft
test(storage): cover historical fidelity and replay
docs(gui): document historical workspace boundaries
```

最终 handoff 必须列出新增读取合同、fidelity 结果、replay 支持事件、clone 路径策略、测试结果和仍不可恢复的信息。
