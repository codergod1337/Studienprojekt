# hse/carla_connector.py

import threading
import time
import sys
import carla
import queue
import pygame
from timeit import default_timer as timer

from concurrent.futures import ThreadPoolExecutor
from collections import Counter

from typing import Optional, Any
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from hse.data_manager import DataManager
from hse.utils.settings import CAMERA_POSITIONS, CARLA_DIR, CARLA_FPS, SGG_DIR, SGG_FPS





class CarlaConnector(QObject):
    """
    Läuft in eigenem Thread und wartet darauf, dass connect() ausgelöst wird.
    Erst dann liest er host, port und carla_version aus DataManager und verbindet.
    """
    connection_result = pyqtSignal(bool, str)
    blueprints_loaded = pyqtSignal(list)    # list[str] aller vehicle-Blueprint-IDs
    vehicle_model_selected = pyqtSignal(str)     # emit wenn Nutzer ein Modell wählt
    camera_position_selected = pyqtSignal(str)
    frame_recorded = pyqtSignal(int)    # emit nach jedem aufgenommenen Frame


    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data = data_manager


        # ── 1) Attribute initialisieren ───────────────────────────
        self._lock       = threading.Lock()
        self._do_connect = threading.Event()
        self._client             = None
        self._world              = None
        self._spawned_vehicles   = []
        self._command_queue      = queue.Queue()
        self._running            = True
        self._blueprints_loaded  = False
        self._recording_active   = False
        self._record_base_folder = None
        self._SGGClass           = None
        self._sgg                = None
        # Intervall in Sekunden zwischen zwei SGG-Aufzeichnungen
        self._sgg_interval  = round(1.0 / SGG_FPS, 4)
        # Zeitstempel der letzten Aufzeichnung
        self._last_sgg_time = 0.0

        self._record_queue = queue.Queue()
        self._executor   = ThreadPoolExecutor(max_workers=4)
        # starte einen Worker-Loop
        self._executor.submit(self._record_worker)

        """
        # ── 2) Setup CARLA-Python-API & agents-Package ─────────────
        version = self.data.get("carla_version")
        # a) egg-Verzeichnis (enthält carla.egg ohne agents)
        egg_dir = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist"
        if egg_dir.exists():
            eggs = sorted(egg_dir.glob("carla-*.egg"))
            if eggs:
                sys.path.insert(0, str(eggs[-1]))

        # b) nativer carla-Ordner, der auch agents/navigation enthält
        carla_pkg = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla"
        if carla_pkg.exists():
            sys.path.insert(0, str(carla_pkg))

        # Jetzt, **erst** nachdem beide Pfade gesetzt sind, carla importieren:
        import importlib
        self.carla = importlib.import_module("carla")
        """

        # ── 3) Setup SGG-Paket ─────────────────────────────────────
        #    füge carla_scene_graphs ins sys.path, damit carla_sgg gefunden wird
        if SGG_DIR.exists():
            sys.path.insert(0, str(SGG_DIR))
        #    dann importiere SGG
        import importlib
        sgg_mod = importlib.import_module("carla_sgg.sgg")
        self._SGGClass = sgg_mod.SGG

        # ── Abstraktions-Funktionen + Exception importieren ────────────────────────
        from carla_sgg.sgg_abstractor import (
            process_to_rsv,           # RSV = Entities + Lanes + Relations
            entities   as E,          # E   = Entities only
            semgraph   as EL,         # EL  = Entities + Lanes
            process_to_rsv as ER,     # ER  = Entities + Relations only
            EgoNotInLaneException
        )

        # ── 4) Connector-Thread starten ─────────────────────────────
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()


    def _setup_sgg_imports(self):
        """
        Sorgt dafür, dass sowohl die CARLA-API (mit agents.*) als auch
        das carla_sgg-Paket gefunden werden, und lädt dann SGG.
        """
        version = self.data.get("carla_version")

        # 1) CARLA-PythonAPI ins sys.path
        carla_api_pkg = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla"
        if carla_api_pkg.exists():
            sys.path.insert(0, str(carla_api_pkg))

        # 2) Scene-Graph-Repo ins sys.path
        #    SGG_DIR zeigt auf .../carla_scene_graphs
        if SGG_DIR.exists():
            sys.path.insert(0, str(SGG_DIR))

        # 3) Jetzt importieren
        #    carla_sgg ist das Paket, sgg.py darin enthält class SGG
        import importlib
        module = importlib.import_module("carla_sgg.sgg")
        self._SGGClass = module.SGG




    def set_controller_manager(self, cm):
        """Euer ControllerManager-Instanz setzen, damit wir .get_current_control() aufrufen können."""
        self._controller_manager = cm

    def connect(self):
        """Wird aufgerufen, wenn der Benutzer den Connect-Button klickt."""
        self._do_connect.set()

    def disconnect(self):
        """Manuelle Trennung: setzt Client=None, feuert Signal."""
        with self._lock:
            self._client = None
        self.connection_result.emit(False, "Disconnected by user")


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



    def disconnect(self):
        """
        Setzt CARLA zurück in den asynchronen Modus und trennt den Client,
        so dass CARLA weiterläuft, wenn unser Client endet.
        """
        # ① Sync-Modus ausschalten
        if hasattr(self, "_world") and self._world:
            settings = self._world.get_settings()
            settings.synchronous_mode    = False
            settings.fixed_delta_seconds = 0.0
            self._world.apply_settings(settings)

        # ② Traffic Manager zurücksetzen
        if hasattr(self, "_client") and self._client:
            try:
                tm = self._client.get_trafficmanager()
                tm.set_synchronous_mode(False)
            except Exception:
                pass

        # ③ echten Disconnect
        with self._lock:
            self._client = None
        self.connection_result.emit(False, "Disconnected")









    @pyqtSlot()
    def start_recording(self):
        """Wird vom ControlPanel-Button gerufen."""
        # 1) Tages-Ordner anlegen
        folder = self.data.get_next_record_folder()
        self._record_base_folder = folder

        # 2) SGG-Instanz einmalig anlegen
        if self._sgg is None:
            #self._sgg = SGG(self._client)  # oder ggf. SGG(self._client, ego_id=None)
            self._sgg = self._SGGClass(self._client)

        # 3) State setzen
        self.data.set("recording_active", True)
        self._recording_active = True

    @pyqtSlot()
    def stop_recording(self):
        """Beendet das Aufzeichnen."""
        self.data.set("recording_active", False)
        self._recording_active = False
        self._record_base_folder = None


    def _record_worker(self):
        """
        Holt aus self._record_queue die Tupel (frame, ego_id, control, folder)
        und führt darin die SGG-Erzeugung + das Speichern aus.
        """
        while True:
            frame, ego_id, control_dict, folder = self._record_queue.get()
            try:
                # 1) Ego setzen
                self._sgg.ego_id = ego_id
                # 2) Graph erzeugen
                sg = self._sgg.generate_graph_for_frame(
                    frame_num=frame,
                    ego_control=control_dict,
                    render_dist=20
                )
                # 3) Speichern
                self._sgg.save(sg, folder)
                #print(f"Frame {frame} aufgenommen und gespeichert.")
                # ➞ Signal senden:
                try:
                    self.frame_recorded.emit(self._sgg.timestep)
                except Exception:
                    pass
            except Exception as e:
                print(f"Fehler beim Aufzeichnen von Frame {frame}: {e}")
            finally:
                self._record_queue.task_done()



    def _run(self):
        """Heart-loop deines Connectors, läuft im eigenen Thread."""
        # Zustand 1: Disconnected → warten auf connect()
        self._wait_for_connect()

        # Danach Zustand 2: Connected → alles initialisieren
        if not self._initialize_connection():
            return  # Abbruch, wenn Connect fehlgeschlagen

        # Sobald verbunden, in die Haupt-Schleife wechseln
        self._simulation_loop()

    def _wait_for_connect(self):
        """Blockiert, bis connect() das Event setzt."""
        self._do_connect.wait()

    def _initialize_connection(self) -> bool:
        """
        Baut Client auf, setzt sync-Modus, lädt Blueprints,
        wählt Modell/Kamera, feuert connection_result.
        Gibt False zurück, wenn Fehler aufgetreten.
        """
        try:

            # Setup CARLA-Python-API & agents-Package ─────────────
            version = self.data.get("carla_version")
            # egg-Verzeichnis (enthält carla.egg ohne agents)
            egg_dir = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist"
            if egg_dir.exists():
                eggs = sorted(egg_dir.glob("carla-*.egg"))
                if eggs:
                    sys.path.insert(0, str(eggs[-1]))

            # nativer carla-Ordner, der auch agents/navigation enthält
            carla_pkg = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla"
            if carla_pkg.exists():
                sys.path.insert(0, str(carla_pkg))

            # Jetzt, **erst** nachdem beide Pfade gesetzt sind, carla importieren:
            import importlib
            self.carla = importlib.import_module("carla")

            host = self.data.get("host")
            port = self.data.get("port")
            version = self.data.get("carla_version")
            client = self.carla.Client(host, port)
            client.set_timeout(self.data.get("timeout", 10.0))

            world = client.get_world()

            # Sync + fixed delta
            from hse.utils.settings import CARLA_FPS
            settings = world.get_settings()
            settings.synchronous_mode    = True
            settings.fixed_delta_seconds = 0.01 #1.0 / CARLA_FPS
            world.apply_settings(settings)

            # TrafficManager
            tm = client.get_trafficmanager()
            tm.set_synchronous_mode(True)

            # intern speichern
            with self._lock:
                self._client = client
                self._world  = world

            # UI-Signal
            self.connection_result.emit(True, f"Connected to {host}:{port} (version {version})")

            # Blueprints & Auto-Select
            self._load_and_select_blueprints(world)
            self._auto_select_camera(world)

            return True
        except Exception as e:
            self.connection_result.emit(False, f"Connection failed: {e}")
            return False

    def _load_and_select_blueprints(self, world):
        bps = [bp.id for bp in world.get_blueprint_library().filter("vehicle.*")]
        with self._lock:
            self._blueprints = bps
        self.blueprints_loaded.emit(bps)
        self._blueprints_loaded = True

        saved_model = self.data.get("model")
        if saved_model in bps:
            with self._lock:
                self._vehicle_model = saved_model
            self.vehicle_model_selected.emit(saved_model)

    def _auto_select_camera(self, world):
        from hse.utils.settings import CAMERA_POSITIONS
        saved_cam = self.data.get("camera_selected")
        if saved_cam in CAMERA_POSITIONS:
            with self._lock:
                self._camera_selected = saved_cam
            self.camera_position_selected.emit(saved_cam)

    def _simulation_loop(self):
        """
        Läuft so lange _running True ist:
         - tick()
         - spawn
         - control
         - camera
         - sgg
        """
        while self._running and self._client:
            # 1) Einen Frame weiterticken (respektiert fixed_delta_seconds!)
            snapshot = self._world.tick()

            # 2) Spawn
            self._process_spawn()

            # 3) Steuerung
            self._process_control()

            # 4) Kamera
            self._apply_camera()

            # 5) Scene-Graph, falls recording aktiv
            if self._sgg and self._recording_active and self._record_base_folder:
                now = time.time()
                if (now - self._last_sgg_time) >= self._sgg_interval:
                    self._last_sgg_time = now
                    self._record_current_frame()


    def _process_spawn(self):
        """
        Prüft, ob über die Queue ein Spawn-Befehl hereingekommen ist,
        und spawnt genau dann **ein** neues Fahrzeug.
        """
        try:
            # 1) Ohne Blockieren aus der Queue lesen
            cmd = self._command_queue.get_nowait()
        except queue.Empty:
            # Keine Befehle vorhanden → nichts tun
            return

        # 2) Wenn Befehl "spawn" und wir haben ein Modell ausgewählt
        if cmd == "spawn" and self._vehicle_model:
            # a) Hol alle Spawn-Punkte der Map
            spawn_points = self._world.get_map().get_spawn_points()
            if not spawn_points:
                # Falls es keine Spawn-Punkte gibt, abbrechen
                return

            # b) Index-Berechnung:
            #    Wir wollen jeweils den nächsten Punkt benutzen,
            #    damit Fahrzeuge sich nicht alle am gleichen Ort stapeln.
            idx = len(self._spawned_vehicles) % len(spawn_points)
            transform = spawn_points[idx]

            # c) Blueprint anhand der gespeicherten Modell-ID
            bp = self._world.get_blueprint_library().find(self._vehicle_model)

            # d) Ein neues Fahrzeug (Actor) spawnieren
            actor = self._world.spawn_actor(bp, transform)

            # e) Den neuen Actor in unsere Liste eintragen
            self._spawned_vehicles.append(actor)

            # Hinweis: Wenn ihr später mal Fahrzeuge zerstören wollt,
            # könnt ihr hier `actor.destroy()` verwenden.

    def _process_control(self):
        """
        Liest Steuerwerte vom ControllerManager und wendet sie auf das aktuell
        gespawnte Fahrzeug an. Keine Keyboard-Fallbacks momentan.
        """
        # 0) Abbruch, wenn kein Fahrzeug oder kein ControllerManager vorhanden
        if not (self._spawned_vehicles and self._controller_manager):
            return

        # TODO: PFUSCH HIER
        # 1) Aktuelle Werte aus dem Mapping (Joystick, Buttons etc.)
        current  = self._controller_manager.get_mapped_controls()
        throttle = current.get("throttle", 0.0)
        brake    = current.get("brake",    0.0)
        steer    = current.get("steering", 0.0)
        reverse  = (current.get("reverse", 0.0) > 0.5)

        # 2) Reverse-Logik: Rückwärtsgang überschreibt Gas
        if reverse:
            # Vorwärts-Gas auf 0, stattdessen Bremse als Rückwärts-Gas
            throttle = brake
            brake    = 0.0

        # 3) VehicleControl bauen und anwenden
        control = self.carla.VehicleControl(
            throttle = throttle,
            brake    = brake,
            steer    = steer,
            reverse  = reverse,
        )
        # Wir steuern immer das zuletzt gespawnte Fahrzeug
        vehicle = self._spawned_vehicles[-1]
        vehicle.apply_control(control)


    def _apply_camera(self):
        """
        Setzt den Spectator (Kameraview) relativ zum zuletzt gespawnten Fahrzeug.
        Wir rechnen den in settings definierten lokalen Offset in Weltkoordinaten um,
        addieren ihn zur Fahrzeugposition und rotieren entsprechend.
        """
        # 1) Nur weitermachen, wenn bereits ein Fahrzeug existiert und wir verbunden sind
        if not self._client or not self._spawned_vehicles:
            return

        # 2) Hole den Namen der gewählten Kameraposition (z.B. "bird", "cockpit", "free")
        cam_key = self._camera_selected
        cfg = CAMERA_POSITIONS.get(cam_key)
        #    - Bei "free" ist cfg == None → wir verändern nichts
        if not cfg:
            return

        # 3) Hol das letzte gespawnte Fahrzeug und seine Transform (Position+Rotation)
        actor = self._spawned_vehicles[-1]
        actor_tf = actor.get_transform()
        #    - actor_tf.location ist ein carla.Location (x, y, z)
        #    - actor_tf.rotation ist ein carla.Rotation (pitch, yaw, roll)

        # 4) Lies aus settings den lokalen Versatz:
        #    loc: {"x": float, "y": float, "z": float}
        #         x = nach vorn, y = seitlich rechts, z = nach oben
        #    rot: {"pitch": float, "yaw": float, "roll": float}
        loc = cfg["transform"]["location"]
        rot = cfg["transform"]["rotation"]

        # 5) Baue den Welt-Offset aus den lokalen Achsen des Fahrzeugs:
        #    - forward = Einheitsvektor in Fahrzeugvorwärtsrichtung
        #    - right   = Einheitsvektor in Fahrzeugrechtsrichtung
        #    - up      = Einheitsvektor in Fahrzeugoberseite
        forward = actor_tf.get_forward_vector()
        right   = actor_tf.get_right_vector()
        up      = actor_tf.get_up_vector()

        #    Dann: world_offset = forward*loc.x + right*loc.y + up*loc.z
        world_offset = self.carla.Location(
            x = forward.x * loc["x"] + right.x * loc["y"] + up.x * loc["z"],
            y = forward.y * loc["x"] + right.y * loc["y"] + up.y * loc["z"],
            z = forward.z * loc["x"] + right.z * loc["y"] + up.z * loc["z"],
        )

        # 6) Bestimme die neue Kameraposition = Fahrzeugposition + Welt-Offset
        #    actor_tf.location ist ebenfalls eine carla.Location,
        #    daher unterstützt carla.Location + carla.Location
        new_location = actor_tf.location + world_offset

        # 7) Berechne die Kamerarotation relativ zum Fahrzeug
        #    Wir addieren einfach die Rotations-Offsets aus settings:
        base_rot = actor_tf.rotation
        new_rotation = self.carla.Rotation(
            pitch = base_rot.pitch + rot["pitch"],
            yaw   = base_rot.yaw   + rot["yaw"],
            roll  = base_rot.roll  + rot["roll"],
        )

        # 8) Erstelle ein neues Transform-Objekt und setze den Spectator darauf
        new_transform = self.carla.Transform(new_location, new_rotation)
        spectator = self._world.get_spectator()
        spectator.set_transform(new_transform)

    def _record_current_frame(self):
        """
        Packt für jeden Frame nur die minimalen Daten in die Queue:
        (frame, ego_id, ego_control, folder)
        und übergibt sie an den Record-Worker.
        """
        if not self._spawned_vehicles:
            print("Kein Fahrzeugs-Actor vorhanden –> Recording übersprungen.")
            return

        latest_spawned_vehicle = self._spawned_vehicles[-1]
        frame = self._sgg.timestep
        ego_id = latest_spawned_vehicle.id
        ctrl = latest_spawned_vehicle.get_control()
        control_copy = {
            "throttle":        ctrl.throttle,
            "steer":           ctrl.steer,
            "brake":           ctrl.brake,
            "hand_brake":      ctrl.hand_brake,
            "reverse":         ctrl.reverse,
            "manual_gear_shift": ctrl.manual_gear_shift,
            "gear":            ctrl.gear
        }

        

        self._record_queue.put((frame, ego_id, control_copy, self._record_base_folder))





