# hse/docs/controller_manager_README.md

# ControllerManager

The `ControllerManager` handles joystick discovery, raw input polling, and mapping user-defined controls (throttle, brake, steering, etc.) to application-level commands. It runs a background thread to continuously update axis and button states via `pygame`.

---

## 1. Initialization

When instantiated (`__init__`), the manager:

* Initializes `pygame` and joystick subsystems.
* Detects connected joysticks and registers them, saving metadata (axis IDs, button IDs) into `known_devices` in `DataManager`.
* Restores the previously active controller (if available) from state; otherwise defaults to the first detected joystick.
* Sets up raw state dictionaries:

  * `raw_axes`: maps axis index → `float` (\[-1.0, +1.0]) or `None` until first read.
  * `raw_buttons`: maps button index → `int` (0 or 1).
* Loads existing control-to-input mappings (`controls_cfg`) from `DataManager`.
* Starts a daemon thread (`_thread`) running `_scan_loop()` at \~30 Hz.

## 2. Background Polling Loop (`_scan_loop`)

The scan loop executes continuously while `_running` is `True`:

1. `pygame.event.pump()` to process internal events.
2. Acquires a lock (`self._lock`) to safely:

   * Read each axis value via `get_axis()` into `raw_axes`.
   * Read each button state via `get_button()` into `raw_buttons`.
3. Sleeps \~0.033 s to throttle polling frequency (\~30 Hz).

This loop ensures up-to-date raw input data for downstream mapping.

## 3. Value Processing & Mapping

### 3.1 get\_all\_states()

Returns processed states as a dict:

```json
{
  "axes":   { index: float or None },
  "buttons":{ index: int }
}
```

* Applies per-device metadata (inversion and style) from `known_devices`:

  * **Inversion**: Negates raw value if `inverted=True`.
  * **Style**: Converts to unipolar (`(val+1)/2`) or bipolar (`[-1..1]`).

### 3.2 get\_mapped\_controls()

Returns a dict mapping each control function to its current value:

```json
{ "throttle": 0.75, "brake": 0.0, "respawn": 1.0, … }
```

* For each function defined in `controls_cfg`, retrieves the mapped axis or button value (or `None` if unmapped).

## 4. API Methods

| Method                         | Description                                                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `get_all_states()`             | Returns raw and processed axis/button states.                                                                |
| `get_mapped_controls()`        | Returns application-level control values based on current mappings.                                          |
| `set_mapping(func, type, idx)` | Assigns a control function (`func`) to an input (`type`: "axis"/"button", `idx`). Persists to `DataManager`. |
| `set_device(index)`            | Switches active joystick to the one at `index`. Resets raw state dicts.                                      |
| `shutdown()`                   | Stops the polling thread and quits `pygame`.                                                                 |

## 5. Configuration & Persistence

* **DataManager Keys:**

  * `known_devices`: Metadata for each joystick (axes list, buttons list).
  * `controls`: Control-to-input mappings (`func` → `{type, id}`).
  * `active_controller`: Name of the last used joystick.

All settings are saved in `state.json` via `DataManager.set()`.

## 6. Threading & Concurrency

* **Lock (`self._lock`)** protects `raw_axes` and `raw_buttons` during updates and reads.
* **Daemon Thread** ensures polling stops when the application exits.

## 7. Debug Usage

For debugging purposes, you can run the `ControllerManager` module directly. This will start the polling loop in the console and print all joystick axis and button values in real time:

```bash
python -m hse.controller_manager
```

Example output:

```
Active joystick: Xbox Wireless Controller

Axes:
  Axis 0: 0.000
  Axis 1: -0.125
  Axis 2: 1.000
  ...

Buttons:
  Button 0: Released
  Button 1: Pressed
  ...
```

Press `Ctrl+C` to exit and cleanly shut down the polling thread.

---

**See Also:**

* [Main README](../../README.md)
* [CarlaConnector module](carla_connector_README.md)

