"""Safe hardware configuration checker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from qulab.config import ConfigError, load_yaml_config, parse_experiment_config
from qulab.core import ActionStep, AverageStep, CleanupStep, MeasurementStep, Procedure, RunStep, ScanStep, Step
from qulab.instruments.base import InstrumentSafetyError

OUTPUT_METHODS = {"output_on", "start", "play"}
AO_METHODS = {"set_voltage", "set_waveform"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely preflight or connect Qulab hardware configs.")
    parser.add_argument("--config", required=True, help="Setup or experiment YAML config")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preflight only; do not connect hardware")
    parser.add_argument("--connect-only", action="store_true", help="Connect, health_check, snapshot, disconnect")
    parser.add_argument("--allow-output", action="store_true", help="Allow MW/ASG/AWG output actions during future smoke steps")
    parser.add_argument("--allow-ao", action="store_true", help="Allow NI analog output actions during future smoke steps")
    args = parser.parse_args(argv)

    if args.dry_run and args.connect_only:
        parser.error("Choose exactly one of --dry-run or --connect-only")
    if not args.dry_run and not args.connect_only:
        args.dry_run = True

    try:
        config = load_yaml_config(Path(args.config))
        parsed = parse_experiment_config(config)
        _check_safety(parsed.procedure, allow_output=args.allow_output, allow_ao=args.allow_ao)
        _print_header(args.config, mode="connect-only" if args.connect_only else "dry-run")
        _print_validation(parsed.validation)
        _print_resources(parsed.resolved_config.get("resources", {}), parsed.context.resources)

        if args.dry_run:
            print("connect status: skipped (dry-run)")
            return 0 if parsed.validation.ok else 2

        return _connect_only(parsed.context.resources)
    except (ConfigError, InstrumentSafetyError, Exception) as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _print_header(config_path: str, mode: str) -> None:
    print(f"config: {config_path}")
    print(f"mode: {mode}")
    print("safety: outputs disabled unless --allow-output; NI AO disabled unless --allow-ao")


def _print_validation(validation: Any) -> None:
    print(f"preflight ok: {validation.ok}")
    for issue in validation.issues:
        print(f"{issue.severity.upper()} {issue.code}: {issue.message}")


def _print_resources(resources_config: dict[str, Any], resources: dict[str, Any]) -> None:
    print("resources:")
    for name, resource in resources.items():
        raw = resources_config.get(name, {})
        capabilities = raw.get("capabilities") or sorted(resource.capabilities())
        mode = "simulation" if getattr(resource, "simulation", False) else "hardware"
        print(f"  - {name}")
        print(f"    adapter: {raw.get('adapter', getattr(resource, 'adapter', 'unknown'))}")
        print(f"    capabilities: {list(capabilities)}")
        print(f"    mode: {mode}")
        print(f"    connected: {getattr(resource, 'connected', False)}")


def _connect_only(resources: dict[str, Any]) -> int:
    failures = 0
    for name, resource in resources.items():
        print(f"connecting: {name}")
        try:
            resource.connect()
            print(f"  connect status: ok")
            print(f"  health: {json.dumps(resource.health_check(), sort_keys=True, default=str)}")
            print(f"  snapshot: {json.dumps(resource.snapshot(), sort_keys=True, default=str)}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  connect status: error: {type(exc).__name__}: {exc}")
        finally:
            try:
                resource.disconnect()
                print("  disconnect: ok")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  disconnect: error: {type(exc).__name__}: {exc}")
    return 0 if failures == 0 else 3


def _check_safety(procedure: Procedure, *, allow_output: bool, allow_ao: bool) -> None:
    for section, steps in (("setup", procedure.setup), ("procedure", procedure.body), ("cleanup", procedure.cleanup)):
        for step in _walk_steps(steps):
            if not isinstance(step, ActionStep):
                continue
            method = step.action.split(".", 1)[1] if isinstance(step.action, str) and "." in step.action else ""
            if method in OUTPUT_METHODS and not allow_output:
                raise InstrumentSafetyError(
                    f"{section} contains output action '{step.action}'. Re-run with --allow-output only at the bench."
                )
            if method in AO_METHODS and not allow_ao:
                raise InstrumentSafetyError(
                    f"{section} contains analog output action '{step.action}'. Re-run with --allow-ao only when safe."
                )


def _walk_steps(steps: list[Step]):
    for step in steps:
        yield step
        if isinstance(step, (ScanStep, AverageStep, MeasurementStep, RunStep, CleanupStep)):
            yield from _walk_steps(step.body)


if __name__ == "__main__":
    raise SystemExit(main())
