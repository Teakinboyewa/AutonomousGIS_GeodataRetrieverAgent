"""Headless check that the QGIS debug connection is in place (QGIS stays closed).

Run with QGIS's Python INSIDE the QGIS environment and unbuffered, e.g. on Windows
from a .bat that first does `call "<QGIS>\\bin\\o4w_env.bat"` and sets PATH,
QGIS_PREFIX_PATH, QT_PLUGIN_PATH and PYTHONPATH like <QGIS>\\bin\\python-qgis*.bat:

    python -u verify_debug.py --plugin-folder <PluginFolder> [--profile default] [--port 5699]

Checks:
  1. the profile's startup.py opens a debugpy port when QGIS_DEBUGPY=1
     (a spare port is used so a running debug session is not disturbed),
  2. the plugin package imports through the plugins-folder link, and from where.
A headless QgsApplication creates %APPDATA%\\python\\profiles\\default (Windows);
remove it afterwards after checking it only holds default QGIS files.
"""
import argparse
import importlib
import os
import platform
import socket
import sys
import traceback


def profile_dir(profile):
    if platform.system() == "Windows":
        return os.path.join(os.environ["APPDATA"], "QGIS", "QGIS3", "profiles", profile)
    if platform.system() == "Darwin":
        return os.path.expanduser(f"~/Library/Application Support/QGIS/QGIS3/profiles/{profile}")
    return os.path.expanduser(f"~/.local/share/QGIS/QGIS3/profiles/{profile}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-folder", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--port", type=int, default=5699)
    args = parser.parse_args()

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QGIS_DEBUGPY"] = "1"
    os.environ["QGIS_DEBUGPY_PORT"] = str(args.port)
    os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

    from qgis.core import QgsApplication
    app = QgsApplication([], True)
    app.initQgis()

    ok = True
    python_dir = os.path.join(profile_dir(args.profile), "python")
    startup = os.path.join(python_dir, "startup.py")
    try:
        with open(startup, encoding="utf-8") as fh:
            exec(compile(fh.read(), startup, "exec"), {"__name__": "__startup__"})
        s = socket.create_connection(("127.0.0.1", args.port), timeout=5)
        s.close()
        print(f"[ok] startup.py opened the debug port {args.port}")
    except Exception as e:
        ok = False
        print(f"[FAIL] debug port: {e}")

    plugins = os.path.join(python_dir, "plugins")
    link = os.path.join(plugins, args.plugin_folder)
    print(f"plugin link: {link} -> {os.path.realpath(link)}")
    sys.path.insert(0, plugins)
    try:
        module = importlib.import_module(args.plugin_folder)
        print(f"[ok] plugin package imports from {module.__file__}")
        if hasattr(module, "classFactory"):
            print("[ok] classFactory found")
        else:
            print("[warn] no classFactory in the package __init__")
    except Exception:
        ok = False
        print("[FAIL] plugin import:")
        traceback.print_exc()

    print("RESULT:", "OK" if ok else "PROBLEMS FOUND")
    sys.stdout.flush()
    os._exit(0 if ok else 1)


if __name__ == "__main__":
    main()
