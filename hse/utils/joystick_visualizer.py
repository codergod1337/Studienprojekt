import sys
from pathlib import Path

# Ensure project root is in sys.path
root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from typing import Dict, Optional
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QProgressBar, QComboBox, QScrollArea,
    QPushButton, QCheckBox
)
from PyQt5.QtCore import QTimer, Qt
from hse.data_manager import DataManager
from hse.controller_manager import ControllerManager
from hse.utils.settings import DEFAULT_VALUES

class JoystickVisualizer(QWidget):
    def __init__(self, controller_manager: ControllerManager):
        super().__init__()
        self.cm = controller_manager

        # Window setup
        self.setWindowTitle("Joystick & Keybindings Visualizer")
        main_layout = QVBoxLayout(self)

        # Device selector dropdown
        self.device_selector = QComboBox()
        for idx, js in enumerate(self.cm.joysticks):
            self.device_selector.addItem(f"{idx}: {js.get_name()}", idx)
        self.device_selector.currentIndexChanged.connect(self._on_device_change)
        main_layout.addWidget(QLabel("Select Joystick:"))
        main_layout.addWidget(self.device_selector)

        # Scroll area for dynamic UI
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        scroll.setWidget(self.container)
        main_layout.addWidget(scroll)

        # Initialize widget containers
        self.axis_group = None
        self.button_group = None
        self.keybind_group = None
        self.axis_bars: Dict[int, QProgressBar] = {}
        self.axis_values: Dict[int, QLabel] = {}
        self.axis_inverters: Dict[int, QCheckBox] = {}
        self.axis_styles: Dict[int, QComboBox] = {}
        self.button_indicators: Dict[int, QLabel] = {}
        self.keybind_buttons: Dict[str, QPushButton] = {}
        self.keybind_assigned: Dict[str, QLabel] = {}

        # Binding state
        self.current_setting: Optional[str] = None
        self.setting_button: Optional[QPushButton] = None

        # Timer to refresh UI
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_states)
        self._timer.start(50)

        # Preload edge-detection snapshots
        with self.cm._lock:
            self._prev_raw_axes = dict(self.cm.raw_axes)
            self._prev_raw_buttons = dict(self.cm.raw_buttons)

        # Select and build UI for active joystick
        active = self.cm.current_joystick
        if active:
            for i in range(self.device_selector.count()):
                if active.get_name() in self.device_selector.itemText(i):
                    self.device_selector.setCurrentIndex(i)
                    break
        self._build_ui_for_joystick(self.device_selector.currentData())
        

    def _on_device_change(self, index: int):
        """Switch active joystick and rebuild UI."""
        # Clear existing groups
        for grp in (self.axis_group, self.button_group, self.keybind_group):
            if grp:
                self.container_layout.removeWidget(grp)
                grp.deleteLater()
        # Reset widget stores
        self.axis_bars.clear(); self.axis_values.clear()
        self.axis_inverters.clear(); self.axis_styles.clear()
        self.button_indicators.clear(); self.keybind_buttons.clear(); self.keybind_assigned.clear()
        self.current_setting = None; self.setting_button = None

        # Tell ControllerManager to switch device
        self.cm.set_device(index)
        # Rebuild UI
        self._build_ui_for_joystick(index)

    def _build_ui_for_joystick(self, index: int):
        """Create UI groups for axes, buttons, and keybindings."""
        js = self.cm.current_joystick
        name = js.get_name() if js else None
        num_axes = js.get_numaxes() if js else 0
        num_buttons = js.get_numbuttons() if js else 0

        # Axes
        self.axis_group = QGroupBox("Axes")
        axis_layout = QVBoxLayout(self.axis_group)
        for i in range(num_axes):
            lbl = QLabel(f"Axis {i}:")
            bar = QProgressBar(); bar.setRange(0, 100); bar.setTextVisible(False)
            val_lbl = QLabel("0.00"); val_lbl.setFixedWidth(40)
            inv = QCheckBox("Invert")
            style = QComboBox(); style.addItems(["unipolar", "bipolar"])
            # Load defaults
            meta = next((a for a in self.cm.known_devices[name]["axes"] if a["id"] == i), {})
            inv.setChecked(meta.get("inverted", False))
            style.setCurrentText(meta.get("style", "unipolar"))
            inv.stateChanged.connect(lambda s, idx=i: self._on_axis_invert_changed(idx, s == Qt.Checked))
            style.currentTextChanged.connect(lambda t, idx=i: self._on_axis_style_changed(idx, t))

            row = QHBoxLayout()
            row.addWidget(lbl); row.addWidget(bar); row.addWidget(val_lbl)
            row.addWidget(inv); row.addWidget(style)
            axis_layout.addLayout(row)

            self.axis_bars[i] = bar; self.axis_values[i] = val_lbl
            self.axis_inverters[i] = inv; self.axis_styles[i] = style
        self.container_layout.addWidget(self.axis_group)

        # Buttons
        self.button_group = QGroupBox("Buttons")
        btn_layout = QGridLayout(self.button_group)
        for j in range(num_buttons):
            lbl = QLabel(f"Button {j}:")
            ind = QLabel(); ind.setFixedSize(16, 16)
            ind.setStyleSheet(self._indicator_style(False))
            r, c = divmod(j, 4)
            btn_layout.addWidget(lbl, r, c*2)
            btn_layout.addWidget(ind, r, c*2+1)
            self.button_indicators[j] = ind
        self.container_layout.addWidget(self.button_group)

        # Keybindings
        self.keybind_group = QGroupBox("Keybindings")
        kb_layout = QVBoxLayout(self.keybind_group)
        for func in self.cm.controls_cfg:
            lbl = QLabel(f"{func}:")
            assigned = QLabel(self._assigned_text(func)); assigned.setFixedWidth(80)
            clr = DEFAULT_VALUES["controls"][func]["color"]
            assigned.setStyleSheet(f"color:{clr}; font-weight:bold;")
            btn = QPushButton("Set"); btn.setObjectName(func)
            btn.clicked.connect(self._on_set_clicked)
            hl = QHBoxLayout(); hl.addWidget(lbl); hl.addWidget(assigned)
            hl.addWidget(btn); hl.addStretch()
            kb_layout.addLayout(hl)
            self.keybind_assigned[func] = assigned; self.keybind_buttons[func] = btn
        self.container_layout.addWidget(self.keybind_group)

        self._update_highlights()

    def _on_axis_invert_changed(self, axis_idx: int, flag: bool):
        """Update inversion setting."""
        name = self.cm.current_joystick.get_name()
        for a in self.cm.known_devices[name]["axes"]:
            if a["id"] == axis_idx: a["inverted"] = flag; break
        self.cm.data.set("known_devices", self.cm.known_devices)

    def _on_axis_style_changed(self, axis_idx: int, style: str):
        """Update style setting."""
        name = self.cm.current_joystick.get_name()
        for a in self.cm.known_devices[name]["axes"]:
            if a["id"] == axis_idx: a["style"] = style; break
        self.cm.data.set("known_devices", self.cm.known_devices)

    def _on_set_clicked(self):
        """Enter binding mode."""
        sender = self.sender()
        if isinstance(sender, QPushButton):
            self.current_setting = sender.objectName()
            self.setting_button = sender
            sender.setText("Move...")

    def _reset_set_button(self):
        """Exit binding mode and reset text."""
        if self.setting_button: self.setting_button.setText("Set")
        self.current_setting = None; self.setting_button = None

    def update_states(self):
        """Refresh UI and handle binding logic."""
        js = self.cm.current_joystick
        if not js: return
        # Raw snapshots
        with self.cm._lock:
            raw_axes = dict(self.cm.raw_axes)
            raw_buttons = dict(self.cm.raw_buttons)
        # Binding
        if self.current_setting:
            def mapped(t, i): return any(
                cfg.get("type") == t and cfg.get("id") == i
                for f, cfg in self.cm.controls_cfg.items() if f != self.current_setting
            )
            for j, curr in raw_buttons.items():
                prev = self._prev_raw_buttons.get(j, 0)
                if curr == 1 and prev == 0 and not mapped("button", j):
                    self.cm.set_mapping(self.current_setting, "button", j)
                    self.keybind_assigned[self.current_setting].setText(f"Btn {j}")
                    self._reset_set_button(); self._update_highlights(); break
            else:
                for i, curr in raw_axes.items():
                    prev = self._prev_raw_axes.get(i, 0.0) or 0.0
                    if abs(curr) > 0.5 and abs(prev) <= 0.5 and not mapped("axis", i):
                        self.cm.set_mapping(self.current_setting, "axis", i)
                        self.keybind_assigned[self.current_setting].setText(f"Axis {i}")
                        self._reset_set_button(); self._update_highlights(); break
            self._prev_raw_axes = raw_axes; self._prev_raw_buttons = raw_buttons
            return
        # Display
        states = self.cm.get_all_states()
        for i, bar in self.axis_bars.items():
            val = states["axes"].get(i, 0.0)
            style = self.axis_styles[i].currentText()
            pct = int(val * 100) if style == "unipolar" else int((val + 1.0) * 50)
            bar.setValue(pct); self.axis_values[i].setText(f"{val:.2f}")
        for j, ind in self.button_indicators.items():
            func = self._func_for_button(j)
            if func:
                v = self.cm.get_mapped_controls().get(func, 0.0)
                pressed = v == 1.0; clr = DEFAULT_VALUES["controls"][func]["color"]
                bg = "#0f0" if pressed else "#888"
                ind.setStyleSheet(f"background-color:{bg}; border:2px solid {clr}; border-radius:8px;")
            else:
                pressed = states["buttons"].get(j, 0)
                ind.setStyleSheet(self._indicator_style(bool(pressed)))

    def _assigned_text(self, func: str) -> str:
        m = self.cm.controls_cfg.get(func, {})
        if m.get("type") == "axis": return f"Axis {m['id']}"
        if m.get("type") == "button": return f"Btn {m['id']}"
        return "None"

    def _func_for_button(self, btn_idx: int) -> Optional[str]:
        for f, m in self.cm.controls_cfg.items():
            if m.get("type") == "button" and m.get("id") == btn_idx:
                return f
        return None

    def _update_highlights(self):
        # Reset
        for bar in self.axis_bars.values(): bar.setStyleSheet("")
        for ind in self.button_indicators.values(): ind.setStyleSheet(self._indicator_style(False))
        # Highlight
        for func, m in self.cm.controls_cfg.items():
            clr = DEFAULT_VALUES["controls"][func]["color"]
            if m.get("type") == "axis":
                idx = m["id"]; self.axis_bars[idx].setStyleSheet(f"QProgressBar {{ border:2px solid {clr}; }}")
            elif m.get("type") == "button":
                idx = m["id"]; self.button_indicators[idx].setStyleSheet(
                    f"background-color:#888; border:2px solid {clr}; border-radius:8px;"
                )

    def _indicator_style(self, pressed: bool) -> str:
        bg = "#0f0" if pressed else "#888"
        return f"background-color:{bg}; border:1px solid black; border-radius:8px;"

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dm = DataManager()
    cm = ControllerManager(dm)
    viz = JoystickVisualizer(cm)
    viz.show()
    sys.exit(app.exec_())
