# hse/docs/control_panel_README.md

# ControlPanel

The `ControlPanel` is the main PyQt5-based GUI for interacting with the CARLA simulator and other modules. It ties together the `DataManager`, `ControllerManager`, and `CarlaConnector` to provide controls for connecting, spawning vehicles, adjusting camera views, and managing recordings. This Class is responsible for the correct shutdown process so all background threads from all classes can be terminated.

---

## 1. Setup & Initialization

Upon instantiation (`__init__`), the `ControlPanel`:

1. **Creates** a `DataManager` instance to persist the App-State.
2. **Receives** external `ControllerManager` and `CarlaConnector` references.
3. **Builds** the UI via `build_ui(self)` and stores widget references in `self.refs`.
4. **Initializes** field values from `DataManager` (`host`, `port`, `carla_version`, `sgg_loaded`).
5. **Connects** PyQt signals/slots for UI controls.
6. **Starts** an input polling thread (`InputWorker`) to update joystick values in the UI.
7. **Populates** camera menu based on `CAMERA_POSITIONS`.
8. **Subscribes** to connector events for connection results, blueprint loading, etc.

Optional: The **JoystickVisualizer** window is instantiated but hidden until invoked via the **Controls** menu.

## 2. UI Components

The ControlPanel UI consists of several grouped sections:

* **Connector**: Host/Port input, **Connect** button, status indicator, and vehicle/camera labels.
* **Scene Graph Generator**: SGG status, frame counter, **Start Recording**/**Stop Recording** buttons.
* **CARLA**: Dropdown for CARLA version selection and **Open CARLA Folder** button.
* **Input**: Live display of joystick name, axis values, and button states.
* **Menu Bar**: Actions for pulling SGG repo, spawning vehicles, switching cameras, and opening the Joystick Visualizer.

## 3. Key Slots & Handlers

| Slot/Handler                        | Trigger                                       | Action                                                                |
| ----------------------------------- | --------------------------------------------- | --------------------------------------------------------------------- |
| `_on_connect()`                     | **Connect** button clicked                    | Updates status label to “Connecting...”, calls `connector.connect()`. |
| `_on_connector_result(success,msg)` | Emitted by `CarlaConnector.connection_result` | Updates status label (🟢/🔴), displays error dialog on failure.       |
| `_populate_vehicle_menu(bps)`       | `blueprints_loaded` signal                    | Fills **Vehicle** menu with blueprint IDs.                            |
| `_on_spawn_clicked()`               | **Spawn Vehicle** button clicked              | Calls `connector.spawn_vehicle()`.                                    |
| `_on_start_recording()`             | **Start Recording** clicked                   | Disables start, enables stop, calls `connector.start_recording()`.    |
| `_on_stop_recording()`              | **Stop Recording** clicked                    | Enables start, disables stop, calls `connector.stop_recording()`.     |
| `_update_input_fields(current,dev)` | Emitted by `InputWorker.update_signal`        | Updates axis/button labels with live values.                          |

## 4. Input Polling Thread

`InputWorker` is a `QObject` running in its own `QThread`:

* Polls `ControllerManager.get_mapped_controls()` every 0.1s.
* Emits `update_signal(current_controls: dict, device_name: str)` to update the main UI.
* Stops cleanly on window close (`closeEvent`).

## 5. Camera Menu

Built from `CAMERA_POSITIONS` in `settings.py`. Selecting a camera action calls `connector.set_camera_position(cam_id)` and updates the UI label via `camera_position_selected` signal.

## 6. Data Persistence

`ControlPanel` uses `DataManager` to store and retrieve:

* `host`, `port`, `carla_version`, `model`, `camera_selected`
* `sgg_loaded` state to update the SGG status indicator

Changes to IP, port, and version dropdown selections are persisted on focus loss or selection.

## 7. Shutdown Sequence

On close (`closeEvent`):

1. Calls `connector.shutdown()` and `controller_manager.shutdown()`.
2. Stops `InputWorker` and quits its thread.
3. Calls `super().closeEvent(event)` to complete.

---

**See Also:**

* [Main README](../../README.md)

