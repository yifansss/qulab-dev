# Naming and Git Rules

## 1. 命名规范

Python：

- module：`snake_case.py`
- package：`snake_case`
- class：`PascalCase`
- function/method：`snake_case`
- variable：`snake_case`
- constant：`UPPER_SNAKE_CASE`

实验参数：

- 使用物理含义清楚的 snake_case。
- 推荐：`mw_freq_hz`、`mw_power_dbm`、`tau_s`、`laser_width_s`。
- 不推荐：`x`、`p1`、`freq`。

资源命名：

- `mw`
- `asg`
- `daq`
- `awg`
- 多个同类设备：`mw_drive`、`mw_probe`。

文件命名：

- config：`rabi_2d.yaml`
- setup：`nv_room_temp_setup.yaml`
- adapter：`pycontrol_asg.py`
- tests：`test_<module>.py`

## 2. Git 分支规范

项目使用以下分支约定：

- `main`：稳定可运行。
- `feat/core-procedure`
- `feat/pycontrol-adapters`
- `feat/storage-run-store`
- `fix/daq-timeout`
- `docs/worker-guides`

小型、低风险修改可以直接提交到 `main`；较长或会改变公共接口的工作使用短期分支，验收后合并并删除。不要提交实验运行数据、凭据或本机专用配置。

## 3. Commit 规范

使用 Conventional Commits：

- `feat(core): add scan step model`
- `feat(adapter): add pycontrol ASG adapter`
- `fix(storage): flush events on failure`
- `docs(sync): define ASG-NI trigger plan`
- `test(core): add average dry-run coverage`
- `refactor(gui): separate operator view models`
- `chore(repo): update development tooling`

格式为 `<type>(<scope>): <简短祈使描述>`。标题保持简短，不加句号；常用 type 为 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`。每个 commit 只做一类事情。

## 4. 仓库边界

- qulab 跟踪 `src/`、`tests/`、`configs/`、`docs/`、`prompts/`、`tools/`、`scripts/` 和项目元数据。
- `drivers/pycontrol/` 是独立仓库，不纳入 qulab；部署时单独 clone 到该路径。
- qulab 的发布或实验交接文档必须记录兼容的 pycontrol commit SHA。
- `runs/`、`demo_runs/`、缓存、构建产物、归档文件及本机配置不进入仓库。

## 5. AI Agent Git 规则

AI agent 必须：

1. 修改前查看当前文件状态。
2. 不重置用户改动。
3. 不使用 destructive git 命令，除非用户明确要求。
4. 不把大数据、run 输出、硬件 SDK、DLL 提交进仓库。
5. 修改公共接口时同步更新文档和测试。
