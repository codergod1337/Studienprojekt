# hse/controller_manager.py

import sys
import threading
import time
from pathlib import Path

# Wenn das Modul direkt ausgeführt wird, sicherstellen, dass das Projekt-Root drin ist
root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

import pygame
from typing import Dict, Any, Optional, Tuple

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QProgressBar, QSizePolicy, QComboBox, QScrollArea,
    QPushButton, QCheckBox
)
from PyQt5.QtCore import QTimer, Qt, QObject
from hse.data_manager import DataManager

from hse.utils.settings import DEFAULT_VALUES



class ControllerManager(QObject):

    def __init__(self, data_manager: DataManager):
        super().__init__()
        # Reference to DataManager for saving and loading control settings
        self.data = data_manager
        pygame.init()
        pygame.joystick.init()

        #  Discover and initialize all connected joystick devices
        self.joysticks = []  # will hold pygame.Joystick instances
        # Right now connected:
        device_count = pygame.joystick.get_count()

        for current_joystick_index in range(device_count):
            current_joystick = pygame.joystick.Joystick(current_joystick_index)
            current_joystick.init()
            name = current_joystick.get_name()
            self.joysticks.append(current_joystick)
            print(f"Joystick found: index={current_joystick_index}, name='{name}'")

        # Load known_devices dict from state.json
        self.known_devices = self.data.get("known_devices", {}) or {}

        # Register any newly discovered joysticks
        #    - For each joystick, if its name not in known_devices, add an entry
        #    - Each axis gets a dict with default style="unipolar", inverted=False
        for current_joystick in self.joysticks:
            name = current_joystick.get_name()
            # build list of axis descriptors
            axes_info = []
            for axis_current_joystick in range(current_joystick.get_numaxes()):
                axes_info.append({
                    "id": axis_current_joystick,
                    "style": "unipolar",   # default mapping style
                    "inverted": False      # default inversion flag
                })
            # build list of button indices
            buttons = list(range(current_joystick.get_numbuttons()))

            # if this device is not yet known, register it
            if name not in self.known_devices:
                self.known_devices[name] = {
                    "axes": axes_info,
                    "buttons": buttons
                }
                print(f"Registering new device in known_devices: '{name}'")

        # Persist updated known_devices back to state.json
        self.data.set("known_devices", self.known_devices)

        # Determine which joystick to activate
        active_name = self.data.get("active_controller", None)
        self.current_joystick = None

        # known hardware found -> activating
        if active_name in self.known_devices:
            for current_joystick in self.joysticks:
                if current_joystick.get_name() == active_name:
                    self.current_joystick = current_joystick
                    print(f"Re-activating previously active joystick: '{active_name}'")
                    break

        if self.current_joystick is None and self.joysticks:
            # No prior active or it wasn't found—use the first one
            self.current_joystick = self.joysticks[0]
            new_name = self.current_joystick.get_name()
            self.data.set("active_controller", new_name)
            print(f"No valid active_controller found; defaulting to '{new_name}'")

        if not self.current_joystick:
            print("No joystick available after checking active_controller.")

        # Initialize raw state containers for the active joystick
        #   - raw_axes: axis_index -> Optional[float], starts at None until first read
        #   - raw_buttons: button_index -> int (0 or 1), starts at 0 (not pressed)
        if self.current_joystick:
            self.raw_axes   = { i: None for i in range(self.current_joystick.get_numaxes()) }
            self.raw_buttons = { j:  0   for j in range(self.current_joystick.get_numbuttons()) }
        else:
            self.raw_axes   = {}
            self.raw_buttons = {}




        # Load control mappings (function -> {type, id}) from state, default to empty
        self.controls_cfg: Dict[str, Dict[str, Optional[int]]] = self.data.get("controls", {})

        # Initialize the “previously mapped values” dictionary
        # We use this to detect changes in each control since the last poll.
        # Starting with None indicates “no prior value recorded yet”.
        self._last_mapped_controls = {
            func: None
            for func in self.controls_cfg
        }


        # Threading primitives for continuous background scanning
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    def _scan_loop(self):
        """Background thread: polls pygame and updates raw state dicts."""
        while self._running:
            try:
                pygame.event.pump()
            except pygame.error:
                break

            with self._lock:
                if self.current_joystick:
                    # update each axis value (float in [-1.0, +1.0])
                    for axis_current_joystick in list(self.raw_axes.keys()):
                        self.raw_axes[axis_current_joystick] = self.current_joystick.get_axis(axis_current_joystick)
                    # update each button state (int 0 or 1)
                    for btn_idx in list(self.raw_buttons.keys()):
                        self.raw_buttons[btn_idx] = int(self.current_joystick.get_button(btn_idx))


            time.sleep(0.033)   # ~30Hz



    def get_all_states(self):
        """
        FOR DEBUG!!!!!
        Returns processed axis and button states:
          {
            "axes":   { idx: float in [-1..1] or [0..1] depending on style },
            "buttons":{ idx: int (0 or 1) }
          }
        Uses the stored 'style' and 'inverted' flags from known_devices,
        which were guaranteed to exist at initialization time.
        """
        with self._lock:
            axes_out = {}
            dev_name = (self.current_joystick.get_name()
                        if self.current_joystick else None)

            for axis_idx, raw in self.raw_axes.items():
                if raw is None:
                    # never read yet
                    axes_out[axis_idx] = None
                    continue

                # look up axis metadata (guaranteed to have style/inverted)
                meta = None
                if dev_name:
                    for a in self.known_devices[dev_name]["axes"]:
                        if a["id"] == axis_idx:
                            meta = a
                            break

                # apply inversion
                val = -raw if meta and meta["inverted"] else raw

                # apply style
                if meta and meta["style"] == "unipolar":
                    val = (val + 1.0) / 2.0

                axes_out[axis_idx] = val

            # buttons are already 0 or 1
            return {"axes": axes_out, "buttons": dict(self.raw_buttons)}
        
    def get_mapped_controls(self) -> Dict[str, Optional[float]]:
        """
        For each function defined in controls_cfg, return its current
        mapped value based on the latest raw states:
          * Axis mapping yields a float (or None if unmapped)
          * Button mapping yields 0 or 1 (or None if unmapped)
        """
        # Fetch the latest processed states (already styled/unipolar or bipolar)
        states = self.get_all_states()
        mapped: Dict[str, Optional[float]] = {}

        for func, cfg in self.controls_cfg.items():
            mapping_type = cfg.get("type")
            mapping_id   = cfg.get("id")

            if mapping_type == "axis":
                # Retrieve the axis value (may be None until first poll)
                mapped[func] = states["axes"].get(mapping_id)
            elif mapping_type == "button":
                # Retrieve the button state as 0 or 1
                mapped[func] = states["buttons"].get(mapping_id)
            else:
                # No assignment, so no value
                mapped[func] = None
        return mapped

 


    def set_mapping(self, func: str, mtype: str, idx: int):
        with self._lock:
            self.controls_cfg[func] = {"type": mtype, "id": idx}
            self.data.set("controls", self.controls_cfg)


    def set_device(self, index: int):
        with self._lock:
            if self.joystick:
                self.joystick.quit()
            js = pygame.joystick.Joystick(index)
            js.init()
            self.joystick = js
            # reset raw_axes/raw_buttons für neue Counts
            self.raw_axes = {i: 0.0 for i in range(js.get_numaxes())}
            self.raw_buttons = {j: False for j in range(js.get_numbuttons())}

    def shutdown(self):
        self._running = False
        self._thread.join(timeout=0.5)
        if self.current_joystick:
            self.current_joystick.quit()
        pygame.quit()


if __name__ == "__main__":
    import os
    import time
    from hse.data_manager import DataManager

    # -----------------------------------------------------------------------------
    # Instantiate DataManager and ControllerManager
    # -----------------------------------------------------------------------------
    dm = DataManager()
    cm = ControllerManager(dm)

    # -----------------------------------------------------------------------------
    # Simple console UI: poll and display all axis/button values of the active joystick
    # Clears the console each frame so the output appears “static”
    # -----------------------------------------------------------------------------
    print("Joystick test running. Press Ctrl+C to exit.")
    try:
        while True:
            # 1) Fetch the latest raw & mapped states
            states = cm.get_all_states()
            # 2) Clear screen (Windows vs. Unix)
            os.system("cls" if os.name == "nt" else "clear")

            # 3) Header
            active = cm.current_joystick.get_name() if cm.current_joystick else "None"
            print(f"Active joystick: {active}\n")

            # 4) Axes
            print("Axes:")
            for axis_idx, val in states["axes"].items():
                if val is None:
                    print(f"  Axis {axis_idx}: <no data yet>")
                else:
                    print(f"  Axis {axis_idx}: {val:.3f}")

            # 5) Buttons
            print("\nButtons:")
            for btn_idx, pressed in states["buttons"].items():
                print(f"  Button {btn_idx}: {'Pressed' if pressed else 'Released'}")

            # 6) Wait a short moment before next update (~20 Hz)
            time.sleep(0.05)

    except KeyboardInterrupt:
        # User requested exit
        print("\nExiting joystick test...")

    finally:
        # Clean up thread and pygame
        cm.shutdown()







































