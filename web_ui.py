"""
J.A.R.V.I.S Web Server — Flask backend
"""
import os, sys, json, io, base64, time, threading
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

# Load config from HF secrets if available
cfg_path = BASE_DIR / "jarvis_config.json"
if cfg_path.exists():
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
else:
    cfg = {}
if os.environ.get("GROQ_API_KEY"):
    cfg["groq_api_key"] = os.environ["GROQ_API_KEY"]
if os.environ.get("GEMINI_API_KEY"):
    cfg["gemini_api_key"] = os.environ["GEMINI_API_KEY"]
cfg["voice_enabled"] = False
cfg["hand_tracking"] = False
json.dump(cfg, open(cfg_path, "w", encoding="utf-8"))

from jarvis_master import Jarvis
from download import register_download_routes

app = Flask(__name__, static_folder=str(BASE_DIR))
CORS(app)

register_download_routes(app)

jarvis = Jarvis()
_start_time = time.time()

@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR), "web_ui.html")

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"reply": "Say something, sir."})
    if message.startswith("/"):
        if jarvis._handle_command(message):
            return jsonify({"reply": "Command dispatched."})
    reply = jarvis.ask_ai(message)
    return jsonify({"reply": reply})

@app.route("/api/voice", methods=["POST"])
def api_voice():
    return jsonify({"ok": False, "error": "Voice not available on HF Spaces"}), 501

@app.route("/api/speak", methods=["POST"])
def api_speak():
    return jsonify({"error": "Voice not available on HF Spaces"}), 501

@app.route("/api/status")
def api_status():
    import psutil
    mem = jarvis._load_memory()
    return jsonify({
        "status": "online",
        "engine": jarvis.cfg.get("active_model", "groq").upper(),
        "model": jarvis.cfg.get(f"{jarvis.cfg.get('active_model', 'groq')}_model", "?"),
        "voice_enabled": jarvis.cfg.get("voice_enabled", True),
        "custom_voice": voice_ready(),
        "transcription": "local (faster-whisper)" if not _whisper_model is None else "loading",
        "hostname": os.environ.get("COMPUTERNAME", "unknown"),
        "cpu": psutil.cpu_percent(interval=0.2),
        "memory": psutil.virtual_memory().percent,
        "facts": len(mem),
        "uptime": int(time.time() - _start_time),
    })

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "What do you see?").strip()
    result = jarvis._analyze_camera(prompt)
    return jsonify({"result": result})

@app.route("/api/screenshot", methods=["POST"])
def api_screenshot():
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "What's on the screen?").strip()
    try:
        import mss
        from PIL import Image
        import io as io_mod
        import base64
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            img = sct.grab(monitor)
            pil_img = Image.frombytes("RGB", img.size, img.rgb)
        if jarvis.gemini_client:
            buf = io_mod.BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            from google import genai
            now = __import__('datetime').datetime.now()
            sys_p = jarvis.cfg["system_prompt"].format(date=now.strftime("%A, %d %B %Y"), time=now.strftime("%I:%M %p"))
            reasoning_prompt = (
                f"{sys_p}\n\n"
                f"The user requests analysis of what is on the screen: {prompt}\n\n"
                "Think step-by-step:\n"
                "1. What application or content is visible? Identify precisely.\n"
                "2. Analyze layout, UI elements, data shown.\n"
                "3. If code or text: review for errors, optimizations, or insights.\n"
                "4. If a design or image: assess composition, colors, engineering aspects.\n"
                "5. Provide actionable feedback or next steps.\n"
                "Be thorough and critical."
            )
            resp = jarvis.gemini_client.models.generate_content(
                model=jarvis.cfg["gemini_model"],
                contents=[reasoning_prompt, genai.types.Part.from_bytes(data=buf.read(), mime_type="image/png")],
                config=genai.types.GenerateContentConfig(max_output_tokens=2048),
            )
            return jsonify({"result": resp.text.strip()})
        buf = io_mod.BytesIO()
        pil_img.save(buf, format="JPEG")
        buf.seek(0)
        import base64 as b64
        return jsonify({"result": "Screenshot captured, but Gemini vision API is unavailable.", "image": b64.b64encode(buf.read()).decode()})
    except Exception as e:
        return jsonify({"result": f"Screenshot error: {e}"})

@app.route("/api/system", methods=["POST"])
def api_system():
    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"result": "No command, sir."})
    result = jarvis._execute_system(cmd)
    if result:
        return jsonify({"result": result})
    reply = jarvis.ask_ai(cmd)
    return jsonify({"result": reply})

@app.route("/api/stream", methods=["POST"])
def api_stream():
    """Server-Sent Events streaming endpoint — yields tokens as they arrive."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "No message"}), 400
    def generate():
        try:
            for token in jarvis._ask_groq_stream(message):
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                             "Access-Control-Allow-Origin": "*"})

@app.route("/api/tools", methods=["POST"])
def api_tools():
    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"result": "No command provided, sir."})
    handled = jarvis._handle_command(cmd)
    if handled:
        return jsonify({"result": "Command dispatched.", "handled": True})
    reply = jarvis.ask_ai(cmd)
    jarvis.speak(reply)
    return jsonify({"result": reply, "handled": False})

if __name__ == "__main__":
    print(f"\n  J.A.R.V.I.S Web UI — http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
