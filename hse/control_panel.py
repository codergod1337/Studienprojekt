# hse/control_panel.py 

import sys
import time
import subprocess
import psutil
from pathlib import Path
import datetime
from typing import Dict, Any

from PyQt5.QtCore import QObject, QEvent, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QComboBox, QMessageBox, QAction

from hse.ui_builder import build_ui
from hse.data_manager import DataManager
from hse.utils.settings import CARLA_DIR, SGG_DIR, DEFAULT_VALUES
from hse.controller_manager import JoystickVisualizer, ControllerManager
from hse.carla_connector import CarlaConnector
from hse.utils.settings import CAMERA_POSITIONS


class ControlPanel(QMainWindow):
    def __init__(self, controller_manager: ControllerManager, connector: CarlaConnector):
        super().__init__()
        self.data = DataManager()                   # ← DataManager laden
        self.cm = controller_manager                 # ← ControllerManager von außen übernehmen
        self.connector = connector                  # ← CarlaConnector von außen übernehmen
        
        self.connector.set_controller_manager(self.cm) # ControllerManager an den Connector übergeben, damit er .get_current_control() nutzt

        self.refs = build_ui(self)
        self._init_values_from_data()               # ← Werte aus JSON setzen
        self._init_connections()
        self._carla_pid = None                      # Merke PID lokal

        # Spawn-Button deaktiviert, bis connect + Modell
        self.refs["spawn_button"].setEnabled(False)
        self._connected = False

        # Recording-Buttons koppeln
        self.refs["start_record_btn"].clicked.connect(self._on_start_recording)
        self.refs["stop_record_btn"].clicked.connect(self._on_stop_recording)
        recording = self.data.get("recording_active", False)
        self.refs["start_record_btn"].setEnabled(not recording)
        self.refs["stop_record_btn"].setEnabled(recording)

        # Frame-Counter updaten
        self.refs["label_framecount"].setText("0")
        self.connector.frame_recorded.connect(self._on_frame_recorded)

        # Verbindung zur Menü-Action "controls":
        self.refs["action_controls"].triggered.connect(self._open_control_manager)

        # ── Worker-Thread für Input-GroupBox (alle 0.1 s) ──
        self._input_thread = QThread(self)
        self._input_worker = InputWorker(self.cm)
        self._input_worker.moveToThread(self._input_thread)
        self._input_thread.started.connect(self._input_worker.run)
        self._input_worker.update_signal.connect(self._update_input_fields)
        self._input_thread.start()

        # Camera Positionen laden
        self._populate_camera_menu()


        # Connector-Signal abonnieren (für nach carla connect)
        self.connector.connection_result.connect(self._on_connector_result)
        self.connector.blueprints_loaded.connect(self._populate_vehicle_menu)
        self.connector.vehicle_model_selected.connect(self._update_vehicle_label)
        self.connector.camera_position_selected.connect(self._update_camera_label)

        # Spawn-Button klick → Connector.spawn_vehicle
        self.refs["spawn_button"].clicked.connect(self._on_spawn_clicked)

    @pyqtSlot(int)
    def _on_frame_recorded(self, count: int):
        """Aktualisiert das Frame-Counter-Label."""
        self.refs["label_framecount"].setText(str(count))

    def _open_control_manager(self):
        """Öffnet das Joystick-Visualisierungs-Fenster."""
        if hasattr(self, "_control_win") and self._control_win.isVisible():
            self._control_win.raise_()
            self._control_win.activateWindow()
        else:
            self._control_win = JoystickVisualizer(self.cm)
            self._control_win.show()

    def _populate_camera_menu(self):
        """Füllt CARLA→Camera mit den in settings definierten Perspektiven."""
        menu = self.refs["menu_camera"]
        menu.clear()
        for cam in CAMERA_POSITIONS.keys():
            act = QAction(cam, self)
            act.triggered.connect(lambda _, c=cam: self.connector.set_camera_position(c))
            menu.addAction(act)


    @pyqtSlot(str)
    def _update_camera_label(self, cam_id: str):
        """Aktualisiert das Label in der Connector-GroupBox."""
        self.refs["label_camera"].setText(cam_id)


    def closeEvent(self, event):
        """Beim Schließen Worker ordentlich stoppen und Thread beenden."""
        self._input_worker.stop()
        self._input_thread.quit()
        self._input_thread.wait()
        super().closeEvent(event)


        """
        Zusätzlich hatte der Slot‐Decorator @pyqtSlot(Dict, str) provoziert, dass PyQt in 3.7 
        die Typen nicht akzeptiert. Man darf im @pyqtSlot nur dict (das eingebaute Python‐dict) 
        verwenden, nicht Dict aus typing. Erst die Methodensignatur kann intern als current: 
        Dict[str, Any] stehen, aber der Decorator muss @pyqtSlot(dict, str) lauten.
        """
    @pyqtSlot(dict, str)
    def _update_input_fields(self, current: Dict[str, Any], device_name: str):
        """
        Slot, der vom Worker-Thread alle 0.1 s aufgerufen wird.
        Schreibt Joystick‐Name und jeden Control‐Wert in die Input‐GroupBox.
        """
        # 1. Joystick‐Name
        self.refs["input_device"].setText(device_name)

        # 2. Werte pro Feature aus DEFAULT_VALUES["controls"]
        for func in DEFAULT_VALUES["controls"]:
            lbl = self.refs.get(f"input_{func}")
            if not lbl:
                continue

            val = current.get(func)
            if isinstance(val, bool):
                text = "1.00" if val else "0.00"
            elif isinstance(val, (int, float)):
                text = f"{val:.2f}"
            else:
                text = "0.00"

            color = DEFAULT_VALUES["controls"][func]["color"]
            lbl.setText(text)
            lbl.setStyleSheet(f"color: {color}; font-weight: bold;")


    def _init_values_from_data(self):
        """Lese aus DataManager und fülle UI-Felder bei Start."""
        # IP / Port
        self.refs["input_ip"].setText(self.data.get("host"))
        self.refs["input_port"].setText(str(self.data.get("port")))

        # CARLA-Version Dropdown befüllen
        dropdown: QComboBox = self.refs["carla_version"]
        dropdown.clear()
        dropdown.addItems(self.data.carla_versions)

        # Gespeicherte Version vorauswählen
        saved_version = self.data.get("carla_version")
        if saved_version in self.data.carla_versions:
            index = dropdown.findText(saved_version)
            if index != -1:
                dropdown.setCurrentIndex(index)

        # Änderung speichern, wenn Auswahl geändert wird
        dropdown.currentTextChanged.connect(lambda v: self.data.set("carla_version", v))

        # SGG-Status
        loaded = self.data.get("sgg_loaded")
        if loaded:
            self.refs["label_sgg_status"].setText("🟢 SGG ready")
            self.refs["label_sgg_status"].setStyleSheet("color: green; font-weight: bold;")
        else:
            self.refs["label_sgg_status"].setText("🔴 SGG fehlt")
            self.refs["label_sgg_status"].setStyleSheet("color: red; font-weight: bold;")


    def _init_connections(self):
        """Registriere Event-Filter und Button-/Action-Handler."""
        # Event-Filter für IP- und Port-Feld
        ip_filter = FocusEventFilter(self._save_field_on_focus_lost)
        port_filter = FocusEventFilter(self._save_field_on_focus_lost)
        self.refs["input_ip"].installEventFilter(ip_filter)
        self.refs["input_port"].installEventFilter(port_filter)
        # Filter-Referenzen speichern, sonst werden sie gelöscht
        self._focus_filters = [ip_filter, port_filter]

        # CARLA-Open-Button
        self.refs["open_folder_button"].clicked.connect(self._on_open_carla_folder)

        # file → pull SGG
        self.refs["action_pull_sgg"].triggered.connect(self._on_pull_sgg)

        #  Connect-Button im Connector-GroupBox
        self.refs["toolButton"].clicked.connect(self._on_connect)



    def _save_field_on_focus_lost(self, field):
        """Callback, wenn IP- oder Port-Feld den Fokus verliert: speichere neuen Wert."""
        if field == self.refs["input_ip"]:
            new_ip = field.text()
            self.data.set("host", new_ip)
            print(f"💾 Neue IP gespeichert: {new_ip}")
        elif field == self.refs["input_port"]:
            try:
                port = int(field.text())
                self.data.set("port", port)
                print(f"💾 Neuer Port gespeichert: {port}")
            except ValueError:
                print("⚠️ Ungültiger Portwert – nicht gespeichert.")


    def _on_connect(self):
        """
        Wird ausgelöst, wenn der Benutzer im Connector-Bereich auf „Connect“ klickt.
        Löst connector.connect() aus.
        """
        # UI Status sofort auf „Connecting…“
        self.refs["label_status"].setText("🔄 Connecting...")
        self.refs["label_status"].setStyleSheet("color: orange; font-weight: bold;")

        # Connector löst Hintergrund-Verbindung aus
        self.connector.connect()

    @pyqtSlot(bool, str)
    def _on_connector_result(self, success: bool, message: str):
        """
        Reagiert auf das Signal aus CarlaConnector.connection_result.
        Setzt Status-Label grün oder rot.
        """
        if success:
            self._connected = True
            self.refs["label_status"].setText("🟢 Connected")
            self.refs["label_status"].setStyleSheet("color: green; font-weight: bold;")
            # CARLA-Version im UI anzeigen
            version = self.data.get("carla_version")
            self.refs["label_version"].setText(version)
            # sobald verbunden, initial Camera-Label (falls der Connector das Signal noch nicht geschickt hat):
            cam = self.data.get("camera_selected", "free")
            self.refs["label_camera"].setText(cam)
            
            # Spawn-Button aktivieren, wenn schon ein Modell gewählt
            if self.data.get("model"):
                self.refs["spawn_button"].setEnabled(True)            
        else:
            self.refs["label_status"].setText("🔴 Disconnected")
            self.refs["label_status"].setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Verbindungsfehler", message)



    # CARLA BOX
    @staticmethod
    def process_exists(pid_str: str) -> bool:
        """Prüft, ob ein Prozess mit gegebener PID noch läuft."""
        try:
            pid = int(pid_str)
            p = psutil.Process(pid)
            return p.is_running()
        except (ValueError, psutil.NoSuchProcess):
            return False

    @pyqtSlot(str)
    def _on_model_selected(self, model_id: str):
        """Wenn der Connector meldet, dass ein Modell gewählt wurde."""
        # Label updaten (bereits in _update_vehicle_label) …
        # Spawn-Button nur aktiv, wenn wir verbunden sind
        if self._connected:
            self.refs["spawn_button"].setEnabled(True)

    @pyqtSlot()
    def _on_spawn_clicked(self):
        """Leite Klick an Connector weiter."""
        self.connector.spawn_vehicle()

    def _on_open_carla_folder(self):
        """Öffnet im Explorer den WindowsNoEditor-Ordner der ausgewählten Version."""
        version = self.refs["carla_version"].currentText()
        path = CARLA_DIR / version / "WindowsNoEditor"
        if path.exists():
            subprocess.Popen(["explorer", str(path)])
        else:
            QMessageBox.critical(self, "Fehler", f"Ordner nicht gefunden:\n{path}")



    def _on_pull_sgg(self):
        """Klont oder updated das SGG‐Repository und setzt den Status."""
        GIT_URL = "https://github.com/less-lab-uva/carla_scene_graphs.git"
        try:
            if not SGG_DIR.exists():
                print("📦 Klone SGG-Repository...")
                result = subprocess.run(
                    ["git", "clone", GIT_URL],
                    cwd=CARLA_DIR.parent,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr)
            else:
                print("🔄 Aktualisiere SGG-Repository (Pull)...")
                result = subprocess.run(
                    ["git", "pull"],
                    cwd=SGG_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr)

            print("✅ SGG erfolgreich geladen.")
            self.data.set("sgg_loaded", True)
            self.refs["label_sgg_status"].setText("🟢 SGG ready")
            self.refs["label_sgg_status"].setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            print("❌ Fehler beim Laden von SGG:", e)
            self.refs["label_sgg_status"].setText("🔴 Fehler beim Laden")
            self.refs["label_sgg_status"].setStyleSheet("color: red; font-weight: bold;")
            self.data.set("sgg_loaded", False)


    def _populate_vehicle_menu(self, blueprints: list):
        """Füllt das CARLA→Vehicle-Menü mit allen Blueprint-IDs."""
        menu = self.refs["menu_vehicle"]
        menu.clear()
        for bp_id in blueprints:
            action = QAction(bp_id, self)
            action.triggered.connect(lambda checked, bp=bp_id: self.connector.set_vehicle_model(bp))
            menu.addAction(action)

    @pyqtSlot(str)
    def _update_vehicle_label(self, model_id: str):
        """Setzt das Vehicle-Label in der Connector-GroupBox."""
        self.refs["label_vehicle"].setText(model_id)


    def _on_start_recording(self):
        """Startet eine neue Recording-Session."""
        # Buttons updaten
        self.refs["start_record_btn"].setEnabled(False)
        self.refs["stop_record_btn"].setEnabled(True)

        # eigentliche Record-Logik anstoßen
        self.connector.start_recording()
      

    def _on_stop_recording(self):
        """Beendet die Recording-Session."""
        # Buttons updaten
        self.refs["start_record_btn"].setEnabled(True)
        self.refs["stop_record_btn"].setEnabled(False)

        # Record-Logik beenden/Dateien schließen...
        self.connector.stop_recording()


























# ── Worker, der alle 0.1 s die aktuellen Werte sammelt und signalisiert ──
class InputWorker(QObject):
    update_signal = pyqtSignal(dict, str)
    """
    emit: (current_controls: dict, device_name: str)
    """

    def __init__(self, controller_manager):
        super().__init__()
        self.cm = controller_manager
        self._running = True

    @pyqtSlot()
    def run(self):
        while self._running:
            current = self.cm.get_current_control()
            js = self.cm.joystick
            device_name = js.get_name() if js else "–"
            self.update_signal.emit(current, device_name)
            time.sleep(0.1)

    def stop(self):
        self._running = False



# Event Filter, der beim Unselect eines QLineEdit greift
class FocusEventFilter(QObject):
    def __init__(self, on_focus_lost_callback):
        super().__init__()
        self.on_focus_lost_callback = on_focus_lost_callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FocusOut:
            self.on_focus_lost_callback(obj)
        return False  # Event weiterreichen