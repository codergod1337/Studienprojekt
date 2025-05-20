# utils/paths.py

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]  # z. B. .../Studienprojekt

CARLA_DIR = ROOT_DIR / "CARLA"
CARLA_SGG_DIR = ROOT_DIR / "carla_scene_graphs"
DATA_DIR = ROOT_DIR / "thomas" / "data"
CONFIG_PATH = DATA_DIR / "state.json"
DEFAULTS_PATH = DATA_DIR / "default_values.json"


def get_egg_file_path(version: str) -> Path:
    """
    Gibt Pfad zur .egg-Datei der übergebenen CARLA-Version zurück.
    Beispiel: version = "CARLA_0.9.14"
    """
    target_folder = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist"

    for file in target_folder.glob("*.egg"):
        return file

    raise FileNotFoundError(f"Keine passende .egg-Datei gefunden für Version: {version}")