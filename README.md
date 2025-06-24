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
this includes the dependencies for the SGG repo

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

### 5. installing

1. connect Controller Device to your PC and install it correctly
2. start App:
```bash
python hse/examples/run.py
```
3. in the App: click file/pull SGG
-> in the Gropbox Scene Graph Generator status is supposed to switch to SGG ready
this is only nescessary ONCE! you can click it again to update (git pull) the SGG-Repo


# User Interface (UI)
- **Purpose:**  
  Provides an intuitive front-end for the user to interact with the simulator and underlying modules without touching code.

- **Responsibilities:**  
  - **Connection panel:**  
    - Input fields for CARLA host/port/version  
    - “Connect” button that invokes `CarlaConnector.connect()`  
    - Status indicator showing “Connected” / “Disconnected”  
  - **Vehicle controls:**  
    - Dropdown to select a vehicle blueprint (populated via `blueprints_loaded` signal)  
    - “Spawn” button that calls `CarlaConnector.spawn_vehicle()`  
    - Live display of the last-spawned vehicle’s ID or type  
  - **Camera view selector:**  
    - Dropdown or radio buttons listing available views (e.g. bird’s-eye, cockpit, free)  
    - Emits `set_camera_position` when changed  
  - **Recording controls:**  
    - Toggle button for Start/Stop recording (wired to `start_recording()` / `stop_recording()`)  
    - Frame count display updated via `frame_recorded` signal  
  - **Joystick visualizer widget:**  
    - Embedded view showing axis positions and button states in real time  
    - Option to enter “rebind” mode to capture a new button or axis for a control function  
  - **menue: file/ pull SGG**  
    - pulls the Scene Graph Repo  
  - **menue: CARLA/**  
    - after connecting to Carla the vehicle modle (blueprint) can be selected  
    - the camera position can be chosen
  - **menue: controls**  
    - the JoystickVisualizer is started as a widget and can be used for Key-Binding
    - the active "Hardware-Input-Divice" can be selected
      

 

- **Behavior:**  
  - All GUI actions emit Qt signals or call slots on `CarlaConnector` and `ControllerManager`.  
  - On window close (`closeEvent`), it  cleans up all threads.  

# Functions (under the hood)
## DataManager
- **Purpose:**  
  Persists the application’s state (e.g. host, port, selected vehicle model, key bindings) in a `data/state.json` file and reloads it on startup.  
- **Responsibilities:**  
  - Load saved settings to restore the previous session.  
  - Let any other class save or retrieve arbitrary key–value pairs.

## ControllerManager
- **Purpose:**  
  Reads joystick or gamepad input continuously in a background thread (powered by `pygame.init()`).  
- **Responsibilities:**  
  - Poll hardware controls and map raw axes/buttons into named control functions (e.g. `"throttle"`, `"brake"`, `"respawn"`).  
  - Expose `get_mapped_controls()` to return only the controls you’ve explicitly bound.  
  - Provide `get_all_states()` for debugging, which dumps every axis and button value to the console.  
- **Bonus:**  
  Can run standalone in debug mode to print all joystick activity.

### JoystickVisualizer
- **Purpose:**  
  A small UI helper that shows your current control mappings in real time.  
- **Responsibilities:**  
  - Display which axis or button is mapped to which function.  
  - Let you assign or rebind controls on the fly.

## CarlaConnector
- **Purpose:**  
  Manages the connection to the CARLA simulator and drives the simulation loop in its own thread.  
- **Responsibilities:**  
  1. Dynamically import CARLA’s Python API based on your selected version in `initialize_connection()`.  
  2. Connect to the CARLA server and enable synchronous (“fixed‐tick”) mode.  
  3. Run `_run()` in the background, which kicks off `_simulation_loop()`.  
  4. Spawn vehicles on demand (processing “spawn” commands from a queue).  
  5. Fetch control inputs from `ControllerManager` and apply them to the most recently spawned vehicle.  
  6. Adjust the spectator camera based on your chosen view.  
  7. Use a thread pool for `_record_worker` tasks, allowing multiple scene‐graph (SGG) snapshots to be generated and saved in parallel.

## ControlPanel (GUI)
- **Purpose:**  
  The central user interface that ties everything together.  
- **Responsibilities:**  
  - Visualize the current state of `DataManager`, `ControllerManager`, and `CarlaConnector`.  
  - Offer buttons, dropdowns, and status indicators for connecting, spawning, recording, etc.  
  - Override `closeEvent` to orchestrate a clean shutdown of all background threads and resources.