# --- VS Code debugging (added for QGIS plugin development) -----------------
# QGIS runs this file at start-up (<profile>/python/startup.py). When QGIS is
# started with QGIS_DEBUGPY=1 (e.g. by the plugin repository's dev/qgis-debug
# launcher), open a debugpy port so VS Code can attach ("Attach to QGIS").
# Without the variable nothing happens.
import os as _os
import sys as _sys

if _os.environ.get("QGIS_DEBUGPY") == "1":
    try:
        import debugpy as _debugpy

        # Inside QGIS, sys.executable is the QGIS binary, not Python: point debugpy at QGIS's Python.
        if _sys.platform == "win32":
            _python = _os.path.join(_sys.prefix, "python.exe")
        else:
            _python = _os.path.join(_sys.prefix, "bin", "python3")
        _debugpy.configure(python=_python)
        _port = int(_os.environ.get("QGIS_DEBUGPY_PORT", "5678"))
        _debugpy.listen(("127.0.0.1", _port))
        print(f"debugpy: listening on 127.0.0.1:{_port} - attach VS Code with 'Attach to QGIS'")
        if _os.environ.get("QGIS_DEBUGPY_WAIT") == "1":
            print("debugpy: waiting for VS Code to attach...")
            _debugpy.wait_for_client()
    except Exception as _e:  # never stop QGIS from starting
        print(f"debugpy could not start: {_e}")
# ---------------------------------------------------------------------------
