# control_panel.py

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QMessageBox,
    QVBoxLayout, QHBoxLayout, QMenuBar, QAction, QMenu, QStatusBar
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer
from pathlib import Path
from typing import List

from utils.paths import CARLA_DIR
from settings_manager import SettingsManager
from carla_connector import CarlaConnector
import subprocess


class ControlPanel(QMainWindow):
    def __init__(self, callbacks=None):
        super().__init__()
        self.setWindowTitle("🕹️ CARLA Steuerungsfenster")
        self.setGeometry(200, 200, 520, 320)

        self.callbacks = callbacks or {}
        self.settings = SettingsManager()
        self.connector = CarlaConnector()

        # === Zentraler Bereich ===
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)

        # === Menüleiste ===
        menu_bar = self.menuBar()
        self._build_menu_bar(menu_bar)

        # === Button-Reihen ===
        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()

        self.btn_reset = QPushButton("🔁 Fahrzeug zurücksetzen")
        self.btn_change_model = QPushButton("🚘 Modell wechseln")
        self.btn_toggle_sgg = QPushButton("🧠 SGG: An/Aus")
        self.btn_pause = QPushButton("⏸️ Pause/Weiter")
        self.btn_record = QPushButton("⏺️ Aufnahme: An/Aus")

        row1.addWidget(self.btn_reset)
        row1.addWidget(self.btn_change_model)
        row2.addWidget(self.btn_toggle_sgg)
        row2.addWidget(self.btn_pause)
        row3.addWidget(self.btn_record)

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)

        # === CARLA-STARTEN ===
        carla_menu = menu_bar.addMenu("server starten")

        start_action = QAction("Simulator starten", self)
        start_action.triggered.connect(self.start_carla_simulator)
        carla_menu.addAction(start_action)

        for version in self.list_carla_versions():
            action = QAction(version, self)
            action.triggered.connect(lambda _, v=version: self._call("select_carla_version", v))
            carla_menu.addAction(action)

        # === Statusleiste ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.carla_version_label = QLabel(f"Version: {self.settings.get('carla_version', '❓')}")
        self.connection_icon = QLabel()
        self.connection_text = QLabel("Verbindung: unbekannt")

        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.red)
        self.connection_icon.setPixmap(pixmap)

        self.status_bar.addPermanentWidget(self.connection_icon)
        self.status_bar.addPermanentWidget(self.connection_text)
        self.status_bar.addPermanentWidget(self.carla_version_label)

        # === Button-Verbindungen ===
        self.btn_reset.clicked.connect(lambda: self._call("reset"))
        self.btn_change_model.clicked.connect(self._print_all_models)
        self.btn_toggle_sgg.clicked.connect(lambda: self._call("toggle_sgg"))
        self.btn_pause.clicked.connect(lambda: self._call("toggle_pause"))
        self.btn_record.clicked.connect(lambda: self._call("toggle_record"))

        # === Verbindung regelmäßig prüfen ===
        self.connection_timer = QTimer(self)
        self.connection_timer.timeout.connect(self._update_connection_status)
        self.connection_timer.start(2000)

        # === Initiale Anzeige
        self._update_connection_status()

    def start_carla_simulator(self):
        version = self.settings.get("carla_version")
        exe_path = CARLA_DIR / version / "WindowsNoEditor" / "CarlaUE4.exe"

        if exe_path.exists():
            try:
                subprocess.Popen([str(exe_path)], cwd=exe_path.parent)
                self.set_status("🎮 CARLA wird gestartet...", "blue")
            except Exception as e:
                QMessageBox.critical(self, "Fehler beim Start", str(e))
        else:
            QMessageBox.warning(
                self,
                "Simulator nicht gefunden",
                f"Die Datei wurde nicht gefunden:\n{exe_path}"
            )

    def _build_menu_bar(self, menu_bar: QMenuBar):
        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(lambda: self._call("exit"))
        file_menu.addAction(exit_action)

        vehicle_menu = menu_bar.addMenu("Vehicle")
        model_menu = QMenu("Model", self)

        dummy_action = QAction("Modelle über Button abrufen", self)
        dummy_action.triggered.connect(self._print_all_models)
        model_menu.addAction(dummy_action)
        vehicle_menu.addMenu(model_menu)

        carla_menu = menu_bar.addMenu("CARLA")
        for version in self.list_carla_versions():
            action = QAction(version, self)
            action.triggered.connect(lambda _, v=version: self._call("select_carla_version", v))
            carla_menu.addAction(action)

        help_menu = menu_bar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(lambda: self._call("about"))
        help_menu.addAction(about_action)

    def _update_connection_status(self):
        connected = self.connector.is_connected()
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.green if connected else Qt.red)
        self.connection_icon.setPixmap(pixmap)

        self.connection_text.setText("Verbindung: Connected" if connected else "Verbindung: Disconnected")
        self.connection_text.setStyleSheet(f"font-weight: bold; color: {'green' if connected else 'red'}")

    def _print_all_models(self):
        if self.connector.is_connected():
            print("=== CARLA Modelle ===")
            for model in self.connector.get_available_vehicles():
                print(model)
            print("=== Ende ===")
            self._call("change_model")
        else:
            print("❌ Nicht verbunden mit CARLA")

    def _call(self, action, *args):
        if action == "select_carla_version" and args:
            version = args[0]
            self.settings.set("carla_version", version)
            self.carla_version_label.setText(f"Version: {version}")
        
        callback = self.callbacks.get(action)
        if callback:
            callback(*args)

    def list_carla_versions(self, root_folder: Path = CARLA_DIR) -> List[str]:
        if not root_folder.exists():
            print(f"❌ Pfad existiert nicht: {root_folder}")
            return []
        return [f.name for f in root_folder.iterdir() if f.is_dir()]