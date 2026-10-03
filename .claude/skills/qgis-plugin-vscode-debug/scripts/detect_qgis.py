"""Discover everything needed to connect a QGIS plugin repository to QGIS.

Usage (any Python 3.8+; standard library only):
    python detect_qgis.py --repo <path to plugin repo> [--profile default] [--plugin-folder NAME] [--json]

Reports: QGIS installations and their Python, whether debugpy is installed there,
the profile / plugins folder, the startup.py debug block, whether QGIS is running,
the plugin folder name candidates, an existing installed copy of the plugin
(identical to the repo? files only in the installed copy?), and QGIS3.ini entries.
Nothing is changed.
"""
import argparse
import configparser
import glob
import json
import os
import platform
import subprocess
import sys

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", ".claude", "node_modules"}


def qgis_installs():
    found = []
    system = platform.system()
    if system == "Windows":
        roots = glob.glob(r"C:\Program Files\QGIS *") + glob.glob(r"C:\OSGeo4W*")
        for root in roots:
            pythons = sorted(glob.glob(os.path.join(root, "apps", "Python3*", "python.exe")))
            launchers = [p for p in glob.glob(os.path.join(root, "bin", "qgis*.bat"))
                         if os.path.basename(p).lower() in ("qgis.bat", "qgis-ltr.bat")]
            if pythons or launchers:
                found.append({"root": root, "python": pythons[-1] if pythons else None,
                              "launchers": launchers,
                              "env_bat": os.path.join(root, "bin", "o4w_env.bat")})
    elif system == "Darwin":
        for app in glob.glob("/Applications/QGIS*.app"):
            py = os.path.join(app, "Contents", "MacOS", "bin", "python3")
            found.append({"root": app, "python": py if os.path.exists(py) else None,
                          "launchers": [os.path.join(app, "Contents", "MacOS", "QGIS")]})
    else:
        qgis = shutil_which("qgis")
        if qgis:
            found.append({"root": os.path.dirname(qgis), "python": shutil_which("python3"), "launchers": [qgis]})
    for item in found:
        item["debugpy_installed"] = _has_debugpy(item.get("python"))
    return found


def shutil_which(name):
    import shutil
    return shutil.which(name)


def _has_debugpy(python):
    if not python or not os.path.exists(python):
        return None
    try:
        out = subprocess.run([python, "-c", "import debugpy, sys; print(debugpy.__version__)"],
                             capture_output=True, text=True, timeout=60)
        return out.stdout.strip() or False
    except Exception:
        return None


def profiles_root():
    system = platform.system()
    if system == "Windows":
        return os.path.join(os.environ.get("APPDATA", ""), "QGIS", "QGIS3", "profiles")
    if system == "Darwin":
        return os.path.expanduser("~/Library/Application Support/QGIS/QGIS3/profiles")
    return os.path.expanduser("~/.local/share/QGIS/QGIS3/profiles")


def qgis_running():
    try:
        if platform.system() == "Windows":
            out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=30).stdout
            names = {line.split('","')[0].strip('"') for line in out.splitlines() if line}
            return sorted(n for n in names if n.lower().startswith("qgis"))
        out = subprocess.run(["pgrep", "-l", "-i", "qgis"], capture_output=True, text=True, timeout=30).stdout
        return [line for line in out.splitlines() if line.strip()]
    except Exception as e:
        return [f"unknown ({e})"]


def is_link(path):
    if os.path.islink(path):
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction and isjunction(path):
        return True
    try:
        return os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.abspath(path))
    except OSError:
        return False


def read_metadata(repo):
    meta = os.path.join(repo, "metadata.txt")
    if not os.path.exists(meta):
        return {}
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read(meta, encoding="utf-8")
        return dict(config["general"]) if config.has_section("general") else {}
    except Exception:
        return {}


def _files(root):
    result = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(base, name)
            result[os.path.relpath(full, root).replace("\\", "/")] = full
    return result


def _same(a, b):
    try:
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read().replace(b"\r\n", b"\n") == fb.read().replace(b"\r\n", b"\n")
    except OSError:
        return False


def compare(repo, installed):
    """Compare an installed plugin copy with the repo (line endings ignored)."""
    repo_files, inst_files = _files(repo), _files(installed)
    only_installed = sorted(set(inst_files) - set(repo_files))
    only_repo = sorted(set(repo_files) - set(inst_files))
    differing = sorted(p for p in set(repo_files) & set(inst_files) if not _same(repo_files[p], inst_files[p]))
    return {"identical": not (only_installed or differing or only_repo),
            "only_in_installed": only_installed, "differing": differing, "only_in_repo_count": len(only_repo)}


def enabled_entries(profile_dir, names):
    ini = os.path.join(profile_dir, "QGIS", "QGIS3.ini")
    entries = []
    if os.path.exists(ini):
        with open(ini, encoding="utf-8", errors="replace") as fh:
            in_section = False
            for line in fh:
                line = line.strip()
                if line.startswith("["):
                    in_section = line == "[PythonPlugins]"
                elif in_section and "=" in line:
                    key = line.split("=", 1)[0]
                    if any(n and key.lower().startswith(n.lower()) for n in names):
                        entries.append(line)
    return {"file": ini, "exists": os.path.exists(ini), "matching_entries": entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--plugin-folder", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    meta = read_metadata(repo)
    profile_dir = os.path.join(profiles_root(), args.profile)
    plugins_dir = os.path.join(profile_dir, "python", "plugins")
    startup = os.path.join(profile_dir, "python", "startup.py")

    candidates = [n for n in dict.fromkeys([args.plugin_folder, os.path.basename(repo)]) if n]
    installed = []
    if os.path.isdir(plugins_dir):
        for entry in sorted(os.listdir(plugins_dir)):
            path = os.path.join(plugins_dir, entry)
            if not os.path.isdir(path):
                continue
            related = any(entry.lower().startswith(c.lower().split("-")[0][:12]) for c in candidates)
            same_name = (meta.get("name", "").strip() and
                         read_metadata(path).get("name", "").strip() == meta.get("name", "").strip())
            if related or same_name:
                info = {"folder": entry, "path": path, "is_link": is_link(path),
                        "link_target": os.path.realpath(path) if is_link(path) else None}
                if not info["is_link"]:
                    info["comparison"] = compare(repo, path)
                installed.append(info)
                if entry not in candidates and not entry.lower().endswith(("-master", "-main")):
                    candidates.append(entry)

    report = {
        "os": platform.system(),
        "qgis_installs": qgis_installs(),
        "qgis_running": qgis_running(),
        "profile_dir": profile_dir,
        "profile_exists": os.path.isdir(profile_dir),
        "plugins_dir": plugins_dir,
        "startup_py": {"path": startup, "exists": os.path.exists(startup),
                       "has_debug_block": os.path.exists(startup) and
                       "QGIS_DEBUGPY" in open(startup, encoding="utf-8", errors="replace").read()},
        "repo": repo,
        "repo_metadata": {k: meta.get(k) for k in ("name", "version", "qgisminimumversion") if k in meta},
        "plugin_folder_candidates": candidates,
        "related_installed_plugins": installed,
        "qgis3_ini": enabled_entries(profile_dir, candidates + [i["folder"] for i in installed]),
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"OS: {report['os']}")
    for q in report["qgis_installs"]:
        print(f"QGIS: {q['root']}\n  python: {q.get('python')}\n  launchers: {q.get('launchers')}"
              f"\n  debugpy: {q.get('debugpy_installed')}")
    if not report["qgis_installs"]:
        print("QGIS: not found in the usual places - ask the user where it is installed.")
    print(f"QGIS running: {report['qgis_running'] or 'no'}")
    print(f"Profile: {profile_dir} (exists: {report['profile_exists']})")
    print(f"startup.py: {startup} exists={report['startup_py']['exists']} "
          f"debug block={report['startup_py']['has_debug_block']}")
    print(f"Repo: {repo}  metadata: {report['repo_metadata']}")
    print(f"Plugin folder name candidates: {candidates}")
    for i in installed:
        line = f"Installed: {i['folder']}  link={i['is_link']}"
        if i["is_link"]:
            line += f" -> {i['link_target']}"
        else:
            c = i["comparison"]
            line += (f"  identical={c['identical']}  differing={len(c['differing'])}"
                     f"  only_in_installed={c['only_in_installed'][:20]}")
        print(line)
    ini = report["qgis3_ini"]
    print(f"QGIS3.ini: {ini['file']} exists={ini['exists']} entries={ini['matching_entries']}")


if __name__ == "__main__":
    sys.exit(main())
