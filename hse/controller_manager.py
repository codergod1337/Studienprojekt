# hse/controller_manager.py

import sys
import threading
import time
from pathlib import Path

# Wenn das Modul direkt ausgeführt wird, sicherstellen, dass das Projekt-Root drin ist
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import pygame
from typing import Dict, Any, Optional

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QProgressBar, QSizePolicy, QComboBox, QScrollArea,
    QPushButton, QCheckBox
)
from PyQt5.QtCore import QTimer, Qt, QObject
from hse.data_manager import DataManager

from hse.utils.settings import DEFAULT_VALUES



class ControllerManager(QObject):
    """
    Kern-Loop für Joystick-Eingaben in einem eigenen Thread:
    - Liest kontinuierlich alle Achsen- und Button-Zustände.
    - Speichert in self.raw_axes und self.raw_buttons die rohen Werte.
    - Speichert in self.last_values die Werte nur für die aktuell gemappten Funktionen.
    - Bietet get_all_states() und get_current_control().
    """

    def __init__(self, data_manager: DataManager):
        super().__init__()
        pygame.init()
        pygame.joystick.init()

        self.data = data_manager
        self.controls_cfg: Dict[str, Dict[str, Optional[int]]] = self.data.get("controls", {})
        self.invert_cfg: Dict[int, bool] = self.data.get("invert_axes", {}) or {}

        # Raw-Werte für alle Achsen und Buttons
        self.raw_axes: Dict[int, float] = {}
        self.raw_buttons: Dict[int, bool] = {}

        # Gemappte Funktions-Werte
        self.last_values: Dict[str, Any] = {func: None for func in self.controls_cfg.keys()}

        self.dead_zone = 0.05

        self.joystick: Optional[pygame.joystick.Joystick] = None
        if pygame.joystick.get_count() > 0:
            js = pygame.joystick.Joystick(0)
            js.init()
            self.joystick = js
            # Initialisiere raw dicts, sobald Joystick da ist:
            for i in range(js.get_numaxes()):
                self.raw_axes[i] = 0.0
            for j in range(js.get_numbuttons()):
                self.raw_buttons[j] = False
            print(f"Gerät gefunden: {js.get_name()}")
        else:
            print("Kein Joystick gefunden – der Hintergrund-Thread läuft trotzdem.")

        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    def _scan_loop(self):
        while self._running:
            try:
                pygame.event.pump()
            except pygame.error:
                break

            with self._lock:
                if self.joystick:
                    # Alle Achsen-Rohwerte aktualisieren
                    for i in range(self.joystick.get_numaxes()):
                        raw = self.joystick.get_axis(i)
                        if abs(raw) < self.dead_zone:
                            raw = 0.0
                        if self.invert_cfg.get(i, False):
                            raw = -raw
                        self.raw_axes[i] = raw

                    # Alle Button-Rohwerte aktualisieren
                    for j in range(self.joystick.get_numbuttons()):
                        self.raw_buttons[j] = bool(self.joystick.get_button(j))

                # Gemappte Funktions-Werte anhand controls_cfg berechnen
                for func, mapping in self.controls_cfg.items():
                    mtype = mapping.get("type")
                    idx = mapping.get("id")
                    if mtype == "axis" and idx in self.raw_axes:
                        self.last_values[func] = self.raw_axes[idx]
                    elif mtype == "button" and idx in self.raw_buttons:
                        self.last_values[func] = 1.0 if self.raw_buttons[idx] else 0.0
                    else:
                        self.last_values[func] = None

            time.sleep(0.033)   # ~30Hz

    def get_all_states(self) -> Dict[str, Dict[Any, Any]]:
        """
        Gibt alle rohen Achsen- und Button-Werte zurück:
          {
            "axes":   {0: 0.00, 1: -0.50, ...},
            "buttons": {0: False, 1: True, ...}
          }
        """
        with self._lock:
            return {
                "axes": dict(self.raw_axes),
                "buttons": dict(self.raw_buttons)
            }

    def get_current_control(self) -> Dict[str, Any]:
        """
        Gibt nur die Werte für aktuell gemappte Funktionen zurück, z. B.:
          {
            "throttle": 0.75,
            "brake":    0.00,
            "reverse":  1.0,
            ...
          }
        """
        with self._lock:
            return dict(self.last_values)

    def set_mapping(self, func: str, mtype: str, idx: int):
        with self._lock:
            self.controls_cfg[func] = {"type": mtype, "id": idx}
            self.data.set("controls", self.controls_cfg)

    def set_invert(self, axis_idx: int, invert_flag: bool):
        with self._lock:
            self.invert_cfg[axis_idx] = invert_flag
            self.data.set("invert_axes", self.invert_cfg)

    def set_device(self, index: int):
        with self._lock:
            if self.joystick:
                self.joystick.quit()
            js = pygame.joystick.Joystick(index)
            js.init()
            self.joystick = js
            # reset raw_axes/raw_buttons für neue Counts
            self.raw_axes = {i: 0.0 for i in range(js.get_numaxes())}
            self.raw_buttons = {j: False for j in range(js.get_numbuttons())}

    def shutdown(self):
        self._running = False
        self._thread.join(timeout=0.5)
        if self.joystick:
            self.joystick.quit()
        pygame.quit()
        """
        Stoppt den Hintergrund-Thread und beendet pygame (Joystick).
        """
        self._running = False
        self._thread.join(timeout=0.5)
        if self.joystick:
            self.joystick.quit()
        pygame.quit()


class JoystickVisualizer(QWidget):
    """
    GUI, die die Daten aus einem vorhandenen ControllerManager verwendet:
    - Liest Achsen- und Button-Werte via cm.get_current_control()
    - Erkennt Keybinding („Set“), indem es direkt auf cm.joystick zugreift
    - Inversionen über cm.set_invert() speichern
    - Highlight und Farbcodierung analog zu den Funktionen
    """

    def __init__(self, controller_manager):
        super().__init__()
        self.cm = controller_manager
        # DataManager und Mapping/Inversion übernehmen
        self.data_manager = self.cm.data
        self.controls_cfg = self.cm.controls_cfg
        self.invert_cfg = self.cm.invert_cfg

        self.setWindowTitle("Joystick & Keybindings Visualizer")
        self.layout = QVBoxLayout(self)

        # Dropdown für Joystick (wählt nur das Gerät, CM benutzt immer den ersten)
        self.device_selector = QComboBox()
        self.device_selector.currentIndexChanged.connect(self._on_device_change)
        self.layout.addWidget(QLabel("Joystick auswählen:"))
        self.layout.addWidget(self.device_selector)

        # Container, der Achsen, Buttons, Keybindings enthält
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.container = QWidget()                    # ← in Attribut umwandeln
        self.container_layout = QVBoxLayout(self.container)
        scroll.setWidget(self.container)
        self.layout.addWidget(scroll)

        # Platzhalter-GroupBoxes
        self.axis_group: Optional[QGroupBox] = None
        self.button_group: Optional[QGroupBox] = None
        self.keybind_group: Optional[QGroupBox] = None

        # Widgets-Referenzen
        self.axis_bars: Dict[int, QProgressBar] = {}
        self.axis_values: Dict[int, QLabel] = {}
        self.axis_inverters: Dict[int, QCheckBox] = {}
        self.button_indicators: Dict[int, QLabel] = {}
        self.keybind_buttons: Dict[str, QPushButton] = {}
        self.keybind_assigned: Dict[str, QLabel] = {}

        # Keybinding-Zustand
        self.current_setting: Optional[str] = None
        self.setting_button: Optional[QPushButton] = None

        # Joystick-Liste ins Dropdown füllen (ohne CM zu verändern)
        pygame.event.pump()
        self.device_selector.blockSignals(True)
        self._init_device_list()
        self.device_selector.blockSignals(False)

        # Wenn mindestens ein Joystick, UI aufbauen
        if self.device_selector.count() > 0:
            self.device_selector.setCurrentIndex(0)
            self._build_ui_for_joystick(0)

        # Timer, um alle 50 ms die GUI zu aktualisieren
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update_states)
        self._timer.start(50)

        # → Alle Child-Layouts einmal aktualisieren, damit sizeHint stimmt:
        self.container.adjustSize()
        self.adjustSize()

        # → Berechne Breite und Höhe anhand des gesamten Inhalts:
        content_height = self.container.sizeHint().height()
        selector_height = self.device_selector.sizeHint().height()
        extra = 50
        content_width = self.container.sizeHint().width()

        self.setMinimumSize(content_width + 40, selector_height + content_height + extra)
        self.resize(content_width + 40, selector_height + content_height + extra)

        self.show()

    def _init_device_list(self):
        """Füllt das Dropdown mit allen vorhandenen Joysticks."""
        count = pygame.joystick.get_count()
        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()
            name = js.get_name()
            self.device_selector.addItem(f"{i}: {name}")

    def _on_device_change(self, index: int):
        """
        Wechselt das angezeigte GUI für einen anderen Joystick.
        (CM benutzt jedoch immer den ersten – hier nur UI‐Neubau.)
        """
        for grp in (self.axis_group, self.button_group, self.keybind_group):
            if grp:
                self.container_layout.removeWidget(grp)
                grp.deleteLater()
        self.axis_group = self.button_group = self.keybind_group = None
        self.axis_bars.clear()
        self.axis_values.clear()
        self.axis_inverters.clear()
        self.button_indicators.clear()
        self.keybind_buttons.clear()
        self.keybind_assigned.clear()
        self.current_setting = None
        self.setting_button = None

        # Joystick-Index für CM setzen (optional)
        if pygame.joystick.get_count() > index:
            # Sage dem ControllerManager, er soll auf Gerät `index` umschalten
            self.cm.set_device(index)

            #js = pygame.joystick.Joystick(index)
            #js.init()
            ## CM verwendet diesen Joystick
            #self.cm.joystick = js

        self._build_ui_for_joystick(index)
        self.adjustSize()

    def _build_ui_for_joystick(self, index: int):
        """Erstellt die GroupBoxes für Achsen, Buttons und Keybindings."""
        js = self.cm.joystick
        num_axes = 0 if js is None else js.get_numaxes()
        num_buttons = 0 if js is None else js.get_numbuttons()

        # ‣ Achsen-GroupBox
        self.axis_group = QGroupBox("Achsen")
        axis_layout = QVBoxLayout(self.axis_group)
        for i in range(num_axes):
            row = QHBoxLayout()
            label = QLabel(f"Achse {i}:")
            label.setFixedWidth(60)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(50)
            bar.setTextVisible(False)
            bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

            value_label = QLabel("0.00")
            value_label.setFixedWidth(40)

            inverter = QCheckBox("Invertiere")
            inverter.setChecked(self.invert_cfg.get(i, False))
            # Wenn invert umgeschaltet, direkt in CM speichern:
            inverter.stateChanged.connect(lambda state, idx=i: self.cm.set_invert(idx, state == Qt.Checked))

            row.addWidget(label)
            row.addWidget(bar)
            row.addWidget(value_label)
            row.addWidget(inverter)

            axis_layout.addLayout(row)
            self.axis_bars[i] = bar
            self.axis_values[i] = value_label
            self.axis_inverters[i] = inverter

        self.container_layout.addWidget(self.axis_group)

        # ‣ Buttons-GroupBox
        self.button_group = QGroupBox("Buttons")
        button_layout = QGridLayout(self.button_group)
        for j in range(num_buttons):
            btn_label = QLabel(f"Button {j}:")
            btn_label.setFixedWidth(70)

            indicator = QLabel()
            indicator.setFixedSize(16, 16)
            indicator.setStyleSheet(self._indicator_style(False))

            row = j // 4
            col = (j % 4) * 2
            button_layout.addWidget(btn_label, row, col)
            button_layout.addWidget(indicator, row, col + 1)

            self.button_indicators[j] = indicator

        self.container_layout.addWidget(self.button_group)

        # ‣ Keybindings-GroupBox
        self.keybind_group = QGroupBox("Keybindings")
        key_layout = QVBoxLayout(self.keybind_group)
        functions = list(self.controls_cfg.keys())
        for func in functions:
            h = QHBoxLayout()
            lbl = QLabel(f"{func}:")
            lbl.setFixedWidth(100)

            assigned_label = QLabel(self._assigned_text(func))
            clr = DEFAULT_VALUES["controls"].get(func, {}).get("color", "#000")
            assigned_label.setStyleSheet(
            f"color: {clr}; font-weight: bold;")
            assigned_label.setFixedWidth(80)

            btn = QPushButton("Set")
            btn.setFixedWidth(80)
            btn.setObjectName(func)
            btn.clicked.connect(self._on_set_clicked)

            h.addWidget(lbl)
            h.addWidget(assigned_label)
            h.addWidget(btn)
            h.addStretch()
            key_layout.addLayout(h)

            self.keybind_buttons[func] = btn
            self.keybind_assigned[func] = assigned_label

        self.container_layout.addWidget(self.keybind_group)

        # Markierungen aller bereits gemappten Steuerungen
        self._update_highlights()

    def _assigned_text(self, func: str) -> str:
        mapping = self.controls_cfg.get(func, {"type": None, "id": None})
        if mapping.get("type") == "axis":
            return f"Axis {mapping.get('id')}"
        elif mapping.get("type") == "button":
            return f"Btn {mapping.get('id')}"
        else:
            return "None"

    def _on_set_clicked(self):
        """Wechselt in den Keybinding-Modus für die gewählte Funktion."""
        sender = self.sender()
        if isinstance(sender, QPushButton):
            self.current_setting = sender.objectName()
            self.setting_button = sender
            sender.setText("Move...")

    def update_states(self):
        """
        Wird per Timer alle 50 ms aufgerufen:
        - Liest aktuelle Werte via cm.get_all_states() und cm.get_current_control()
        - Aktualisiert Balken, Werte-Labels und Button-Indikatoren
        - Wenn im Keybinding-Modus, ordnet Achse/Knopf via cm.set_mapping() neu zu
        """
        js = self.cm.joystick
        if js is None:
            return

        # ‣ Keybinding-Modus?
        if self.current_setting and self.setting_button:
            # Button‐Mapping prüfen
            for j in range(js.get_numbuttons()):
                if js.get_button(j):
                    self.cm.set_mapping(self.current_setting, "button", j)
                    self.keybind_assigned[self.current_setting].setText(f"Btn {j}")
                    self._reset_set_button()
                    self._update_highlights()
                    return

            # Achsen‐Mapping prüfen (|Wert| > 0.5)
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                if abs(val) > 0.5:
                    self.cm.set_mapping(self.current_setting, "axis", i)
                    self.keybind_assigned[self.current_setting].setText(f"Axis {i}")
                    self._reset_set_button()
                    self._update_highlights()
                    return

            # Wenn weiterhin im Set-Modus, brechen wir ohne Update ab
            return

        # ‣ Normale Anzeige (Rohdaten aus ControllerManager)
        all_states = self.cm.get_all_states()
        axes_states = all_states["axes"]
        buttons_states = all_states["buttons"]

        # – Achsen anzeigen:
        for i, bar in self.axis_bars.items():
            raw = axes_states.get(i, 0.0)

            pct = int((raw + 1.0) * 50)
            bar.setValue(pct)
            self.axis_values[i].setText(f"{raw:.2f}")

        # – Buttons anzeigen:
        for j, indicator in self.button_indicators.items():
            func_name = self._func_for_button(j)
            if func_name:
                # Wenn dieser Button einer Funktion zugeordnet ist,
                # dann den bereits gemappten Wert aus get_current_control() verwenden
                mapped_values = self.cm.get_current_control()
                val = mapped_values.get(func_name, 0.0)
                pressed = (val == 1.0)
                color = DEFAULT_VALUES["controls"].get(func_name, {}).get("color", "#000")
                bg_color = "#0f0" if pressed else "#888"
                indicator.setStyleSheet(
                    f"background-color: {bg_color}; border: 2px solid {color}; border-radius: 8px;"
                )
            else:
                # Wenn nicht gemappt, trotzdem den rohen Button-Zustand anzeigen
                pressed = buttons_states.get(j, False)
                indicator.setStyleSheet(self._indicator_style(pressed))

    def _func_for_axis(self, axis_idx: int) -> Optional[str]:
        """Gibt den Funktionsnamen zurück, der auf Achse axis_idx gemappt ist."""
        for func, mapping in self.controls_cfg.items():
            if mapping.get("type") == "axis" and mapping.get("id") == axis_idx:
                return func
        return None

    def _func_for_button(self, btn_idx: int) -> Optional[str]:
        """Gibt den Funktionsnamen zurück, der auf Button btn_idx gemappt ist."""
        for func, mapping in self.controls_cfg.items():
            if mapping.get("type") == "button" and mapping.get("id") == btn_idx:
                return func
        return None

    def _reset_set_button(self):
        """Beendet den Keybinding-Modus und setzt den Button-Text zurück."""
        if self.setting_button:
            self.setting_button.setText("Set")
        self.current_setting = None
        self.setting_button = None

    def _update_highlights(self):
        """Hebt alle gemappten Achsen/Buttons farblich hervor."""
        for i, bar in self.axis_bars.items():
            bar.setStyleSheet("")
        for j, indicator in self.button_indicators.items():
            indicator.setStyleSheet(self._indicator_style(False))

        for func, mapping in self.controls_cfg.items():
            color = DEFAULT_VALUES["controls"].get(func, {}).get("color", "#000")
            if mapping.get("type") == "axis":
                idx = mapping.get("id")
                if idx in self.axis_bars:
                    self.axis_bars[idx].setStyleSheet(
                        f"QProgressBar {{border: 2px solid {color};}}"
                    )
            elif mapping.get("type") == "button":
                idx = mapping.get("id")
                if idx in self.button_indicators:
                    self.button_indicators[idx].setStyleSheet(
                        f"background-color: #888; border: 2px solid {color}; border-radius: 8px;"
                    )

    def _indicator_style(self, pressed: bool) -> str:
        """Stylesheet: Grün, wenn gedrückt; Grau, wenn nicht."""
        color = "#0f0" if pressed else "#888"
        return (
            f"background-color: {color}; "
            "border: 1px solid black; "
            "border-radius: 8px;"
        )

    def closeEvent(self, event):
        """
        Nur die Visualisierung schließen, ControllerManager bleibt aktiv.
        Daher rufen wir hier nicht pygame.quit() auf, sondern nur das Fenster schließen.
        """
        self._timer.stop()
        super().closeEvent(event)


if __name__ == "__main__":
    """
    Startet beim Direktaufruf:
    1. Den ControllerManager (im Hintergrund-Thread).
    2. Die JoystickVisualizer-GUI, die live die Werte anzeigt und Keybindings erlaubt.
    """
    app = QApplication(sys.argv)
    dm = DataManager()
    cm = ControllerManager(dm)
    visualizer = JoystickVisualizer(cm)
    sys.exit(app.exec_())









































