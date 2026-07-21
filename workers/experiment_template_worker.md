# Experiment Template Worker Specification

## Mission

实现可复用实验模板，让新人能快速跑常见 NV 实验。

## Deliverables

1. `experiments/odmr.py`
2. `experiments/rabi.py`
3. `experiments/ramsey.py`
4. `experiments/pulsed_odmr.py`
5. matching YAML examples in `configs/experiments`

## Template Rules

1. 模板必须依赖 capability，不依赖具体 adapter。
2. 模板必须有 simulation example。
3. 模板必须说明 required resources。
4. 模板必须保存推荐 plot config。

## MVP Templates

ODMR：

- scan microwave frequency。
- read counts。
- line plot。

Rabi：

- scan pulse width tau。
- set sequence param。
- read counts。
- line plot。

2D Rabi/ODMR：

- nested scan。
- heatmap。

