"""
Password-protected file download endpoint for JARVIS.
Access: POST /api/download with {"password": "stark industries"}
Returns a ZIP of all JARVIS source files.
"""
import os, io, zipfile, time
from pathlib import Path
from flask import request, jsonify, send_file

BASE = Path(__file__).parent
PASSWORD = "stark industries"
_RATE_LIMIT = {}

def cleanup_rate():
    now = time.time()
    for ip in list(_RATE_LIMIT.keys()):
        if now - _RATE_LIMIT[ip] > 60:
            del _RATE_LIMIT[ip]

def register_download_routes(app):
    @app.route("/api/download", methods=["POST"])
    def api_download():
        ip = request.remote_addr
        now = time.time()
        cleanup_rate()

        # Rate limit: 1 attempt per 10 seconds
        if ip in _RATE_LIMIT and now - _RATE_LIMIT[ip] < 10:
            return jsonify({"error": "Too fast. Wait 10s."}), 429

        data = request.get_json(silent=True) or {}
        pw = data.get("password", "").strip().lower()

        if pw != PASSWORD:
            _RATE_LIMIT[ip] = now
            return jsonify({"error": "Incorrect password."}), 403

        # Build ZIP in memory
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(BASE):
                # Skip git, pycache, venv
                dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "venv", ".venv", "node_modules")]
                for f in files:
                    if f.endswith((".py", ".html", ".json", ".txt", ".bat", ".png", ".ico", ".spec", ".task")):
                        full = Path(root) / f
                        arcname = full.relative_to(BASE)
                        zf.write(full, arcname)

        buf.seek(0)
        _RATE_LIMIT[ip] = now
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"JARVIS_{time.strftime('%Y%m%d')}.zip"
        )
