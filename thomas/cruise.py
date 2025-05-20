import glob
import os
import sys
import time
import carla
import random

# ==== Verbindung zu CARLA ====
client = carla.Client('localhost', 2000)
client.set_timeout(10.0)
world = client.get_world()

# ==== Blueprint für Fahrzeug auswählen ====
blueprint_library = world.get_blueprint_library()
bp_vehicle = blueprint_library.filter('vehicle.tesla.model3')[0]  # oder anderes Modell

# ==== Spawn-Punkt wählen ====
spawn_points = world.get_map().get_spawn_points()
spawn_point = random.choice(spawn_points)

# ==== Fahrzeug spawnen ====
vehicle = world.spawn_actor(bp_vehicle, spawn_point)
print(f"🚗 Fahrzeug gespawnt: {vehicle.type_id}")

# ==== Kamera fix hinter dem Auto ====
spectator = world.get_spectator()

def follow_vehicle():
    transform = vehicle.get_transform()
    location = transform.location + transform.get_forward_vector() * -6 + carla.Location(z=3)
    rotation = transform.rotation
    spectator.set_transform(carla.Transform(location, rotation))

# ==== Route um einen Häuserblock (einfach gehalten mit Waypoints) ====
map = world.get_map()
waypoints = map.generate_waypoints(distance=5.0)

# Nimm nahegelegene Punkte in Fahrtrichtung
def get_nearby_route(vehicle, count=30):
    route = []
    start_location = vehicle.get_location()
    start_wp = map.get_waypoint(start_location, project_to_road=True, lane_type=carla.LaneType.Driving)
    current_wp = start_wp
    for _ in range(count):
        next_wps = current_wp.next(4.0)
        if next_wps:
            current_wp = random.choice(next_wps)
            route.append(current_wp.transform)
    return route

route = get_nearby_route(vehicle)

# ==== Fahrzeug fahren lassen ====
vehicle.set_autopilot(True)

# Optional: Steuere selbst mit apply_control, wenn du z. B. Kurven nachbauen willst

# ==== Kamera-Update-Loop ====
try:
    while True:
        follow_vehicle()
        time.sleep(0.05)
except KeyboardInterrupt:
    print("⛔ Beendet durch Nutzer")
finally:
    vehicle.destroy()
    print("🚗 Fahrzeug entfernt")