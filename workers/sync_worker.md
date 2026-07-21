# Sync Worker Specification

## Mission

实现硬件同步描述和 preflight 检查，优先支持 ASG master + NI receiver。

## Must Read

- `docs/HARDWARE_SYNC.md`
- `docs/ADAPTER_REQUIREMENTS.md`

## Deliverables

1. `sync/trigger_plan.py`
2. `sync/timing_model.py`
3. `sync/validators.py`
4. unit tests

## Required Objects

- `SyncPlan`
- `TriggerEdge`
- `ClockRelation`
- `ExecutionOrder`
- `SyncValidationIssue`
- `SyncValidator`

## MVP Checks

1. resource exists。
2. trigger source/target syntax valid。
3. receiver arm before source start。
4. sample window >= expected sequence duration。
5. timeout positive。
6. safety shutdown actions exist。

## Rules

1. 不做完整 pulse compiler。
2. 不尝试推断所有硬件线缆。
3. 对未知硬件关系给 warning，不伪造确定性。
4. validator 输出结构化 issue，不只返回字符串。

