# 🚗 CARLA Scene Graph Cruise Demo

Dieses Projekt zeigt, wie ein autonom fahrendes Fahrzeug in CARLA 0.9.14 kontinuierlich einen **Scene Graph (SGG)** erzeugt und diesen **live visualisiert**.  
Verwendet wird das [carla_scene_graphs](https://github.com/less-lab-uva/carla_scene_graphs) Repository (SGG-Framework der University of Virginia).

---

## 🔧 Voraussetzungen

- **CARLA 0.9.14** installiert unter `D:\Studienprojekt\CARLA\CARLA_0.9.14`
- Lokales Repo: `D:\Studienprojekt\carla_scene_graphs`
- Eigener Code: `D:\Studienprojekt\thomas\cruise_sgg.py`
- Python 3.7 (z. B. `conda env --name all37`)
- GPU-fähige PyTorch-Installation (`torch.cuda.is_available()`)

## 📁 Projektstruktur

HDD:
├── Studienprojekt
│ ├── CARLA
│ │ └── CARLA_0.9.14
│ ├── carla_scene_graphs
│ └── thomas
│ └── cruise_sgg.py


evtl. https://visualstudio.microsoft.com/de/visual-cpp-build-tools/

conda create -n all37 python=3.7 -y
conda activate all37

pip install dist\carla-0.9 .whql

pip install networkx pandas matplotlib shapely pyquaternion plotly  setuptools wheel pygame numpy pyqt5 pygame
conda install pytorch=1.10.1 cudatoolkit=11.3 -c pytorch
pip install pytorch-lightning==1.2.5