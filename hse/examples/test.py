import sys
from pathlib import Path
import pickle

import networkx as nx
import matplotlib.pyplot as plt

# ── Pfade konfigurieren ─────────────────────────────────────────────────────
HERE      = Path(__file__).resolve().parent        # …/hse/examples
HSE_DIR   = HERE.parents[0]                        # …/hse
PROJECT   = HSE_DIR.parents[0]                     # …/Studienprojekt

# ── carla_sgg ins sys.path packen ──────────────────────────────────────────
sys.path.insert(0, str(PROJECT / "carla_scene_graphs"))

# ── Abstraktions-Funktionen + Exception importieren ────────────────────────
from carla_sgg.sgg_abstractor import (
    process_to_rsv,    # RSV = Entities + Lanes + Relations
    entities as E,     # E   = Entities only
    semgraph as EL,    # EL  = Entities + Lanes
    process_to_rsv as ER,   # ER  = Entities + Relations only
    EgoNotInLaneException
)

# ── Custom-Unpickler, um persistent IDs zu ignorieren ───────────────────────
class SGGUnpickler(pickle.Unpickler):
    def persistent_load(self, pid):
        if pid == "please_ignore_me":
            return None
        raise pickle.UnpicklingError(f"Unhandled pid {pid!r}")

def load_scene_graph(pkl_path: Path) -> nx.Graph:
    with open(pkl_path, "rb") as f:
        return SGGUnpickler(f).load()

# ── Plot-Hilfsfunktion ────────────────────────────────────────────────────
def plot_graph(g: nx.Graph, title: str):
    plt.figure(figsize=(6,5))
    pos    = nx.spring_layout(g)
    sizes  = [g.graph.get("node_size", {}).get(n, 100) for n in g.nodes]
    colors = [g.graph.get("node_colors", {}).get(n, "gray") for n in g.nodes]
    nx.draw_networkx_nodes(g, pos, node_size=sizes, node_color=colors, alpha=0.8)
    nx.draw_networkx_edges(g, pos, alpha=0.5)
    nx.draw_networkx_labels(g, pos, font_size=7)
    plt.title(title)
    plt.axis("off")
    plt.tight_layout()
    plt.show()

# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    RECORD = PROJECT / "hse" / "data" / "record"
    pkl_files = sorted(RECORD.rglob("*.pkl"))
    if not pkl_files:
        print("Keine .pkl-Dateien gefunden.")
        sys.exit(1)

    # Suche das erste SG mit einem 'ego'-Knoten
    sg = None
    pkl_with_ego = None
    for pkl in pkl_files:
        tmp = load_scene_graph(pkl)
        if "ego" in tmp.nodes:
            sg = tmp
            pkl_with_ego = pkl
            break

    if sg is None:
        print("Kein Scene-Graph mit einem 'ego'-Knoten gefunden.")
        sys.exit(1)

    print("Verwende Scene-Graph mit Ego:", pkl_with_ego.relative_to(RECORD))

    # 1) E = Entities only
    try:
        g_e = E(sg)
        plot_graph(g_e, f"E (Entities)\n{pkl_with_ego.name}")
    except Exception as ex:
        print("E-Abstraktion fehlgeschlagen:", ex)

    # 2) EL = Entities + Lanes
    try:
        g_el = EL(sg)
        plot_graph(g_el, f"EL (Entities+Lanes)\n{pkl_with_ego.name}")
    except EgoNotInLaneException:
        print("EL übersprungen: Ego nicht in Lane.")
    except Exception as ex:
        print("EL-Abstraktion fehlgeschlagen:", ex)

    # 3) ER = Entities + Relations
    try:
        g_er = ER(sg, gen_relationships=True, gen_lanes=False)
        plot_graph(g_er, f"ER (Entities+Relations)\n{pkl_with_ego.name}")
    except EgoNotInLaneException:
        print("ER übersprungen: Ego nicht in Lane.")
    except Exception as ex:
        print("ER-Abstraktion fehlgeschlagen:", ex)

    # 4) RSV = Full RoadScene2Vec abstraction
    try:
        g_rsv = process_to_rsv(sg)
        plot_graph(g_rsv, f"RSV (Full)\n{pkl_with_ego.name}")
    except EgoNotInLaneException:
        print("RSV übersprungen: Ego nicht in Lane.")
    except Exception as ex:
        print("RSV-Abstraktion fehlgeschlagen:", ex)