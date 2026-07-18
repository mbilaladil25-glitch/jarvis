"""
Background daemon monitors — system health, clipboard, file watcher, security, weather, telemetry.
All events flow through a shared notification queue so they never interrupt an AI reply.
"""
import threading, time, json, os, subprocess, re, queue, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime

# ── Shared event channel ────────────────────────────────────────────
_event_queue = queue.Queue()
_listeners = []
_listener_lock = threading.Lock()

def emit(event_type, data):
    _event_queue.put({"type": event_type, "data": data, "timestamp": time.time()})

def register_listener(callback):
    with _listener_lock:
        _listeners.append(callback)

def get_events(clear=True):
    events = []
    while not _event_queue.empty():
        try:
            events.append(_event_queue.get_nowait())
        except queue.Empty:
            break
    return events

def _notify_listeners():
    events = get_events()
    with _listener_lock:
        for cb in _listeners:
            try:
                cb(events)
            except:
                pass

# ── System Health Monitor ──────────────────────────────────────────
_health = {"cpu": "N/A", "ram": "N/A", "disk": [], "uptime": "N/A", "gpu": "N/A"}
_health_lock = threading.Lock()

def _poll_health():
    while True:
        try:
            info = {}
            try:
                r = subprocess.run("wmic cpu get loadpercentage", capture_output=True, text=True, timeout=5, shell=True)
                info["cpu"] = r.stdout.strip().split("\n")[-1].strip() + "%"
            except:
                info["cpu"] = "N/A"
            try:
                r = subprocess.run("wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value",
                                  capture_output=True, text=True, timeout=5, shell=True)
                free = int(re.search(r"FreePhysicalMemory=(\d+)", r.stdout).group(1))
                total = int(re.search(r"TotalVisibleMemorySize=(\d+)", r.stdout).group(1))
                info["ram"] = f"{round((total-free)/total*100,1)}%"
                info["ram_gb"] = f"{round((total-free)/1024/1024,1)}/{round(total/1024/1024,1)}"
            except:
                info["ram"] = "N/A"
            try:
                r = subprocess.run("wmic logicaldisk where DriveType=3 get DeviceID,FreeSpace,Size",
                                  capture_output=True, text=True, timeout=5, shell=True)
                disks = []
                for m in re.finditer(r"([A-Z]:)\s+(\d+)\s+(\d+)", r.stdout):
                    did, free_b, total_b = m.group(1), int(m.group(2)), int(m.group(3))
                    pct = round((total_b - free_b) / total_b * 100, 1) if total_b else 0
                    disks.append({"drive": did, "percent": pct,
                                  "free": f"{round(free_b/1e9,1)}GB",
                                  "total": f"{round(total_b/1e9,1)}GB"})
                info["disk"] = disks
            except:
                info["disk"] = []
            try:
                r = subprocess.run("wmic os get LastBootUpTime", capture_output=True, text=True, timeout=5, shell=True)
                boot = re.search(r"(\d{14})", r.stdout)
                if boot:
                    bd = datetime.strptime(boot.group(1), "%Y%m%d%H%M%S")
                    d = datetime.now() - bd
                    info["uptime"] = f"{d.days}d {d.seconds//3600}h {(d.seconds%3600)//60}m"
            except:
                info["uptime"] = "N/A"
            try:
                r = subprocess.run('wmic path win32_videocontroller get name', capture_output=True, text=True, timeout=5, shell=True)
                gpu = [l.strip() for l in r.stdout.strip().split("\n") if l.strip() and "name" not in l.lower()]
                info["gpu"] = gpu[0] if gpu else "N/A"
            except:
                info["gpu"] = "N/A"
            with _health_lock:
                _health.update(info)
            emit("health", dict(info))
        except:
            pass
        time.sleep(30)

# ── Clipboard Watcher ──────────────────────────────────────────────
_last_clip = ""

def _watch_clipboard():
    global _last_clip
    while True:
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                              capture_output=True, text=True, timeout=5)
            curr = r.stdout.strip()
            if curr and curr != _last_clip:
                _last_clip = curr
                emit("clipboard", {"text": curr[:300], "full": curr[:2000]})
        except:
            pass
        time.sleep(1)

# ── File Watcher ───────────────────────────────────────────────────
_watched_dirs = []
_file_cache = {}

def add_watch(path):
    p = Path(path)
    if p.is_dir() and path not in _watched_dirs:
        _watched_dirs.append(path)
        _file_cache[path] = {str(f): f.stat().st_mtime for f in p.iterdir() if f.is_file()}
        return True
    return False

def _watch_files():
    while True:
        for d in _watched_dirs:
            try:
                p = Path(d)
                curr = {str(f): f.stat().st_mtime for f in p.iterdir() if f.is_file()}
                prev = _file_cache.get(d, {})
                new_files = [f for f in curr if f not in prev]
                deleted = [f for f in prev if f not in curr]
                modified = [f for f in curr if f in prev and curr[f] != prev[f] and f not in new_files]
                if new_files:
                    emit("file_event", {"dir": d, "type": "new", "files": new_files})
                if deleted:
                    emit("file_event", {"dir": d, "type": "deleted", "files": deleted})
                if modified:
                    emit("file_event", {"dir": d, "type": "modified", "files": modified})
                _file_cache[d] = curr
            except:
                pass
        time.sleep(5)

# ── Security Monitor ───────────────────────────────────────────────
_last_processes = set()

def _watch_security():
    global _last_processes
    while True:
        try:
            r = subprocess.run("wmic process get Name", capture_output=True, text=True, timeout=5, shell=True)
            curr = set(l.strip().lower() for l in r.stdout.strip().split("\n") if l.strip() and "name" not in l.lower())
            if _last_processes:
                new_procs = curr - _last_processes
                suspicious = [p for p in new_procs if p in
                    ["taskmgr.exe","regedit.exe","cmd.exe","powershell.exe","procexp.exe","procmon.exe",
                     "wireshark.exe","tcpview.exe","netstat.exe","psexec.exe","mimikatz.exe"]]
                if suspicious:
                    emit("security", {"type": "process_spawned", "processes": suspicious})
            _last_processes = curr
        except:
            pass
        time.sleep(10)

# ── Weather Updater ────────────────────────────────────────────────
_weather_cache = {}
_last_weather_fetch = 0

def _update_weather():
    global _weather_cache, _last_weather_fetch
    while True:
        if time.time() - _last_weather_fetch > 600:
            try:
                with urllib.request.urlopen("https://wttr.in?format=j1", timeout=10) as r:
                    data = json.loads(r.read())
                c = data["current_condition"][0]
                area = data["nearest_area"][0]
                _weather_cache = {
                    "city": area["areaName"][0]["value"],
                    "temp": c["temp_C"],
                    "feels_like": c["FeelsLikeC"],
                    "desc": c["weatherDesc"][0]["value"],
                    "humidity": c["humidity"],
                    "wind": c["windspeedKmph"],
                    "uv": c.get("uv_index", 0),
                }
                _last_weather_fetch = time.time()
                emit("weather", dict(_weather_cache))
            except:
                pass
        time.sleep(300)

# ── Telemetry Bundle (for SSE / UI) ───────────────────────────────
def get_telemetry():
    with _health_lock:
        h = dict(_health)
    w = dict(_weather_cache)
    return {
        "health": h,
        "weather": w,
        "timestamp": time.time(),
    }

# ── Start all monitors ─────────────────────────────────────────────
_monitor_threads = []

def start_all():
    monitors = [
        ("health", _poll_health, 30),
        ("clipboard", _watch_clipboard, 1),
        ("security", _watch_security, 10),
        ("weather", _update_weather, 300),
    ]
    for name, fn, interval in monitors:
        t = threading.Thread(target=fn, daemon=True, name=f"mon_{name}")
        t.start()
        _monitor_threads.append(t)
    emit("system", {"message": "All monitors started", "monitors": [m[0] for m in monitors]})
    return _monitor_threads

# ── File watcher (separate, only if dirs added) ────────────────────
def start_file_watcher():
    t = threading.Thread(target=_watch_files, daemon=True, name="mon_filewatch")
    t.start()
    _monitor_threads.append(t)
    return t
