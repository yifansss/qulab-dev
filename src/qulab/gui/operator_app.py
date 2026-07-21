"""Tkinter operator console entry point."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from qulab.core import Event

from .controller import OperatorController
from .models import ParameterEdit, format_parameter_value
from .plot_model import PlotSeries
from .procedure_tree import ProcedureTreeNode, build_procedure_tree


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "experiments" / "dry_run_rabi.yaml"
ODMR_CONFIG = PROJECT_ROOT / "configs" / "experiments" / "dry_run_odmr.yaml"


class OperatorApp:
    """Small, dependency-free Tk operator console."""

    def __init__(self, controller: OperatorController | None = None) -> None:
        self.controller = controller or OperatorController(PROJECT_ROOT / "runs")
        self.root = tk.Tk()
        self.root.title("Qulab Operator Console")
        self.root.geometry("1180x820")
        self.event_queue: queue.Queue[Any] = queue.Queue()
        self.plot_series = PlotSeries()
        self.parameter_edits: list[ParameterEdit] = []
        self.parameter_vars: dict[str, tk.StringVar] = {}
        self.running = False

        self._build_ui()
        self._load_config(DEFAULT_CONFIG)
        self.root.after(100, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)
        ttk.Label(self.root, text="Qulab Operator Console", font=("TkDefaultFont", 15, "bold")).grid(
            row=0, column=0, sticky="ew", padx=10, pady=(8, 4)
        )

        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)

        left = ttk.Frame(main, padding=6)
        center = ttk.Frame(main, padding=6)
        right = ttk.Frame(main, padding=6)
        main.add(left, weight=1)
        main.add(center, weight=2)
        main.add(right, weight=2)

        self._build_experiment_panel(left)
        self._build_tree_panel(center)
        self._build_preflight_panel(right)
        self._build_plot_and_log()

    def _build_experiment_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Experiments", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Button(parent, text="dry_run_rabi", command=lambda: self._load_config(DEFAULT_CONFIG)).grid(
            row=1, column=0, sticky="ew", pady=2
        )
        ttk.Button(parent, text="dry_run_odmr", command=lambda: self._load_config(ODMR_CONFIG)).grid(
            row=2, column=0, sticky="ew", pady=2
        )
        ttk.Button(parent, text="Load YAML...", command=self._choose_yaml).grid(row=3, column=0, sticky="ew", pady=2)

        ttk.Separator(parent).grid(row=4, column=0, sticky="ew", pady=8)
        ttk.Label(parent, text="Parameters", font=("TkDefaultFont", 11, "bold")).grid(row=5, column=0, sticky="w")
        self.parameters_frame = ttk.Frame(parent)
        self.parameters_frame.grid(row=6, column=0, sticky="nsew")
        parent.rowconfigure(6, weight=1)

    def _build_tree_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        ttk.Label(parent, text="Procedure Tree", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.tree = ttk.Treeview(parent, columns=("kind", "details"), show="tree headings", height=18)
        self.tree.heading("#0", text="Step")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("details", text="Details")
        self.tree.column("#0", width=230, stretch=True)
        self.tree.column("kind", width=90, stretch=False)
        self.tree.column("details", width=180, stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew")

    def _build_preflight_panel(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)
        ttk.Label(parent, text="Resources", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.resources = tk.Text(parent, height=8, wrap="word")
        self.resources.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        ttk.Label(parent, text="Preflight", font=("TkDefaultFont", 11, "bold")).grid(row=2, column=0, sticky="w")
        self.preflight = tk.Text(parent, height=8, wrap="word")
        self.preflight.grid(row=3, column=0, sticky="nsew")

        buttons = ttk.Frame(parent)
        buttons.grid(row=4, column=0, sticky="ew", pady=8)
        buttons.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(buttons, text="Prepare", command=self._prepare).grid(row=0, column=0, sticky="ew", padx=2)
        self.start_button = ttk.Button(buttons, text="Start", command=self._start)
        self.start_button.grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(buttons, text="Stop", command=self._stop).grid(row=0, column=2, sticky="ew", padx=2)

    def _build_plot_and_log(self) -> None:
        bottom = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        bottom.grid(row=2, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self.root.rowconfigure(2, weight=1)

        plot_frame = ttk.Frame(bottom, padding=6)
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(1, weight=1)
        ttk.Label(plot_frame, text="Live Plot", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(plot_frame, height=180, bg="white", highlightthickness=1, highlightbackground="#c8c8c8")
        self.canvas.grid(row=1, column=0, sticky="nsew")
        bottom.add(plot_frame, weight=1)

        log_frame = ttk.Frame(bottom, padding=6)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, text="Run Log", font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w")
        self.log = tk.Text(log_frame, height=10, wrap="word")
        self.log.grid(row=1, column=0, sticky="nsew")
        bottom.add(log_frame, weight=1)

    def _choose_yaml(self) -> None:
        path = filedialog.askopenfilename(
            title="Load experiment YAML",
            filetypes=(("YAML files", "*.yaml *.yml"), ("All files", "*.*")),
        )
        if path:
            self._load_config(Path(path))

    def _load_config(self, path: Path) -> None:
        try:
            self.controller.load_config(path)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            return
        self.plot_series.clear()
        self._draw_plot()
        self._log(f"Loaded config: {path}")
        self._refresh_parameters()
        self._refresh_tree()
        self._clear_text(self.resources)
        self._clear_text(self.preflight)

    def _refresh_parameters(self) -> None:
        for child in self.parameters_frame.winfo_children():
            child.destroy()
        self.parameter_vars.clear()
        self.parameter_edits = self.controller.get_parameter_edit_model()
        for row, edit in enumerate(self.parameter_edits):
            ttk.Label(self.parameters_frame, text=edit.label).grid(row=row, column=0, sticky="w", pady=2)
            var = tk.StringVar(value=format_parameter_value(edit.value))
            self.parameter_vars[edit.id] = var
            ttk.Entry(self.parameters_frame, textvariable=var, width=18).grid(row=row, column=1, sticky="ew", pady=2)
        self.parameters_frame.columnconfigure(1, weight=1)

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for node in build_procedure_tree(self.controller.current_procedure_tree_config()):
            self._insert_tree_node("", node)

    def _insert_tree_node(self, parent: str, node: ProcedureTreeNode) -> None:
        item = self.tree.insert(parent, "end", text=node.label, values=(node.kind, node.details), open=True)
        for child in node.children:
            self._insert_tree_node(item, child)

    def _apply_parameter_entries(self) -> bool:
        for edit in self.parameter_edits:
            try:
                self.controller.update_parameter(edit.id, self.parameter_vars[edit.id].get())
            except Exception as exc:
                messagebox.showerror("Parameter error", f"{edit.label}: {exc}")
                return False
        self._refresh_tree()
        return True

    def _prepare(self) -> bool:
        if not self._apply_parameter_entries():
            return False
        try:
            view = self.controller.prepare()
        except Exception as exc:
            messagebox.showerror("Prepare failed", str(exc))
            return False
        self._show_preflight(view)
        self._log("Preflight OK" if view.ok else "Preflight has errors")
        return view.ok

    def _show_preflight(self, view: Any) -> None:
        self._clear_text(self.resources)
        for resource in view.resources:
            caps = ", ".join(resource.capabilities)
            self.resources.insert(
                "end",
                f"{resource.name}  {resource.adapter}  connected={resource.connected} "
                f"simulation={resource.simulation}  capabilities={caps}\n",
            )
        self._clear_text(self.preflight)
        if not view.issues:
            self.preflight.insert("end", "ok resources exist\nok sync order ok\n")
        for issue in view.issues:
            self.preflight.insert("end", f"{issue.severity.upper()} {issue.code}: {issue.message}\n")

    def _start(self) -> None:
        if self.running:
            self._log("Start ignored: dry-run is already running.")
            return
        if not self._prepare():
            return
        self.running = True
        self.start_button.state(["disabled"])
        self.plot_series.clear()
        self._draw_plot()
        self._log("Starting dry-run...")
        thread = threading.Thread(target=self._run_worker, daemon=True)
        thread.start()

    def _run_worker(self) -> None:
        try:
            result = self.controller.start_dry_run(event_callback=self.event_queue.put)
            self.event_queue.put(("run_result", result))
        except Exception as exc:
            self.event_queue.put(("error", exc))

    def _stop(self) -> None:
        if self.running:
            self._log("Stop requested: current dry-run executor does not support reliable mid-run cancellation yet.")
        else:
            self._log("Stop is idle: no dry-run is running.")

    def _drain_events(self) -> None:
        try:
            while True:
                item = self.event_queue.get_nowait()
                if isinstance(item, Event):
                    self.plot_series.handle_event(item)
                    self._log(_event_to_log_line(item))
                    self._draw_plot()
                elif isinstance(item, tuple) and item[0] == "run_result":
                    result = item[1]
                    self._log(f"Run path: {result.run_path}")
                    self._log(f"RunCompleted {result.status}")
                    self.running = False
                    self.start_button.state(["!disabled"])
                elif isinstance(item, tuple) and item[0] == "error":
                    self._log(f"ERROR {item[1]}")
                    self.running = False
                    self.start_button.state(["!disabled"])
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _draw_plot(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 400)
        height = max(canvas.winfo_height(), 160)
        left, right, top, bottom = 48, width - 18, 18, height - 34
        canvas.create_line(left, bottom, right, bottom, fill="#555")
        canvas.create_line(left, bottom, left, top, fill="#555")
        points = self.plot_series.points
        canvas.create_text(left + 8, top + 8, anchor="nw", text=f"points: {len(points)}", fill="#333")
        if not points:
            canvas.create_text((left + right) / 2, (top + bottom) / 2, text="Waiting for DataPoint events", fill="#777")
            return
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        scaled = [
            (
                left + (x - min_x) / span_x * (right - left),
                bottom - (y - min_y) / span_y * (bottom - top),
            )
            for x, y in points
        ]
        if len(scaled) == 1:
            x, y = scaled[0]
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#1f77b4", outline="")
        else:
            flat = [coord for point in scaled for coord in point]
            canvas.create_line(*flat, fill="#1f77b4", width=2)
            for x, y in scaled[-5:]:
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#1f77b4", outline="")

    def _log(self, line: str) -> None:
        self.log.insert("end", f"{line}\n")
        self.log.see("end")

    @staticmethod
    def _clear_text(widget: tk.Text) -> None:
        widget.delete("1.0", "end")


def _event_to_log_line(event: Event) -> str:
    event_type = event.type
    if event_type == "RunStarted":
        return f"RunStarted {getattr(event, 'procedure_name', '')}"
    if event_type == "ParameterChanged":
        return f"ParameterChanged {getattr(event, 'name', '')}={getattr(event, 'value', '')}"
    if event_type == "MeasurementStarted":
        return f"MeasurementStarted {getattr(event, 'point_id', '')} coords={getattr(event, 'coords', {})}"
    if event_type == "DataPoint":
        return f"DataPoint {getattr(event, 'point_id', '')} data={getattr(event, 'data', {})}"
    if event_type == "MeasurementCompleted":
        return f"MeasurementCompleted {getattr(event, 'point_id', '')} {getattr(event, 'status', '')}"
    if event_type == "RunCompleted":
        return f"RunCompleted {getattr(event, 'status', '')}"
    if event_type == "ErrorRaised":
        return f"ErrorRaised {getattr(event, 'error_type', '')}: {getattr(event, 'message', '')}"
    return event_type


def main() -> None:
    app = OperatorApp()
    app.run()


if __name__ == "__main__":
    main()
