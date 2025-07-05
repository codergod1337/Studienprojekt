# hse/utils/settings.py

"""
This module defines all of the fixed paths, simulation parameters, 
camera presets, and default application state values for the HSE CARLA tools.
"""

from pathlib import Path
from typing import Dict, Any  # Statt dict[...] → Dict[...] verwenden


# === Project directory structure ===
ROOT_DIR = Path(__file__).resolve().parents[2]  
CARLA_DIR = ROOT_DIR / "CARLA"
SGG_DIR = ROOT_DIR / "carla_scene_graphs" 
DATA_DIR = ROOT_DIR / "hse" / "data"
CONFIG_PATH = DATA_DIR / "state.json"
MAP_DIR   = ROOT_DIR / "hse" / "maps"


# === Simulation parameters ===
SGG_FPS = 20.0
SGG_RENDER_DIST = 20 #Default is 50
QUEUE_WORKER_COUNT: int = 4 #Threads used for recording SG Frames
CARLA_FPS: int = 20 # not in use


# === Camera preset ===
# key = friendly name, value = transform dict (None gives free camera)
CAMERA_POSITIONS: Dict[str, Any] = {
    "free": None,
    "cockpit": {
        "transform": {
            "location": {"x": 0.8, "y": 0.0, "z": 1.2},
            "rotation": {"pitch": 10.0, "yaw": 0.0, "roll": 0.0}
        }
    },
    "bird": {
        "transform": {
            "location": {"x": -6.0, "y": 0.0, "z": 6.0},
            "rotation": {"pitch": -30.0, "yaw": 0.0, "roll": 0.0}
        }
    }
}


# === Default application state ===
DEFAULT_VALUES: Dict[str, object] = {
    "host": "localhost",
    "port": 2000,
    "timeout": 15.0,
    "carla_version": "CARLA_0.9.14",  
    "model": "vehicle.tesla.model3", 
    "sgg_loaded": False,
    "last_record_date": "",
    "last_record_number": 0,
    "camera_selected": "free",
    "active_controller":None,
    
    
        "controls": {
        "throttle":   {"type": None, "id": None, "color": "#e6194b"},
        "brake":      {"type": None, "id": None, "color": "#3cb44b"},
        "steering":   {"type": None, "id": None, "color": "#4363d8"},
        "reverse":    {"type": None, "id": None, "color": "#f58231"},
        "respawn":    {"type": None, "id": None, "color": "#911eb4"},
        "cam_switch": {"type": None, "id": None, "color": "#42d4f4"},
        "record":     {"type": None, "id": None, "color": "#f032e6"},
    },
    "known_devices": {}
}
