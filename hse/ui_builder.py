# hse/ui_builder.py 

from PyQt5.QtWidgets import (
    QWidget, QPushButton, QLabel, QLineEdit, QCheckBox, QComboBox, QFrame, QSizePolicy,
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
    layout_connector.addRow("IP-Address:", input_ip)
    layout_connector.addRow("Port:", input_port)

    toolButton = QToolButton(group_connector)
    toolButton.setText("Connect")
    layout_connector.addRow("", toolButton)


    # Vehicle-Label
    label_vehicle = QLabel("—", group_connector)
    label_vehicle.setEnabled(False)
    layout_connector.addRow("Vehicle:", label_vehicle)

    # CARLA-Version-Label
    label_version = QLabel("—", group_connector)
    label_version.setEnabled(False)
    layout_connector.addRow("CARLA Version:", label_version)

    # Camera-Position-Label
    label_camera = QLabel("—", group_connector)
    label_camera.setEnabled(False)
    layout_connector.addRow("Camera Position:", label_camera)

    # Spawn Vehicle Button (initial disabled)
    spawn_button = QPushButton("Spawn Vehicle", group_connector)
    spawn_button.setEnabled(False)
    layout_connector.addRow("", spawn_button)

    # Widget-Refs für ControlPanel
    refs["input_ip"]      = input_ip
    refs["input_port"]    = input_port
    refs["toolButton"]    = toolButton
    refs["label_status"]  = label_status
    refs["label_vehicle"] = label_vehicle
    refs["label_version"] = label_version
    refs["label_camera"]  = label_camera
    refs["spawn_button"]  = spawn_button


    # === SGG GroupBox mit Layout ===
    group_sgg = QGroupBox("Scene Graph Generator", central_widget)
    group_sgg.setGeometry(350, 50, 300, 150)
    layout_sgg = QFormLayout(group_sgg)

    label_sgg_status = QLabel("nicht geladen", group_sgg)
    label_sgg_status.setStyleSheet("color: red; font-weight: bold;")
    layout_sgg.addRow("Status:", label_sgg_status)
    
#    checkbox_graph1 = QCheckBox("Graph 1", group_sgg)
#    checkbox_graph2 = QCheckBox("Graph 2", group_sgg)
#    layout_sgg.addRow(checkbox_graph1)
#    layout_sgg.addRow(checkbox_graph2)

    # ── Trennlinie ──
    line = QFrame(group_sgg)
    line.setFrameShape(QFrame.HLine)
    layout_sgg.addRow(line)

    # ── Frame-Counter ──
    label_frame_caption = QLabel("Frames recorded:", group_sgg)
    label_framecount = QLabel("0", group_sgg)
    label_framecount.setStyleSheet("font-weight: bold;")
    layout_sgg.addRow(label_frame_caption, label_framecount)

    # ── Recording-Buttons ──
    start_btn = QPushButton("Start Recording", group_sgg)
    stop_btn  = QPushButton("Stop Recording",  group_sgg)
    stop_btn.setEnabled(False)
    # ── Einheitliche Button Größe ──
    #for btn in (start_btn, stop_btn):
    #    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
     #   btn.setFixedHeight(30)            # Höhe so wie andere Buttons

    # ── Gleiche Breite: zwei Spalten, beide expandieren ──
    layout_sgg.addRow(start_btn, stop_btn)

    refs["label_sgg_status"] = label_sgg_status
#    refs["checkbox_graph1"] = checkbox_graph1
#    refs["checkbox_graph2"] = checkbox_graph2
    refs["label_framecount"] = label_framecount
    refs["start_record_btn"]    = start_btn
    refs["stop_record_btn"]     = stop_btn


    # === CARLA GroupBox ===
    group_carla = QGroupBox("CARLA", central_widget)
    group_carla.setGeometry(20, 290, 300, 120)
    layout_carla = QFormLayout(group_carla)

    dropdown_carla_version = QComboBox(group_carla)
    layout_carla.addRow("Version:", dropdown_carla_version)

    open_folder_button = QPushButton("Open CARLA Folder", group_carla)
    layout_carla.addRow("", open_folder_button)

    refs["carla_version"]      = dropdown_carla_version
    refs["open_folder_button"] = open_folder_button


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





    # === Menu ===
    menubar = QMenuBar(window)
    window.setMenuBar(menubar)

    menu_file = QMenu("file", window)
    menu_carla = QMenu("CARLA", window)
    menu_controls = QMenu("controls", window)

    action_pull_sgg = QAction("pull SGG", window)
    action_exit = QAction("exit", window)
        #action_vehicle = QAction("vehicle", window)
    action_controls = QAction("controls", window)

    # Untermenü, später mit allen Blueprints befüllt
    menu_vehicle = QMenu("Vehicle", window)
    menu_carla.addMenu(menu_vehicle)
    # ── Camera‐Submenü ──
    menu_camera = QMenu("Camera", window)
    menu_carla.addMenu(menu_camera)

    menu_file.addAction(action_pull_sgg)
    menu_file.addSeparator()
    menu_file.addAction(action_exit)

        #menu_carla.addAction(action_vehicle)

    menu_controls.addAction(action_controls)

    menubar.addMenu(menu_file)
    menubar.addMenu(menu_carla)
    menubar.addMenu(menu_controls)


    # === Menüaktionen ===
    refs["action_pull_sgg"] = action_pull_sgg
    #refs["action_exit"] = action_exit
    #refs["action_vehicle"] = action_vehicle
    refs["action_controls"] = action_controls
    refs["menu_vehicle"] = menu_vehicle
    refs["menu_camera"] = menu_camera

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