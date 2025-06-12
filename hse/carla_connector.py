# hse/carla_connector.py

import threading
import time
import sys
import carla
import queue
from typing import Optional, Any

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from hse.data_manager import DataManager
from hse.utils.settings import CAMERA_POSITIONS, CARLA_DIR, CARLA_FPS


class CarlaConnector(QObject):
    """
    Läuft in eigenem Thread und wartet darauf, dass connect() ausgelöst wird.
    Erst dann liest er host, port und carla_version aus DataManager und verbindet.
    """
    connection_result = pyqtSignal(bool, str)
    blueprints_loaded = pyqtSignal(list)    # list[str] aller vehicle-Blueprint-IDs
    vehicle_model_selected = pyqtSignal(str)     # emit wenn Nutzer ein Modell wählt
    camera_position_selected = pyqtSignal(str)
    


    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data = data_manager
        self._lock               = threading.Lock()
        self._do_connect         = threading.Event()
        self._running            = True
        self._controler_manager    = None

        # Client, Model & Camera
        self._client: Optional[Any] = None
        self._vehicle_model: Optional[str] = None
        self._camera_selected: Optional[str] = None

        # Queue für Spawn-Befehle
        self._command_queue      = queue.Queue()
        self._spawned_vehicles   = []

        # Nur einmal Blueprints laden
        self._blueprints_loaded  = False

        # ── Dynamisch CARLA-API laden ──
        version = self.data.get("carla_version")
        egg_dir = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist"
        if egg_dir.exists():
            eggs = sorted(egg_dir.glob("carla-*.egg"))
            if eggs:
                sys.path.insert(0, str(eggs[-1]))
        # Jetzt das Modul importieren
        import importlib
        self.carla = importlib.import_module("carla")

        # Start Thread
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_controler_manager(self, cm):
        """Euer ControlerManager-Instanz setzen, damit wir .get_current_control() aufrufen können."""
        self._controler_manager = cm

    def connect(self):
        """Wird aufgerufen, wenn der Benutzer den Connect-Button klickt."""
        self._do_connect.set()

    def disconnect(self):
        """Manuelle Trennung: setzt Client=None, feuert Signal."""
        with self._lock:
            self._client = None
        self.connection_result.emit(False, "Disconnected by user")


    def _apply_camera(self):
        """Setzt den Spectator-View anhand self._camera_selected auf das letzte Vehicle."""
        if not self._client or not self._spawned_vehicles:
            return

        cam = self._camera_selected
        cfg = CAMERA_POSITIONS.get(cam)
        if not cfg:
            return  # 'free' oder unbekannt → keine Änderung

        world = self._client.get_world()
        spectator = world.get_spectator()

        # Basis-Transform des letzten Fahrzeugs
        actor_tf = self._spawned_vehicles[-1].get_transform()

        # Offset aus settings
        loc = cfg["transform"]["location"]
        rot = cfg["transform"]["rotation"]

        # 1) Neue Location = Fahrzeug-Location + Offset
        new_loc = actor_tf.location
        new_loc.x += loc["x"]
        new_loc.y += loc["y"]
        new_loc.z += loc["z"]

        # 2) Neue Rotation = Fahrzeug-Rotation + Offset
        base_rot = actor_tf.rotation
        new_rot = self.carla.Rotation(
            pitch=base_rot.pitch + rot["pitch"],
            yaw=   base_rot.yaw   + rot["yaw"],
            roll=  base_rot.roll  + rot["roll"]
        )

        # 3) Neuer Transform und anwenden
        new_tf = self.carla.Transform(new_loc, new_rot)
        spectator.set_transform(new_tf)

    def get_client(self) -> Optional[carla.Client]:
        """Gibt den aktive carla.Client-Instanz zurück (oder None)."""
        with self._lock:
            return self._client

    def shutdown(self):
        """Stoppt Thread, setzt Client=None."""
        self._running = False
        self._thread.join(timeout=0.5)
        with self._lock:
            self._client = None

    @pyqtSlot(str)
    def set_vehicle_model(self, model_id: str):
        """Vom UI aufgerufen, wenn der Nutzer ein Blueprint auswählt."""
        with self._lock:
            self._vehicle_model = model_id
            # persistieren
            self.data.set("model", model_id)
        # UI benachrichtigen
        self.vehicle_model_selected.emit(model_id)

    @pyqtSlot()
    def spawn_vehicle(self):
        """UI-Thread ruft das, um im Connector-Thread ein Fahrzeug zu spawnen."""
        # Nur prüfen, Queue akzeptiert auch ohne Client
        self._command_queue.put("spawn")    

    @pyqtSlot(str)
    def set_camera_position(self, cam_id: str):
        """Vom UI aufgerufen, wenn der Nutzer eine neue Kameraposition wählt."""
        if cam_id not in CAMERA_POSITIONS:
            return
        with self._lock:
            self._camera_selected = cam_id
        # sofort persistieren
        self.data.set("camera_selected", cam_id)
        # UI informieren
        self.camera_position_selected.emit(cam_id)   
        # Unmittelbar Kamera anpassen (falls schon gespawnte Fahrzeuge existieren)
        self._apply_camera()   






    def _run(self):
        """
        Haupt-Loop läuft erst nach connect():
        1) Warten auf connect()
        2) World & Sync-Modus einmalig einrichten
        3) Endlosschleife: tick(), Spawn, Steuerung, Kamera
        """
        FIXED_FPS = 20.0

        # ── 1) Vor dem Connect blockieren ─────────────────────────────
        # Wir blockieren hier, bis connect() einmal aufgerufen wurde.
        self._do_connect.wait()

        # ── 2) Nach dem Connect: Client, World & Sync-Einstellungen ───
        with self._lock:
            host          = self.data.get("host")
            port          = self.data.get("port")
            carla_version = self.data.get("carla_version")

        try:
            # Client & World initialisieren
            client = self.carla.Client(host, port)
            client.set_timeout(self.data.get("timeout", 10.0))
            world  = client.get_world()

            # Sync-Modus auf FIXED_FPS setzen
            settings = world.get_settings()
            settings.synchronous_mode    = True
            settings.fixed_delta_seconds = 0.05 #1.0 / FIXED_FPS
            world.apply_settings(settings)

            # Intern speichern
            with self._lock:
                self._client = client
                self._world  = world

            # UI über Connection-Status informieren
            self.connection_result.emit(
                True,
                f"Connected to {host}:{port} (version {carla_version})"
            )

            # Blueprints einmalig laden & Auto-Select Model/Camera
            bps = [bp.id for bp in world.get_blueprint_library().filter("vehicle.*")]
            with self._lock:
                self._blueprints = bps
            self.blueprints_loaded.emit(bps)
            self._blueprints_loaded = True

            # Auto-Select gespeichertes Model
            saved_model = self.data.get("model")
            if saved_model in bps:
                with self._lock:
                    self._vehicle_model = saved_model
                self.vehicle_model_selected.emit(saved_model)

            # Auto-Select gespeicherte Kamera
            from hse.utils.settings import CAMERA_POSITIONS
            saved_cam = self.data.get("camera_selected")
            if saved_cam in CAMERA_POSITIONS:
                with self._lock:
                    self._camera_selected = saved_cam
                self.camera_position_selected.emit(saved_cam)

        except Exception as e:
            self.connection_result.emit(False, f"Connection failed: {e}")
            return  # Thread beenden, wenn Connect fehlschlägt

        # ── 3) Haupt-Schleife: tick(), Spawn, Steuerung, Kamera ────────
        while self._running:
            # 3.1 Simulationstakt
            #self._world.tick()
            #time.sleep(0.1)

            # 3.2 Spawn-Befehle
            try:
                cmd = self._command_queue.get_nowait()
            except queue.Empty:
                cmd = None

            if cmd == "spawn" and self._vehicle_model:
                spawn_points = self._world.get_map().get_spawn_points()
                idx = len(self._spawned_vehicles) % len(spawn_points)
                transform = spawn_points[idx]
                bp = self._world.get_blueprint_library().find(self._vehicle_model)
                actor = self._world.spawn_actor(bp, transform)
                self._spawned_vehicles.append(actor)

            # 3.3 Steuerung (Throttle, Brake, Steering, Reverse)
            if self._spawned_vehicles and self._controler_manager:
                current = self._controler_manager.get_current_control()
                vehicle = self._spawned_vehicles[-1]

                # Steering-Fallback: Achse oder Left/Right-Tasten
                steer = current.get("steering", 0.0)
                if abs(steer) < 1e-3:
                    steer = current.get("steering_right", 0.0) - current.get("steering_left", 0.0)

                ctrl = self.carla.VehicleControl(
                    throttle=current.get("throttle", 0.0),
                    brake   =current.get("brake",    0.0),
                    steer   =steer,
                    reverse =(current.get("reverse", 0.0) > 0.5),
                )
                vehicle.apply_control(ctrl)

            # 3.4 Kamera-Update (offset)
            self._apply_camera()

   