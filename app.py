"""
J.A.R.V.I.S — Gradio Web UI (Hugging Face Spaces entry point)
"""
import os, sys, json, time, io, zipfile
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

import gradio as gr

# Apply HF secrets to config before importing jarvis_master
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
cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

from jarvis_master import Jarvis

jarvis = Jarvis()

DOWNLOAD_PASSWORD = "stark industries"
_rate_limit: dict[str, float] = {}


def chat_respond(message: str, history: list):
    if not message or not message.strip():
        return history, ""
    msg = message.strip()
    t0 = time.time()
    try:
        reply = jarvis.ask_ai(msg)
    except Exception as e:
        reply = f"Error: {e}"
    elapsed = time.time() - t0
    error_indicators = ("Groq error", "Gemini error", "Ollama error",
                        "Rate limited", "All engines failed", "Vision error")
    is_error = any(ind in reply for ind in error_indicators)
    if is_error:
        reply = f"**Error:** {reply}"
    else:
        reply = f"**JARVIS:** {reply}"
    history = history + [(message, f"{reply}\n\n*Responded in {elapsed:.2f}s*")]
    return history, ""


def clear_chat():
    jarvis.history = []
    jarvis.cfg["conversation_history"] = []
    from jarvis_master import save_config
    save_config(jarvis.cfg)
    return [], ""


def generate_download(password: str):
    now = time.time()
    ip = "local"
    _rate_limit.pop(ip, None)
    if ip in _rate_limit and now - _rate_limit[ip] < 10:
        remaining = int(10 - (now - _rate_limit[ip]))
        raise gr.Error(f"Too fast. Wait {remaining}s.")

    if password.strip().lower() != DOWNLOAD_PASSWORD:
        _rate_limit[ip] = now
        raise gr.Error("Incorrect password, sir.")

    _rate_limit[ip] = now
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "venv", ".venv", "node_modules")]
            for f in files:
                if f.endswith((".py", ".html", ".json", ".txt", ".bat", ".png", ".ico", ".spec", ".task")):
                    full = Path(root) / f
                    arcname = full.relative_to(BASE_DIR)
                    zf.write(full, arcname)
    buf.seek(0)
    zip_path = BASE_DIR / f"JARVIS_{time.strftime('%Y%m%d')}.zip"
    zip_path.write_bytes(buf.read())
    return str(zip_path)


system_message = (
    "# J.A.R.V.I.S\n"
    "Just A Rather Very Intelligent System — Online and ready, sir.\n\n"
    "Type your message below. I handle engineering, code, design, system control, and general queries.\n"
    "Use `/clear` to reset conversation history."
)

with gr.Blocks(
    title="J.A.R.V.I.S",
    theme=gr.themes.Soft(primary_hue="cyan", secondary_hue="blue"),
    css="""
    .chatbot {height: 65vh !important}
    #send-btn {background: #06b6d4 !important; color: white !important}
    """
) as demo:
    gr.Markdown("# J.A.R.V.I.S — AI Assistant")
    gr.Markdown("*Just A Rather Very Intelligent System*")

    with gr.Tabs():
        with gr.TabItem("Chat"):
            chatbot = gr.Chatbot(elem_classes=["chatbot"], label="J.A.R.V.I.S", height=500)
            with gr.Row():
                msg_box = gr.Textbox(
                    placeholder="Ask JARVIS anything, sir...",
                    show_label=False,
                    scale=9,
                    container=False,
                )
                send_btn = gr.Button("Send", elem_id="send-btn", scale=1)
            with gr.Row():
                clear_btn = gr.Button("Clear History", size="sm")
            gr.Markdown(system_message)

            msg_box.submit(chat_respond, [msg_box, chatbot], [chatbot, msg_box])
            send_btn.click(chat_respond, [msg_box, chatbot], [chatbot, msg_box])
            clear_btn.click(clear_chat, [], [chatbot, msg_box])

        with gr.TabItem("Download Source"):
            gr.Markdown(
                "## Download JARVIS Source Code\n"
                "Enter the password to download all source files as a ZIP archive.\n\n"
                "*Rate limited to 1 attempt per 10 seconds.*"
            )
            dl_password = gr.Textbox(
                label="Password",
                type="password",
                placeholder="Enter password...",
            )
            dl_btn = gr.Button("Generate Download", variant="primary")
            dl_file = gr.File(label="Download", visible=True)
            dl_btn.click(generate_download, inputs=[dl_password], outputs=[dl_file])

    demo.queue().launch(server_name="0.0.0.0", server_port=7860)
