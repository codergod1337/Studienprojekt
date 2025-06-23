# hse/control_panel.py 

import sys
import time
import subprocess
import psutil
from pathlib import Path
import datetime
from typing import Dict, Any
import platform

from PyQt5.QtCore import QObject, QEvent, QTimer, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QComboBox, QMessageBox, QAction

from hse.ui_builder import build_ui
from hse.data_manager import DataManager
from hse.utils.settings import CARLA_DIR, SGG_DIR, DEFAULT_VALUES
from hse.controller_manager import ControllerManager
from hse.utils.joystick_visualizer import JoystickVisualizer
from hse.carla_connector import CarlaConnector
from hse.utils.settings import CAMERA_POSITIONS


class ControlPanel(QMainWindow):
    def __init__(self, controller_manager: ControllerManager, connector: CarlaConnector):
        super().__init__()
        # Initialize the data manager for storing configuration = state of application
        self.data = DataManager()
        # Keep a reference to the external controller manager                   
        self.cm = controller_manager  
        # Keep a reference to the external Carla connector               
        self.connector = connector                  
        
        # Inform the connector about which controller manager to use
        self.connector.set_controller_manager(self.cm) 
        # Create a separate window for visualizing joystick input
        self._control_win = JoystickVisualizer(self.cm)

        # Build the UI components and store references
        self.refs = build_ui(self)
        self._init_values_from_data()
        # Set up signal-slot connections for UI interactions              
        self._init_connections()
        

        # Disable the spawn button until a successful connection and model selection
        self.refs["spawn_button"].setEnabled(False)
        self._connected = False

        # Link recording buttons to their handlers
        self.refs["start_record_btn"].clicked.connect(self._on_start_recording)
        self.refs["stop_record_btn"].clicked.connect(self._on_stop_recording)
        recording = self.connector.get_recording_status()
        self.refs["start_record_btn"].setEnabled(not recording)
        self.refs["stop_record_btn"].setEnabled(recording)
        # listen so signal
        self.connector.recording_status.connect(self._on_recording_status_changed)

        # Initialize frame counter display and connect to connector's signal
        self.refs["label_framecount"].setText("0")
        self.connector.frame_recorded.connect(self._on_frame_recorded)

        # Connect the "controls" menu action to opening the joystick-visualizer-window
        self.refs["action_controls"].triggered.connect(self._open_control_manager)

        # Start a background thread that polls joystick input every 0.1 seconds
        self._input_thread = QThread(self)
        self._input_worker = InputWorker(self.cm)
        self._input_worker.moveToThread(self._input_thread)
        self._input_thread.started.connect(self._input_worker.run)
        self._input_worker.update_signal.connect(self._update_input_fields)
        self._input_thread.start()

        # Populate camera selection menu with data from settings
        self._populate_camera_menu()


        # Subscribe to connector events for connection results, blueprint loading etc...
        self.connector.connection_result.connect(self._on_connector_result)
        self.connector.blueprints_loaded.connect(self._populate_vehicle_menu)
        self.connector.vehicle_model_selected.connect(self._update_vehicle_label)
        self.connector.camera_position_selected.connect(self._update_camera_label)

        # Link the spawn button to the connector's spawn_vehicle method
        self.refs["spawn_button"].clicked.connect(self._on_spawn_clicked)

    @pyqtSlot(int)
    def _on_frame_recorded(self, count: int):
        """Update the label showing how many frames have been recorded"""
        self.refs["label_framecount"].setText(str(count))

    def _open_control_manager(self):
        """Bring the existing joystick window to front, or create and show it"""
        if hasattr(self, "_control_win") and self._control_win.isVisible():
            self._control_win.raise_()
            self._control_win.activateWindow()
        else:
            self._control_win = JoystickVisualizer(self.cm)
            self._control_win.show()

    def _populate_camera_menu(self):
        """Clear existing camera menu and add actions for each predefined camera position"""
        menu = self.refs["menu_camera"]
        menu.clear()
        for cam in CAMERA_POSITIONS.keys():
            act = QAction(cam, self)
            # When selected, instruct the connector to switch camera
            act.triggered.connect(lambda _, c=cam: self.connector.set_camera_position(c))
            menu.addAction(act)


    @pyqtSlot(str)
    def _update_camera_label(self, cam_id: str):
        """Reflect the selected camera position in the UI label"""
        self.refs["label_camera"].setText(cam_id)


    def closeEvent(self, event):
        """Stop the input polling worker and clean up the thread on window close."""
        print("close event, Control Panel says Goodbye!")
        self.connector.shutdown()
        self.cm.shutdown() 

        self._input_worker.stop()
        self._input_thread.quit()
        self._input_thread.wait()


        super().closeEvent(event)
       


    @pyqtSlot(dict, str)
    def _update_input_fields(self, current: Dict[str, Any], device_name: str):
        """
        Display the name of the current joystick device
        """
        # 1. Joystick‐Name
        self.refs["input_device"].setText(device_name)

        # Update each control value label with formatted text and color
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
        # Load saved host (IP) and port from DataManager and populate the text fields.
        self.refs["input_ip"].setText(self.data.get("host"))
        self.refs["input_port"].setText(str(self.data.get("port")))

        # Fill the CARLA version dropdown with all available versions.
        dropdown: QComboBox = self.refs["carla_version"]
        dropdown.clear()
        dropdown.addItems(self.data.carla_versions)

        # Pre-select the saved CARLA version if it exists in the list.
        saved_version = self.data.get("carla_version")
        if saved_version in self.data.carla_versions:
            index = dropdown.findText(saved_version)
            if index != -1:
                dropdown.setCurrentIndex(index)

        # Whenever the user picks a different version, save it back to DataManager.
        dropdown.currentTextChanged.connect(lambda v: self.data.set("carla_version", v))

        # Show whether the Scene Graph Generator (SGG) is loaded/ pulled or missing.
        loaded = self.data.get("sgg_loaded")
        if loaded:
            self.refs["label_sgg_status"].setText("🟢 SGG ready")
            self.refs["label_sgg_status"].setStyleSheet("color: green; font-weight: bold;")
        else:
            self.refs["label_sgg_status"].setText("🔴 SGG fehlt")
            self.refs["label_sgg_status"].setStyleSheet("color: red; font-weight: bold;")


    def _init_connections(self):
        # Install event filters on the IP and port QLineEdits to detect focus loss.
        ip_filter = FocusEventFilter(self._save_field_on_focus_lost)
        port_filter = FocusEventFilter(self._save_field_on_focus_lost)
        self.refs["input_ip"].installEventFilter(ip_filter)
        self.refs["input_port"].installEventFilter(port_filter)

        # Keep references to the filters so they aren’t garbage-collected.
        self._focus_filters = [ip_filter, port_filter]

        # Connect the "Open Folder" button to its handler.
        self.refs["open_folder_button"].clicked.connect(self._on_open_carla_folder)

        # Connect the "Pull SGG" action in the menu to its handler.
        self.refs["action_pull_sgg"].triggered.connect(self._on_pull_sgg)

        # Connect the "Connect" button in the connector group to its handler.
        self.refs["toolButton"].clicked.connect(self._on_connect)



    def _save_field_on_focus_lost(self, field):
        """
        Triggered when the IP or port field loses focus.
        If it's the IP field, save the new host string.
        """
        if field == self.refs["input_ip"]:
            new_ip = field.text()
            self.data.set("host", new_ip)
            print(f"💾 New host saved: {new_ip}")
        # If it's the port field, try converting to int and save; ignore invalid entries.    
        elif field == self.refs["input_port"]:
            try:
                port = int(field.text())
                self.data.set("port", port)
                print(f"💾 New port saved: {port}")
            except ValueError:
                print("⚠️ Invalid port value – not saved.")


    def _on_connect(self):
        """
        Called when the user clicks "Connect".
        Immediately update the status label to show “connecting…”.
        """
        self.refs["label_status"].setText("🔄 Connecting...")
        self.refs["label_status"].setStyleSheet("color: orange; font-weight: bold;")

        # Delegate the actual connection logic to the connector.
        self.connector.connect()

    @pyqtSlot(bool, str)
    def _on_connector_result(self, success: bool, message: str):
        """
        Slot that receives the outcome of connector.connect()
        """
        if success:
            # Mark as connected and update UI to green “Connected”.
            self._connected = True
            self.refs["label_status"].setText("🟢 Connected")
            self.refs["label_status"].setStyleSheet("color: green; font-weight: bold;")

            # Display the CARLA version in the UI.
            version = self.data.get("carla_version")
            self.refs["label_version"].setText(version)

            # Ensure the camera label is initialized (in case connector didn't emit it yet).
            cam = self.data.get("camera_selected", "free")
            self.refs["label_camera"].setText(cam)
            
            # Enable the spawn button if a vehicle model is already selected.
            if self.data.get("model"):
                self.refs["spawn_button"].setEnabled(True)            
        else:
            self.refs["label_status"].setText("🔴 Disconnected")
            self.refs["label_status"].setStyleSheet("color: red; font-weight: bold;")
            QMessageBox.critical(self, "Verbindungsfehler", message)



    @pyqtSlot(str)
    def _on_model_selected(self, model_id: str):
        """
        When the Connector notifies that a vehicle model was chosen,
        enable the spawn button if we are already connected.
        """
        if self._connected:
            self.refs["spawn_button"].setEnabled(True)


    @pyqtSlot()
    def _on_spawn_clicked(self):
        """Forward the spawn action to the connector when the user clicks Spawn."""
        self.connector.spawn_vehicle()


    def _on_open_carla_folder(self):
        """Open the WindowsNoEditor folder for the selected CARLA version."""
        version = self.refs["carla_version"].currentText()
        path = CARLA_DIR / version / "WindowsNoEditor"
        if path.exists():
            try:
                # Delegate the actual “open” operation to our helper method below
                print(path)
                self.open_folder(path)
            except Exception as e:
                QMessageBox.critical(self, "Error opening folder", str(e))
        else:
            QMessageBox.critical(self, "Fehler", f"Ordner nicht gefunden:\n{path}")

    def open_folder(self, path: Path):
        """
        Open a folder in the native file browser, depending on the current platform.
        Supports Windows, macOS (Darwin) and Linux.
        """
        system = platform.system()
        print(system)
        if system == "Windows":
            # On Windows use Explorer
            subprocess.Popen(["explorer", str(path)])
        elif system == "Darwin":
            # On macOS use open
            subprocess.Popen(["open", str(path)])
        else:
            # Fallback for most Linux distributions
            subprocess.Popen(["xdg-open", str(path)])


    def _on_pull_sgg(self):
        """Clone or update the Carla Scene Graph repository."""
        GIT_URL = "https://github.com/less-lab-uva/carla_scene_graphs.git"
        try:
            if not SGG_DIR.exists():
                print("📦 Cloning SGG repository...")
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
                print("🔄 Pulling latest SGG changes...")
                result = subprocess.run(
                    ["git", "pull"],
                    cwd=SGG_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr)
            
            # Upon success, mark SGG as loaded and update the status label.
            print("✅ SGG loaded successfully.")
            self.data.set("sgg_loaded", True)
            self.refs["label_sgg_status"].setText("🟢 SGG ready")
            self.refs["label_sgg_status"].setStyleSheet("color: green; font-weight: bold;")
        except Exception as e:
            print("❌ Error loading SGG:", e)
            self.refs["label_sgg_status"].setText("🔴 Load error")
            self.refs["label_sgg_status"].setStyleSheet("color: red; font-weight: bold;")
            self.data.set("sgg_loaded", False)


    def _populate_vehicle_menu(self, blueprints: list):
        """Fill the "Vehicle" submenu with QAction items for each blueprint ID."""
        menu = self.refs["menu_vehicle"]
        menu.clear()
        for bp_id in blueprints:
            action = QAction(bp_id, self)
            # When selected, instruct the connector to use this vehicle model.
            action.triggered.connect(lambda checked, bp=bp_id: self.connector.set_vehicle_model(bp))
            menu.addAction(action)


    @pyqtSlot(str)
    def _update_vehicle_label(self, model_id: str):
        """Update the label showing which vehicle model is currently selected."""
        self.refs["label_vehicle"].setText(model_id)


    def _on_start_recording(self):
        """Disable the "Start" button, enable the "Stop" button, and start recording via the connector."""
        # Buttons update
        self.refs["start_record_btn"].setEnabled(False)
        self.refs["stop_record_btn"].setEnabled(True)

        # Record-Logic start
        self.connector.start_recording()
      

    def _on_stop_recording(self):
        """Re-enable the "Start" button, disable the "Stop" button, and stop recording via the connector."""
        # Buttons updaten
        self.refs["start_record_btn"].setEnabled(True)
        self.refs["stop_record_btn"].setEnabled(False)

        # Record-Logik terminate...
        self.connector.stop_recording()

    @pyqtSlot(bool)
    def _on_recording_status_changed(self, active: bool):
        """UI-Update"""
        self.refs["start_record_btn"].setEnabled(not active)
        self.refs["stop_record_btn"].setEnabled(active)











# Worker that polls the controller every 0.1s and emits a signal
class InputWorker(QObject):
    update_signal = pyqtSignal(dict, str)
    """
    # Emits a tuple: (current_controls: dict, device_name: str)
    """

    def __init__(self, controller_manager):
        super().__init__()
        self.cm = controller_manager
        self._running = True


    @pyqtSlot()
    def run(self):
        # Main loop: while running, fetch mapped controls and emit them
        while self._running:
            current = self.cm.get_mapped_controls()
            js = self.cm.current_joystick
            device_name = js.get_name() if js else "–"
            # Emit the current control states and joystick name to the UI.
            self.update_signal.emit(current, device_name)
            time.sleep(0.1)


    def stop(self):
        # Signal the loop to exit cleanly.
        self._running = False



# Event filter to detect when a QLineEdit loses focus.
class FocusEventFilter(QObject):
    def __init__(self, on_focus_lost_callback):
        super().__init__()
        # Store the callback to invoke on focus loss.
        self.on_focus_lost_callback = on_focus_lost_callback


    def eventFilter(self, obj, event):
        # If the event is a focus-out, call the provided callback.
        if event.type() == QEvent.FocusOut:
            self.on_focus_lost_callback(obj)
        # Return False to allow normal event propagation.
        return False  