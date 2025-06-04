# hse/carla_connector.py

import threading
import time
import carla
from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal

from hse.data_manager import DataManager


class CarlaConnector(QObject):
    """
    Läuft in eigenem Thread und wartet darauf, dass connect() ausgelöst wird.
    Erst dann liest er host, port und carla_version aus DataManager und verbindet.
    """
    connection_result = pyqtSignal(bool, str)

    def __init__(self, data_manager: DataManager):
        super().__init__()
        self.data = data_manager

        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._carla_version: Optional[str] = None
        self._client: Optional[carla.Client] = None

        self._lock = threading.Lock()
        self._do_connect = threading.Event()
        self._running = True

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def connect(self):
        """Wird aufgerufen, wenn der Benutzer den Connect-Button klickt."""
        self._do_connect.set()

    def disconnect(self):
        """Manuelle Trennung: setzt Client=None, feuert Signal."""
        with self._lock:
            self._client = None
        self.connection_result.emit(False, "Disconnected by user")

    def _run(self):
        """Hintergrundloop, reagiert auf connect()."""
        while self._running:
            if self._do_connect.is_set():
                self._do_connect.clear()

                with self._lock:
                    host = self.data.get("host")
                    port = self.data.get("port")
                    carla_version = self.data.get("carla_version")

                self._host = host
                self._port = port
                self._carla_version = carla_version

                try:
                    client = carla.Client(host, port)
                    client.set_timeout(10.0)
                    _ = client.get_world()

                    with self._lock:
                        self._client = client

                    self.connection_result.emit(True, f"Connected to {host}:{port} (version {carla_version})")
                except Exception as e:
                    self.connection_result.emit(False, f"Connection failed: {e}")

            time.sleep(0.1)

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