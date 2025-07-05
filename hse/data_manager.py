# hse/data_manager.py
import sys
import json
from pathlib import Path
# Add project root to PYTHONPATH so that the 'hse' package can be imported when running this module directly
root_path = Path(__file__).resolve().parent.parent
sys.path.append(str(root_path))

import datetime
from typing import Any, Dict
from hse.utils.settings import CONFIG_PATH, DEFAULT_VALUES, CARLA_DIR, DATA_DIR, MAP_DIR


class DataManager:
    """
    The DataManager handles loading, saving, and validating configuration state.
    It loads from a JSON file `state.json` and merges missing or invalid entries
    with predefined default values. It also scans available CARLA versions
    in the project directory.
    """

    def __init__(self):
        self.state = {}
        self.carla_versions: list[str] = []
        self._validate_and_load()
        self._scan_carla_versions()             


    def _validate_and_load(self) -> None:
        """
        Load JSON config from CONFIG_PATH, merge with DEFAULT_VALUES,
        correct invalid entries, and save back if changes were made.
        """

        # Ensure the state file exists
        if not CONFIG_PATH.exists():
            print("🆕 state.json not found – creating a new one.")
            self._save_json(CONFIG_PATH, {})

        # Load existing state
        self.state = self._load_json(CONFIG_PATH)
        changed = False

        # Iterate through each key/default pair in DEFAULT_VALUES
        for key, default_value in DEFAULT_VALUES.items():
            if key not in self.state:
                # --- Key Missing: Apply Default ---
                # For missing configuration settings, assign the predefined default
                print(f"➕ Setting default for '{key}': {default_value}")
                if key == "controls":
                    # Deep copy each control mapping to avoid mutating global DEFAULT_VALUES
                    self.state[key] = {
                        func: vals.copy()
                        for func, vals in default_value.items()
                    }
                else:
                    # Direct assignment for scalar defaults (host, port, timeout, etc.)
                    self.state[key] = default_value
                changed = True
            else:
                # --- Key Present: Perform Validation ---
                if key == "controls":
                    # Validate 'controls' mapping structure
                    controls = self.state["controls"]
                    for func, vals in default_value.items():
                        # Ensure each expected control exists
                        if func not in controls:
                            print(f"Adding missing control '{func}': {vals}")
                            controls[func] = vals.copy()
                            changed = True
                    if changed:
                        # Update state if any controls were added
                        self.state["controls"] = controls
                elif key == "port":
                    # Validate TCP port: must be int in range 1–65535
                    port_val = self.state[key]
                    if not isinstance(port_val, int) or not (0 < port_val < 65536):
                        print(f"Invalid port '{port_val}' – resetting to default {default_value}")
                        self.state[key] = default_value
                        changed = True
                elif key == "timeout":
                    # Validate timeout: must be positive int or float
                    timeout_val = self.state[key]
                    if not isinstance(timeout_val, (int, float)) or timeout_val <= 0:
                        print(f"Invalid timeout '{timeout_val}' – resetting to default {default_value}")
                        self.state[key] = default_value
                        changed = True
                # Note: other keys (host, carla_version, model, etc.) rely on DEFAULT_VALUES types

        # If any defaults were applied or corrections made, persist the new state
        if changed:
            self._save_json(CONFIG_PATH, self.state)
            print("💾 state.json updated with default values and corrections.")


    def _load_json(self, path: Path) -> Dict[str, Any]:
        """
        Helper to load JSON data from a file. Returns an empty dict on error.
        Args:
            path (Path): File path to load.
        Returns:
            dict: Parsed JSON or empty dict.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path.name}: {e}")
            return {}


    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        """
        Helper to save a dict to JSON, creating parent dirs as needed.
        Args:
            path (Path): File path to write.
            data (dict): The data to serialize.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving {path.name}: {e}")


    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from the state dict, returning default if absent.
        Args:
            key (str): The configuration key.
            default (Any): Fallback value.
        Returns:
            Any: Stored value or default.
        """
        return self.state.get(key, default)


    def set(self, key: str, value: Any) -> None:
        """
        Assign a new value in state and immediately persist to disk.
        Args:
            key (str): Configuration key.
            value (Any): Value to store.
        """
        self.state[key] = value
        self._save_json(CONFIG_PATH, self.state)


    def _scan_carla_versions(self) -> None:
        """
        Scan CARLA_DIR for subfolders starting with 'CARLA_' and update list.
        Warn if directory missing or no versions found.
        """
        if not CARLA_DIR.exists():
            print("⚠️ CARLA directory not found:", CARLA_DIR)
            self.carla_versions = []
            return

        self.carla_versions = sorted(
            d.name for d in CARLA_DIR.iterdir()
            if d.is_dir() and d.name.startswith("CARLA_")
        )
        print(f"🔍 Found CARLA versions: {self.carla_versions}")

        if not self.carla_versions:
            print("⚠️ No CARLA versions detected! Please download and extract at least CARLA 0.9.14 to:")
            print(f"    → {CARLA_DIR}")


    def get_next_record_folder(self) -> Path:
        """
        Create and return a new record folder under DATA_DIR/record/YYYY-MM-DD/record_N.
        Counter resets on date change.
        """
        today = datetime.date.today().isoformat()
        last_date = self.get("last_record_date", "")
        last_num = self.get("last_record_number", 0)

        # Reset count when the date has changed
        if last_date != today:
            last_num = 0

        next_num = last_num + 1
        folder = DATA_DIR / "record" / today / f"record_{next_num}"
        folder.mkdir(parents=True, exist_ok=True)

        # Save updated date and counter
        self.set("last_record_date", today)
        self.set("last_record_number", next_num)

        return folder



if __name__ == "__main__":
    # Instantiate DataManager and run simple test to display internal state
    manager = DataManager()
    # Print the full loaded and validated state
    print("Current state:")
    print(manager.state)
    print("-" * 40)
    # Print the detected CARLA versions
    print("Detected CARLA versions:")
    print(manager.carla_versions)
    print("-" * 40)
    # Create and display the next record folder path
    next_folder = manager.get_next_record_folder()
    print("Next record folder:", next_folder)