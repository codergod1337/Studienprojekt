# hse/utils/paths.py

from pathlib import Path
from typing import Dict, Any  # Statt dict[...] → Dict[...] verwenden

ROOT_DIR = Path(__file__).resolve().parents[2]  # z. B. .../Studienprojekt

CARLA_DIR = ROOT_DIR / "CARLA"
SGG_DIR = ROOT_DIR / "carla_scene_graphs" 
DATA_DIR = ROOT_DIR / "hse" / "data"
CONFIG_PATH = DATA_DIR / "state.json"

CARLA_FPS: int = 20 # not in use

# === Kamera-Perspektiven ===
# Schlüssel = Name, Wert = optionaler Transform (None = free-Camera)
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


SGG_FPS = 20.0
SGG_RENDER_DIST = 20 #Default is 50
QUEUE_WORKER_COUNT: int = 4 #Threads used for recording SG Frames

# === Default-Konfiguration ===
DEFAULT_VALUES: Dict[str, object] = {
    "host": "localhost",
    "port": 2000,
    "timeout": 15.0,
    "carla_version": "CARLA_0.9.14",  # wird beim Start ggf. gesetzt
    "model": "vehicle.tesla.model3", 
    "sgg_loaded": False,
    "recording_active": False,
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
