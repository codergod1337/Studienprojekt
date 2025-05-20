#test_run_control_panel.py

import sys
from pathlib import Path
from PyQt5.QtWidgets import QApplication
from control_panel import ControlPanel

# Projekt-Root zum Suchpfad hinzufügen
sys.path.append(str(Path(__file__).resolve().parent.parent))

# === Dummy-Funktionen für Callback-Test ===
def dummy_callback(name):
    def callback(*args):
        print(f"🔧 Aktion: {name}, args: {args}")
    return callback

callbacks = {
    "reset": dummy_callback("reset"),
    "change_model": dummy_callback("change_model"),
    "toggle_sgg": dummy_callback("toggle_sgg"),
    "toggle_pause": dummy_callback("toggle_pause"),
    "toggle_record": dummy_callback("toggle_record"),
    "select_model": dummy_callback("select_model"),
    "select_carla_version": dummy_callback("select_carla_version"),
    "about": dummy_callback("about"),
    "exit": sys.exit,
}

# === Panel starten ===
app = QApplication(sys.argv)
panel = ControlPanel(callbacks=callbacks)
panel.show()
sys.exit(app.exec_())