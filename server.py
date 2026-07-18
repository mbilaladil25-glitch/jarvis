#!/usr/bin/env python
"""
JARVIS Server — Deploy anywhere in the world.
Run: python server.py
Optional: python server.py --port 8080
"""
import os, sys, json, threading, subprocess, signal, webbrowser, time
from pathlib import Path

BASE = Path(__file__).parent

def check_deps():
    missing = []
    for mod in ["flask", "flask_cors", "gunicorn", "pyngrok"]:
        try:
            __import__(mod.replace("-","_"))
        except:
            missing.append(mod)
    if missing:
        print(f"Install: pip install {' '.join(missing)}")
        sys.exit(1)

def start_via_gunicorn(port):
    """Production-ready with gunicorn (Linux/Mac) or waitress (Windows fallback)."""
    if sys.platform == "win32":
        # Windows: use Flask dev with threading (gunicorn doesn't work on Windows)
        from web_ui import app
        print(f" * Running on http://0.0.0.0:{port}")
        app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
    else:
        os.execvp("gunicorn", [
            "gunicorn", "web_ui:app",
            "--bind", f"0.0.0.0:{port}",
            "--workers", "2",
            "--threads", "4",
            "--worker-class", "gthread",
            "--timeout", "120",
            "--keep-alive", "60",
            "--access-logfile", "-",
        ])

def start_with_ngrok(port):
    """Expose via ngrok tunnel so anyone overseas can access."""
    from pyngrok import ngrok, conf
    conf.get_default().monitor_thread = False
    tunnel = ngrok.connect(port, "http")
    public_url = tunnel.public_url
    print(f"\n  🌍 Public URL: {public_url}")
    print(f"  🔑 Anyone with this URL can access JARVIS.\n")
    webbrowser.open(public_url)
    return tunnel

def main():
    check_deps()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

    # Kill old
    if sys.platform == "win32":
        subprocess.run(f"for /f \"tokens=5\" %a in ('netstat -ano ^| findstr :{port}') do taskkill /f /pid %a",
                       shell=True, capture_output=True)

    # Start gunicorn/flask in background thread
    srv_thread = threading.Thread(target=start_via_gunicorn, args=(port,), daemon=True)
    srv_thread.start()
    time.sleep(3)

    # Expose via ngrok
    tunnel = start_with_ngrok(port)

    print("  JARVIS Server running. Press Ctrl+C to stop.\n")

    def cleanup(*_):
        print("\nShutting down...")
        try:
            ngrok.kill()
        except:
            pass
        os._exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()

if __name__ == "__main__":
    main()
