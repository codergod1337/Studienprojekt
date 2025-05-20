# carla_connector.py

import carla
import random
from typing import List

class CarlaConnector:
    def __init__(self, host="localhost", port=2000, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout

        self.client = None
        self.world = None
        self.connected = False

        self.available_vehicle_list = []
        self.vehicle = None

        self._connect()

    def _connect(self):
        try:
            self.client = carla.Client(self.host, self.port)
            self.client.set_timeout(self.timeout)
            self.world = self.client.get_world()
            self._load_available_vehicles()
            self.connected = True
            print("✅ Verbindung zu CARLA hergestellt")
        except Exception as e:
            self.connected = False
            print(f"❌ Fehler bei Verbindung zu CARLA: {e}")
    
    def is_connected(self) -> bool:
        return self.connected
    
    def _load_available_vehicles(self):
        try:
            blueprint_library = self.world.get_blueprint_library()
            self.available_vehicle_list = [
                bp.id for bp in blueprint_library.filter("vehicle.*")
            ]
            print(f"🚗 {len(self.available_vehicle_list)} Fahrzeugmodelle geladen.")
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Fahrzeugmodelle: {e}")
            self.available_vehicle_list = []

    def spawn_vehicle(self, model_id=None):
        if not self.world or not self.blueprint_library:
            print("❌ Welt oder Blueprints nicht geladen")
            return None

        if self.vehicle:
            self.destroy_vehicle()

        blueprint = self.blueprint_library.find(model_id or "vehicle.tesla.model3")
        spawn_point = random.choice(self.world.get_map().get_spawn_points())
        self.vehicle = self.world.try_spawn_actor(blueprint, spawn_point)

        if self.vehicle:
            print(f"🚗 Fahrzeug gespawnt: {self.vehicle.type_id}")
        else:
            print("❌ Fahrzeug konnte nicht gespawnt werden")
        return self.vehicle

    def set_autopilot(self, enabled=True):
        if self.vehicle:
            self.vehicle.set_autopilot(enabled)

    def get_spectator(self):
        if self.world:
            return self.world.get_spectator()
        return None

    def destroy_vehicle(self):
        if self.vehicle:
            self.vehicle.destroy()
            print("🗑️ Fahrzeug entfernt")
            self.vehicle = None

    def get_world_snapshot(self):
        if self.world:
            return self.world.get_snapshot()
        return None

    def get_map(self):
        if self.world:
            return self.world.get_map()
        return None

    def get_available_vehicles(self) -> List[str]:
        return self.available_vehicle_list