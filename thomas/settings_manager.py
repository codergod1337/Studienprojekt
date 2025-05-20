# settings_manager.py

import json
from pathlib import Path
from utils.paths import CONFIG_PATH, DEFAULTS_PATH, CARLA_DIR

class SettingsManager:
    def __init__(self):
        self.state_path = CONFIG_PATH
        self.defaults_path = DEFAULTS_PATH

        self._ensure_files()

        self.defaults = self._load_json(self.defaults_path)
        self.state = self._load_json(self.state_path)

        # === CARLA-Versionen prüfen und ggf. erste setzen ===
        available_versions = self._get_available_carla_versions()
        self.set("available_carla_versions", available_versions)

        current_version = self.state.get("carla_version")
        if not current_version or current_version not in available_versions:
            if available_versions:
                chosen = available_versions[0]
                self.set("carla_version", chosen)
                self.set("status_message", f"CARLA-Version gesetzt: {chosen}")
            else:
                self.set("status_message", "Keine CARLA-Versionen gefunden")

    def _ensure_files(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not self.state_path.exists():
            self._save_json(self.state_path, {})
            print("🆕 First use on this machine. Creating state.json")

    def _load_json(self, path: Path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"⚠️ Fehler beim Lesen von {path}. Datei wird geleert.")
                return {}

    def _save_json(self, path: Path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=4)

    def get(self, key, fallback=None):
        return self.state.get(key, self.defaults.get(key, fallback))

    def set(self, key, value):
        self.state[key] = value
        self._save_json(self.state_path, self.state)

    def _get_available_carla_versions(self):
        if not CARLA_DIR.exists():
            return []
        return [folder.name for folder in CARLA_DIR.iterdir() if folder.is_dir()]