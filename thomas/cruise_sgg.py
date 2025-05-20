# thomas/cruise_sgg.py

import sys
import time
import random
import torch
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from shapely.geometry import Point

# === Einstellungen ===
INTERVAL_SGG = 1.0  # Sekunden zwischen zwei Scene-Graph-Generierungen

# === Lokale Pfade einbinden ===
sys.path.append(r"C:\Users\binde\Documents\Studienprojekt\carla_scene_graphs")
sys.path.append(r"C:\Users\binde\Documents\Studienprojekt\CARLA\CARLA_0.9.14\WindowsNoEditor\PythonAPI\carla")
sys.path.append(r"C:\Users\binde\Documents\Studienprojekt\CARLA\CARLA_0.9.14\WindowsNoEditor\PythonAPI\carla\agents")

# === CARLA-Importe ===
import carla
from agents.navigation.basic_agent import BasicAgent
from carla_sgg.sgg import SGG

# === Verbindung zu CARLA ===
client = carla.Client("localhost", 2000)
client.set_timeout(20.0)
world = client.get_world()

# === Fahrzeug erstellen ===
blueprint_library = world.get_blueprint_library()
vehicle_bp = blueprint_library.filter("vehicle.tesla.model3")[0]
spawn_point = random.choice(world.get_map().get_spawn_points())
vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)

if not vehicle:
    print("❌ Fahrzeug konnte nicht gespawnt werden.")
    sys.exit(1)

print(f"🚗 Fahrzeug gespawnt: {vehicle.type_id}")

# === Agent starten ===
agent = BasicAgent(vehicle)
new_target = random.choice(world.get_map().get_spawn_points()).location
agent.set_destination(new_target)

# === Kamera folgt dem Fahrzeug ===
spectator = world.get_spectator()

def follow_vehicle():
    transform = vehicle.get_transform()
    offset_back = 8.0
    offset_up = 4.0
    forward = transform.get_forward_vector()
    camera_location = transform.location - forward * offset_back
    camera_location.z += offset_up
    rotation = carla.Rotation(
        pitch=transform.rotation.pitch,
        yaw=transform.rotation.yaw,
        roll=transform.rotation.roll
    )
    spectator.set_transform(carla.Transform(camera_location, rotation))

# === Scene Graph Generator ===
sgg = SGG(client, ego_id=vehicle.id)

# === Plot Setup ===
plt.ion()
fig, ax = plt.subplots(figsize=(12, 8))

def draw_graph_live(scene_graph):
    ax.clear()

    pos = {}
    labels = {}

    for node, data in scene_graph.nodes(data=True):
        vp = data.get("vertex_point")
        label = data.get("sem_class", "unknown")

        if isinstance(vp, Point):
            x, y = vp.x, vp.y
        elif isinstance(vp, (tuple, list, np.ndarray)) and len(vp) >= 2:
            x, y = vp[:2]
        else:
            continue

        pos[node] = (x, y)
        labels[node] = label

    nx.draw(
        scene_graph,
        pos,
        ax=ax,
        node_size=20,
        node_color="skyblue",
        with_labels=False,
        edge_color="gray",
        linewidths=0.5,
    )

    for node, (x, y) in pos.items():
        label = labels.get(node, "")
        if label != "Driving":
            ax.text(x, y + 1.0, label, fontsize=8, ha="center",
                    color="black", bbox=dict(facecolor='white', alpha=0.6, boxstyle='round,pad=0.2'))

    if "ego" in pos:
        ax.scatter(*pos["ego"], c="red", s=80, label="ego")

    ax.set_title("Scene Graph (beschriftet)")
    ax.axis("equal")
    fig.canvas.draw()
    fig.canvas.flush_events()

# === GPU-Check ===
if torch.cuda.is_available():
    print(f"✅ GPU erkannt: {torch.cuda.get_device_name(0)}")
else:
    print("⚠️ Keine GPU erkannt – PyTorch läuft auf CPU")

# === Hauptloop ===
try:
    print("🏁 Starte autonome Fahrt mit Scene Graph Visualisierung...")
    next_graph_time = time.time()

    while True:
        follow_vehicle()

        if agent.done():
            new_target = random.choice(world.get_map().get_spawn_points()).location
            print(f"🎯 Neues Ziel: {new_target}")
            agent.set_destination(new_target)

        control = agent.run_step()
        vehicle.apply_control(control)

        if time.time() >= next_graph_time:
            frame = world.get_snapshot().frame
            print(f"🧠 Generiere Scene Graph für Frame {frame}...")
            try:
                sg = sgg.generate_graph_for_frame(frame)
                draw_graph_live(sg)
            except Exception as e:
                print(f"⚠️ Fehler beim Zeichnen: {e}")
            next_graph_time += INTERVAL_SGG

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n⛔ Abbruch durch Nutzer")

finally:
    if vehicle:
        vehicle.destroy()
        print("🚗 Fahrzeug entfernt")