# hse/ui_builder.py 

from PyQt5.QtWidgets import (
    QWidget, QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox,
    QGroupBox, QVBoxLayout, QHBoxLayout, QToolButton, QMenuBar, QMenu, QAction, QStatusBar, QFormLayout
)
from PyQt5.QtCore import Qt

from hse.utils.settings import DEFAULT_VALUES  # <-- Importiere die Default-Controls


def build_ui(window):
    window.setWindowTitle("CARLA Control Panel")
    window.setGeometry(100, 100, 951, 678)
    refs = {}

    # === Zentral-Widget ===
    central_widget = QWidget(window)
    window.setCentralWidget(central_widget)

    # === Connector GroupBox mit FormLayout ===
    group_connector = QGroupBox("Connector", central_widget)
    group_connector.setGeometry(20, 50, 300, 220)
    layout_connector = QFormLayout(group_connector)

    label_status = QLabel("Disconnected", group_connector)
    label_status.setStyleSheet("color: red; font-weight: bold;")
    layout_connector.addRow("Status:", label_status)

    input_ip = QLineEdit("localhost", group_connector)
    input_port = QLineEdit("2000", group_connector)
    layout_connector.addRow("IP-Adresse:", input_ip)
    layout_connector.addRow("Port:", input_port)

    toolButton = QToolButton(group_connector)
    toolButton.setText("Connect")
    layout_connector.addRow("", toolButton)

    label_vehicle = QLabel("—", group_connector)
    label_vehicle.setEnabled(False)
    layout_connector.addRow("Vehicle:", label_vehicle)

    label_version = QLabel("—", group_connector)
    label_version.setEnabled(False)
    layout_connector.addRow("CARLA Version:", label_version)

    refs["input_ip"] = input_ip
    refs["input_port"] = input_port
    refs["toolButton"] = toolButton
    refs["label_status"] = label_status
    refs["label_vehicle"] = label_vehicle
    refs["label_version"] = label_version

    # === SGG GroupBox mit Layout ===
    group_sgg = QGroupBox("Scene Graph Generator", central_widget)
    group_sgg.setGeometry(350, 50, 300, 120)
    layout_sgg = QFormLayout(group_sgg)

    label_sgg_status = QLabel("nicht geladen", group_sgg)
    label_sgg_status.setStyleSheet("color: red; font-weight: bold;")
    layout_sgg.addRow("Status:", label_sgg_status)
    
    checkbox_graph1 = QCheckBox("Graph 1", group_sgg)
    checkbox_graph2 = QCheckBox("Graph 2", group_sgg)
    layout_sgg.addRow(checkbox_graph1)
    layout_sgg.addRow(checkbox_graph2)

    refs["label_sgg_status"] = label_sgg_status
    refs["checkbox_graph1"] = checkbox_graph1
    refs["checkbox_graph2"] = checkbox_graph2

    # === CARLA GroupBox ===
    group_carla = QGroupBox("CARLA", central_widget)
    group_carla.setGeometry(20, 290, 300, 150)
    layout_carla = QFormLayout(group_carla)

    label_carla_status = QLabel("Stopped", group_carla)
    label_carla_status.setStyleSheet("color: red; font-weight: bold;")
    layout_carla.addRow("Status:", label_carla_status)

    carla_process_id = QLabel("None", group_carla)
    layout_carla.addRow("Prozess-ID:", carla_process_id)

    dropdown_carla_version = QComboBox(group_carla)
    layout_carla.addRow("Version:", dropdown_carla_version)

    start_carla_button = QPushButton("Start CARLA", group_carla)
    layout_carla.addRow("", start_carla_button)

    refs["carla_process_id"] = carla_process_id
    refs["carla_version"] = dropdown_carla_version
    refs["start_carla_button"] = start_carla_button
    refs["label_carla_status"] = label_carla_status


    # === Input ===
    group_input = QGroupBox("Input", central_widget)
    group_input.setGeometry(350, 180, 300, 240)
    layout_input = QFormLayout(group_input)

    # Connected Device:
    label_device_desc = QLabel("Connected Device:", group_input)
    label_device_name = QLabel("–", group_input)
    layout_input.addRow(label_device_desc, label_device_name)
    refs["input_device"] = label_device_name

    # Dynamisch alle Control-Features aus DEFAULT_VALUES["controls"]
    for func in DEFAULT_VALUES["controls"].keys():
        lbl_desc = QLabel(f"{func}:", group_input)
        lbl_value = QLabel("0.00", group_input)
        # Farbe direkt aus DEFAULT_VALUES ziehen
        color = DEFAULT_VALUES["controls"].get(func, {}).get("color", "#000")
        lbl_value.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout_input.addRow(lbl_desc, lbl_value)
        refs[f"input_{func}"] = lbl_value

    refs["group_input"] = group_input





    # === Menü ===
    menubar = QMenuBar(window)
    window.setMenuBar(menubar)

    menu_file = QMenu("file", window)
    menu_carla = QMenu("CARLA", window)
    menu_controls = QMenu("controls", window)

    action_pull_sgg = QAction("pull SGG", window)
    action_exit = QAction("exit", window)
    action_vehicle = QAction("vehicle", window)
    action_controls = QAction("controls", window)

    menu_file.addAction(action_pull_sgg)
    menu_file.addSeparator()
    menu_file.addAction(action_exit)

    menu_carla.addAction(action_vehicle)

    menu_controls.addAction(action_controls)

    menubar.addMenu(menu_file)
    menubar.addMenu(menu_carla)
    menubar.addMenu(menu_controls)


    # === Menüaktionen ===
    refs["action_pull_sgg"] = action_pull_sgg
    #refs["action_exit"] = action_exit
    #refs["action_vehicle"] = action_vehicle
    refs["action_controls"] = action_controls

    # === Statusbar ===
    statusbar = QStatusBar(window)
    window.setStatusBar(statusbar)
    label_conn_status = QLabel("Disconnected")
    label_conn_status.setStyleSheet("color: red;")
    label_output1 = QLabel("—")
    label_output2 = QLabel("—")
    statusbar.addWidget(label_conn_status)
    statusbar.addWidget(label_output1)
    statusbar.addWidget(label_output2)

    return refs