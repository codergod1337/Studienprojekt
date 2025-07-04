# hse/docs/carla_connector_README.md

# CarlaConnector

The `CarlaConnector` encapsulates all communication with the CARLA simulator in a dedicated background thread. It handles synchronous control, vehicle spawning, scene graph recording, and integrates the Scene Graph Generator (SGG).

---

## 1. Initialization (Light)

When instantiated (`__init__`), the connector does not yet know which CARLA version to use. Therefore, it performs a light initialization:

* Sets up internal data structures (queues, flags, locks).
* Starts the main daemon thread (`self._thread`) where the full workflow will later run.
* **Does not** import the CARLA Python API, since the path to the `.egg` file is only known after version selection.

## 2. Deferred Import & Connect

The actual CARLA import and connection happen in `connect()` and the subsequent `_initialize_connection()`:

1. **Read version** from `DataManager` → determine paths to the CARLA `.egg` and `PythonAPI/carla`.
2. **Modify** `sys.path` to include the `.egg` and source directory.
3. **Import** `carla` via `importlib`, making the CARLA client and world available.
4. **Configure** synchronous mode and Traffic Manager settings.
5. **Emit** `connection_result(success: bool, message: str)` to report status.

This deferred import strategy allows you to keep multiple CARLA versions in the project and select one at runtime.

## 3. Thread Workflow

### 3.1 Main Daemon Thread (`_run`)

The connector spawns a daemon thread that is divided into two phases:

1. **Initialization Phase** (`_wait_for_connect()`)

   * Blocks until `connect()` is called.
   * then: `_initialize_connection()`
   
2. **Core Simulation Loop** (`_simulation_loop()`)

   * Runs as long as `_running` is `True`.
   * Repeats each tick:

     * **tick()**: Advance the world by calling `world.tick()` in synchronous mode.
     * **spawn**: Process any pending spawn commands via `_process_spawn()`.
     * **control**: Apply joystick inputs to the vehicle via `_process_control()`.
     * **camera**: Update the spectator camera position via `_apply_camera()`.
     * **sgg**: When the SGG interval elapses, enqueue frame data to the recording pool.

### 3.2 Scene-Graph Recording

When it’s time to record a frame, the connector:

* Packs a tuple `(frame, ego_id, controls, folder)` into `self._record_queue`.
* A `ThreadPoolExecutor` (with worker threads) pulls these tuples asynchronously.
* In `_record_worker()`, the SGG module:

  1. Generates the scene graph: `self._sgg.generate_graph_for_frame(...)`.
  2. Saves it: `self._sgg.save(sg, folder)`.
  3. Emits `self.frame_recorded.emit(self._sgg.timestep)`.

This design keeps the main loop responsive by offloading expensive graph processing to the thread pool.

## 4. Key API Methods

| Method                    | Description                                                      |
| ------------------------- | ---------------------------------------------------------------- |
| `connect()`               | Initiates the connection process (deferred CARLA import).        |
| `spawn_vehicle()`         | Enqueues a spawn command to run on the next simulation tick.     |
| `set_vehicle_model(id)`   | Saves the blueprint ID and emits `vehicle_model_selected`.       |
| `set_camera_position(id)` | Updates camera view and emits `camera_position_selected`.        |
| `start_recording()`       | Initializes SGG and starts asynchronous scene-graph recording.   |
| `stop_recording()`        | Stops recording and releases resources.                          |
| `get_recording_status()`  | Returns a boolean indicating if recording is active.             |
| `shutdown()`              | Disconnects from CARLA, stops threads, and shuts down executors. |

## 5. Qt Signals

| Signal                     | Parameters    | Description                                   |
| -------------------------- | ------------- | --------------------------------------------- |
| `connection_result`        | `(bool, str)` | Emitted after attempting to connect.          |
| `blueprints_loaded`        | `list[str]`   | Emitted with available vehicle blueprint IDs. |
| `vehicle_model_selected`   | `str`         | Emitted when a blueprint is selected.         |
| `camera_position_selected` | `str`         | Emitted after changing the camera position.   |
| `frame_recorded`           | `int`         | Emitted each time a frame is recorded.        |
| `recording_status`         | `bool`        | Emitted when recording starts or stops.       |

## 6. Internals & Threading

* **Daemon Thread**: `self._thread` runs the `_run()` method for initialization and the core loop.
* **Command Queue**: `self._command_queue` buffers spawn requests.
* **Record Queue**: `self._record_queue` buffers frames for SGG processing.
* **Executor**: `ThreadPoolExecutor` handles the `_record_worker()` tasks in parallel.
* **Lock**: `self._lock` protects shared resources (`self._client`, `self._world`).


---

**See Also:**

* [Main README](../../README.md): `../../README.md`

