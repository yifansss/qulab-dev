# QA Worker Specification

## Mission

保证项目可持续迭代，避免 AI worker 引入隐性破坏。

## Deliverables

1. pytest setup。
2. unit tests。
3. integration dry-run tests。
4. optional hardware tests。
5. lint/type check configuration。

## Test Layers

Unit：

- no hardware。
- no GUI。
- fast。

Integration：

- mock adapters。
- run full dry-run experiment。
- write temp run store。

Hardware：

- marked with `hardware`。
- never run by default。
- requires explicit config。

## Required Commands

Recommended:

```bash
python -m pytest
python -m pytest tests/integration
python -m pytest tests/hardware -m hardware
```

## Rules

1. Do not require physical hardware in default tests。
2. Do not write test output into project `runs/`。
3. Use temporary directories。
4. Add regression tests for every bug fix。

