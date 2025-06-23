# CarlaProject need a name^^

## Project Overview

This is a data collection and scene graph generation framework for human driver behavior 
in the CARLA simulator. The goal is to record real human driving maneuvers and reconstruct detailed scene graphs, enabling:

* **Behavior Analysis**: Capture throttle, braking, steering, and camera interactions of a human operator to build a rich dataset of realistic driving patterns.
* **Scenario Recreation**: Reproduce and analyze traffic incidents (near-misses, collisions) by replaying human-driven trajectories in a controlled simulation environment.
* **Scene Graph Extraction**: Automatically generate spatial and relational graphs of scene entities (vehicles, lanes, signs) synchronized with control inputs.

## Repository Structure
Below is the top-level folder structure of this project:
Studienprojekt/
├── CARLA/
│   ├── CARLA_0.9.14/ # <- mandatory other versions optional
│   └── CARLA_0.9.15/
├── carla_scene_graphs/ # <- https://github.com/less-lab-uva/carla_scene_graphs.git 
├── hse/
│   ├── examples/
│   │   └── run.py
│   ├── control_panel.py
│   ├── carla_connector.py
│   ├── controller_manager.py
│   ├── data_manager.py
│   ├── ui_builder.py
│   └── utils/
│       ├── settings.py
│       ├── paths.py
│       └── joystick_visualizer.py
├── requirements.txt
└── README.md

## Scene Graph Generation Library
This project uses the scene graph extraction code from the less-lab-uva/carla_scene_graphs repository. We have integrated this library directly into our workflow to process simulation state into relational graphs of entities, lanes, and their interactions

## Installation

Follow these steps to set up the development environment:

### 1. Clone the Repository

```bash
# Change into your desired workspace and clone the project
git clone https://github.com/codergod1337/Studienprojekt.git
cd Studienprojekt
```

### 2. Create Conda Environment

```bash
# Create a new Conda environment named "carla" with Python 3.7
conda create -n carla python=3.7 -y
# Activate the environment
conda activate carla
```

### 3. Install Dependencies

```bash
# Install required Python packages
python -m pip install --upgrade pip setuptools wheel
# install correct pytorchversion first! ESPECIALY FOR WINDOWS-USERS
pip install torch==1.10.1+cu113 torchvision==0.11.2+cu113 --extra-index-url https://download.pytorch.org/whl/cu113
pip install -r requirements.txt


linux:
pip install pycocotools
#pycocotools==2.0.3


windowsuser extra command:
pip install pycocotools-windows
```

### 4. Set Up CARLA Simulator

1. Download and extract CARLA 0.9.14 or 0.9.15 to the `CARLA/` directory in the project root.
2. Verify that `CARLA_0.9.14/WindowsNoEditor` (or your chosen version) exists.

https://carla.readthedocs.io/en/latest/download/

## Usage/ starting

1. connect Controller Device to your PC and install it
2. start App:
```bash
python hse/examples/run.py
```
