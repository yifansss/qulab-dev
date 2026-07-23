# -*- coding: utf-8 -*-
"""
Edit Sequence Dialog (PyQt5) — Advanced Style
==============================================
Replicates the MATLAB EditSequence.fig GUI in PyQt5.
Classic white/gray Windows-style appearance.
Upgraded with precise absolute positioning for individual pulses,
dynamic visual timing highlights, load/save menus, and empty clicks.
"""

import os
import sys
import json
import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QScrollArea,
    QWidget, QSizePolicy, QFrame, QApplication, QComboBox, QLineEdit,
    QMessageBox, QFileDialog, QCheckBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette

import matplotlib
matplotlib.use("Qt5Agg")
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure


# ─────────────────────────────────────────────────────────────────────────────
# Classic MATLAB-style channel colors
# ─────────────────────────────────────────────────────────────────────────────
CHANNEL_COLORS = [
    "#008000",  # green
    "#ff0000",  # red
    "#0000ff",  # blue
    "#000000",  # black
    "#ff00ff",  # magenta
    "#00aaaa",  # cyan
]


def classic_style() -> str:
    """Traditional Windows/MATLAB-style white background stylesheet."""
    return """
    QDialog, QWidget {
        background-color: #f0f0f0;
        color: #000000;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 12px;
    }
    QGroupBox {
        border: 1px solid #a0a0a0;
        border-radius: 4px;
        margin-top: 14px;
        padding: 6px 4px 4px 4px;
        background-color: #f5f5f5;
        color: #000000;
        font-weight: bold;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #000000;
    }
    QLabel {
        color: #000000;
        background: transparent;
    }
    QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QCheckBox {
        background-color: #ffffff;
        color: #000000;
        border: 1px solid #808080;
        border-radius: 2px;
        padding: 2px 4px;
    }
    QCheckBox {
        background: transparent;
        border: none;
    }
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QLineEdit:focus {
        border: 1px solid #0078d7;
    }
    QPushButton {
        background-color: #e1e1e1;
        color: #000000;
        border: 1px solid #a0a0a0;
        border-radius: 3px;
        padding: 4px 14px;
        min-height: 22px;
    }
    QPushButton:hover {
        background-color: #c8e0f8;
        border-color: #0078d7;
    }
    QPushButton:pressed {
        background-color: #0078d7;
        color: #ffffff;
    }
    QPushButton#btnOK {
        background-color: #0078d7;
        color: #ffffff;
        border: 1px solid #005fa3;
        font-weight: bold;
    }
    QPushButton#btnOK:hover {
        background-color: #005fa3;
    }
    QScrollArea {
        border: 1px solid #c0c0c0;
        border-radius: 3px;
        background-color: #f0f0f0;
    }
    QFrame[frameShape="4"] {
        color: #c0c0c0;
    }
    QFrame[frameShape="5"] {
        color: #c0c0c0;
    }
    """


def adapt_legacy_sequence(params: list) -> list:
    """Adapts old single-pulse channel format to the new absolute start_time multi-pulse format."""
    if not params:
        return []
    adapted = []
    for i, ch in enumerate(params):
        if isinstance(ch, dict) and "pulses" in ch:
            adapted.append(ch)
        else:
            # Convert legacy format
            adapted.append({
                "channel_name": f"Channel {i + 1}",
                "delay_off": ch.get("delay_off", 0.0),
                "pulses": [
                    {
                        "pbn": ch.get("pbn", i),
                        "rise": ch.get("rise", 1),
                        "time_on": ch.get("time_on", 1.0),
                        "d": ch.get("dt", 10.0),
                        "start_time": ch.get("delay_on", 0.0),
                        "type": "notype",
                        "phas": 0.0
                    }
                ]
            })
    return adapted


def _get_channel_pbn(ch: dict, default_idx: int) -> int:
    """Safely extracts physical channel pbn from a channel dict or falls back to first pulse or default index."""
    if not isinstance(ch, dict):
        return default_idx
    ch_pbn = ch.get("pbn")
    if ch_pbn is not None:
        try:
            return int(ch_pbn)
        except (ValueError, TypeError):
            pass
    pulses = ch.get("pulses", [])
    if pulses and isinstance(pulses, list) and len(pulses) > 0:
        p = pulses[0]
        if isinstance(p, dict):
            try:
                return int(p.get("pbn", default_idx))
            except (ValueError, TypeError):
                pass
    return default_idx


def export_to_legacy(channels: list, filepath: str):
    """Exports the sequence channels structure to the legacy MATLAB tab-separated text format."""
    with open(filepath, "w", encoding="utf-8") as f:
        for i, ch in enumerate(channels):
            pulses = ch.get("pulses", [])
            if not pulses:
                continue

            # Gather all individual pulse repetitions (events)
            individual_pulses = []
            for p in pulses:
                rise = int(p.get("rise", 1))
                ton = float(p.get("time_on", 1.0))
                d = float(p.get("d", 10.0))
                p_start = float(p.get("start_time", 0.0))
                phas = float(p.get("phas", 0.0))
                p_type = str(p.get("type", "notype"))

                for k in range(rise):
                    t_s = p_start + k * d
                    individual_pulses.append({
                        "t_start": t_s * 1e-6,      # convert µs to seconds
                        "duration": ton * 1e-6,      # convert µs to seconds
                        "phase": int(phas),
                        "type": p_type
                    })

            # Sort events chronologically by start time
            individual_pulses.sort(key=lambda x: x["t_start"])
            n_rise = len(individual_pulses)
            pbn = _get_channel_pbn(ch, i)

            # Write Channel Header
            f.write(f"PB{pbn}\t{n_rise}\n")

            # Write T (Start times)
            t_str = "\t".join(f"{x['t_start']:.10f}" for x in individual_pulses)
            f.write(f"{t_str}\t\n")

            # Write DT (Durations)
            dt_str = "\t".join(f"{x['duration']:.10f}" for x in individual_pulses)
            f.write(f"{dt_str}\t\n")

            # Write Phases
            phase_str = "\t".join(str(x["phase"]) for x in individual_pulses)
            f.write(f"{phase_str}\t\n")

            # Write Types
            type_str = "\t".join(x["type"] for x in individual_pulses)
            f.write(f"{type_str}\t\n")

            # Write Delays [DelayON, DelayOFF]
            delay_on = float(ch.get("delay_on", 0.0)) * 1e-6
            delay_off = float(ch.get("delay_off", 0.0)) * 1e-6
            f.write(f"{delay_on:.10f}\t{delay_off:.10f}\t\n")

        # Trailing comments marker
        f.write("\nComments:\n")


def parse_legacy_sequence(filepath: str) -> list:
    """Parses a legacy MATLAB-style tab-separated sequence text file into the new format."""
    channels = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    lines = [line.strip() for line in content.split("\n")]
    line_idx = 0
    num_lines = len(lines)

    while line_idx < num_lines:
        line = lines[line_idx].strip()
        if not line:
            line_idx += 1
            continue

        if line.startswith("PB"):
            # Line format: "PB<PBN>\t<NRise>"
            parts = line.split()
            if len(parts) < 2:
                line_idx += 1
                continue

            pbn_str = parts[0][2:]
            try:
                pbn = int(pbn_str)
                n_rise = int(parts[1])
            except ValueError:
                line_idx += 1
                continue

            # Read T (Start times)
            line_idx += 1
            while line_idx < num_lines and not lines[line_idx].strip():
                line_idx += 1
            if line_idx >= num_lines:
                break
            t_values = [float(val) * 1e6 for val in lines[line_idx].split() if val]

            # Read DT (Durations / Time ON)
            line_idx += 1
            while line_idx < num_lines and not lines[line_idx].strip():
                line_idx += 1
            if line_idx >= num_lines:
                break
            dt_values = [float(val) * 1e6 for val in lines[line_idx].split() if val]

            # Read Phases
            line_idx += 1
            while line_idx < num_lines and not lines[line_idx].strip():
                line_idx += 1
            if line_idx >= num_lines:
                break
            phase_values = []
            for val in lines[line_idx].split():
                try:
                    phase_values.append(float(val))
                except ValueError:
                    pass
            if len(phase_values) < n_rise:
                phase_values += [0.0] * (n_rise - len(phase_values))

            # Read Types
            line_idx += 1
            while line_idx < num_lines and not lines[line_idx].strip():
                line_idx += 1
            if line_idx >= num_lines:
                break
            type_values = [val for val in lines[line_idx].split() if val]
            if len(type_values) < n_rise:
                type_values += ["notype"] * (n_rise - len(type_values))

            # Read Delays [DelayON, DelayOFF]
            line_idx += 1
            while line_idx < num_lines and not lines[line_idx].strip():
                line_idx += 1
            if line_idx >= num_lines:
                break
            delay_values = []
            for val in lines[line_idx].split():
                try:
                    delay_values.append(float(val) * 1e6)
                except ValueError:
                    pass
            if len(delay_values) < 2:
                delay_values = [0.0, 0.0]

            delay_on = delay_values[0]
            delay_off = delay_values[1]

            # Reconstruct pulses list. In new format, each event becomes a single-pulse block.
            pulses = []
            for i in range(min(n_rise, len(t_values), len(dt_values))):
                pulses.append({
                    "rise": 1,
                    "time_on": dt_values[i],
                    "d": dt_values[i] + 10.0,  # default cycle period > time_on
                    "type": type_values[i],
                    "phas": phase_values[i],
                    "pbn": pbn,
                    "start_time": t_values[i]
                })

            channels.append({
                "channel_name": f"Channel {len(channels) + 1}",
                "delay_on": delay_on,
                "delay_off": delay_off,
                "pulses": pulses,
                "pbn": pbn
            })

            line_idx += 1
        elif line.startswith("Comments:"):
            break
        else:
            line_idx += 1

    # Fill remaining channels up to 4 to match UI standard
    while len(channels) < 4:
        channels.append({
            "channel_name": f"Channel {len(channels) + 1}",
            "delay_off": 0.0,
            "pulses": []
        })

    return channels


class ChannelRow(QWidget):
    """One row of pulse parameters in the selected channel table."""
    changed = pyqtSignal()
    deleteRequested = pyqtSignal(QWidget)
    focused = pyqtSignal(QWidget)

    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self._build_ui()
        self.set_selected(False)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Delete button
        self.btn_delete = QPushButton("X")
        self.btn_delete.setFixedWidth(26)
        self.btn_delete.setToolTip("Delete this pulse block / 删除此脉冲组")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                color: #cc0000;
                font-weight: bold;
                border: 1px solid #dcdcdc;
                background-color: #fcfcfc;
                min-height: 18px;
            }
            QPushButton:hover {
                background-color: #ffe6e6;
                border-color: #cc0000;
            }
        """)
        self.btn_delete.clicked.connect(lambda: self.deleteRequested.emit(self))
        layout.addWidget(self.btn_delete)

        # Rise N
        self.spn_rise = QSpinBox()
        self.spn_rise.setRange(1, 1000)
        self.spn_rise.setFixedWidth(55)
        self.spn_rise.setToolTip("当前脉冲组的重复周期次数 (Rise N)")
        layout.addWidget(self.spn_rise)

        # Time ON
        self.spn_ton = QDoubleSpinBox()
        self.spn_ton.setRange(0.001, 1e6)
        self.spn_ton.setDecimals(3)
        self.spn_ton.setSingleStep(0.001)
        self.spn_ton.setSuffix(" µs")
        self.spn_ton.setFixedWidth(105)
        self.spn_ton.setToolTip("高电平持续时间 (Time ON)")
        layout.addWidget(self.spn_ton)

        # Time OFF (Backend key remains 'd' for compatibility)
        self.spn_dt = QDoubleSpinBox()
        self.spn_dt.setRange(0.001, 1e6)
        self.spn_dt.setDecimals(3)
        self.spn_dt.setSingleStep(0.001)
        self.spn_dt.setSuffix(" µs")
        self.spn_dt.setFixedWidth(105)
        self.spn_dt.setToolTip("脉冲断开持续时间 (Time OFF / D)")
        layout.addWidget(self.spn_dt)

        # Type
        self.txt_type = QLineEdit("notype")
        self.txt_type.setFixedWidth(95)
        self.txt_type.setToolTip("脉冲类型标识 (laser, mw, rf, daq)")
        layout.addWidget(self.txt_type)

        # Phas
        self.spn_phas = QDoubleSpinBox()
        self.spn_phas.setRange(0.0, 360.0)
        self.spn_phas.setDecimals(1)
        self.spn_phas.setSingleStep(5.0)
        self.spn_phas.setFixedWidth(65)
        self.spn_phas.setToolTip("相位角度 (Phas)")
        layout.addWidget(self.spn_phas)

        layout.addStretch()

        # Connect slots
        for w in [self.spn_rise, self.spn_ton, self.spn_dt, self.spn_phas]:
            w.valueChanged.connect(self.changed)
        self.txt_type.textChanged.connect(self.changed)

        # Mouse press redirection for selection click
        self.setFocusPolicy(Qt.ClickFocus)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.focused.emit(self)

    def set_selected(self, selected: bool):
        self.setAutoFillBackground(True)
        p = self.palette()
        if selected:
            p.setColor(QPalette.Window, QColor("#ffe680")) # Selected highlighted soft yellow
        else:
            if self.index % 2 == 0:
                p.setColor(QPalette.Window, QColor("#ffffff"))
            else:
                p.setColor(QPalette.Window, QColor("#f5f5f5"))
        self.setPalette(p)

    def get_params(self) -> dict:
        return {
            "rise":      self.spn_rise.value(),
            "time_on":   self.spn_ton.value(),
            "d":         self.spn_dt.value(),
            "type":      self.txt_type.text(),
            "phas":      self.spn_phas.value(),
        }

    def set_params(self, p: dict):
        self.spn_rise.blockSignals(True)
        self.spn_ton.blockSignals(True)
        self.spn_dt.blockSignals(True)
        self.txt_type.blockSignals(True)
        self.spn_phas.blockSignals(True)
        try:
            self.spn_rise.setValue(int(p.get("rise", 1)))
            self.spn_ton.setValue(float(p.get("time_on", 1.0)))
            self.spn_dt.setValue(float(p.get("d", 10.0)))
            self.txt_type.setText(str(p.get("type", "notype")))
            self.spn_phas.setValue(float(p.get("phas", 0.0)))
        finally:
            self.spn_rise.blockSignals(False)
            self.spn_ton.blockSignals(False)
            self.spn_dt.blockSignals(False)
            self.txt_type.blockSignals(False)
            self.spn_phas.blockSignals(False)


class WaveformCanvas(FigureCanvas):
    """Matplotlib canvas — white background, absolute start_time timing diagram with direct mouse selections and drags."""
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 3.5), facecolor="#ffffff")
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)

        # Matplotlib and selection states
        self.dialog = None
        self.scale = 1.0
        self.plotted_pulses = []

        # Drag state variables
        self.drag_channel = None
        self.drag_pulse_idx = None
        self.drag_rep_idx = None
        self.drag_param = None
        self.drag_start_x = 0.0
        self.drag_start_val = 0.0

        # Connect callbacks
        self.mpl_connect("button_press_event", self.on_press)
        self.mpl_connect("motion_notify_event", self.on_motion)
        self.mpl_connect("button_release_event", self.on_release)

    def draw_sequence(self, channels: list):
        self.fig.clear()
        self.plotted_pulses = []
        n_chn = len(channels)
        if n_chn == 0:
            self.draw()
            return

        # Compute total duration across all channels
        t_max = 0.0
        for ch in channels:
            for p in ch.get("pulses", []):
                t_max = max(t_max, p.get("start_time", 0.0) + p["rise"] * p["d"])
            t_max = max(t_max, ch.get("delay_off", 0.0))
        if t_max <= 0:
            t_max = 1.0

        # Scaling unit
        if t_max <= 100.0:
            self.scale, unit = 1.0, "µs"
        elif t_max <= 100000.0:
            self.scale, unit = 1e-3, "ms"
        else:
            self.scale, unit = 1e-6, "s"

        ax = self.fig.add_subplot(111, facecolor="#ffffff")
        ax.set_xlabel(f"Time ({unit})", fontsize=10, color="#000000")
        ax.tick_params(colors="#000000", labelsize=9)
        for sp in ax.spines.values():
            sp.set_edgecolor("#808080")

        row_h = 1.4

        # Plot selected pulse highlight (Adaptive based on Shift checkboxes)
        if self.dialog and self.dialog.selected_pulse is not None:
            sel_ch_idx, sel_p_idx = self.dialog.selected_pulse
            if sel_ch_idx < len(channels):
                ch = channels[sel_ch_idx]
                pulses = ch.get("pulses", [])
                if sel_p_idx < len(pulses):
                    p = pulses[sel_p_idx]
                    p_start = p.get("start_time", 0.0)
                    t_start_highlight = p_start * self.scale
                    
                    if self.dialog.chk_shift_all.isChecked():
                        # Global highlight: full-height vertical span from start_time to t_max
                        ax.axvspan(t_start_highlight, t_max * self.scale,
                                   color="#ffd700", alpha=0.25, zorder=0)
                    elif self.dialog.chk_shift_chan.isChecked():
                        # Channel highlight: horizontal block from start_time to t_max on this channel only
                        y_low = sel_ch_idx * row_h
                        y_high = y_low + 1.0
                        ax.fill_between([t_start_highlight, t_max * self.scale],
                                        y_low - 0.1, y_high + 0.1,
                                        color="#ffd700", alpha=0.25, zorder=0)
                    else:
                        # Local highlight: only covers the selected pulse block locally on this channel
                        block_len = p["rise"] * p["d"]
                        y_low = sel_ch_idx * row_h
                        y_high = y_low + 1.0
                        ax.fill_between([t_start_highlight, (p_start + block_len) * self.scale],
                                        y_low - 0.1, y_high + 0.1,
                                        color="#ffd700", alpha=0.25, zorder=0)

        for i, ch in enumerate(channels):
            color = CHANNEL_COLORS[i % len(CHANNEL_COLORS)]
            y_low  = i * row_h
            y_high = y_low + 1.0

            xs, ys = [0.0], [y_low]
            pulses = ch.get("pulses", [])
            
            # Sort pulses chronologically to draw continuous timing diagram lines
            sorted_pulses = sorted(pulses, key=lambda x: x.get("start_time", 0.0))
            
            for p_idx, p in enumerate(pulses):
                ton = p["time_on"]
                dt = p["d"]
                rise = p["rise"]
                p_start = p.get("start_time", 0.0)

                for k in range(rise):
                    t_s = p_start + k * dt
                    t_e = t_s + ton
                    
                    # Store exact timing and boundaries for click searches
                    self.plotted_pulses.append({
                        "ch_idx": i,
                        "p_idx": p_idx,
                        "rep_idx": k,
                        "t_start": t_s,
                        "t_end": t_e,
                        "t_block_start": p_start,
                        "y_low": y_low,
                        "y_high": y_high,
                        "d": dt,
                        "ton": ton,
                        "rise": rise
                    })
            
            # Re-draw lines continuously chronologically
            for p in sorted_pulses:
                p_start = p.get("start_time", 0.0)
                xs.append(p_start * self.scale)
                ys.append(y_low)
                for k in range(p["rise"]):
                    t_s = p_start + k * p["d"]
                    t_e = t_s + p["time_on"]
                    xs += [t_s * self.scale, t_s * self.scale,
                           t_e * self.scale, t_e * self.scale]
                    ys += [y_low, y_high, y_high, y_low]
            
            xs.append(t_max * self.scale)
            ys.append(y_low)

            ax.plot(xs, ys, color=color, linewidth=1.5)
            
            # Label
            lbl = ch.get("channel_name", f"CH{i + 1}")
            ch_pbn = _get_channel_pbn(ch, i)
            pbn_lbl = f"{lbl} (PB{ch_pbn})"
            ax.text(0.002 * t_max * self.scale, y_low + 0.5,
                    pbn_lbl, color=color, fontsize=9,
                    fontweight="bold", va="center")

        ax.set_xlim(0, t_max * self.scale)
        ax.set_ylim(-0.3, n_chn * row_h + 0.2)
        ax.set_yticks([])
        ax.grid(axis="x", color="#e0e0e0", linestyle="--", linewidth=0.6)
        self.fig.tight_layout(pad=0.5)
        self.draw()

    def on_press(self, event):
        if not self.dialog or event.xdata is None or event.ydata is None:
            return

        if event.button != 1:  # Left click only
            return

        x_click_us = event.xdata / self.scale
        y_click = event.ydata

        n_chn = len(self.dialog.channels) # Total channels in active dialog data
        if n_chn == 0:
            return

        row_h = 1.4

        # Identify which channel was clicked vertically
        clicked_channel_idx = None
        for idx in range(n_chn):
            y_low = idx * row_h
            y_high = y_low + 1.0
            if y_low - 0.25 <= y_click <= y_high + 0.25:
                clicked_channel_idx = idx
                break

        if clicked_channel_idx is None:
            return

        # Find closest pulse edge/body
        clicked_pulse = None
        min_dist = 999.0

        # 1. Edge click detection
        for p in self.plotted_pulses:
            if p["ch_idx"] == clicked_channel_idx:
                t_block_end = p["t_block_start"] + p["rise"] * p["d"]
                if p["t_block_start"] - 5.0 <= x_click_us <= t_block_end + 5.0:
                    d_start = abs(x_click_us - p["t_start"])
                    d_end = abs(x_click_us - p["t_end"])
                    if min(d_start, d_end) < min_dist:
                        min_dist = min(d_start, d_end)
                        clicked_pulse = p

        # Calculate threshold
        t_max = max((p["t_block_start"] + p["rise"] * p["d"] for p in self.plotted_pulses), default=1.0)
        threshold = 0.015 * t_max

        # 2. Body click detection (if no edge was clicked)
        if clicked_pulse is None or min_dist >= threshold:
            for p in self.plotted_pulses:
                if p["ch_idx"] == clicked_channel_idx:
                    if p["t_start"] <= x_click_us <= p["t_end"]:
                        clicked_pulse = p
                        min_dist = threshold + 1.0  # Force body drag
                        break

        # 3. Handle click behavior
        if clicked_pulse is None:
            # Clicked on the blank/empty space of a channel!
            # Switch the editor active channel to this clicked channel index,
            # and select its first pulse by default so that the control area populates it!
            ch = self.dialog.channels[clicked_channel_idx]
            if ch.get("pulses", []):
                self.dialog.select_pulse(clicked_channel_idx, 0)
            else:
                self.dialog.cmb_channel.setCurrentIndex(clicked_channel_idx)
            return

        # Clicked a pulse! Select it
        ch_idx = clicked_pulse["ch_idx"]
        p_idx = clicked_pulse["p_idx"]
        self.dialog.select_pulse(ch_idx, p_idx)

        # Setup dragging parameter values
        if min_dist < threshold:
            # Edge Drag
            d_start = abs(x_click_us - clicked_pulse["t_start"])
            d_end = abs(x_click_us - clicked_pulse["t_end"])
            
            if d_end < d_start:
                # Dragging right edge to change TimeON
                self.drag_param = "time_on"
                self.drag_start_val = clicked_pulse["ton"]
            else:
                # Dragging left edge
                if clicked_pulse["rep_idx"] > 0:
                    # Repeating pulse start: drag Time OFF spacing
                    self.drag_param = "d"
                    self.drag_start_val = clicked_pulse["d"]
                else:
                    # First pulse start: drag start_time offset
                    self.drag_param = "start_time"
                    self.drag_start_val = clicked_pulse["t_block_start"]
        else:
            # Body Drag: translate pulse block start_time
            self.drag_param = "start_time"
            self.drag_start_val = clicked_pulse["t_block_start"]

        self.drag_channel = ch_idx
        self.drag_pulse_idx = p_idx
        self.drag_rep_idx = clicked_pulse["rep_idx"]
        self.drag_start_x = x_click_us
        self.setCursor(Qt.SizeHorCursor)

    def on_motion(self, event):
        if self.drag_channel is None or event.xdata is None:
            return

        x_curr_us = event.xdata / self.scale
        dx = x_curr_us - self.drag_start_x

        ch_idx = self.drag_channel
        p_idx = self.drag_pulse_idx
        k = self.drag_rep_idx

        # Drag updates
        if self.drag_param == "start_time":
            new_val = max(0.0, self.drag_start_val + dx)
            delta = new_val - self.drag_start_val
            
            self.dialog.shift_pulse_timeline(ch_idx, p_idx, delta)

        elif self.drag_param == "time_on":
            new_val = max(0.001, self.drag_start_val + dx)
            if ch_idx == self.dialog.active_channel_idx:
                if p_idx < len(self.dialog.rows):
                    row = self.dialog.rows[p_idx]
                    if row.spn_rise.value() > 1:
                        new_val = min(new_val, row.spn_dt.value() - 0.001)
                    row.spn_ton.setValue(new_val)
            else:
                if ch_idx < len(self.dialog.channels) and p_idx < len(self.dialog.channels[ch_idx].get("pulses", [])):
                    p = self.dialog.channels[ch_idx]["pulses"][p_idx]
                    if p["rise"] > 1:
                        new_val = min(new_val, p["d"] - 0.001)
                    p["time_on"] = new_val
                    self.dialog._redraw()

        elif self.drag_param == "d":
            # Repetition drag: scale down delta by rep index k
            new_val = max(0.001, self.drag_start_val + dx / k)
            if ch_idx == self.dialog.active_channel_idx:
                if p_idx < len(self.dialog.rows):
                    row = self.dialog.rows[p_idx]
                    new_val = max(row.spn_ton.value() + 0.001, new_val)
                    row.spn_dt.setValue(new_val)
            else:
                if ch_idx < len(self.dialog.channels) and p_idx < len(self.dialog.channels[ch_idx].get("pulses", [])):
                    p = self.dialog.channels[ch_idx]["pulses"][p_idx]
                    new_val = max(p["time_on"] + 0.001, new_val)
                    p["d"] = new_val
                    self.dialog._redraw()

    def on_release(self, event):
        if self.drag_channel is not None:
            self.drag_channel = None
            self.drag_param = None
            self.drag_pulse_idx = None
            self.drag_rep_idx = None
            self.unsetCursor()


class EditSequenceDialog(QDialog):
    """Pulse sequence editor — advanced style multi-pulse dialog."""
    sequenceAccepted = pyqtSignal(list)

    def __init__(self, initial_params: list = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Pulse Sequence / 编辑脉冲时序")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(680)
        self.setStyleSheet(classic_style())

        self.active_file = ""
        self.channels = []
        self.active_channel_idx = -1
        self.selected_pulse = None # (ch_idx, pulse_idx)

        self._build_ui()
        self.canvas.dialog = self

        if initial_params:
            import copy
            self.load_params(copy.deepcopy(adapt_legacy_sequence(initial_params)))
        else:
            self._reset_defaults()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(10, 10, 10, 10)

        # Top Toolbar (Load, Save, Save As)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        
        self.btn_open = QPushButton("Open / 载入")
        self.btn_open.clicked.connect(self.load_sequence_from_file)
        toolbar.addWidget(self.btn_open)

        self.btn_save = QPushButton("Save / 保存")
        self.btn_save.setStyleSheet("font-weight: bold; background-color: #0078d7; color: #ffffff;")
        self.btn_save.clicked.connect(self.save_sequence)
        toolbar.addWidget(self.btn_save)

        self.btn_save_as = QPushButton("Save As… / 另存为…")
        self.btn_save_as.clicked.connect(self.save_sequence_as)
        toolbar.addWidget(self.btn_save_as)

        self.btn_import_legacy = QPushButton("Import Legacy / 导入Legacy")
        self.btn_import_legacy.clicked.connect(self.import_legacy_sequence)
        toolbar.addWidget(self.btn_import_legacy)

        self.btn_export_legacy = QPushButton("Export Legacy / 导出Legacy")
        self.btn_export_legacy.clicked.connect(self.export_legacy_sequence)
        toolbar.addWidget(self.btn_export_legacy)
        toolbar.addStretch()
        root.addLayout(toolbar)

        # Main horizontal splitter-like split
        main_layout = QHBoxLayout()
        main_layout.setSpacing(8)

        # ── Bottom-Left Editor Group (Selected Channel & Pulses) ──────────────────────
        editor_grp = QGroupBox("Pulse Sequence Detail Editor / 脉冲时序细节设计")
        eg_l = QVBoxLayout(editor_grp)
        eg_l.setSpacing(6)

        # Channel Selector row
        ch_sel_row = QHBoxLayout()
        ch_sel_row.addWidget(QLabel("Logical Channel / 逻辑通道:"))
        self.cmb_channel = QComboBox()
        self.cmb_channel.setFixedWidth(130)
        self.cmb_channel.currentIndexChanged.connect(self._on_channel_selection_changed)
        ch_sel_row.addWidget(self.cmb_channel)

        ch_sel_row.addWidget(QLabel("Physical PB / 物理通道:"))
        self.spn_pb_mapping = QSpinBox()
        self.spn_pb_mapping.setRange(0, 23)
        self.spn_pb_mapping.setFixedWidth(55)
        self.spn_pb_mapping.setToolTip("ASG/Pulse Blaster physical channel (0 to 23)")
        self.spn_pb_mapping.valueChanged.connect(self._on_pb_mapping_changed)
        ch_sel_row.addWidget(self.spn_pb_mapping)

        self.btn_add_ch = QPushButton("Add CH / 添加通道")
        self.btn_add_ch.clicked.connect(self.add_logical_channel)
        ch_sel_row.addWidget(self.btn_add_ch)

        self.btn_del_ch = QPushButton("Del CH / 删除通道")
        self.btn_del_ch.setStyleSheet("color: #cc0000;")
        self.btn_del_ch.clicked.connect(self.delete_logical_channel)
        ch_sel_row.addWidget(self.btn_del_ch)
        ch_sel_row.addStretch()
        eg_l.addLayout(ch_sel_row)

        # Horizontal separator
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        eg_l.addWidget(sep)

        # Table Column Headers
        hdr_w = QWidget()
        hdr_w.setAutoFillBackground(True)
        p = hdr_w.palette()
        p.setColor(QPalette.Window, QColor("#dce6f0"))
        hdr_w.setPalette(p)
        hdr_l = QHBoxLayout(hdr_w)
        hdr_l.setContentsMargins(4, 2, 4, 2)
        hdr_l.setSpacing(6)
        
        for txt, w in [("Del", 35), ("Rise N", 65),
                       ("Time ON (µs)", 115), ("Time OFF (µs)", 115),
                       ("Type", 105), ("Phas", 75)]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(w)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("font-weight: bold; background: transparent;")
            hdr_l.addWidget(lbl)
        hdr_l.addStretch()
        eg_l.addWidget(hdr_w)

        # Table Scroll Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMinimumHeight(160)
        self.scroll.setMaximumHeight(280)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(2)

        self.rows = []
        
        # Vertical spacer
        self.spacer = QWidget()
        self.spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.scroll_layout.addWidget(self.spacer)
        
        self.scroll.setWidget(self.scroll_content)
        eg_l.addWidget(self.scroll)

        # Add Pulse Controls
        sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setFrameShadow(QFrame.Sunken)
        eg_l.addWidget(sep2)

        pulse_btns = QHBoxLayout()
        self.btn_add_pulse = QPushButton("+ Add Pulse / 添加脉冲")
        self.btn_add_pulse.setStyleSheet("font-weight: bold; color: #0078d7;")
        self.btn_add_pulse.clicked.connect(lambda: self.add_pulse_row())
        pulse_btns.addWidget(self.btn_add_pulse)

        self.btn_clear_pulses = QPushButton("Clear Pulses / 清空脉冲")
        self.btn_clear_pulses.clicked.connect(self.clear_pulse_rows)
        pulse_btns.addWidget(self.btn_clear_pulses)
        pulse_btns.addStretch()
        eg_l.addLayout(pulse_btns)

        # Channel Delays (Now representing Start Time and End Time of Selected Pulse Block)
        sep3 = QFrame(); sep3.setFrameShape(QFrame.HLine); sep3.setFrameShadow(QFrame.Sunken)
        eg_l.addWidget(sep3)

        delays_row = QHBoxLayout()
        delays_row.addWidget(QLabel("Pulse Start Time (DelayON):"))
        self.spn_delay_on = QDoubleSpinBox()
        self.spn_delay_on.setRange(0.0, 1e6)
        self.spn_delay_on.setDecimals(3)
        self.spn_delay_on.setSingleStep(1.0)
        self.spn_delay_on.setSuffix(" µs")
        self.spn_delay_on.setFixedWidth(110)
        self.spn_delay_on.valueChanged.connect(self._on_delay_on_changed)
        delays_row.addWidget(self.spn_delay_on)

        delays_row.addWidget(QLabel("Pulse End Time (DelayOFF):"))
        self.spn_delay_off = QDoubleSpinBox()
        self.spn_delay_off.setRange(0.0, 1e6)
        self.spn_delay_off.setDecimals(3)
        self.spn_delay_off.setSingleStep(1.0)
        self.spn_delay_off.setSuffix(" µs")
        self.spn_delay_off.setFixedWidth(110)
        self.spn_delay_off.setReadOnly(True) # Read-only mathematically bound readout
        delays_row.addWidget(self.spn_delay_off)
        delays_row.addStretch()
        eg_l.addLayout(delays_row)

        # Shifting Options checkboxes
        shift_row = QHBoxLayout()
        self.chk_shift_chan = QCheckBox("Shift all following events in the Channel / 平移本通道后续所有事件")
        self.chk_shift_chan.setChecked(True)
        self.chk_shift_chan.toggled.connect(self._redraw) # Live update timeline highlight
        shift_row.addWidget(self.chk_shift_chan)
        
        self.chk_shift_all = QCheckBox("Shift all following events in ALL Channels / 平移所有通道后续所有事件")
        self.chk_shift_all.setChecked(False)
        self.chk_shift_all.toggled.connect(self._redraw) # Live update timeline highlight
        shift_row.addWidget(self.chk_shift_all)
        shift_row.addStretch()
        eg_l.addLayout(shift_row)

        main_layout.addWidget(editor_grp, stretch=5)
        root.addLayout(main_layout)

        # Waveform preview canvas
        wgrp = QGroupBox("Live Timing Diagram / 实时时序预览 — click a pulse to select, drag edges to stretch/shift")
        wl = QVBoxLayout(wgrp)
        wl.setContentsMargins(4, 4, 4, 4)
        self.canvas = WaveformCanvas()
        wl.addWidget(self.canvas)
        root.addWidget(wgrp)

        # Bottom Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_reset = QPushButton("Reset Defaults / 重置")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)
        btn_cancel = QPushButton("Cancel / 取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        btn_ok = QPushButton("OK / 确认")
        btn_ok.setObjectName("btnOK")
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_ok)
        root.addLayout(btn_row)

    def select_pulse(self, channel_idx: int, pulse_idx: int):
        """Highlights the clicked pulse on the diagram and highlights its row in the table."""
        self.selected_pulse = (channel_idx, pulse_idx)
        
        if channel_idx != self.active_channel_idx:
            # Switch combobox first (which calls selection changed and updates active_channel_idx)
            self.cmb_channel.setCurrentIndex(channel_idx)
            
        # Highlight corresponding row in the table
        for i, row in enumerate(self.rows):
            if i == pulse_idx:
                row.set_selected(True)
                self.scroll.ensureWidgetVisible(row)
            else:
                row.set_selected(False)

        # Update absolute start/end delay spinners
        ch = self.channels[channel_idx]
        pulses = ch.get("pulses", [])
        if pulse_idx < len(pulses):
            p = pulses[pulse_idx]
            self.spn_delay_on.blockSignals(True)
            self.spn_delay_off.blockSignals(True)
            self.spn_delay_on.setValue(p.get("start_time", 0.0))
            self.spn_delay_off.setValue(p.get("start_time", 0.0) + p["rise"] * p["d"])
            self.spn_delay_on.blockSignals(False)
            self.spn_delay_off.blockSignals(False)

        self._redraw()

    def _on_row_focused(self, row: ChannelRow):
        """Callback when user clicks directly inside a row's inputs."""
        self.select_pulse(self.active_channel_idx, row.index)

    def _on_pb_mapping_changed(self, val: int):
        if self.active_channel_idx >= 0 and self.active_channel_idx < len(self.channels):
            self.channels[self.active_channel_idx]["pbn"] = val
            # Sync to any existing pulses in the channel for 100% legacy compatibility
            for p in self.channels[self.active_channel_idx].get("pulses", []):
                p["pbn"] = val
            self._redraw()

    def _on_channel_selection_changed(self, new_idx: int):
        if new_idx < 0 or new_idx >= len(self.channels):
            return
        
        # 1. Save current active rows to previous channel pulses
        self.save_current_channel_pulses()

        # 2. Switch indices
        self.active_channel_idx = new_idx
        ch = self.channels[new_idx]

        self._loading_channel = True
        try:
            # 2.1 Load channel pbn mapping into general channel spinbox
            self.spn_pb_mapping.blockSignals(True)
            ch_pbn = _get_channel_pbn(ch, new_idx)
            self.spn_pb_mapping.setValue(ch_pbn)
            self.spn_pb_mapping.blockSignals(False)

            # 3. Reload pulse rows inside the table
            self.clear_pulse_rows_only()
            for i, p in enumerate(ch.get("pulses", [])):
                self.add_pulse_row(p, trigger_redraw=False)
                
            self.reindex_pulse_rows()

            # 4. If selected pulse belongs to this channel, keep highlighting
            if self.selected_pulse and self.selected_pulse[0] == new_idx:
                sel_pulse_idx = self.selected_pulse[1]
                if sel_pulse_idx < len(self.rows) and sel_pulse_idx < len(ch.get("pulses", [])):
                    self.rows[sel_pulse_idx].set_selected(True)
                    p = ch["pulses"][sel_pulse_idx]
                    self.spn_delay_on.blockSignals(True)
                    self.spn_delay_off.blockSignals(True)
                    self.spn_delay_on.setValue(p.get("start_time", 0.0))
                    self.spn_delay_off.setValue(p.get("start_time", 0.0) + p["rise"] * p["d"])
                    self.spn_delay_on.blockSignals(False)
                    self.spn_delay_off.blockSignals(False)
                else:
                    self.selected_pulse = None
                    self.spn_delay_on.blockSignals(True)
                    self.spn_delay_off.blockSignals(True)
                    self.spn_delay_on.setValue(0.0)
                    self.spn_delay_off.setValue(0.0)
                    self.spn_delay_on.blockSignals(False)
                    self.spn_delay_off.blockSignals(False)
            else:
                # Select first pulse in channel by default
                if self.rows:
                    self.select_pulse(new_idx, 0)
                else:
                    self.selected_pulse = None
                    self.spn_delay_on.blockSignals(True)
                    self.spn_delay_off.blockSignals(True)
                    self.spn_delay_on.setValue(0.0)
                    self.spn_delay_off.setValue(0.0)
                    self.spn_delay_on.blockSignals(False)
                    self.spn_delay_off.blockSignals(False)
        finally:
            self._loading_channel = False

        self._redraw()

    def save_current_channel_pulses(self):
        """Saves current table row values to self.channels list."""
        if self.active_channel_idx >= 0 and self.active_channel_idx < len(self.channels):
            # Save channel level pbn
            self.channels[self.active_channel_idx]["pbn"] = self.spn_pb_mapping.value()
            
            # Keep start_times from raw data when mapping table row entries
            existing_pulses = self.channels[self.active_channel_idx].get("pulses", [])
            row_pulses = []
            for i, r in enumerate(self.rows):
                p_params = r.get_params()
                # Overwrite p_params["pbn"] with channel physical pbn value for legacy compatibility
                p_params["pbn"] = self.spn_pb_mapping.value()
                # Preserve existing start_time
                if i < len(existing_pulses):
                    p_params["start_time"] = existing_pulses[i].get("start_time", 0.0)
                else:
                    # New pulse starts at the end of the previous pulse
                    if row_pulses:
                        prev_p = row_pulses[-1]
                        p_params["start_time"] = prev_p["start_time"] + prev_p["rise"] * prev_p["d"]
                    else:
                        p_params["start_time"] = 0.0
                row_pulses.append(p_params)
                
            self.channels[self.active_channel_idx]["pulses"] = row_pulses

    def _on_delay_on_changed(self, new_val):
        """Called when user edits Pulse Start Time spinbox."""
        if not self.selected_pulse:
            return
        ch_idx, p_idx = self.selected_pulse
        pulses = self.channels[ch_idx].get("pulses", [])
        if p_idx < len(pulses):
            p = pulses[p_idx]
            old_start = p.get("start_time", 0.0)
            delta = new_val - old_start
            
            self.shift_pulse_timeline(ch_idx, p_idx, delta)

    def shift_pulse_timeline(self, ch_idx: int, p_idx: int, delta: float):
        """Applies timeline shifting to the selected pulse block (and subsequent ones if checkboxes are checked)."""
        if abs(delta) < 1e-6:
            return

        p_target = self.channels[ch_idx]["pulses"][p_idx]
        t_threshold = p_target.get("start_time", 0.0)

        if self.chk_shift_all.isChecked():
            # Shift all channels
            for ch in self.channels:
                for p in ch.get("pulses", []):
                    if p.get("start_time", 0.0) >= t_threshold - 1e-4:
                        p["start_time"] = max(0.0, p.get("start_time", 0.0) + delta)
        elif self.chk_shift_chan.isChecked():
            # Shift this channel only
            ch = self.channels[ch_idx]
            for p in ch.get("pulses", []):
                if p.get("start_time", 0.0) >= t_threshold - 1e-4:
                    p["start_time"] = max(0.0, p.get("start_time", 0.0) + delta)
        else:
            # Shift this selected pulse block only
            p_target["start_time"] = max(0.0, p_target.get("start_time", 0.0) + delta)

        # Update end time readout spinner
        p_target_new = self.channels[ch_idx]["pulses"][p_idx]
        self.spn_delay_on.blockSignals(True)
        self.spn_delay_off.blockSignals(True)
        if abs(self.spn_delay_on.value() - p_target_new.get("start_time", 0.0)) > 1e-6:
            self.spn_delay_on.setValue(p_target_new.get("start_time", 0.0))
        self.spn_delay_off.setValue(p_target_new.get("start_time", 0.0) + p_target_new["rise"] * p_target_new["d"])
        self.spn_delay_on.blockSignals(False)
        self.spn_delay_off.blockSignals(False)

        self._redraw()

    def add_pulse_row(self, p: dict = None, trigger_redraw: bool = True) -> ChannelRow:
        idx = len(self.rows)
        row = ChannelRow(idx, parent=self.scroll_content)
        row.changed.connect(self._on_table_row_changed)
        row.deleteRequested.connect(self.remove_pulse_row)
        row.focused.connect(self._on_row_focused)

        if p:
            row.set_params(p)
        else:
            # Default values
            row.spn_rise.setValue(1)
            row.spn_ton.setValue(1.0)
            row.spn_dt.setValue(10.0)
            row.txt_type.setText("notype")
            row.spn_phas.setValue(0.0)

        # Insert row just before spacer
        self.scroll_layout.insertWidget(len(self.rows), row)
        self.rows.append(row)

        self.reindex_pulse_rows()
        if trigger_redraw:
            self.save_current_channel_pulses()
            self._redraw()
        return row

    def remove_pulse_row(self, row: ChannelRow):
        self.scroll_layout.removeWidget(row)
        row.deleteLater()
        self.rows.remove(row)
        self.reindex_pulse_rows()
        
        # Select another pulse in active channel
        if self.rows:
            self.select_pulse(self.active_channel_idx, max(0, row.index - 1))
        else:
            self.selected_pulse = None
            self.spn_delay_on.blockSignals(True)
            self.spn_delay_off.blockSignals(True)
            self.spn_delay_on.setValue(0.0)
            self.spn_delay_off.setValue(0.0)
            self.spn_delay_on.blockSignals(False)
            self.spn_delay_off.blockSignals(False)
        
        self.save_current_channel_pulses()
        self._redraw()

    def clear_pulse_rows(self):
        self.clear_pulse_rows_only()
        self.selected_pulse = None
        self.spn_delay_on.blockSignals(True)
        self.spn_delay_off.blockSignals(True)
        self.spn_delay_on.setValue(0.0)
        self.spn_delay_off.setValue(0.0)
        self.spn_delay_on.blockSignals(False)
        self.spn_delay_off.blockSignals(False)
        self.save_current_channel_pulses()
        self._redraw()

    def clear_pulse_rows_only(self):
        for r in list(self.rows):
            self.scroll_layout.removeWidget(r)
            r.deleteLater()
        self.rows.clear()

    def reindex_pulse_rows(self):
        for i, r in enumerate(self.rows):
            r.index = i
            r.set_selected(self.selected_pulse == (self.active_channel_idx, i))

    def _on_table_row_changed(self):
        if getattr(self, "_loading_channel", False):
            return
        self.save_current_channel_pulses()
        # Update DelayOFF spinner end time
        if self.selected_pulse:
            ch_idx, p_idx = self.selected_pulse
            if ch_idx == self.active_channel_idx and p_idx < len(self.rows):
                r = self.rows[p_idx]
                p = r.get_params()
                self.spn_delay_off.setValue(self.spn_delay_on.value() + p["rise"] * p["d"])
        self._redraw()

    def add_logical_channel(self):
        """Adds a completely new logical channel to the selector."""
        self.save_current_channel_pulses()
        new_ch_idx = len(self.channels)
        
        new_ch = {
            "channel_name": f"Channel {new_ch_idx + 1}",
            "delay_off": 0.0,
            "pbn": new_ch_idx,
            "pulses": []
        }
        self.channels.append(new_ch)
        
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.addItem(new_ch["channel_name"])
        self.cmb_channel.blockSignals(False)
        
        # Switch to newly added channel
        self.cmb_channel.setCurrentIndex(new_ch_idx)

    def delete_logical_channel(self):
        """Deletes the active logical channel."""
        if len(self.channels) <= 1:
            QMessageBox.warning(self, "Warning", "Cannot delete! Must keep at least one channel.")
            return

        self.channels.pop(self.active_channel_idx)
        
        # Re-index remaining logical channel names
        for i, ch in enumerate(self.channels):
            ch["channel_name"] = f"Channel {i + 1}"

        # Re-build combobox items
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.clear()
        for ch in self.channels:
            self.cmb_channel.addItem(ch["channel_name"])
        self.cmb_channel.blockSignals(False)

        # Switch to nearest channel
        next_idx = max(0, self.active_channel_idx - 1)
        self.cmb_channel.setCurrentIndex(next_idx)

    def load_sequence_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Sequence / 载入时序", "", "JSON (*.json);;All (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                params = json.load(f)
            self.load_params(adapt_legacy_sequence(params))
            self.active_file = path
            QMessageBox.information(self, "Success / 成功", f"Sequence loaded successfully from:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error / 错误", f"Failed to load sequence: {e}")

    def save_sequence(self):
        self.save_current_channel_pulses()
        if not self.active_file:
            self.save_sequence_as()
            return
        try:
            params = self.get_params()
            with open(self.active_file, "w", encoding="utf-8") as f:
                json.dump(params, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "Success / 成功", f"Sequence successfully saved to:\n{self.active_file}")
        except Exception as e:
            QMessageBox.critical(self, "Error / 错误", f"Failed to save sequence: {e}")

    def save_sequence_as(self):
        self.save_current_channel_pulses()
        path, _ = QFileDialog.getSaveFileName(self, "Save Sequence As", "", "JSON (*.json);;All (*)")
        if not path:
            return
        try:
            params = self.get_params()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(params, f, indent=2, ensure_ascii=False)
            self.active_file = path
            QMessageBox.information(self, "Success / 成功", f"Sequence exported successfully to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error / 错误", f"Failed to save sequence: {e}")

    def import_legacy_sequence(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Legacy Sequence / 导入旧版时序", "", "Text Files (*.txt);;All (*)")
        if not path:
            return
        try:
            parsed_channels = parse_legacy_sequence(path)
            self.load_params(parsed_channels)
            self.active_file = ""  # Reset active JSON file path since this is imported
            QMessageBox.information(self, "Success / 成功", f"Legacy sequence imported successfully from:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error / 错误", f"Failed to import legacy sequence: {e}")

    def export_legacy_sequence(self):
        self.save_current_channel_pulses()
        path, _ = QFileDialog.getSaveFileName(self, "Export Legacy Sequence / 导出旧版时序", "", "Text Files (*.txt);;All (*)")
        if not path:
            return
        try:
            export_to_legacy(self.channels, path)
            QMessageBox.information(self, "Success / 成功", f"Sequence exported successfully in legacy format to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error / 错误", f"Failed to export legacy sequence: {e}")

    def _redraw(self):
        if hasattr(self, "canvas"):
            # Deep clone parameters list with active updates
            display_channels = []
            for i, ch in enumerate(self.channels):
                if i == self.active_channel_idx:
                    # Update pulses start_times from active row details
                    row_pulses = []
                    existing_pulses = ch.get("pulses", [])
                    for r_idx, r in enumerate(self.rows):
                        p_params = r.get_params()
                        if r_idx < len(existing_pulses):
                            p_params["start_time"] = existing_pulses[r_idx].get("start_time", 0.0)
                        row_pulses.append(p_params)
                        
                    display_channels.append({
                        "channel_name": ch["channel_name"],
                        "delay_off": ch.get("delay_off", 0.0),
                        "pbn": self.spn_pb_mapping.value(),
                        "pulses": row_pulses
                    })
                else:
                    display_channels.append(ch)
            self.canvas.draw_sequence(display_channels)

    def _accept(self):
        self.save_current_channel_pulses()
        self.sequenceAccepted.emit(self.channels)
        self.accept()

    def _reset_defaults(self):
        self.load_params([
            {
                "channel_name": f"Channel {i + 1}",
                "delay_off": 0.0,
                "pulses": []
            }
            for i in range(4)
        ])

    def load_params(self, params: list):
        self.channels = params
        
        # Populate combobox and select index 0 with signals blocked to avoid redundant trigger
        self.cmb_channel.blockSignals(True)
        self.cmb_channel.clear()
        for ch in self.channels:
            self.cmb_channel.addItem(ch.get("channel_name", "Channel"))
        self.cmb_channel.setCurrentIndex(0)
        self.cmb_channel.blockSignals(False)

        # Set active_channel_idx to -1 so the first explicit selection load does not overwrite loaded data
        self.active_channel_idx = -1
        self._on_channel_selection_changed(0)

    def get_params(self) -> list:
        self.save_current_channel_pulses()
        return self.channels


if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = EditSequenceDialog()
    if dlg.exec_() == QDialog.Accepted:
        print(json.dumps(dlg.get_params(), indent=2, ensure_ascii=False))
    sys.exit(0)
