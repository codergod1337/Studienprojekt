# hse/examples/run.py 

import sys
from pathlib import Path

# Projekt-Stammverzeichnis hinzufügen
root_path = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_path))

from PyQt5.QtWidgets import QApplication

from hse.control_panel import ControlPanel
from hse.data_manager import DataManager
from hse.controller_manager import ControllerManager
from hse.utils.joystick_visualizer import JoystickVisualizer
from hse.carla_connector import CarlaConnector


def main():
    app = QApplication(sys.argv)

    dm = DataManager()
    cm = ControllerManager(dm)
    connector = CarlaConnector(dm)

    window = ControlPanel(cm, connector)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()