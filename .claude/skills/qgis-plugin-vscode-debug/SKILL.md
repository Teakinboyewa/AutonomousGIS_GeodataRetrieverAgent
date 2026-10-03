---
name: qgis-plugin-vscode-debug
description: Connect a QGIS plugin repository to a local QGIS so the plugin runs straight from the repo and can be debugged live from VS Code (breakpoints, stepping, variables) - installs debugpy into QGIS's Python, adds a guarded startup.py, links the repo into the QGIS plugins folder, enables it, and adds VS Code launch/task configs. Use when the user wants to "connect", "link", "debug", "attach VS Code to", or "run from the repo" a QGIS plugin, or asks why breakpoints in a QGIS plugin are not hit.
---

# Connect a QGIS plugin repository to QGIS for VS Code debugging

Goal: QGIS loads the plugin **directly from the repository** (via a link in the QGIS
plugins folder), opens a **debugpy** port only when started in debug mode, and VS Code
**attaches** to it. Editing in VS Code + *Plugin Reloader* in QGIS = no copying, no restart.

This skill is only about the connection. Do not refactor the plugin beyond the small
debugging hooks in step 7.

Files in this skill folder:
- `scripts/detect_qgis.py` - finds QGIS installs, its Python, profiles, plugins, whether QGIS runs,
  and compares an installed copy of the plugin with the repo. Run it first.
- `scripts/verify_debug.py` - headless check that the port opens and the plugin imports through the link.
- `templates/` - `startup_debugpy.py`, `qgis-debug.bat`, `qgis-debug.sh`, `launch.json`, `tasks.json`,
  `debug_support.py`, `dev_README.md`.

## 0. Ground rules (learned the hard way)

- **Never delete an installed copy of the plugin without checking it.** Compare it with the repo
  (`detect_qgis.py --repo ...` does this, ignoring line endings). Files only in the installed copy
  (API-key configs, `*.keys`, `*.ini`, user data) must be moved somewhere safe or the user asked first.
  Prefer renaming it to `<name>.bak-<date>` over deleting.
- **QGIS must be closed** while relinking the plugin folder or editing `QGIS3.ini`. Check the process list.
- **Ask before** the outward/destructive steps: replacing the plugin folder and editing `QGIS3.ini`
  (always make a `.bak` copy of `QGIS3.ini` first).
- On Windows, `python`/`python3` may be the Microsoft Store stub that hangs waiting for input.
  Always call QGIS's interpreter by full path (e.g. `C:\Program Files\QGIS 3.x\apps\Python3xx\python.exe`).
- Shell heredocs in Git Bash can mangle `\n`/`\u` escapes inside Python strings. Write helper scripts
  to a file with the editor tool, then run them.

## 1. Discover

Run with QGIS's Python (any Python 3 works for detection):

```
"<QGIS>\apps\Python3xx\python.exe" scripts/detect_qgis.py --repo "<path to plugin repo>"
```

It reports: QGIS installs and their `python.exe`, the default profile folder, the plugins folder,
installed plugins, whether QGIS is running, the plugin package name candidates (repo folder name,
`metadata.txt` name), and - if a plugin folder with the same name exists - whether it is identical to
the repo and which files exist only there.

Decide with the user:
- **Plugin folder name** (= QGIS plugin id and Python package name). Use the name of the plugin as
  published on the QGIS repository / already installed (e.g. `MyPlugin`), not a GitHub zip name like
  `MyPlugin-master`. It must be a valid package name for relative imports to work reliably.
- **Profile** (usually `default`).

Paths by OS:
| | Profile folder | QGIS Python |
|---|---|---|
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\<profile>` | `C:\Program Files\QGIS 3.x\apps\Python3xx\python.exe` |
| Linux | `~/.local/share/QGIS/QGIS3/profiles/<profile>` | system `python3` used by QGIS |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/<profile>` | `/Applications/QGIS.app/Contents/MacOS/bin/python3` |

## 2. Install debugpy into QGIS's Python

```
"<QGIS python>" -m pip install --user debugpy
"<QGIS python>" -c "import debugpy; print(debugpy.__version__)"
```

## 3. Add the guarded debug port to the profile's `startup.py`

QGIS runs `<profile>/python/startup.py` at start-up. Append the block from
`templates/startup_debugpy.py` (create the file if missing; if it exists, append - never overwrite
the user's code). It only listens when the environment variable `QGIS_DEBUGPY=1` is set, so normal
QGIS starts are unaffected.

Key detail: inside QGIS, `sys.executable` is the QGIS binary, not Python, so the block calls
`debugpy.configure(python=os.path.join(sys.prefix, "python.exe"))` on Windows
(`sys.prefix/bin/python3` elsewhere). Without it debugpy cannot start its adapter.

## 4. Link the repository into the plugins folder (QGIS closed!)

```
# Windows (junction, no admin rights needed)
mklink /J "<profile>\python\plugins\<PluginFolder>" "<repo>"
# PowerShell equivalent
New-Item -ItemType Junction -Path "<profile>\python\plugins\<PluginFolder>" -Target "<repo>"
# Linux / macOS
ln -s "<repo>" "<profile>/python/plugins/<PluginFolder>"
```

Before linking, handle any existing folder of that name (and stray copies such as `<PluginFolder>-master`)
as described in step 0. Verify afterwards that `<link>\metadata.txt` resolves.

## 5. Enable the plugin under its folder name

QGIS stores enabled plugins in `<profile>/QGIS/QGIS3.ini`, section `[PythonPlugins]`,
as `<PluginFolder>=true`. If the user previously ran it under another folder name
(e.g. `<PluginFolder>-master=true`), rename that entry. Back up the file first, edit as bytes so the
encoding/line endings are kept, and assert exactly one match. (Alternatively tell the user to tick the
plugin in *Plugins > Manage and Install Plugins*.)

## 6. Launcher and VS Code configuration

Copy into the repo and fill the placeholders:
- `templates/qgis-debug.bat` -> `dev/qgis-debug.bat` (Windows) / `templates/qgis-debug.sh` -> `dev/qgis-debug.sh`.
  It sets `QGIS_DEBUGPY=1` (+ `PYDEVD_DISABLE_FILE_VALIDATION=1` to silence the harmless
  "frozen modules" warning), finds QGIS, starts it, and waits until the port accepts connections.
- `templates/launch.json` and `templates/tasks.json` -> `.vscode/`.
  Replace `__PLUGIN_FOLDER__` with the plugin folder name. `pathMappings` maps the repo
  (`localRoot`) to the linked path QGIS reports (`remoteRoot`); it is required because QGIS sees the
  files under the plugins folder, not under the repo path.
- If the user's VS Code workspace is a **parent folder** of the repo, also add the configs to the
  workspace's `.vscode/` with `localRoot` = `${workspaceFolder}/<relative path to repo>` and the task
  command pointing at `<relative path>/dev/qgis-debug.bat`.
- `templates/dev_README.md` -> `dev/README.md` (one-time setup + everyday use, for collaborators).

## 7. Small plugin hooks so every breakpoint works

Search the plugin and apply only what is needed:

1. **Qt threads** - debugpy only traces threads started via `threading`. For each `QThread`
   subclass whose `run()` executes plugin code (`grep -n "class .*(QThread)"`), add
   `debug_this_thread()` as the first line of `run()`, importing it from a copy of
   `templates/debug_support.py` (it is a no-op unless debugpy is loaded).
2. **Code run with `exec()` from a file** - `exec(source, ...)` has no file name, so breakpoints in
   that file never bind. Use `exec(compile(source, script_path, "exec"), ...)`.
3. **Modules imported by bare name from a sub-folder added to `sys.path`** (e.g. `import helper`) -
   after a reload QGIS can keep a stale module of that name, or another plugin's module. If you see
   "module has no attribute" after reloading, load them from the plugin's own folder explicitly
   (check `module.__file__`, drop it from `sys.modules` and re-import if it is not the plugin's).
4. **Secrets** - the plugin now runs from the repository. Find where it *writes* files
   (`grep -n "open(.*'w'\|\.write(" `): API-key configs, `.keys`, tokens, caches written into the plugin
   folder would now land in the git working tree. Make sure they are git-ignored, or better, write them
   to the user's profile (`QgsApplication.qgisSettingsDirPath()`) instead. Never commit real keys.

## 8. Verify (headless, without opening QGIS)

Run `scripts/verify_debug.py` with QGIS's Python *inside the QGIS environment*
(Windows: create a small .bat that `call`s `<QGIS>\bin\o4w_env.bat`, sets
`PATH=%OSGEO4W_ROOT%\apps\qgis-ltr\bin;%PATH%` (or `apps\qgis`), `QGIS_PREFIX_PATH`, `QT_PLUGIN_PATH`,
`PYTHONPATH=%OSGEO4W_ROOT%\apps\qgis(-ltr)\python`, then runs python **with `-u`** - the script ends
with `os._exit`, which drops buffered output otherwise). It:
- runs the profile `startup.py` with a spare port and checks the port opens,
- imports the plugin package through the plugins folder link and reports its `__file__`.

Note: a headless `QgsApplication` without a profile creates `%APPDATA%\python\profiles\default`.
Remove that folder afterwards (only after checking it contains just the default QGIS files).

Do not claim breakpoints work until the user has attached once; the headless check only proves the
port and the link.

## 9. Hand-over to the user

Tell the user, briefly:
1. Install the VS Code extensions **Python** and **Python Debugger** (Microsoft).
2. Close QGIS, then run **"Start QGIS and attach"** (F5). QGIS opens; VS Code attaches when ready.
   If QGIS is already running in debug mode, use **"Attach to QGIS"**.
3. First time in QGIS: check the plugin is enabled; install **Plugin Reloader** and point it at
   `<PluginFolder>`; re-enter any settings that lived in the old installed copy.
4. Set a breakpoint, use the plugin, VS Code stops there. After edits, reload with Plugin Reloader.
5. To test the published version instead, use a separate QGIS profile, or remove the link.

Mention anything that was backed up (old plugin folder, `QGIS3.ini.bak-...`).
