# Core Worker Specification

## Mission

实现 `src/qulab/core`，让实验流程可以在无硬件情况下表达、验证、dry-run 执行。

## Must Read

- `PROJECT_BLUEPRINT.md`
- `docs/ARCHITECTURE.md`
- `docs/CONFIG_SCHEMA.md`

## Deliverables

1. `parameter.py`
2. `procedure.py`
3. `context.py`
4. `events.py`
5. `executor.py`
6. unit tests

## Required Model

实现以下概念：

- `Parameter`
- `ParameterRef`
- `ScanValues`
- `Step`
- `ActionStep`
- `ScanStep`
- `AverageStep`
- `RunStep`
- `MeasurementStep`
- `Procedure`
- `ExperimentContext`
- `Event`
- `EventBus`
- `ExperimentExecutor`

## Rules

1. core 不导入 PyQt。
2. core 不导入 pycontrol。
3. core 不写 HDF5。
4. executor 只通过 context 获取 resource。
5. 所有 step 支持 dry-run。
6. 所有事件包含 timestamp。
7. 每个 measurement point 生成稳定 `point_id`。
8. 不假设每个点只有一个 scalar 输出。

## Tests

至少覆盖：

- 单 scan 参数值顺序。
- 二维 scan 嵌套顺序。
- average 次数。
- action call 参数引用解析。
- measurement step 生成 point_id。
- 单个 measurement 内多个数据输出能关联到同一 point_id。
- executor 出错后发出 error event。
- cleanup 总会执行。
