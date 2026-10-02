# Debugging the plugin in QGIS from VS Code

QGIS runs the plugin; VS Code attaches to it, so breakpoints, stepping and
variable inspection work on the real plugin (map, layers and API calls included).

## One-time setup (Windows)

1. **Install debugpy into QGIS's Python** (adjust the QGIS version):
   ```
   "C:\Program Files\QGIS 3.44.14\apps\Python312\python.exe" -m pip install --user debugpy
   ```
2. **Add a `startup.py` to your QGIS profile** at
   `%APPDATA%\QGIS\QGIS3\profiles\default\python\startup.py`. It opens a debug
   port only when QGIS is started with `QGIS_DEBUGPY=1`:
   ```python
   import os, sys
   if os.environ.get("QGIS_DEBUGPY") == "1":
       try:
           import debugpy
           debugpy.configure(python=os.path.join(sys.prefix, "python.exe"))
           debugpy.listen(("127.0.0.1", int(os.environ.get("QGIS_DEBUGPY_PORT", "5678"))))
       except Exception as e:
           print(f"debugpy could not start: {e}")
   ```
3. **Let QGIS load the plugin from this repository** (QGIS closed), so edits here
   are what QGIS runs. In `cmd`:
   ```
   mklink /J "%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\AutonomousGIS_GeodataRetrieverAgent" "<path to this repository>"
   ```
   (Remove any other copy of the plugin in that `plugins` folder first.) Then
   enable the plugin in *Plugins > Manage and Install Plugins*.
4. **Install the "Plugin Reloader" plugin** in QGIS, to reload the plugin after
   editing without restarting QGIS.
5. In VS Code, install the **Python** and **Python Debugger** extensions.

## Everyday use

* Open this repository folder in VS Code, set breakpoints, and run
  **Start QGIS and attach** (F5). It starts QGIS through `dev\qgis-debug.bat`
  and attaches once QGIS is ready.
* If QGIS is already running in debug mode, use **Attach to QGIS** instead.
* After editing code, reload the plugin with *Plugin Reloader* (or restart QGIS).

Breakpoints work in the dock widget, the Handbook Studio, the data request
script (`LLM_Find/LLM_FIND.py`) and the code it calls. The plugin's Qt
background threads register with the debugger through `debug_support.py`.

Keys entered in the plugin are saved in the QGIS profile
(`AutonomousGIS_GeodataRetrieverAgent_data/Keys`), never in this repository.
