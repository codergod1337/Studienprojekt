# hse/carla_connector.py

from __future__ import annotations

import threading
import time
import sys
#import carla
import queue
import pygame
from timeit import default_timer as timer

from concurrent.futures import ThreadPoolExecutor
from collections import Counter

from typing import Optional, Any, TYPE_CHECKING
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from hse.data_manager import DataManager
from hse.utils.settings import CAMERA_POSITIONS, CARLA_DIR, CARLA_FPS, SGG_DIR, SGG_FPS, SGG_RENDER_DIST, QUEUE_WORKER_COUNT


if TYPE_CHECKING:
    import carla    # nur für die Typprüfung



class CarlaConnector(QObject):
    """
    Runs in its own thread, waits for connect() to be triggered,
    then reads host/port/version from DataManager and establishes CARLA connection.
    """
    # Signals to communicate back to the GUI thread:
    connection_result        = pyqtSignal(bool, str)   # success flag + message
    blueprints_loaded        = pyqtSignal(list)        # emitted with list[str] of vehicle blueprints
    vehicle_model_selected   = pyqtSignal(str)         # emitted when user picks a model
    camera_position_selected = pyqtSignal(str)         # emitted when camera choice changes
    frame_recorded           = pyqtSignal(int)          # emitted after each recorded frame
    recording_status         = pyqtSignal(bool)



    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data = data_manager

        # Initialize all internal attributes 
        # Lock to protect client/world objects across threads
        self._lock       = threading.Lock()

        # Event to signal "connect()" was called from GUI
        self._do_connect = threading.Event()

        # Will hold the carla.Client once connected
        self._client             = None

        # Will hold the world instance after connection
        self._world              = None

        # List of all spawned Actor references
        self._spawned_vehicles   = []

        # Queue for commands (e.g. "spawn") coming from GUI thread
        self._command_queue      = queue.Queue()

        # Control flag for main loop
        self._running            = True

        # Have we loaded blueprints yet?
        self._blueprints_loaded  = False

        # Recording state and folder
        self._recording_active   = False
        self._record_base_folder = None

        # SGG (scene graph) classes and instance
        self._SGGClass           = None
        self._sgg                = None

        # Compute the interval between SGG snapshots (in seconds) based on desired frames per second (SGG_FPS)
        self._sgg_interval  = round(1.0 / SGG_FPS, 4)
        # Timestamp of the last SGG snapshot
        self._last_sgg_time = 0.0

        # Queue for handing off frame-by-frame recording work
        self._record_queue = queue.Queue()
        # Thread pool to run the recording worker in background
        self._executor   = ThreadPoolExecutor(max_workers=QUEUE_WORKER_COUNT)
        # Start the recording worker in the pool
        self._executor.submit(self._record_worker)

        """
        # Prepare the SGG package import 
        # If the SGG repo folder exists, insert it into sys.path so we can import it.
        if SGG_DIR.exists():
            sys.path.insert(0, str(SGG_DIR))
        # Dynamically import carla_sgg.sgg to get the SGG class
        import importlib
        sgg_mod = importlib.import_module("carla_sgg.sgg")
        self._SGGClass = sgg_mod.SGG

        # Prepare SGG abstractor functions 
        # Import the abstractor utilities that process simulation state into graphs.
        # process_to_rsv: full scene graph (Entities + Lanes + Relations)
        # EgoNotInLaneException: raised when ego-vehicle is outside any lane
        from carla_sgg.sgg_abstractor import (
            process_to_rsv,           # RSV = Entities + Lanes + Relations
            entities   as E,          # E   = Entities only
            semgraph   as EL,         # EL  = Entities + Lanes
            process_to_rsv as ER,     # ER  = Entities + Relations only
            EgoNotInLaneException
        )
        # The connector can now use these functions to build and filter graphs as needed.
        self._abstract_rsv       = process_to_rsv
        self._abstract_entities  = E
        self._abstract_semgraph  = EL
        self._abstract_er        = ER
        self._ego_not_in_lane_ex = EgoNotInLaneException
        """

        # Keep last values for each mapped control so we can detect button presses
        self._last_control_values = {
            func: 0.0
            for func in self.data.get("controls", {})
        }

        # Start the main connector thread 
        # This thread will run self._run() as long as self._running is True in a background thread.
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()


    def set_controller_manager(self, cm):
        """
        Store the provided ControllerManager instance so that later
        we can call cm.get_mapped_controls() to read joystick inputs.
        """
        self._controller_manager = cm


    def connect(self):
        """
        Called from the GUI thread when the user clicks "Connect".
        Sets an event flag that wakes up the connector thread to start connecting.
        """
        self._do_connect.set()


    def get_client(self) -> Optional[carla.Client]:
        """
        Return the active carla.Client, or None if not connected.
        This is thread-safe thanks to the lock.
        """
        with self._lock:
            return self._client


    def shutdown(self):
        """
        Gracefully shut down the connector:
        1) Disconnect from the CARLA server (reset sync mode, clear client).
        2) Stop the main loop thread.
        3) Shut down the recording worker executor.
        """
        # 1) Delegate CARLA‐specific teardown to disconnect()
        #    (this will disable sync mode, reset TrafficManager, clear self._client and emit the signal)
        self.disconnect()

        # 2) Stop the simulation loop
        #    Setting _running=False causes _simulation_loop to exit at its next iteration.
        self._running = False
        if hasattr(self, "_thread") and self._thread.is_alive():
            # Wait briefly for the thread to finish
            self._thread.join(timeout=1.0)

        # 3) Shut down the recording worker pool
        #    wait=True blocks until all queued recording tasks have completed.
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=True)
        
        print("Connector says goodbye!")


    @pyqtSlot(str)
    def set_vehicle_model(self, model_id: str):
        """
        Invoked by the UI when the user selects a blueprint ID.
        Store it under lock, persist via DataManager, and emit a signal so
        the ControlPanel can update its label and enable the spawn button.
        """
        with self._lock:
            self._vehicle_model = model_id
            # persist
            self.data.set("model", model_id)
        # UI update
        self.vehicle_model_selected.emit(model_id)


    @pyqtSlot()
    def spawn_vehicle(self):
        """
        Called by the UI thread when the user clicks “Spawn”.
        Places a simple string command into the queue for the connector thread
        to pick up and actually spawn the vehicle in context.
        """
        self._command_queue.put("spawn")    


    @pyqtSlot(str)
    def set_camera_position(self, cam_id: str):
        """
        UI-triggered slot when user picks a camera view.
        Validate cam_id, store it under lock, persist, emit signal,
        and immediately apply the new camera if in a running world.
        """
        if cam_id not in CAMERA_POSITIONS:
            return
        with self._lock:
            self._camera_selected = cam_id
        # update state
        self.data.set("camera_selected", cam_id)
        # UI update
        self.camera_position_selected.emit(cam_id)   
        # set new cam (if there is a spawned vehicle)
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
        """
        Begin a new recording session when the user clicks “Start Recording”.
        Create a fresh folder, instantiate the SGG generator if needed,
        and flip the recording flags.
        """
        # 1) Get a timestamped folder from DataManager
        folder = self.data.get_next_record_folder()
        self._record_base_folder = folder

        # 2) Instantiate the SGG class once
        if self._sgg is None:
            self._sgg = self._SGGClass(self._client)

        # 3) Update state in both DataManager and locally
        self._recording_active = True
        self.recording_status.emit(True)
    

    @pyqtSlot()
    def stop_recording(self):
        """
        End the recording session when the user clicks “Stop Recording”.
        Clears flags so no more SGG snapshots are taken.
        """
        self._recording_active = False
        self.recording_status.emit(False)
        self._record_base_folder = None


    def get_recording_status(self):
        return self._recording_active


    def _record_worker(self):
        while self._running:
            # 1) Versuche ein Task mit Timeout zu holen
            try:
                frame, ego_id, control_dict, folder = self._record_queue.get(timeout=0.5)
            except queue.Empty:
                # Keine Tasks gerade → wieder von vorn
                continue

            # 2) Jetzt haben wir ein echtes Item, also hier verarbeiten...
            try:
                self._sgg.ego_id = ego_id
                sg = self._sgg.generate_graph_for_frame(
                    frame_num=frame,
                    ego_control=control_dict,
                    render_dist=SGG_RENDER_DIST
                )
                self._sgg.save(sg, folder)
                try:
                    self.frame_recorded.emit(self._sgg.timestep)
                except Exception:
                    pass
            except Exception as e:
                print(f"Fehler beim Aufzeichnen von Frame {frame}: {e}")
            finally:
                # 3) task_done() NUR aufrufen, wenn wir wirklich ein Item hatten
                self._record_queue.task_done()


    def _run(self):
        """
        Main loop of the connector running in its own thread.
        1) Wait for the GUI to request connection
        2) Initialize connection (sync-mode, blueprints)
        3) Enter the simulation tick loop
        """
        # 1)
        self._wait_for_connect()
        # 2)
        if not self._initialize_connection():
            return 
        # 3)
        self._simulation_loop()


    def _wait_for_connect(self):
        """Block until connect() sets the event flag."""
        self._do_connect.wait()


    def _initialize_connection(self) -> bool:
        """
        Establish the CARLA client and world, enable synchronous mode,
        set up the traffic manager, load blueprints, and auto-select previous settings.
        Returns False if any step fails.
        """
        try:
            # 1) Insert the CARLA .egg file into sys.path for API + agents
            version = self.data.get("carla_version")
            # egg-Verzeichnis (enthält carla.egg ohne agents)
            egg_dir = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist"
            if egg_dir.exists():
                eggs = sorted(egg_dir.glob("carla-*.egg"))
                if eggs:
                    sys.path.insert(0, str(eggs[-1]))

            # 2) Also add the non-egg carla folder for agents
            carla_pkg = CARLA_DIR / version / "WindowsNoEditor" / "PythonAPI" / "carla"
            if carla_pkg.exists():
                sys.path.insert(0, str(carla_pkg))

            # 3) Import the CARLA module now that paths are set
            import importlib
            self.carla = importlib.import_module("carla")

            # 4) Create the client and world, apply sync settings
            host = self.data.get("host")
            port = self.data.get("port")
            version = self.data.get("carla_version")
            client = self.carla.Client(host, port)
            client.set_timeout(self.data.get("timeout", 10.0))

            world = client.get_world()

            # Sync + fixed delta
            settings = world.get_settings()
            settings.synchronous_mode    = True
            settings.fixed_delta_seconds = 0.01 #recommended from CARLA -> DO NOT INCREASE or physics become weird!
            world.apply_settings(settings)

            # 5) Configure the Traffic Manager for sync mode
            tm = client.get_trafficmanager()
            tm.set_synchronous_mode(True)

            # 6) Save client/world under lock and notify GUI success
            with self._lock:
                self._client = client
                self._world  = world
            self.connection_result.emit(True, f"Connected to {host}:{port} (version {version})")

            # 7) Load available blueprints & notify UI
            self._load_and_select_blueprints(world)

            # 8) Auto-select previously saved camera position
            self._auto_select_camera(world)

            # 9) Prepare the SGG package import 
            # If the SGG repo folder exists, insert it into sys.path so we can import it.
            if SGG_DIR.exists():
                sys.path.insert(0, str(SGG_DIR))
            # Dynamically import carla_sgg.sgg to get the SGG class
            import importlib
            sgg_mod = importlib.import_module("carla_sgg.sgg")
            self._SGGClass = sgg_mod.SGG

            # Prepare SGG abstractor functions 
            # Import the abstractor utilities that process simulation state into graphs.
            # process_to_rsv: full scene graph (Entities + Lanes + Relations)
            # EgoNotInLaneException: raised when ego-vehicle is outside any lane
            from carla_sgg.sgg_abstractor import (
                process_to_rsv,           # RSV = Entities + Lanes + Relations
                entities   as E,          # E   = Entities only
                semgraph   as EL,         # EL  = Entities + Lanes
                process_to_rsv as ER,     # ER  = Entities + Relations only
                EgoNotInLaneException
            )
            # The connector can now use these functions to build and filter graphs as needed.
            self._abstract_rsv       = process_to_rsv
            self._abstract_entities  = E
            self._abstract_semgraph  = EL
            self._abstract_er        = ER
            self._ego_not_in_lane_ex = EgoNotInLaneException
            

            return True
        except Exception as e:
            self.connection_result.emit(False, f"Connection failed: {e}")
            return False


    def _load_and_select_blueprints(self, world):
        """
        Fetch all vehicle.* blueprints from the world, store them,
        emit them to populate the UI menu, and auto-select last model if found.
        """
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
        """
        If a saved camera key exists in settings, re-apply it
        by emitting the camera_position_selected signal.
        """
        saved_cam = self.data.get("camera_selected")
        if saved_cam in CAMERA_POSITIONS:
            with self._lock:
                self._camera_selected = saved_cam
            self.camera_position_selected.emit(saved_cam)

    def _simulation_loop(self):
        """
        Core loop: while running and connected:
         - tick()
         - spawn
         - control
         - camera
         - sgg
        """
        while self._running and self._client:
            # 1) Advance the world one synchronous tick
            snapshot = self._world.tick()

            # 2) Handle any pending spawn command
            self._process_spawn()

            # 3) Read joystick and control the vehicle
            self._process_control()

            # 4) Update the spectator camera
            self._apply_camera()

            # 5) If recording, enqueue a new scene-graph snapshot when interval elapsed
            
            # DEBUG:
            #print(f"[SIM] sgg={bool(self._sgg)}, active={self._recording_active}, folder={self._record_base_folder}")

            if self._sgg and self._recording_active and self._record_base_folder:
                now = time.time()
                # Compare current time against the timestamp of the last SGG capture
                if (now - self._last_sgg_time) >= self._sgg_interval:
                    # Update the timestamp to throttle next capture
                    self._last_sgg_time = now
                    # Enqueue the minimal data (frame, ego_id, controls, folder)
                    # for async graph generation in the record worker
                    self._record_current_frame()


    def _process_spawn(self):
        """
        If a "spawn" command is in the queue and a model was selected,
        spawn exactly one vehicle at the next available map spawn point.
        """
        try:
            cmd = self._command_queue.get_nowait()
        except queue.Empty:
            return

        if cmd == "spawn" and self._vehicle_model:
            # 1) Get all spawn points for the current map
            spawn_points = self._world.get_map().get_spawn_points()
            if not spawn_points:
                return

            # 2) Choose next spawn index in a round-robin fashion
            idx = len(self._spawned_vehicles) % len(spawn_points)
            transform = spawn_points[idx]

            # 3) Find the blueprint by stored model ID
            bp = self._world.get_blueprint_library().find(self._vehicle_model)

            # 4) Spawn the actor and record it
            actor = self._world.spawn_actor(bp, transform)
            self._spawned_vehicles.append(actor)



    def _process_control(self):
        """
        Poll current joystick mappings from ControllerManager,
        translate throttle/brake/steer/reverse into a VehicleControl,
        and apply it to the most recently spawned vehicle.
        """
        # 0) If no vehicle or controller_manager, skip
        #if not (self._spawned_vehicles and self._controller_manager):
        if not (self._spawned_vehicles and hasattr(self, "_controller_manager")):
            return

        # 1) Fetch mapped control values from the joystick manager
        current_controls = self._controller_manager.get_mapped_controls()

        # 2) Handle one-shot button actions via rising-edge detection
        for func, val in current_controls.items():
            # skip unmapped or None entries
            if val is None:
                continue

            # get previous value (0.0 if first frame)
            prev = self._last_control_values.get(func, 0.0)
            # rising edge = just pressed (went from <=0.5 to >0.5)
            pressed = (val > 0.5) and (prev <= 0.5)

            # Camera “next” button pressed?
            if func == "cam_switch" and pressed:
                # cycle forward through CAMERA_POSITIONS keys
                keys = list(CAMERA_POSITIONS.keys())
                try:
                    idx = keys.index(self._camera_selected)
                except (AttributeError, ValueError):
                    idx = 0
                new_cam = keys[(idx + 1) % len(keys)]
                # persist, update internal state, and emit so UI updates
                self.data.set("camera_selected", new_cam)
                self._camera_selected = new_cam
                self.camera_position_selected.emit(new_cam)
            
            # Respawn button pressed?
            if func == "respawn" and pressed:
                self._command_queue.put("spawn")
                self._process_spawn()
                print("respawning")

            # Record toggle pressed?
            if func == "record" and pressed:
                # if already recording, stop; otherwise start
                if self._recording_active:
                    self.stop_recording()
                else:
                    self.start_recording()

            # remember theses values for next tick’s edge detection
            self._last_control_values[func] = val

            # 3) Now handle continuous driving inputs
            throttle = current_controls.get("throttle", 0.0)
            brake    = current_controls.get("brake",    0.0)
            steer    = current_controls.get("steering", 0.0)
            reverse  = (current_controls.get("reverse", 0.0) > 0.5)

            # 4) If reverse is engaged do nothing, works like this maybe needed if u want to bind brake and drive back on same axis... 
            #if reverse:
                #throttle = brake
                #brake    = 0.0

            # 5) Build and send the VehicleControl to the last spawned actor
            control = self.carla.VehicleControl(
                throttle = throttle,
                brake    = brake,
                steer    = steer,
                reverse  = reverse,
            )

            # 6) Apply to the last spawned actor
            vehicle = self._spawned_vehicles[-1]
            vehicle.apply_control(control)


    def _apply_camera(self):
        """
        Position the spectator camera relative to the last spawned vehicle
        using offsets defined in CAMERA_POSITIONS.
        """
        # 1) Only proceed if connected and at least one vehicle exists
        if not self._client or not self._spawned_vehicles:
            return

        # 2) Lookup the configuration for the current camera key (z.B. "bird", "cockpit", "free")
        cam_key = self._camera_selected
        cfg = CAMERA_POSITIONS.get(cam_key)
        # 'free' mode or invalid key
        if not cfg:
            return

        # 3) Get the vehicle’s current transform (position + rotation)
        actor = self._spawned_vehicles[-1]
        actor_tf = actor.get_transform()

        # 4) Extract local offset from the settings dict
        loc = cfg["transform"]["location"]
        rot = cfg["transform"]["rotation"]

        # 5) Compute world-space offset vectors along vehicle axes
        forward = actor_tf.get_forward_vector()
        right   = actor_tf.get_right_vector()
        up      = actor_tf.get_up_vector()

        world_offset = self.carla.Location(
            x = forward.x * loc["x"] + right.x * loc["y"] + up.x * loc["z"],
            y = forward.y * loc["x"] + right.y * loc["y"] + up.y * loc["z"],
            z = forward.z * loc["x"] + right.z * loc["y"] + up.z * loc["z"],
        )

        # 6) Add offset to vehicle position for camera location
        new_location = actor_tf.location + world_offset

        # 7) Compute camera rotation by adding local rotation offsets
        base_rot = actor_tf.rotation
        new_rotation = self.carla.Rotation(
            pitch = base_rot.pitch + rot["pitch"],
            yaw   = base_rot.yaw   + rot["yaw"],
            roll  = base_rot.roll  + rot["roll"],
        )

        # 8) Apply the new transform to the spectator camera
        new_transform = self.carla.Transform(new_location, new_rotation)
        spectator = self._world.get_spectator()
        spectator.set_transform(new_transform)


    def _record_current_frame(self):
        """
        Package up minimal data needed to record the current frame:
        (frame index, ego actor id, control state, destination folder)
        and enqueue it for the recording worker.
        """
        # Debug:
        #print(f"[RCF] spawned={len(self._spawned_vehicles)}, recording_active={self._recording_active}")

        if not self._spawned_vehicles:
            print("Kein Fahrzeugs-Actor vorhanden –> Recording übersprungen.")
            return

        latest_spawned_vehicle = self._spawned_vehicles[-1]
        frame = self._sgg.timestep                  # current SGG frame count
        ego_id = latest_spawned_vehicle.id
        ctrl = latest_spawned_vehicle.get_control() # CARLA VehicleControl state
        control_copy = {
            "throttle":        ctrl.throttle,
            "steer":           ctrl.steer,
            "brake":           ctrl.brake,
            "hand_brake":      ctrl.hand_brake,
            "reverse":         ctrl.reverse,
            "manual_gear_shift": ctrl.manual_gear_shift,
            "gear":            ctrl.gear
        }
       
        # Enqueue the tuple for the background recorder
        # Debug:
        # print(f"[RCF] putting frame={frame}, ego={ego_id}")

        self._record_queue.put((frame, ego_id, control_copy, self._record_base_folder))





