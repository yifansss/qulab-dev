# Bench Test Configs

This document lists the current staged bench configs. They are intentionally
ordered from safe/read-only checks to output and mixed-mode checks. Copy a
template before editing real ports, NI device names, channels, or voltage
ranges.

## Safety Order

1. `bench_00_inventory_connect.template.yaml`
   - Connect-only inventory.
   - No output, no AO.

2. `bench_01_pse_ai1_dark_trace.template.yaml`
   - PSE detector analog output into NI AI1.
   - Read-only AI trace.

3. `bench_02_ni_ao0_to_ai1_loopback.template.yaml`
   - NI AO0 to AI1 loopback.
   - Requires `--allow-ao`.

4. `bench_03_asg_ttl_scope_smoke.template.yaml`
   - ASG TTL output to oscilloscope only.
   - Requires `--allow-output`.

5. `bench_04_asg_to_ni_counter_ttl.template.yaml`
   - ASG TTL to NI counter PFI inputs.
   - Requires `--allow-output`.

6. `bench_05_pse_ai1_asg_triggered_trace.template.yaml`
   - PSE AI1 finite trace started by ASG trigger.
   - Requires `--allow-output`.

7. `bench_06_pse_ai1_manual_slow_scan.template.yaml`
   - Read-only manual condition scan with AI1 traces.
   - No output, no AO.

8. `bench_07_mixed_ao0_slow_asg_pse_ai1.template.yaml`
   - NI AO slow setpoint plus ASG-triggered PSE AI1 trace.
   - Requires both `--allow-output` and `--allow-ao`.

9. `bench_08_mw_lmx_config_no_rf.template.yaml`
   - Microwave source configure-only frequency/power test.
   - Does not call `output_on`.

10. `bench_09_low_power_odmr_pse_ai1_plan.template.yaml`
    - MW frequency scan plus ASG-triggered PSE AI1 trace.
    - ASG output requires `--allow-output`; RF output is intentionally not enabled.

11. `bench_10_generated_rabi_scope.template.yaml`
    - Stage 2 generated Rabi TTL, scope only, three points.
    - Requires explicit output authorization; physically unverified.

12. `bench_11_generated_rabi_asg_ni.template.yaml`
    - Stage 3 generated ASG ch6 -> NI PFI0 acquisition, based on Bench05 ordering.
    - Replace device/route placeholders; physically unverified.

13. `bench_12_low_power_rabi_family.template.yaml`
    - Stage 4 low-power Rabi with MW/ASG/NI cleanup.
    - Requires output and microwave authorization plus replacement of every `CHANGE_ME`.
    - It is a template, not evidence of physical timing validation.

## Recommended Commands

Read-only or configure-only checks:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_00_inventory_connect.template.yaml --connect-only
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_01_pse_ai1_dark_trace.template.yaml --dry-run
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_08_mw_lmx_config_no_rf.template.yaml --dry-run
```

Configs with ASG/AWG/MW output-class methods need explicit output authorization
even for dry-run safety checking:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_03_asg_ttl_scope_smoke.template.yaml --dry-run --allow-output
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_05_pse_ai1_asg_triggered_trace.template.yaml --dry-run --allow-output
```

Configs with NI AO writes need explicit AO authorization:

```bash
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_02_ni_ao0_to_ai1_loopback.template.yaml --dry-run --allow-ao
PYTHONPATH=src python -m qulab.scripts.hardware_check --config configs/experiments/bench_07_mixed_ao0_slow_asg_pse_ai1.template.yaml --dry-run --allow-output --allow-ao
```

## Notes

- `hardware_check --dry-run` only parses and checks safety/preflight; it does not connect hardware.
- `hardware_check --connect-only` connects, health-checks, snapshots, and disconnects resources; it does not execute the experiment procedure.
- Current full experiment execution through the GUI remains mock/dry-run oriented. Real armed-output execution should wait for the bench commissioning workflow and Direct Control safety layer.
- Always verify ASG TTL levels and polarity on an oscilloscope before connecting to laser, microwave switch, or NI PFI inputs.
- Always verify AO voltage range with loopback or a meter before connecting AO to a real device.
