# utils/paths.py

from pathlib import Path
from typing import Dict  # Statt dict[...] → Dict[...] verwenden

ROOT_DIR = Path(__file__).resolve().parents[2]  # z. B. .../Studienprojekt

CARLA_DIR = ROOT_DIR / "CARLA"
SGG_DIR = ROOT_DIR / "carla_scene_graphs"
DATA_DIR = ROOT_DIR / "hse" / "data"
CONFIG_PATH = DATA_DIR / "state.json"





# === Default-Konfiguration ===
DEFAULT_VALUES: Dict[str, object] = {
    "host": "localhost",
    "port": 2000,
    "timeout": 15.0,
    "carla_version": "CARLA_0.9.14",  # wird beim Start ggf. gesetzt
    "model": "vehicle.tesla.model3", 
    "sgg_loaded": False,
    
    
        "controls": {
        "throttle":   {"type": None, "id": None, "color": "#e6194b"},
        "brake":      {"type": None, "id": None, "color": "#3cb44b"},
        "steering":   {"type": None, "id": None, "color": "#4363d8"},
        "reverse":    {"type": None, "id": None, "color": "#f58231"},
        "respawn":    {"type": None, "id": None, "color": "#911eb4"},
        "cam_switch": {"type": None, "id": None, "color": "#42d4f4"},
        "record":     {"type": None, "id": None, "color": "#f032e6"},
    }
}
