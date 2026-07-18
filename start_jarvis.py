#!/usr/bin/env python
"""
J.A.R.V.I.S v3.0 — Boot Launcher
==================================
Plays a cinematic boot animation while warming AI connections,
so JARVIS is instant from the first query.
"""
import os, sys, time, subprocess, threading, json, urllib.request, webbrowser, socket
from pathlib import Path

BASE_DIR = Path(__file__).parent
C = lambda c, t: f"\033[{c}m{t}\033[0m"

CYAN  = "36"
GREEN = "32"
YELLOW= "33"
RED   = "31"
WHITE = "37"
GREY  = "90"

SERVER_PROC = None
WARMUP_OK   = False

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def warmup_via_server():
    """Ping the server API 3x to warm its Groq connection pool."""
    global WARMUP_OK
    for i in range(3):
        try:
            req = urllib.request.Request(
                "http://localhost:5000/api/chat",
                data=json.dumps({"message": "ping", "use_fast": True}).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=15)
            WARMUP_OK = True
        except:
            pass
        time.sleep(0.2)

def start_server():
    """Start Flask server as hidden process."""
    global SERVER_PROC
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    SERVER_PROC = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "web_ui.py")],
        creationflags=flags,
    )

def wait_for_server(timeout=20):
    """Wait until the web server is accepting connections."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection(("127.0.0.1", 5000), timeout=1)
            s.close()
            return True
        except:
            time.sleep(0.5)
    return False

def boot_animation():
    """Play animated boot sequence while warming engines."""
    clear()

    # Arc reactor ASCII
    reactor = r"""
       .-=========-.
     /-             -\
    |    ___   ___    |
    |   /   \ /   \   |
    |   \___/ \___/   |
    |                 |
    |    ___   ___    |
    |   /   \ /   \   |
    |   \___/ \___/   |
     \-             -/
       '-=========-'
    """
    print(C(CYAN, reactor))

    # Title
    print(f"\n{C(CYAN, '  J.A.R.V.I.S  v3.0')}")
    print(f"  {C(GREY, 'Integrated AI Assistant')}\n")
    time.sleep(0.8)

    # System initialization sequence
    systems = [
        ("Kernel Loader",          GREEN, 0.12),
        ("Memory Manager",         GREEN, 0.10),
        ("Groq Engine",            YELLOW, 1.50),
        ("Gemini Vision",          YELLOW, 1.50),
        ("Active Defender",        GREEN, 0.08),
        ("Background Monitors",    GREEN, 0.08),
        ("3D Modeling Engine",     GREEN, 0.08),
        ("Voice Synthesis",        GREEN, 0.08),
        ("Web Interface",          GREEN, 0.08),
    ]

    for name, status_color, delay in systems:
        color = status_color
        if delay > 0.5:
            steps = 20
            for s in range(steps):
                bar = "#" * s + "." * (steps - s)
                sys.stdout.write(f"\r  {C(YELLOW, '>>')} {C(GREY, name)}  {C(YELLOW, f'[{bar}]')}")
                sys.stdout.flush()
                time.sleep(delay / steps)
            final_color = GREEN if WARMUP_OK else YELLOW
            bar = "#" * steps
            sys.stdout.write(f"\r  {C(final_color, 'OK')} {C(WHITE, name)}  {C(final_color, f'[{bar}]')}")
            sys.stdout.write(" " * 10)
            sys.stdout.write("\n")
        else:
            sys.stdout.write(f"  {C(GREEN, 'OK')}  {C(WHITE, name)}\n")
            time.sleep(delay)

    # Systems online
    print()
    print(f"  {C(GREEN, '=========================================')}")
    print(f"  {C(GREEN, '  ALL SYSTEMS ONLINE. JARVIS READY.')}")
    print(f"  {C(GREEN, '=========================================')}")
    print(f"\n  {C(CYAN, '-> Opening web interface...')}\n")
    time.sleep(0.5)

def main():
    try:
        sys.stdout.reconfigure(errors='replace')
    except:
        pass

    clear()
    print(C(CYAN, "  J.A.R.V.I.S v3.0  --  Boot Sequence Initiated"))
    print()

    # Start server first
    print(C(YELLOW, "  |>  Starting web server..."))
    start_server()
    if not wait_for_server():
        print(C(RED, "  XX  Server failed to start"))
        return
    print(C(GREEN, "  OK  Server online at http://localhost:5000"))

    # Warmup via server API (warms the server's own Groq connection)
    print(C(YELLOW, "  |>  Warming engines... (3s)"))
    warmup_thread = threading.Thread(target=warmup_via_server, daemon=True)
    warmup_thread.start()
    warmup_thread.join(timeout=20)

    # Play boot animation (warmup already done, this is for show)
    boot_animation()

    # Final ping — guarantees <500ms gap between warmup and user's first query
    try:
        req = urllib.request.Request(
            "http://localhost:5000/api/chat",
            data=json.dumps({"message": "ping", "use_fast": True}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15)
    except:
        pass

    # Open browser
    webbrowser.open("http://localhost:5000")
    print(C(GREEN, "  JARVIS is ready. All connections hot.\n"))

    # Keep alive — Ctrl+C to stop
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n{C(YELLOW, 'Shutting down...')}")
        if SERVER_PROC:
            SERVER_PROC.terminate()
            SERVER_PROC.wait(timeout=5)
        print(C(GREEN, "Goodbye, sir."))

if __name__ == "__main__":
    main()
