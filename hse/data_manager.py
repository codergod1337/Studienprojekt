# hse/data_manager.py

import json
from pathlib import Path
import datetime
from typing import Any, Dict
from hse.utils.settings import CONFIG_PATH, DEFAULT_VALUES, CARLA_DIR, DATA_DIR


class DataManager:
    """
    Der DataManager verwaltet das Laden, Speichern und Validieren von Konfigurationsdaten.
    Die Daten werden aus der JSON-Datei `state.json` geladen und mit den Default-Werten ergänzt.
    """

    def __init__(self):
        self.state_path = CONFIG_PATH
        self.state = {}
        self.carla_versions = []  # ← Neue Liste für Versionen
        self._validate_and_load()
        self._scan_carla_versions()  # ← Automatisch beim Start

    def _validate_and_load(self):
        """
        Lädt die Konfiguration aus der Datei und ergänzt fehlende oder ungültige Werte
        anhand von DEFAULT_VALUES. Erstellt die Datei, falls sie nicht existiert.
        """

        # === 1. Datei prüfen oder anlegen ===
        if not self.state_path.exists():
            print("🆕 state.json nicht gefunden – wird erstellt.")
            self._save_json(self.state_path, {})  # leere Datei anlegen

        # === 2. Laden der bestehenden Werte ===
        self.state = self._load_json(self.state_path)

        # === 3. Überprüfung & Ergänzung fehlender oder ungültiger Werte ===
        changed = False

        for key, default_value in DEFAULT_VALUES.items():
            if key not in self.state:
                print(f"➕ Setze Standardwert für '{key}': {default_value}")
                if key == "controls":
                    # default_value ist hier bereits das Dict aller Control-Einträge
                    self.state[key] = {
                        func: default_value[func].copy()
                        for func in default_value
                    }
                else:
                    self.state[key] = default_value
                changed = True

            else:
                if key == "controls":
                    loaded_controls = self.state["controls"]
                    # default_value ist hier direkt das Dict sämtlicher Controls
                    for func, func_defaults in default_value.items():
                        if func not in loaded_controls:
                            print(f"➕ Setze Standard-Control-Eintrag für '{func}': {func_defaults}")
                            loaded_controls[func] = func_defaults.copy()
                            changed = True
                    if changed:
                        self.state["controls"] = loaded_controls

                elif key == "port":
                    if not isinstance(self.state[key], int) or not (0 < self.state[key] < 65536):
                        print(f"⚠️ Ungültiger Portwert – setze zurück auf {default_value}")
                        self.state[key] = default_value
                        changed = True

                elif key == "timeout":
                    if not isinstance(self.state[key], (int, float)) or self.state[key] <= 0:
                        print(f"⚠️ Timeout ungültig – setze zurück auf {default_value}")
                        self.state[key] = default_value
                        changed = True

        # === 4. Falls nötig, speichern ===
        if changed:
            self._save_json(self.state_path, self.state)
            print("💾 state.json aktualisiert.")

    def _load_json(self, path: Path) -> Dict[str, Any]:
        """Hilfsfunktion zum Laden einer JSON-Datei."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Fehler beim Laden von {path.name}: {e}")
            return {}

    def _save_json(self, path: Path, data: Dict[str, Any]):
        """Hilfsfunktion zum Speichern einer JSON-Datei."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"❌ Fehler beim Speichern von {path.name}: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Liest einen Wert aus dem Konfigurationszustand."""
        return self.state.get(key, default)

    def set(self, key: str, value: Any):
        """Setzt einen Wert im Konfigurationszustand und speichert direkt."""
        self.state[key] = value
        self._save_json(self.state_path, self.state)

    def _scan_carla_versions(self):
        if not CARLA_DIR.exists():
            print("⚠️ CARLA-Verzeichnis nicht gefunden:", CARLA_DIR)
            self.carla_versions = []
            return

        # Filtere nur Ordner mit Prefix CARLA_
        self.carla_versions = sorted([
            d.name for d in CARLA_DIR.iterdir()
            if d.is_dir() and d.name.startswith("CARLA_")
        ])
        print(f"🔍 Gefundene CARLA-Versionen: {self.carla_versions}")

        # Sicherheitsabfrage: keine Versionen gefunden
        if not self.carla_versions:
            print("⚠️  Keine CARLA-Versionen gefunden!")
            print("💡  Bitte lade mindestens CARLA 0.9.14 herunter und entpacke es in:")
            print(f"    → {CARLA_DIR}")



    def get_next_record_folder(self) -> Path:
        """
        Erzeugt im DATA_DIR/record/YYYY-MM-DD/ eine neue Nummer:
         - Wenn sich das Datum geändert hat, wird counter zurückgesetzt.
         - Gibt den Path zum neuen Ordner zurück und speichert Datum+Nummer im State.
        """
        today = datetime.date.today().isoformat()  # 'YYYY-MM-DD'
        
        # Lade aktuellen State
        last_date = self.get("last_record_date", "")
        last_num  = self.get("last_record_number", 0)

        # Wenn neues Datum, reset counter
        if last_date != today:
            last_num = 0

        # nächste Nummer
        next_num = last_num + 1
        # Pfad: DATA_DIR/record/today/record_{num}
        base = DATA_DIR / "record" / today
        folder = base / f"record_{next_num}"
        folder.mkdir(parents=True, exist_ok=True)

        # Im State speichern
        self.set("last_record_date", today)
        self.set("last_record_number", next_num)

        return folder