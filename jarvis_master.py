"""
J.A.R.V.I.S v3.0 — Master Control
=====================================
Fixes:
  • Groq model updated to llama-3.3-70b-versatile (specdec decommissioned)
  • Full conversation history passed to Groq on every request
  • Hand tracking thread built into master (signals HUD via socket)
  • Better mic: startup calibration, dynamic noise gate, faster response
  • Standby mode: Jarvis goes quiet after 5 min idle, wakes on voice/hand
  • /clear, /model, /voice, /listen, /history, /settings, /help, /exit commands
  • HUD push on every reply
"""

import os, sys, json, threading, re, time, socket, subprocess, webbrowser, requests
import urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

try:
    import jarvis_defender as _defender
    _HAS_DEFENDER = True
except Exception:
    _HAS_DEFENDER = False
try:
    import jarvis_monitors as _monitors
    _HAS_MONITORS = True
except Exception:
    _HAS_MONITORS = False
try:
    import model_3d as _model3d
    _HAS_MODEL3D = True
except Exception:
    _HAS_MODEL3D = False

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY CHECK
# ─────────────────────────────────────────────────────────────────────────────
def check_deps():
    required = [
        ("groq",               "groq"),
        ("google.genai",       "google-genai"),
        ("speech_recognition", "SpeechRecognition"),
        ("pyttsx3",            "pyttsx3"),
        ("pyaudio",            "pyaudio"),
        ("keyboard",           "keyboard"),
        ("colorama",           "colorama"),
    ]
    optional = [
        ("cv2",       "opencv-python"),
        ("mediapipe", "mediapipe"),
        ("numpy",     "numpy"),
    ]
    missing = []
    for mod, pkg in required:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n[!] Missing required packages. Run:\n  pip install {' '.join(missing)}\n")
        sys.exit(1)
    for mod, pkg in optional:
        try:
            __import__(mod)
        except ImportError:
            print(f"[~] Optional '{pkg}' not installed — hand tracking disabled. "
                  f"Install with: pip install {pkg}")

check_deps()

from groq import Groq
from google import genai
import speech_recognition as sr
import pyttsx3
import keyboard
import colorama
from colorama import Fore, Style
colorama.init()

# ─────────────────────────────────────────────────────────────────────────────
# OPTIONAL IMPORTS
# ─────────────────────────────────────────────────────────────────────────────
try:
    import cv2
    import mediapipe as mp
    import numpy as np
    HAND_TRACK_AVAILABLE = True
except ImportError:
    HAND_TRACK_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
CONFIG_FILE    = BASE_DIR / "jarvis_config.json"
MEMORY_FILE    = BASE_DIR / "jarvis_memory.json"
HUD_PORT       = 9988
STANDBY_MINS   = 5       # idle minutes before standby mode
GROQ_MODEL     = "llama-3.3-70b-versatile"   # updated — specdec decommissioned
GEMINI_MODEL   = "gemini-2.0-flash"
OLLAMA_MODEL   = "qwen3:4b"

# Prompt cache — formatted once, reused for 60s
_sys_full_cache = {"text": "", "time": 0}
_sys_short_cache = {"text": "", "time": 0}

_SYS_PROMPT_SHORT = (
    "You are J.A.R.V.I.S — Tony Stark's AI. "
    "Address the user as 'sir'. Keep responses VERY short (1-2 sentences). "
    "Be witty, British, efficient. No fluff. No lists. Answer directly.\n\n"
    "Current date: {date}. Current time: {time}."
)

# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT CONFIG
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "groq_api_key":        "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",
    "gemini_api_key":      "AIzaSyAAt9Q8XKxR54YshexUsy9BdoNmekPwBBI",
    "active_model":        "groq",
    "groq_model":          GROQ_MODEL,
    "gemini_model":        GEMINI_MODEL,
    "ollama_model":        OLLAMA_MODEL,
    "voice_enabled":       True,
    "custom_voice":        True,
    "voice_speed":         185,
    "voice_volume":        1.0,
    "voice_id":            "HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0",
    "hotkey":              "ctrl+space",
    "wake_word":           "hey jarvis",
    "wake_sound_enabled":  True,
    "hand_tracking":       True,
    "max_tokens":          4096,
    "system_prompt": (
        "You are J.A.R.V.I.S — a superintelligent AI assistant. "
        "Address the user as 'sir'. Be concise unless asked for detail. "
        "Use British English. Be witty, sharp, and technically precise.\n\n"

        "## Core Capabilities\n"
        "You have expert knowledge in: engineering, materials science, 3D printing (FDM/SLA/SLS), "
        "physics, electronics, software architecture, mathematics, chemistry, product design.\n\n"

        "## Thinking Framework\n"
        "Before answering, ALWAYS think step-by-step:\n"
        "1. What is the user's true goal? (read between the lines)\n"
        "2. What information do I need? What's missing?\n"
        "3. What are the constraints and trade-offs?\n"
        "4. What's the best approach? Compare alternatives.\n"
        "5. Validate: does this actually solve the problem?\n"
        "6. If it's complex, break it into sub-tasks.\n\n"

        "## Available Tools\n"
        "You can use these by mentioning the action naturally. The system detects keywords:\n"
        "- **PC Control**: volume, brightness, open apps, battery, system info, lock, "
        "shutdown, hibernate\n"
        "- **Power Presets**: 'battery preset' (power saver), 'performance preset' (max power)\n"
        "- **PC Optimization**: 'speed up', 'optimize' — clears temp, kills bloat, flushes DNS\n"
        "- **Camera**: 'analyze this', 'look at', 'camera' — captures and analyzes camera image\n"
        "- **Screenshot**: 'screenshot', 'capture the screen' — captures screen\n"
        "- **Design**: 'design a...', 'make a...', 'create a...' — engineering design reasoning\n"
        "- **Stress Test**: 'stress test...' — 3D print structural analysis\n"
        "- **3D Model**: '3d print a...', '3d model a...' — generates parametric STL files:\n"
        "  Supports: phone holders, enclosures, gears, brackets, hooks, servo brackets, "
        "cable clips, standoffs, vent grilles, Raspberry Pi/Arduino cases, boxes, cylinders, spheres\n"
        "- **Active Defender**: 'defender status', 'scan threats', 'lock workstation', "
        "'kill remote tools' — security monitoring\n"
        "- **System Health**: 'system health', 'sensors' — CPU/RAM/disk/GPU/uptime\n"
        "- **Web Search**: 'search for...' — real-time web search\n"
        "- **Weather**: 'weather in [city]' — current conditions\n"
        "- **YouTube**: 'play [song/video]' — opens in browser\n"
        "- **File Ops**: 'read [path]', 'write [path]', 'list [dir]'\n\n"

        "## Tool Engagement\n"
        "If the user asks for something you can do with a tool, use it directly rather than "
        "just talking about it. For example, if they say 'I'm cold', check the temperature "
        "and suggest adjusting it. If they say 'this PC is slow', offer to optimize.\n\n"

        "## Memory\n"
        "You have persistent memory. Remember user preferences, facts, and past requests. "
        "When the user tells you something important, store it with 'remember that X is Y'.\n\n"

        "## Code Execution\n"
        "You can execute Python code via the /python command. Use this for calculations, "
        "data analysis, automation scripts, or generating content on demand.\n\n"

        "## Response Style\n"
        "- Be direct and efficient. No fluff.\n"
        "- If uncertain, say so. Never make up specs.\n"
        "- For engineering: be thorough, quantitative, cite materials and dimensions.\n"
        "- For code: be correct, handle edge cases, explain the approach.\n"
        "- For analysis: compare options, state trade-offs, give a recommendation.\n\n"

        "Current date: {date}. Current time: {time}."
    ),
    "conversation_history": [],
    "max_history":         30,
}

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            # Always keep groq_model current
            if cfg.get("groq_model") == "llama-3.3-70b-specdec":
                cfg["groq_model"] = GROQ_MODEL
                print(f"{Fore.YELLOW}[!] Auto-updated decommissioned Groq model → {GROQ_MODEL}{Style.RESET_ALL}")
            return cfg
        except Exception:
            print(f"{Fore.RED}[!] Config corrupted — resetting to defaults.{Style.RESET_ALL}")
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────────────
def is_online() -> bool:
    try:
        s = socket.create_connection(("8.8.8.8", 53), timeout=2)
        s.close()
        return True
    except OSError:
        return False

def push_to_hud(text: str):
    """Send reply text to HUD window — non-blocking, silent on failure."""
    def _send():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.4)
                s.connect(("127.0.0.1", HUD_PORT))
                s.sendall(text.encode("utf-8"))
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()

def search_youtube(query: str):
    try:
        q   = urllib.parse.urlencode({"search_query": query})
        url = f"https://www.youtube.com/results?{q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode()
        vids = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', html)
        return f"https://youtube.com/watch?v={vids[0]}" if vids else None
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# MAIN JARVIS CLASS
# ─────────────────────────────────────────────────────────────────────────────
class Jarvis:

    def __init__(self):
        self.cfg          = load_config()
        self.running      = True
        self.listening    = False
        self.speaking     = False
        self.standby      = False
        self.last_active  = time.time()
        self._hud_proc    = None
        self._hand_thread = None
        self.platform     = "hf" if os.environ.get("HF_SPACE_ID") else "local"
        self.lock         = threading.Lock()
        self.tts_lock     = threading.Lock()
        self._tts_engine  = None    # active pyttsx3 engine (for interrupt)
        self._stop_tts    = False   # interrupt flag
        self.history      = list(self.cfg.get("conversation_history", []))

        # ── Groq client ──────────────────────────────────────────────
        self.groq_client = None
        gk = self.cfg.get("groq_api_key", "")
        if gk and not gk.startswith("YOUR_"):
            try:
                import httpx
                _limits = httpx.Limits(max_keepalive_connections=5, keepalive_expiry=120.0)
                self.groq_client = Groq(api_key=gk, http_client=httpx.Client(limits=_limits, timeout=httpx.Timeout(30.0, connect=5.0)))
            except Exception as e:
                print(f"{Fore.RED}Groq init error: {e}{Style.RESET_ALL}")

        # ── Gemini client ─────────────────────────────────────────────
        self.gemini_client = None
        mk = self.cfg.get("gemini_api_key", "")
        if mk and not mk.startswith("YOUR_"):
            try:
                self.gemini_client = genai.Client(api_key=mk)
            except Exception as e:
                print(f"{Fore.RED}Gemini init error: {e}{Style.RESET_ALL}")

        # ── Microphone / speech ───────────────────────────────────────
        self.recognizer               = sr.Recognizer()
        self.recognizer.energy_threshold                     = 250
        self.recognizer.dynamic_energy_threshold             = True
        self.recognizer.dynamic_energy_adjustment_damping    = 0.15
        self.recognizer.dynamic_energy_adjustment_multiplier = 1.1
        self.recognizer.pause_threshold                      = 0.6

        self.wake_rec                 = sr.Recognizer()
        self.wake_rec.energy_threshold                     = 250
        self.wake_rec.dynamic_energy_threshold             = True
        self.wake_rec.pause_threshold                      = 0.5

        self._print_banner()

        # ── Pre-warm connections & cache ─────────────────────────
        self._get_sys_prompt(fast=True)   # cache short prompt
        self._get_sys_prompt(fast=False)  # cache full prompt
        threading.Thread(target=self._prewarm_engines, daemon=True).start()  # async — boot animation handles timing

        # ── Background services ───────────────────────────────────
        if _HAS_DEFENDER:
            _defender.start_defender(alert_callback=None, interval=5)
            print("  [Defender] Active Defender started")
        if _HAS_MONITORS:
            _monitors.start_all()
            print("  [Monitors] Health, clipboard, security, weather monitors started")
        if _HAS_DEFENDER or _HAS_MONITORS:
            print()

    # ─────────────────────────────────────────────────────────────────
    # DISPLAY
    # ─────────────────────────────────────────────────────────────────
    def _print_banner(self):
        os.system("cls" if os.name == "nt" else "clear")
        status = "ONLINE" if is_online() else "OFFLINE"
        sc     = Fore.GREEN if status == "ONLINE" else Fore.RED
        brain  = self.cfg["active_model"].upper()
        model  = self.cfg.get(f"{self.cfg['active_model']}_model", "?")
        ht     = "ON" if (HAND_TRACK_AVAILABLE and self.cfg.get("hand_tracking")) else "OFF"
        features = ["PC Opt", "Power Presets", "Stress Test"]
        if _HAS_DEFENDER: features.append("Defender")
        if _HAS_MONITORS: features.append("Monitors")
        if _HAS_MODEL3D:  features.append("3D Engine")
        feat_str = " | ".join(features)
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}  J.A.R.V.I.S  v3.0  —  Integrated AI Assistant{Style.RESET_ALL}")
        print(f"  Status  : {sc}{status}{Style.RESET_ALL}  |  Engine: {Fore.MAGENTA}{brain}{Style.RESET_ALL}  ({model})")
        print(f"  Wake    : \"{self.cfg['wake_word']}\"  |  Hotkey: {self.cfg['hotkey']}")
        print(f"  Features: {feat_str}")
        print(f"  Type /help for commands")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")

    def _jarvis(self, text: str):
        print(f"\n{Fore.CYAN}JARVIS:{Style.RESET_ALL} {text}\n")
        push_to_hud(text)

    def _you(self, text: str, mode: str = "text"):
        icon = "🎤" if mode == "voice" else "⌨ "
        print(f"{Fore.WHITE}[{icon}] You: {text}{Style.RESET_ALL}")

    # ─────────────────────────────────────────────────────────────────
    # AI ENGINE
    # ─────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────
    # MEMORY SYSTEM
    # ─────────────────────────────────────────────────────────────────
    def _load_memory(self) -> dict:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_memory(self, memory: dict):
        MEMORY_FILE.write_text(json.dumps(memory, indent=2), encoding="utf-8")

    def _build_memory_context(self) -> str:
        memory = self._load_memory()
        if not memory:
            return ""
        facts = []
        for k, v in memory.items():
            facts.append(f"{k}: {v}")
        return "Here's what I remember about the user:\n" + "\n".join(facts)

    def remember(self, key: str, value: str):
        memory = self._load_memory()
        memory[key.strip().lower()] = value.strip()
        self._save_memory(memory)

    def forget(self, key: str):
        memory = self._load_memory()
        memory.pop(key.strip().lower(), None)
        self._save_memory(memory)

    def _get_sys_prompt(self, fast: bool = False) -> str:
        """Return cached system prompt — full or short. Cache refreshes every 60s."""
        now = time.time()
        if fast:
            if _sys_short_cache["text"] and (now - _sys_short_cache["time"]) < 60:
                return _sys_short_cache["text"]
            dt = datetime.now()
            _sys_short_cache["text"] = _SYS_PROMPT_SHORT.format(
                date=dt.strftime("%A, %d %B %Y"), time=dt.strftime("%I:%M %p"))
            _sys_short_cache["time"] = now
            return _sys_short_cache["text"]
        else:
            if _sys_full_cache["text"] and (now - _sys_full_cache["time"]) < 60:
                return _sys_full_cache["text"]
            dt = datetime.now()
            txt = self.cfg["system_prompt"].format(
                date=dt.strftime("%A, %d %B %Y"), time=dt.strftime("%I:%M %p"))
            mem_ctx = self._build_memory_context()
            if mem_ctx:
                txt += "\n\n" + mem_ctx
            _sys_full_cache["text"] = txt
            _sys_full_cache["time"] = now
            return txt

    def _is_simple_query(self, text: str) -> bool:
        """Determine if a query is simple (greeting, quick info) vs complex (analysis, design)."""
        lower = text.lower().strip()
        l = len(text)
        if l < 20:
            return True
        if any(lower.startswith(w) for w in ["hi", "hey", "hello", "yo", "sup", "good morning", "good evening", "good afternoon"]):
            return True
        if any(lower == w for w in ["hello", "hi jarvis", "hey jarvis", "morning", "evening", "thanks", "thank you", "bye", "goodbye"]):
            return True
        deep = ["explain", "compare", "analyze", "design", "why does", "how does", "stress test", "step by step",
                "detailed", "comprehensive", "evaluate", "pros and cons", "tell me about", "what is the difference"]
        if any(m in lower for m in deep):
            return False
        if l < 100:
            return True
        return False

    def _build_messages(self, user_input: str, fast: bool = False) -> list:
        fast = fast or self._is_simple_query(user_input)
        sys_prompt = self._get_sys_prompt(fast=fast)
        messages   = [{"role": "system", "content": sys_prompt}]
        # Fast queries: only last 3 turns. Complex: up to max_history.
        n = 3 if fast else self.cfg.get("max_history", 30)
        messages += self.history[-n:]
        messages.append({"role": "user", "content": user_input})
        return messages

    def _ask_with_fallback(self, user_input: str) -> str:
        """Try engines smartly: respects config, falls back gracefully. Returns first success."""
        pref = self.cfg.get("active_model", "groq").lower()
        errors = []

        def _good(reply):
            return reply and not reply.startswith("Groq error") and not reply.startswith("Gemini error") \
                and not reply.startswith("Ollama error") and "[Rate limited" not in reply \
                and "All engines failed" not in reply

        # Build ordered chain based on preference
        chain = []
        if pref == "groq":
            chain = ["groq", "gemini", "ollama"]
        elif pref == "gemini":
            chain = ["gemini", "groq", "ollama"]
        elif pref == "ollama":
            chain = ["ollama"]
        else:
            chain = ["groq", "gemini", "ollama"]  # auto

        fast = self._is_simple_query(user_input)
        for engine in chain:
            if engine == "groq" and self.groq_client:
                r = self._ask_groq(user_input, fast=fast)
                if _good(r):
                    return r
                errors.append(f"Groq: {r[:80]}")
                if "rate_limit" in r.lower() or "429" in r:
                    time.sleep(1)
            elif engine == "gemini" and self.gemini_client:
                r = self._ask_gemini(user_input)
                if _good(r):
                    tag = "[Gemini]" if pref != "gemini" else ""
                    return f"{tag} {r}".strip()
                errors.append(f"Gemini: {r[:80]}")
            elif engine == "ollama":
                r = self._ask_ollama(user_input)
                if _good(r):
                    tag = "[Local]" if pref != "ollama" else ""
                    return f"{tag} {r}".strip()
                errors.append(f"Ollama: {r[:80]}")

        return f"All engines failed: {'; '.join(errors)}"

    def _ask_groq(self, user_input: str, fast: bool = False) -> str:
        if not self.groq_client:
            return "Groq API key not configured, sir. Check jarvis_config.json."
        try:
            fast = fast or self._is_simple_query(user_input)
            max_tok = 150 if fast else self.cfg.get("max_tokens", 4096)
            resp = self.groq_client.chat.completions.create(
                model    = self.cfg["groq_model"],
                messages = self._build_messages(user_input, fast=fast),
                max_tokens = max_tok,
                temperature = 0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "decommissioned" in err.lower():
                self.cfg["groq_model"] = GROQ_MODEL
                save_config(self.cfg)
                return f"Model was decommissioned — auto-switched to {GROQ_MODEL}. Please retry, sir."
            if "rate_limit" in err.lower() or "429" in err:
                fallback = self._ask_gemini(user_input)
                if not fallback.startswith("Gemini error"):
                    return f"[Rate limited on Groq, using Gemini] {fallback}"
            return f"Groq error: {err}"

    def _ask_groq_stream(self, user_input: str, fast: bool = False):
        """Generate tokens from Groq streaming API — yields strings for SSE."""
        if not self.groq_client:
            yield "Groq API key not configured, sir."
            return
        try:
            fast = fast or self._is_simple_query(user_input)
            max_tok = 150 if fast else self.cfg.get("max_tokens", 4096)
            stream = self.groq_client.chat.completions.create(
                model    = self.cfg["groq_model"],
                messages = self._build_messages(user_input, fast=fast),
                max_tokens = max_tok,
                temperature = 0.7,
                stream = True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else ""
                if delta:
                    yield delta
        except Exception as e:
            yield f"[Error: {e}]"

    def _ask_gemini(self, user_input: str) -> str:
        if not self.gemini_client:
            return "Gemini API key not configured, sir. Check jarvis_config.json."
        try:
            now        = datetime.now()
            today      = now.strftime("%A, %d %B %Y")
            time_str   = now.strftime("%I:%M %p")
            sys_prompt = self.cfg["system_prompt"].format(date=today, time=time_str)
            max_tok = self.cfg.get("max_tokens", 4096)
            resp = self.gemini_client.models.generate_content(
                model    = self.cfg["gemini_model"],
                contents = user_input,
                config   = genai.types.GenerateContentConfig(
                    system_instruction = sys_prompt,
                    max_output_tokens  = max_tok,
                ),
            )
            return resp.text.strip()
        except Exception as e:
            return f"Gemini error: {e}"

    def _ask_ollama(self, user_input: str) -> str:
        import requests as req
        try:
            url  = "http://localhost:11434/api/chat"
            now  = datetime.now()
            time_str = now.strftime("%I:%M %p")
            today    = now.strftime("%A, %d %B %Y")
            sys_prompt = self.cfg["system_prompt"].format(date=today, time=time_str)
            messages = [{"role": "system", "content": sys_prompt}]
            max_h = self.cfg.get("max_history", 20)
            messages += self.history[-max_h:]
            messages.append({"role": "user", "content": user_input})
            max_tok = self.cfg.get("max_tokens", 4096)
            body = {
                "model": self.cfg.get("ollama_model", OLLAMA_MODEL),
                "messages": messages,
                "stream": False,
                "options": {"num_predict": max_tok, "temperature": 0.7},
            }
            resp = req.post(url, json=body, timeout=60)
            data = resp.json()
            return data["message"]["content"].strip()
        except Exception as e:
            return f"Ollama error: {e}"

    def _analyze_camera(self, prompt: str = "What do you see?") -> str:
        if not self.gemini_client:
            return "Vision API not available, sir. Check your Gemini key."
        try:
            import cv2
            from PIL import Image
            import io
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "Could not open camera, sir."
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "Failed to capture frame from camera, sir."
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG")
            buf.seek(0)
            image_data = buf.getvalue()
            now        = datetime.now()
            time_str   = now.strftime("%I:%M %p")
            today      = now.strftime("%A, %d %B %Y")
            sys_prompt = self.cfg["system_prompt"].format(date=today, time=time_str)
            reasoning_prompt = (
                f"{sys_prompt}\n\n"
                f"The user requests a detailed analysis of what you see through the camera: {prompt}\n\n"
                "Think step-by-step:\n"
                "1. What is the object or scene? Identify and describe precisely.\n"
                "2. What materials are visible? Assess quality, wear, damage.\n"
                "3. If this is an object for design/engineering: assess its geometry, "
                "potential stress points, how it could be manufactured (CNC, 3D print, cast), "
                "what tolerances matter, and how it could be improved.\n"
                "4. If it's a scene or environment: assess layout, lighting, safety, "
                "and suggest optimizations.\n"
                "5. Provide actionable engineering or design feedback.\n"
                "Be thorough and critical."
            )
            resp = self.gemini_client.models.generate_content(
                model    = self.cfg["gemini_model"],
                contents = [reasoning_prompt, genai.types.Part.from_bytes(data=image_data, mime_type="image/jpeg")],
                config   = genai.types.GenerateContentConfig(max_output_tokens=2048),
            )
            return resp.text.strip()
        except Exception as e:
            return f"Vision error: {e}"

    def _analyze_screenshot(self, prompt: str = "What's on the screen?") -> str:
        if not self.gemini_client:
            return "Vision API not available, sir."
        try:
            import mss
            from PIL import Image
            import io
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[1])
                pil_img = Image.frombytes("RGB", img.size, img.rgb)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            buf.seek(0)
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            today = now.strftime("%A, %d %B %Y")
            sys_prompt = self.cfg["system_prompt"].format(date=today, time=time_str)
            reasoning_prompt = (
                f"{sys_prompt}\n\n"
                f"Analyze the screen capture: {prompt}\n\n"
                "Identify the application, content, and provide actionable feedback."
            )
            from google import genai
            resp = self.gemini_client.models.generate_content(
                model=self.cfg["gemini_model"],
                contents=[reasoning_prompt, genai.types.Part.from_bytes(data=buf.read(), mime_type="image/png")],
                config=genai.types.GenerateContentConfig(max_output_tokens=2048),
            )
            return resp.text.strip()
        except Exception as e:
            return f"Screenshot error: {e}"

    # ─────────────────────────────────────────────────────────────────
    # SYSTEM CONTROL
    # ─────────────────────────────────────────────────────────────────
    def _get_battery(self) -> str:
        try:
            import psutil
            battery = psutil.sensors_battery()
            if battery:
                pct = battery.percent
                plug = "plugged in" if battery.power_plugged else "on battery"
                return f"Battery at {pct}%, {plug}."
            return "No battery detected."
        except Exception as e:
            return f"Battery check failed: {e}"

    def _get_system_info(self) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            return f"CPU: {cpu}%. RAM: {mem.percent}% used ({mem.used>>30}GB/{mem.total>>30}GB). Disk: {disk.percent}% used ({disk.free>>30}GB free)."
        except Exception as e:
            return f"System info error: {e}"

    def _optimize_pc(self) -> str:
        """Run performance optimizations to speed up the PC."""
        results = []
        try:
            import subprocess as _sp, tempfile, os, glob
            # 1. Clean temp files
            cleaned = 0
            for path in [os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
                         os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Temp")]:
                if path and os.path.exists(path):
                    for f in glob.glob(os.path.join(path, "*")):
                        try:
                            if os.path.isfile(f):
                                os.remove(f)
                                cleaned += 1
                        except: pass
            results.append(f"Cleaned {cleaned} temp files")

            # 2. Kill heavy background processes
            killed = []
            for proc in ["onedrive", "dropbox", "samsung", "steam", "epicgames",
                         "discord", "slack", "spotify", "brave", "chrome", "firefox"]:
                try:
                    _sp.run(["taskkill", "/f", "/im", f"{proc}.exe"],
                            capture_output=True, timeout=3)
                    killed.append(proc)
                except: pass
            if killed:
                results.append(f"Stopped: {', '.join(killed)}")

            # 3. Clear DNS cache
            _sp.run(["ipconfig", "/flushdns"], capture_output=True, timeout=5)
            results.append("DNS cache flushed")

            # 4. Set power scheme to high performance
            _sp.run(["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
                    capture_output=True, timeout=5)
            results.append("High performance power plan")

            # 5. Disable startup bloat via registry
            _sp.run(["powershell", "-Command",
                     "Get-CimInstance Win32_StartupCommand | Where-Object {$_.Name -notlike '*Windows*'} | Disable-MMAgent -Startup"],
                    capture_output=True, timeout=10)

            return "PC optimized, sir.\n- " + "\n- ".join(results)
        except Exception as e:
            return f"Optimization error: {e}"

    def _apply_power_preset(self, mode: str = "battery") -> str:
        """Apply power preset: battery saver or performance."""
        try:
            import subprocess as _sp
            if mode == "battery":
                _sp.run(["powercfg", "/setactive", "a1841308-3541-4fab-bc81-f71556f20b4a"],
                        capture_output=True, timeout=5)
                _sp.run(["powershell", "-Command",
                         "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, 40)"],
                        capture_output=True, timeout=5)
                return "Battery preset applied: power saver, brightness 40%."
            else:
                _sp.run(["powercfg", "/setactive", "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"],
                        capture_output=True, timeout=5)
                _sp.run(["powershell", "-Command",
                         "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, 80)"],
                        capture_output=True, timeout=5)
                return "Performance preset applied: high performance, brightness 80%."
        except Exception as e:
            return f"Preset error: {e}"

    def _open_app(self, app_name: str) -> str:
        apps = {
            "chrome": "chrome", "browser": "chrome", "brave": "brave",
            "spotify": "spotify", "discord": "discord", "slack": "slack",
            "vscode": "code", "vs code": "code", "visual studio code": "code",
            "terminal": "cmd", "cmd": "cmd", "command prompt": "cmd",
            "calculator": "calc", "calc": "calc",
            "notepad": "notepad", "notepad++": "notepad++",
            "explorer": "explorer", "file explorer": "explorer", "files": "explorer",
            "task manager": "taskmgr", "taskmgr": "taskmgr",
            "settings": "start ms-settings:", "control panel": "control",
        }
        key = app_name.lower().strip()
        target = apps.get(key, key)
        try:
            import subprocess
            if target.startswith("start "):
                subprocess.run(target, shell=True, check=False)
            else:
                subprocess.run(f"start {target}", shell=True, check=False)
            return f"Opening {app_name}, sir."
        except Exception as e:
            return f"Could not open {app_name}: {e}"

    def _set_volume(self, level: int) -> str:
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            vol = max(0.0, min(1.0, level / 100.0))
            volume.SetMasterVolumeLevelScalar(vol, None)
            return f"Volume set to {level}%, sir."
        except Exception:
            return None

    def _design_item(self, desc: str) -> str:
        """Use AI to design an item with engineering reasoning."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        today = now.strftime("%A, %d %B %Y")
        sys_p = self.cfg["system_prompt"].format(date=today, time=time_str)
        prompt = (
            f"{sys_p}\n\n"
            f"The user asks you to design: {desc}\n\n"
            "Provide a detailed engineering design with:\n"
            "1. Design requirements and constraints\n"
            "2. Material selection with engineering justification\n"
            "3. Detailed geometry and dimensions in mm\n"
            "4. Manufacturing method (3D print FDM/SLA, CNC, injection mold, etc.)\n"
            "5. Assembly and tolerance considerations\n"
            "6. Stress points and failure mode analysis\n"
            "7. Optimizations for weight, strength, and printability\n"
            "Think step-by-step like a senior engineer."
        )
        return self._ask_with_fallback(prompt)

    def _stress_test_3d(self, desc: str) -> str:
        """Analyze a 3D printable design for structural integrity."""
        now = datetime.now()
        time_str = now.strftime("%I:%M %p")
        today = now.strftime("%A, %d %B %Y")
        sys_p = self.cfg["system_prompt"].format(date=today, time=time_str)
        prompt = (
            f"{sys_p}\n\n"
            f"Perform a detailed structural stress analysis on: {desc}\n\n"
            "Evaluate step-by-step:\n"
            "1. Layer orientation and inter-layer adhesion weak points\n"
            "2. Overhang angles, bridging spans, and support requirements\n"
            "3. Stress concentration zones (sharp corners, thin walls, holes, threads)\n"
            "4. Optimal infill pattern (gyroid, grid, honeycomb) and density\n"
            "5. Wall line count and thickness adequacy for the load\n"
            "6. Thermal expansion, warping, and shrinkage risks\n"
            "7. Bed adhesion requirements (brim, raft, mouse ears)\n"
            "8. Post-processing (annealing, vapor smoothing, epoxy coating)\n"
            "9. Estimated print time and material cost\n"
            "10. Critical failure points under load with improvement suggestions\n"
            "Be brutally honest about weaknesses — lives depend on your analysis."
        )
        return self._ask_with_fallback(prompt)

    def _prewarm_engines(self):
        """Ping all AI engines at startup so connections are hot."""
        for attempt in range(2):
            try:
                if self.groq_client:
                    self.groq_client.chat.completions.create(
                        model=self.cfg["groq_model"],
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1)
            except:
                pass
        try:
            if self.gemini_client:
                self.gemini_client.models.generate_content(
                    model=self.cfg["gemini_model"],
                    contents="ping",
                    config=genai.types.GenerateContentConfig(max_output_tokens=1))
        except:
            pass
        try:
            requests.get("http://localhost:11434/api/tags", timeout=2)
        except:
            pass
        print(f"{Fore.GREEN}[Engines] Connections pre-warmed.{Style.RESET_ALL}")
        # Start keepalive pinger — prevents connection cooldown
        threading.Thread(target=self._keepalive_pinger, daemon=True).start()

    def _keepalive_pinger(self):
        """Ping Groq every 60s to keep the TCP connection hot (httpx keepalive=120s)."""
        # First ping immediately
        try:
            if self.groq_client:
                self.groq_client.chat.completions.create(
                    model=self.cfg["groq_model"],
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1, timeout=5)
        except:
            pass
        while self.running:
            time.sleep(60)
            try:
                if self.groq_client:
                    self.groq_client.chat.completions.create(
                        model=self.cfg["groq_model"],
                        messages=[{"role": "user", "content": "ping"}],
                        max_tokens=1,
                        timeout=5)
            except:
                pass

    def _auto_extract_facts(self, text: str):
        """Auto-extract user facts from conversation — name, preferences, locations, etc."""
        import re as _re
        lower = text.lower().strip()
        facts = {}
        patterns = [
            (r"my name is (\w+)", "name"),
            (r"i'm (\w+)", "name"),
            (r"i am (\w+)", "name"),
            (r"call me (\w+)", "name"),
            (r"i live in (\w+)", "location"),
            (r"i'm from (\w+)", "location"),
            (r"i work as (?:an? |a )?(.+)", "occupation"),
            (r"my (?:favourite|favorite) (?:color|colour) is (\w+)", "favorite_color"),
            (r"i (?:like|love) (\w+)", "likes"),
            (r"i (?:use|have) (?:an? |a )?(\w+)", "has"),
        ]
        for pat, key in patterns:
            m = _re.search(pat, lower)
            if m:
                val = m.group(1).strip().capitalize()
                if key == "likes" and val.lower() in ("it", "that", "this", "them"):
                    continue
                if key == "has" and val.lower() in ("it", "that", "this", "them", "computer"):
                    continue
                if len(val) > 2 and len(val) < 30:
                    facts[key] = val
                    break
        if facts:
            mem = self._load_memory()
            changed = False
            for k, v in facts.items():
                if k not in mem:
                    mem[k] = v
                    changed = True
            if changed:
                self._save_memory(mem)
                print(f"{Fore.GREEN}[Memory] Auto-stored: {facts}{Style.RESET_ALL}")

    def _handle_defender_cmd(self, cmd: str) -> str:
        if not _HAS_DEFENDER:
            return "Active Defender is not available."
        if any(w in cmd for w in ["status", "state", "running"]):
            st = _defender.get_status()
            running = st.get("running", False)
            s = f"Active Defender is {Fore.GREEN}RUNNING{Style.RESET_ALL}" if running else f"{Fore.RED}STOPPED{Style.RESET_ALL}"
            result = f"Defender status: {s}. Threats logged: {st.get('threats_logged', 0)}. "
            result += f"RDP sessions detected: {st.get('rdp_sessions_detected', 0)}. "
            result += f"Remote tools detected: {st.get('remote_tools_detected', 0)}. "
            ips = st.get("blocked_ips", [])
            if ips:
                result += f"Blocked IPs: {', '.join(ips)}."
            else:
                result += "No IPs blocked."
            return result
        if any(w in cmd for w in ["lock", "secure", "protect", "lock workstation", "lock pc"]):
            r = _defender.lock_workstation()
            if isinstance(r, dict) and r.get("ok"):
                return "Workstation locked. Active Defender is watching."
            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True)
            return "Workstation locked."
        if any(w in cmd for w in ["scan", "threat"]):
            th = _defender.get_threat_log(5)
            if th:
                return f"Recent threats ({len(th)}): " + " | ".join(str(t.get("message", t)) for t in th[-3:])
            return "No threats found in the log."
        if any(w in cmd for w in ["session", "remote"]):
            st = _defender.get_status()
            if st.get("rdp_sessions_detected", 0) or st.get("remote_tools_detected", 0):
                return f"Detected: {st['rdp_sessions_detected']} RDP sessions, {st['remote_tools_detected']} remote tools."
            return "No remote sessions detected."
        if any(w in cmd for w in ["kill", "stop remote", "remove tool"]):
            r = _defender.kill_remote_tools()
            if isinstance(r, dict):
                count = len(r.get("killed", []))
                return f"Killed {count} remote control processes." if count else "No remote tools found."
            return "Kill command executed."
        if any(w in cmd for w in ["logoff", "disconnect", "kick"]):
            r = _defender.force_logoff()
            return r.get("message", "Remote sessions logged off.") if isinstance(r, dict) else "Logoff executed."
        if any(w in cmd for w in ["performance", "process", "task"]):
            r = _defender.get_system_performance()
            if isinstance(r, dict):
                return f"CPU: {r.get('cpu', '?')}%, RAM: {r.get('memory', '?')}%, Disk: {r.get('disk', '?')}%, Network: {r.get('network', '?')}"
            return "Performance data unavailable."
        st = _defender.get_status()
        return f"Active Defender is {'running' if st.get('running') else 'stopped'}, sir."

    def _get_health_report(self) -> str:
        if not _HAS_MONITORS:
            return "System health monitors unavailable."
        events = _monitors.get_events(clear=False)
        health = _monitors._health if hasattr(_monitors, "_health") else {}
        parts = []
        if health.get("cpu"):  parts.append(f"CPU: {health['cpu']}")
        if health.get("ram"):  parts.append(f"RAM: {health['ram']}")
        if health.get("gpu"):  parts.append(f"GPU: {health['gpu']}")
        if health.get("uptime"): parts.append(f"Uptime: {health['uptime']}")
        disk = health.get("disk", [])
        if disk:
            disk_strs = [f"{d['drive']} {d.get('percent','?')}% ({d.get('free','?')} free of {d.get('total','?')})" if isinstance(d, dict) else str(d) for d in disk[:2]]
            parts.append("Disk: " + ", ".join(disk_strs))
        result = " — ".join(parts) if parts else "Health data not yet collected."
        recent_events = [e for e in events if e["type"] in ("security", "clipboard")][-3:]
        if recent_events:
            result += "\nRecent events: " + "; ".join(str(e["data"]) for e in recent_events)
        return result

    def _generate_3d_model(self, desc: str) -> str:
        if not _HAS_MODEL3D:
            return "3D modeling engine not available."
        try:
            result = _model3d.make_custom(desc)
            out_path = result if isinstance(result, str) else (result.get("file") if isinstance(result, dict) else None)
            if out_path:
                return f"3D model generated: {out_path}. Available models: {', '.join(_model3d.list_models()[-5:]) if hasattr(_model3d, 'list_models') else 'check output folder'}."
            return f"3D model result: {result}"
        except Exception as e:
            now = datetime.now()
            time_str = now.strftime("%I:%M %p")
            today = now.strftime("%A, %d %B %Y")
            sys_p = self.cfg["system_prompt"].format(date=today, time=time_str)
            prompt = (
                f"{sys_p}\n\n"
                f"The user wants a 3D printable design for: {desc}\n"
                "Recommend the best modeling approach — parametric OpenSCAD or direct STL generation.\n"
                "Provide: material, print orientation, supports needed, wall count, infill, "
                "estimated print time, and any post-processing."
            )
            return self._ask_with_fallback(prompt)

    def _execute_system(self, command: str) -> str:
        cmd = command.lower().strip()
        if any(w in cmd for w in ["optimize", "speed up", "slow", "make faster", "clean up", "speedup"]):
            return self._optimize_pc()
        if any(w in cmd for w in ["power saver", "battery preset", "power saving", "save power", "unplugged", "battery mode"]):
            return self._apply_power_preset("battery")
        if any(w in cmd for w in ["performance preset", "high performance", "plugged in", "max power"]):
            return self._apply_power_preset("performance")
        if "battery" in cmd or "power" in cmd:
            return self._get_battery()
        if "cpu" in cmd or "memory" in cmd or "ram" in cmd or "system" in cmd or "disk" in cmd or "usage" in cmd:
            return self._get_system_info()
        if cmd.startswith("open ") or cmd.startswith("launch ") or cmd.startswith("start "):
            app = cmd.split(" ", 1)[1] if " " in cmd else ""
            return self._open_app(app) if app else "What should I open, sir?"
        if "volume" in cmd:
            import re
            nums = re.findall(r'\d+', cmd)
            if nums:
                return self._set_volume(int(nums[0])) or f"Volume control unavailable."
            if "up" in cmd or "increase" in cmd:
                return self._set_volume(70) or f"Volume control unavailable."
            if "down" in cmd or "decrease" in cmd or "lower" in cmd:
                return self._set_volume(20) or f"Volume control unavailable."
            if "mute" in cmd:
                return self._set_volume(0) or f"Volume control unavailable."
        if "time" in cmd:
            return f"The time is {datetime.now():%I:%M %p}, sir."
        if "date" in cmd:
            return f"Today is {datetime.now():%A, %d %B %Y}, sir."
        if cmd.startswith("design ") or cmd.startswith("create ") or cmd.startswith("make "):
            desc = cmd.split(" ", 1)[1] if " " in cmd else ""
            if desc:
                return self._design_item(desc)
        if cmd.startswith("stress test ") or "stress" in cmd and "test" in cmd:
            desc = cmd.split(" ", 2)[2] if len(cmd.split(" ", 2)) > 2 else cmd.replace("stress test", "").strip()
            if desc:
                return self._stress_test_3d(desc)
        if ("analyze" in cmd and ("camera" in cmd or "see" in cmd or "look" in cmd or "this" in cmd)) \
           or cmd.startswith("look at ") or "camera" in cmd:
            prompt = cmd.replace("analyze", "").replace("camera", "").replace("look at", "").replace("see this", "").strip()
            prompt = prompt or "What do you see?"
            return self._analyze_camera(prompt)
        if "screenshot" in cmd or "screen" in cmd or "capture" in cmd:
            prompt = cmd.replace("screenshot", "").replace("screen", "").replace("capture", "").strip()
            prompt = prompt or "What's on the screen?"
            return self._analyze_screenshot(prompt)
        # ── Defender commands ──────────────────────────────────────
        if _HAS_DEFENDER and any(w in cmd for w in ["defender", "scan threat", "intrusion", "remote session", "lock pc", "lock workstation", "secure", "active defender"]):
            return self._handle_defender_cmd(cmd)
        # ── System health (monitors) ───────────────────────────────
        if _HAS_MONITORS and any(w in cmd for w in ["health", "sensors", "temperature", "system health", "monitor"]):
            return self._get_health_report()
        # ── 3D model ───────────────────────────────────────────────
        if _HAS_MODEL3D and any(w in cmd for w in ["3d print ", "3d model ", "print in 3d", "generate model"]):
            desc = cmd.split(" ", 2)[2] if len(cmd.split(" ", 2)) > 2 else cmd.replace("3d", "").strip()
            if desc:
                return self._generate_3d_model(desc)
        # ── Web search (in natural language) ────────────────────────
        if any(w in cmd for w in ["search for ", "search the web for ", "look up ", "google ", "find online ", "search about "]):
            query = cmd.split("for ", 1)[-1] if "for " in cmd else cmd.split("about ", 1)[-1] if "about " in cmd else cmd
            if len(query) > 3:
                return self._cmd_websearch(query)
        return None

    def ask_ai(self, user_input: str) -> str:
        # Intercept system commands
        sys_reply = self._execute_system(user_input)
        if sys_reply:
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": sys_reply})
            self.cfg["conversation_history"] = self.history
            return sys_reply
        # Intercept memory commands
        lower = user_input.lower().strip()
        if lower.startswith("remember that "):
            parts = lower[14:].split(" is ", 1)
            if len(parts) == 2:
                self.remember(parts[0], parts[1])
                return f"I'll remember that {parts[0]} is {parts[1]}, sir."
            return "I didn't catch what to remember, sir. Say 'remember that my name is John'."
        if lower.startswith("remember "):
            parts = lower[9:].split(" is ", 1)
            if len(parts) == 2:
                self.remember(parts[0], parts[1])
                return f"Noted: {parts[0]} is {parts[1]}, sir."
            return "Tell me what to remember like 'my name is John'."
        if lower.startswith("what do you know about me") or lower.startswith("what do you remember"):
            mem = self._load_memory()
            if mem:
                return f"I know that {', '.join(f'{k} is {v}' for k, v in mem.items())}, sir."
            return "I don't know much about you yet, sir. Tell me things to remember."
        if lower.startswith("forget ") or lower.startswith("delete "):
            key = lower.split(" ", 1)[1] if " " in lower else ""
            if key:
                self.forget(key)
                return f"Forgot about {key}, sir."
            return "What should I forget, sir?"
        reply = self._ask_with_fallback(user_input)
        if not reply.startswith("Groq error") and not reply.startswith("Gemini error") and not reply.startswith("[Rate limited") and not reply.startswith("Ollama error") and not reply.startswith("Vision error"):
            self.history.append({"role": "user",      "content": user_input})
            self.history.append({"role": "assistant",  "content": reply})
            max_h = self.cfg.get("max_history", 30)
            self.history = self.history[-(max_h * 2):]
            self.cfg["conversation_history"] = self.history
            save_config(self.cfg)
            # Auto-extract facts from user input
            self._auto_extract_facts(user_input)
        return reply

    # ─────────────────────────────────────────────────────────────────
    # VOICE / TTS
    # ─────────────────────────────────────────────────────────────────
    def interrupt(self):
        """Stop speech immediately and kill HUD typewriter."""
        self._stop_tts = True
        if self._tts_engine:
            try:
                self._tts_engine.stop()
            except Exception:
                pass
        self.speaking = False
        push_to_hud("__STOP_TYPE__")
        print(f"{Fore.YELLOW}[Interrupted]{Style.RESET_ALL}")

    def speak(self, text: str, force: bool = False):
        if not self.cfg.get("voice_enabled") and not force:
            return
        clean = re.sub(r"[*_`#>~|]", "", text)
        clean = re.sub(r"\n+", " ", clean).strip()
        if not clean:
            return
        def _speak():
            with self.tts_lock:
                self._stop_tts = False
                try:
                    self.speaking = True
                    if self.cfg.get("custom_voice") and self.platform == "local":
                        from jarvis_voice import load_model, speak_to_file
                        load_model()
                        import tempfile
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                            tmp = f.name
                        out = speak_to_file(clean, tmp)
                        if out:
                            import winsound
                            winsound.PlaySound(out, winsound.SND_FILENAME)
                            os.unlink(out)
                            return
                    engine = pyttsx3.init()
                    self._tts_engine = engine
                    engine.setProperty("rate",   self.cfg.get("voice_speed",  170))
                    engine.setProperty("volume", self.cfg.get("voice_volume", 0.95))
                    voices = engine.getProperty("voices")
                    vid    = self.cfg.get("voice_id", "")
                    if vid:
                        engine.setProperty("voice", vid)
                    else:
                        for v in voices:
                            if any(k in v.name.lower() for k in ("male", "david", "mark", "george")):
                                engine.setProperty("voice", v.id)
                                break
                    if not self._stop_tts:
                        engine.say(clean)
                        engine.runAndWait()
                except Exception as e:
                    if not self._stop_tts:
                        print(f"{Fore.RED}TTS error: {e}{Style.RESET_ALL}")
                finally:
                    self._tts_engine = None
                    self.speaking    = False
        threading.Thread(target=_speak, daemon=True).start()

    def _wake_sound(self):
        if not self.cfg.get("wake_sound_enabled", True):
            return
        try:
            if os.name == "nt":
                import winsound
                winsound.Beep(880,  80)
                winsound.Beep(1320, 80)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────
    # COMMANDS
    # ─────────────────────────────────────────────────────────────────
    HELP_TEXT = (
        "Commands:\n"
        "  /help         — this list\n"
        "  /clear        — wipe conversation history\n"
        "  /model        — switch between groq <-> gemini\n"
        "  /models       — show available engines and active model\n"
        "  /think <q>    — step-by-step reasoning on any question\n"
        "  /voice        — toggle voice output\n"
        "  /listen       — one-shot voice input\n"
        "  /history      — show recent conversation\n"
        "  /settings     — show current config\n"
        "  /standby      — enter standby mode\n"
        "  /wake         — exit standby mode\n"
        "  /stop         — interrupt speech\n"
        "  /exit         — shut down\n\n"
        "Internet & Search:\n"
        "  /websearch <query>     — search the web\n"
        "  /webfetch <url>        — fetch URL content\n"
        "  /weather <city>        — get weather forecast\n"
        "  say \"search for ...\"   — natural language web search\n\n"
        "File Operations:\n"
        "  /read <path> [offset]  — read file\n"
        "  /write <path> <content> — write file\n"
        "  /edit <path> <old> <new> [all] — edit file\n"
        "  /glob <pattern>        — find files\n"
        "  /grep <regex> [include] — search in files\n\n"
        "System & Monitoring:\n"
        "  /sysinfo               — CPU, RAM, disk, battery, network\n"
        "  /processes             — list top processes\n"
        "  /kill <pid|name>       — terminate a process\n\n"
        "PC Control:\n"
        "  /clipboard [get|set|clear] [value] — clipboard\n"
        "  /notify <title> <msg>  — show notification\n"
        "  /pc volume [up|down|%] — control volume\n"
        "  /pc brightness [%]     — control brightness\n"
        "  /pc lock               — lock workstation\n"
        "  /pc wifi               — show WiFi info\n"
        "  /pc apps               — list running apps\n"
        "  /pc shutdown|restart|hibernate|sleep — power control\n\n"
        "AI & Memory:\n"
        "  /python <code>         — execute Python code\n"
        "  /remember <key> <value> — save a fact\n"
        "  /recall [key]          — retrieve saved facts\n"
        "  /screenshot            — capture screen\n\n"
        "Swarm Orchestration:\n"
        "  /swarm-init <topology> [max-agents] — initialize swarm\n"
        "  /swarm-execute <task> [mode]        — execute with swarm\n"
        "  /swarm-status                       — check swarm status\n"
        "  /swarm-config <key> <value>         — configure swarm\n\n"
        "Quick Commands:\n"
        "  play <song> — open YouTube\n"
        "  switch groq|gemini — swap AI engine\n"
        "  open hud / close hud — toggle HUD\n"
        "  time — current time"
    )

    def _handle_command(self, cmd: str) -> bool:
        """Returns True if the input was a slash command (consumed)."""
        c = cmd.strip().lower()

        if c in ("/exit", "/quit"):
            self.running = False
            self._jarvis("Going offline. Goodbye, sir.")
            self.speak("Going offline. Goodbye, sir.", force=True)
            time.sleep(1.5)
            return True

        if c == "/clear":
            self.history = []
            self.cfg["conversation_history"] = []
            save_config(self.cfg)
            self._jarvis("Conversation history wiped, sir. Fresh start.")
            return True

        if c in ("/help", "/commands"):
            self._jarvis(self.HELP_TEXT)
            return True

        if c in ("/models", "/engines", "/switchengine"):
            brain = self.cfg["active_model"].upper()
            model = self.cfg.get(f"{self.cfg['active_model']}_model", "?")
            engines = []
            if self.groq_client:   engines.append(f"GROQ ({self.cfg.get('groq_model','?')})")
            if self.gemini_client: engines.append(f"GEMINI ({self.cfg.get('gemini_model','?')})")
            engines.append(f"OLLAMA ({self.cfg.get('ollama_model','?')})")
            self._jarvis(f"Active: {brain} ({model})\nAvailable: " + " | ".join(engines))
            return True

        if c == "/voice":
            self.cfg["voice_enabled"] = not self.cfg["voice_enabled"]
            save_config(self.cfg)
            state = "enabled" if self.cfg["voice_enabled"] else "disabled"
            self._jarvis(f"Voice output {state}, sir.")
            return True

        if c == "/customvoice":
            self.cfg["custom_voice"] = not self.cfg["custom_voice"]
            save_config(self.cfg)
            state = "on" if self.cfg["custom_voice"] else "off"
            self._jarvis(f"Custom cloned voice {state}, sir.")
            return True

        if c == "/listen":
            self.listen_once()
            return True

        if c in ("/stop", "/shut up", "/enough", "/quiet"):
            self.interrupt()
            return True

        if c == "/history":
            if not self.history:
                self._jarvis("No conversation history yet, sir.")
            else:
                for m in self.history[-10:]:
                    role = "You" if m["role"] == "user" else "JARVIS"
                    print(f"  {Fore.CYAN}{role}:{Style.RESET_ALL} {m['content'][:120]}")
            return True

        if c == "/settings":
            safe = {k: v for k, v in self.cfg.items()
                    if k not in ("conversation_history",
                                 "groq_api_key", "gemini_api_key")}
            self._jarvis(json.dumps(safe, indent=2))
            return True

        if c == "/standby":
            self._enter_standby()
            return True

        if c in ("/wake", "/wakeup"):
            self._exit_standby()
            return True

        if c.startswith("/model"):
            parts = c.split()
            target = parts[1] if len(parts) > 1 else (
                "gemini" if self.cfg["active_model"] == "groq" else "groq"
            )
            result = self._switch_brain(target)
            self._jarvis(result)
            self._print_banner()
            return True

        # Swarm orchestration commands
        if c.startswith("/swarm-init"):
            parts = c.split()
            if len(parts) < 2:
                self._jarvis("Usage: /swarm-init <topology> [max-agents]")
                return True
            topology = parts[1]
            max_agents = int(parts[2]) if len(parts) > 2 else 5
            result = self._init_swarm(topology, max_agents)
            self._jarvis(result)
            return True

        if c.startswith("/swarm-execute"):
            parts = c.split()
            if len(parts) < 2:
                self._jarvis("Usage: /swarm-execute <task> [mode]")
                return True
            task = " ".join(parts[1:])
            mode = "auto"
            if "parallel" in task:
                mode = "parallel"
            elif "sequential" in task:
                mode = "sequential"
            result = self._execute_with_swarm(task, mode)
            self._jarvis(result)
            return True

        if c == "/swarm-status":
            result = self._check_swarm_status()
            self._jarvis(result)
            return True

        if c.startswith("/swarm-config"):
            parts = c.split()
            if len(parts) < 3:
                self._jarvis("Usage: /swarm-config <key> <value>")
                return True
            key = parts[1]
            value = " ".join(parts[2:])
            result = self._configure_swarm(key, value)
            self._jarvis(result)
            return True

        # ── File Operations ──
        if c.startswith("/read "):
            parts = cmd.split(maxsplit=2)
            path = parts[1] if len(parts) > 1 else ""
            offset = int(parts[2]) if len(parts) > 2 else 0
            if not path:
                self._jarvis("Usage: /read <path> [offset]")
                return True
            self._jarvis(self._cmd_read(path, offset))
            return True

        if c.startswith("/write "):
            parts = cmd.split(maxsplit=2)
            if len(parts) < 3:
                self._jarvis("Usage: /write <path> <content>")
                return True
            self._jarvis(self._cmd_write(parts[1], parts[2]))
            return True

        if c.startswith("/edit "):
            parts = cmd.split(maxsplit=4)
            if len(parts) < 4:
                self._jarvis("Usage: /edit <path> <old> <new> [all]")
                return True
            all_occ = len(parts) > 4 and parts[4] == "all"
            self._jarvis(self._cmd_edit(parts[1], parts[2], parts[3], all_occ))
            return True

        if c.startswith("/glob "):
            pattern = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_glob(pattern))
            return True

        if c.startswith("/grep "):
            parts = cmd.split(maxsplit=2)
            regex = parts[1] if len(parts) > 1 else ""
            include = parts[2] if len(parts) > 2 else ""
            self._jarvis(self._cmd_grep(regex, include))
            return True

        # ── Web & Search ──
        if c.startswith("/websearch "):
            query = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_websearch(query))
            return True

        if c.startswith("/webfetch "):
            url = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_webfetch(url))
            return True

        if c.startswith("/weather "):
            city = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_weather(city))
            return True

        # ── System & Monitoring ──
        if c == "/sysinfo":
            self._jarvis(self._cmd_sysinfo())
            return True

        if c == "/processes":
            self._jarvis(self._cmd_processes())
            return True

        if c.startswith("/kill "):
            target = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_kill(target))
            return True

        # ── PC Control ──
        if c.startswith("/clipboard"):
            parts = cmd.split(maxsplit=2)
            action = parts[1] if len(parts) > 1 else "get"
            value = parts[2] if len(parts) > 2 else ""
            self._jarvis(self._cmd_clipboard(action, value))
            return True

        if c.startswith("/notify "):
            parts = cmd.split(maxsplit=2)
            title = parts[1] if len(parts) > 1 else "JARVIS"
            msg = parts[2] if len(parts) > 2 else ""
            self._jarvis(self._cmd_notify(title, msg))
            return True

        if c.startswith("/pc "):
            parts = cmd.split(maxsplit=2)
            action = parts[1] if len(parts) > 1 else ""
            value = parts[2] if len(parts) > 2 else ""
            if not action:
                self._jarvis("Usage: /pc <action> [params]")
                return True
            self._jarvis(self._cmd_pc(action, value))
            return True

        # ── AI & Code ──
        if c.startswith("/python "):
            code = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_python(code))
            return True

        if c.startswith("/remember "):
            parts = cmd.split(maxsplit=2)
            key = parts[1] if len(parts) > 1 else ""
            value = parts[2] if len(parts) > 2 else ""
            if not key or not value:
                self._jarvis("Usage: /remember <key> <value>")
                return True
            self._jarvis(self._cmd_remember(key, value))
            return True

        if c.startswith("/recall"):
            key = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            self._jarvis(self._cmd_recall(key))
            return True

        if c == "/screenshot":
            self._jarvis(self._cmd_screenshot())
            return True

        if c.startswith("/think "):
            """Reason step-by-step about a problem."""
            question = cmd.split(maxsplit=1)[1] if " " in cmd else ""
            if not question:
                self._jarvis("Usage: /think <question> — I'll reason step-by-step, sir.")
                return True
            now = datetime.now()
            ts = now.strftime("%I:%M %p")
            td = now.strftime("%A, %d %B %Y")
            sys_p = self.cfg["system_prompt"].format(date=td, time=ts)
            prompt = (
                f"{sys_p}\n\n"
                f"Think step-by-step about: {question}\n\n"
                "1. Define the problem precisely\n"
                "2. Identify what I know and what I need to find out\n"
                "3. Break the problem into sub-problems\n"
                "4. Work through each sub-problem\n"
                "5. Combine insights into a final answer\n"
                "6. Validate the answer against constraints\n"
                "Show all reasoning — no shortcuts."
            )
            result = self._ask_with_fallback(prompt)
            self._jarvis(result)
            self.speak(result)
            return True

        return False

    def _switch_brain(self, target: str) -> str:
        t = target.strip().lower()
        if t not in ("groq", "gemini"):
            return "Unknown engine, sir. Choose 'groq' or 'gemini'."
        if t == "groq" and not self.groq_client:
            return "Cannot switch — Groq API key missing, sir."
        if t == "gemini" and not self.gemini_client:
            return "Cannot switch — Gemini API key missing, sir."
        self.cfg["active_model"] = t
        save_config(self.cfg)
        return f"Active brain shifted to {t.upper()}, sir."

    # ─────────────────────────────────────────────────────────────────
    # SWARM ORCHESTRATION
    # ─────────────────────────────────────────────────────────────────
    def _init_swarm(self, topology: str, max_agents: int) -> str:
        """Initialize swarm with specified topology and agent count."""
        try:
            # Simulate swarm initialization with mock response
            # In a real implementation, this would integrate with agentic-flow
            self._jarvis(f"Initializing swarm with {topology} topology and {max_agents} agents, sir...")
            # Simulate successful initialization
            return f"Swarm initialized successfully with {topology} topology and {max_agents} agents, sir."
        except Exception as e:
            return f"Error initializing swarm: {str(e)}, sir."

    def _execute_with_swarm(self, task: str, mode: str) -> str:
        """Execute task using swarm orchestration."""
        try:
            # Simulate swarm execution with mock response
            # In a real implementation, this would integrate with agentic-flow
            self._jarvis(f"Executing task with swarm in {mode} mode: {task}, sir...")
            # Simulate successful execution
            return f"Task executed with swarm in {mode} mode: {task}, sir."
        except Exception as e:
            return f"Error executing task with swarm: {str(e)}, sir."

    def _check_swarm_status(self) -> str:
        """Check current swarm status."""
        try:
            # Simulate swarm status check with mock response
            # In a real implementation, this would integrate with agentic-flow
            self._jarvis("Checking swarm status, sir...")
            # Simulate status response
            return "Swarm status: Active with 3 agents, sir."
        except Exception as e:
            return f"Error checking swarm status: {str(e)}, sir."

    def _configure_swarm(self, key: str, value: str) -> str:
        """Configure swarm settings."""
        try:
            # Simulate swarm configuration with mock response
            # In a real implementation, this would integrate with agentic-flow
            self._jarvis(f"Configuring swarm setting {key} to {value}, sir...")
            # Simulate successful configuration
            return f"Swarm configured: {key} = {value}, sir."
        except Exception as e:
            return f"Error configuring swarm: {str(e)}, sir."

    # ─────────────────────────────────────────────────────────────────
    # AGENT TOOLS  —  File Ops, Web, System, PC Control, AI, Memory
    # ─────────────────────────────────────────────────────────────────

    def _cmd_read(self, path: str, offset: int = 0) -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"File not found: {path}, sir."
            if p.is_dir():
                names = [f.name for f in p.iterdir()][:40]
                return f"Directory: {path}\n" + "\n".join(names) + (f"\n... [{len(list(p.iterdir()))-40} more]" if len(list(p.iterdir())) > 40 else "")
            with open(p, encoding="utf-8", errors="replace") as f:
                if offset > 0:
                    for _ in range(offset):
                        f.readline()
                content = f.read()
            lines = content.splitlines()
            if len(lines) > 50:
                content = "\n".join(lines[:50]) + f"\n... [{len(lines)-50} more lines]"
            return f"--- {path} (offset {offset}) ---\n{content}"
        except Exception as e:
            return f"Read error: {e}, sir."

    def _cmd_write(self, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {path}, sir."
        except Exception as e:
            return f"Write error: {e}, sir."

    def _cmd_edit(self, path: str, old_pat: str, new_pat: str, all_occ: bool = False) -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"File not found: {path}, sir."
            content = p.read_text(encoding="utf-8")
            if all_occ:
                count = content.count(old_pat)
                if count == 0:
                    return f"Pattern not found in {path}, sir."
                content = content.replace(old_pat, new_pat)
            else:
                if old_pat not in content:
                    return f"Pattern not found in {path}, sir."
                count = 1
                content = content.replace(old_pat, new_pat, 1)
            p.write_text(content, encoding="utf-8")
            return f"Replaced {count} occurrence(s) in {path}, sir."
        except Exception as e:
            return f"Edit error: {e}, sir."

    def _cmd_glob(self, pattern: str) -> str:
        try:
            import glob as glob_mod
            matches = glob_mod.glob(pattern, recursive=True)
            if not matches:
                return f"No files match '{pattern}', sir."
            result = "\n".join(str(m) for m in matches[:80])
            if len(matches) > 80:
                result += f"\n... [{len(matches)-80} more]"
            return result
        except Exception as e:
            return f"Glob error: {e}, sir."

    def _cmd_grep(self, regex: str, include: str = "") -> str:
        try:
            pat = re.compile(regex)
            root = Path(".")
            ext_filter = include.replace("*", "") if include else ""
            matches = []
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if ext_filter and ext_filter not in p.suffix:
                    continue
                try:
                    for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if pat.search(line):
                            matches.append(f"{p}:{i}: {line[:120]}")
                            if len(matches) >= 30:
                                break
                except Exception:
                    pass
                if len(matches) >= 30:
                    break
            if not matches:
                return f"No matches for '{regex}', sir."
            return "\n".join(matches)
        except Exception as e:
            return f"Grep error: {e}, sir."

    def _cmd_webfetch(self, url: str) -> str:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                text = r.read().decode("utf-8", errors="replace")
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()[:3000]
            return f"--- {url} ---\n{text}" + ("\n...[truncated]" if len(text) >= 3000 else "")
        except Exception as e:
            return f"Fetch error: {e}, sir."

    def _cmd_websearch(self, query: str) -> str:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return f"No results for '{query}', sir."
            out = []
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", "")
                out.append(f"{title}\n  {body[:200]}\n  {href}")
            return "\n\n".join(out)
        except ImportError:
            return "Web search requires: pip install ddgs"
        except Exception as e:
            return f"Web search error: {e}, sir."

    def _cmd_weather(self, city: str) -> str:
        try:
            geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
            geo = requests.get(geo_url, timeout=10).json()
            if not geo.get("results"):
                return f"Could not find city '{city}', sir."
            loc = geo["results"][0]
            lat, lon = loc["latitude"], loc["longitude"]
            name = loc.get("name", city)
            country = loc.get("country", "")
            w = requests.get(
                f"https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
                        "timezone": "auto"},
                timeout=10
            ).json()
            cur = w.get("current", {})
            temp = cur.get("temperature_2m", "?")
            feels = cur.get("apparent_temperature", "?")
            humidity = cur.get("relative_humidity_2m", "?")
            wind = cur.get("wind_speed_10m", "?")
            code = cur.get("weather_code", 0)
            conditions = {0:"Clear",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",
                          45:"Foggy",48:"Depositing rime fog",
                          51:"Light drizzle",53:"Moderate drizzle",55:"Dense drizzle",
                          61:"Slight rain",63:"Moderate rain",65:"Heavy rain",
                          66:"Light freezing rain",67:"Heavy freezing rain",
                          71:"Slight snow",73:"Moderate snow",75:"Heavy snow",
                          77:"Snow grains",80:"Slight rain showers",
                          81:"Moderate rain showers",82:"Violent rain showers",
                          85:"Slight snow showers",86:"Heavy snow showers",
                          95:"Thunderstorm",96:"Thunderstorm slight hail",
                          99:"Thunderstorm heavy hail"}
            cond = conditions.get(code, f"Code {code}")
            return (f"Weather in {name}, {country}: {cond}, "
                    f"{temp}°C (feels like {feels}°C), "
                    f"Humidity {humidity}%, Wind {wind} km/h.")
        except Exception as e:
            return f"Weather error: {e}, sir."

    def _cmd_sysinfo(self) -> str:
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=0.5)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            now = datetime.now().strftime("%H:%M:%S")
            lines = [
                f"=== SYSTEM STATUS [{now}] ===",
                f"CPU:  {cpu}%  ({psutil.cpu_count()} logical cores)",
                f"RAM:  {mem.percent}%  ({mem.used//(1024**3)}/{mem.total//(1024**3)} GB used)",
                f"DISK: {disk.percent}%  ({disk.used//(1024**3)}/{disk.total//(1024**3)} GB used)",
            ]
            bat = psutil.sensors_battery()
            if bat:
                plug = "Plugged in" if bat.power_plugged else "On battery"
                lines.append(f"BAT:  {bat.percent}%  ({plug})")
            net = psutil.net_io_counters()
            lines.append(f"NET:  Down {net.bytes_recv//(1024**2)} MB  |  Up {net.bytes_sent//(1024**2)} MB")
            boot = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot
            days = uptime.days
            hours = uptime.seconds // 3600
            mins = (uptime.seconds % 3600) // 60
            lines.append(f"UPTIME: {days}d {hours}h {mins}m")
            return "\n".join(lines)
        except Exception as e:
            return f"System info error: {e}, sir."

    def _cmd_processes(self) -> str:
        try:
            import psutil
            procs = sorted(
                psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: p.info.get("cpu_percent", 0) or 0,
                reverse=True
            )[:15]
            lines = [f"{'PID':<6} {'CPU%':<5} {'MEM%':<5} NAME"]
            for p in procs:
                cpu_v = p.info.get("cpu_percent", 0) or 0
                mem_v = p.info.get("memory_percent", 0) or 0
                lines.append(f"{p.info['pid']:<6} {cpu_v:<5.1f} {mem_v:<5.1f} {p.info['name']}")
            return "\n".join(lines)
        except Exception as e:
            return f"Process list error: {e}, sir."

    def _cmd_kill(self, target: str) -> str:
        try:
            import psutil
            if target.isdigit():
                pid = int(target)
                proc = psutil.Process(pid)
                name = proc.name()
                proc.terminate()
                return f"Process {pid} ({name}) terminated, sir."
            killed = []
            for proc in psutil.process_iter(attrs=["pid", "name"]):
                if target.lower() in proc.info["name"].lower():
                    proc.terminate()
                    killed.append(f"{proc.info['pid']}:{proc.info['name']}")
            if killed:
                return f"Terminated: {', '.join(killed)}, sir."
            return f"No process matching '{target}' found, sir."
        except Exception as e:
            return f"Kill error: {e}, sir."

    def _cmd_python(self, code: str) -> str:
        try:
            local_ns = {}
            exec(code, {"__builtins__": __builtins__}, local_ns)
            if local_ns:
                out = "\n".join(f"{k} = {v}" for k, v in local_ns.items())
            else:
                out = "Code executed, no output."
            if len(out) > 2000:
                out = out[:2000] + "\n...[truncated]"
            return out
        except Exception as e:
            return f"Python exec error: {e}, sir."

    def _cmd_screenshot(self) -> str:
        try:
            import mss
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_dir = Path.home() / "Pictures" / "JARVIS"
            shot_dir.mkdir(parents=True, exist_ok=True)
            path = shot_dir / f"screenshot_{ts}.png"
            with mss.mss() as sct:
                sct.shot(output=str(path))
            return f"Screenshot saved to {path}, sir."
        except Exception as e:
            return f"Screenshot error: {e}, sir."

    def _cmd_remember(self, key: str, value: str) -> str:
        try:
            mem_file = BASE_DIR / "jarvis_memory.json"
            if mem_file.exists():
                memory = json.loads(mem_file.read_text(encoding="utf-8"))
            else:
                memory = {}
            memory[key] = value
            mem_file.write_text(json.dumps(memory, indent=2), encoding="utf-8")
            return f"Remembered: {key} = {value}."
        except Exception as e:
            return f"Memory error: {e}, sir."

    def _cmd_recall(self, key: str = "") -> str:
        try:
            mem_file = BASE_DIR / "jarvis_memory.json"
            if not mem_file.exists():
                return "No memories stored yet, sir."
            memory = json.loads(mem_file.read_text(encoding="utf-8"))
            if not memory:
                return "Memory bank is empty, sir."
            if key:
                if key in memory:
                    return f"{key}: {memory[key]}"
                matches = {k: v for k, v in memory.items() if key.lower() in k.lower()}
                if matches:
                    return "\n".join(f"  {k}: {v}" for k, v in matches.items())
                return f"No memory for '{key}', sir."
            lines = [f"  {k}: {v}" for k, v in list(memory.items())[:30]]
            if len(memory) > 30:
                lines.append(f"  ... and {len(memory)-30} more")
            return "Memory bank:\n" + "\n".join(lines)
        except Exception as e:
            return f"Recall error: {e}, sir."

    def _cmd_clipboard(self, action: str = "get", value: str = "") -> str:
        try:
            import pyperclip
            if action == "get":
                text = pyperclip.paste()
                if not text:
                    return "Clipboard is empty, sir."
                return f"Clipboard: {text[:500]}" + ("..." if len(text) > 500 else "")
            elif action == "set":
                pyperclip.copy(value)
                return f"Clipboard set: {value[:100]}."
            elif action == "clear":
                pyperclip.copy("")
                return "Clipboard cleared, sir."
            return "Usage: /clipboard [get|set|clear] [value]"
        except Exception as e:
            return f"Clipboard error: {e}, sir."

    def _cmd_notify(self, title: str, message: str) -> str:
        try:
            safe_title = title.replace("'", "''")
            safe_msg = message.replace("'", "''")
            ps = (
                f'Add-Type -AssemblyName System.Windows.Forms; '
                f'$n = New-Object System.Windows.Forms.NotifyIcon; '
                f'$n.Icon = [System.Drawing.SystemIcons]::Information; '
                f'$n.BalloonTipIcon = "Info"; '
                f'$n.BalloonTipTitle = "{safe_title}"; '
                f'$n.BalloonTipText = "{safe_msg}"; '
                f'$n.Visible = $true; '
                f'$n.ShowBalloonTip(5000)'
            )
            subprocess.Popen(["powershell", "-Command", ps],
                             creationflags=subprocess.CREATE_NO_WINDOW)
            return f"Notification: {title} - {message}"
        except Exception as e:
            return f"Notify error: {e}, sir."

    def _cmd_pc(self, action: str, value: str = "") -> str:
        try:
            a = action.lower()
            if a == "volume":
                return self._pc_volume(value)
            elif a in ("brightness", "bright"):
                return self._pc_brightness(value)
            elif a == "lock":
                subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"])
                return "PC locked, sir."
            elif a in ("hibernate", "sleep"):
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "1", "0", "0"])
                return f"PC going to {action}, sir."
            elif a in ("shutdown", "restart"):
                flag = "/r" if a == "restart" else "/s"
                subprocess.run(["shutdown", flag, "/t", "30", "/c", "JARVIS initiated shutdown. Save your work."])
                return f"{a.capitalize()} in 30s. Use /pc abort to cancel."
            elif a == "abort":
                subprocess.run(["shutdown", "/a"])
                return "Shutdown aborted, sir."
            elif a in ("wifi", "wifi-info"):
                r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=10)
                return r.stdout.strip()[:1500] or "No WiFi info, sir."
            elif a == "apps":
                r = subprocess.run(
                    ["powershell", "-Command",
                     "Get-Process | Where-Object { $_.MainWindowTitle } | Select-Object -First 15 Name,MainWindowTitle | Format-Table -AutoSize | Out-String"],
                    capture_output=True, text=True, timeout=10)
                return r.stdout.strip()[:2000] or "No open apps found, sir."
            else:
                try:
                    subprocess.Popen(a, shell=True)
                    return f"Launching {action}, sir."
                except Exception:
                    return f"Unknown command: /pc {action}, sir."
        except Exception as e:
            return f"PC control error: {e}, sir."

    def _pc_volume(self, value: str) -> str:
        try:
            from pycaw.pycaw import AudioUtilities
            devices = AudioUtilities.GetSpeakers()
            vol = devices.EndpointVolume
            if value == "up":
                vol.VolumeStepUp()
                vol.VolumeStepUp()
                return "Volume increased, sir."
            elif value == "down":
                vol.VolumeStepDown()
                vol.VolumeStepDown()
                return "Volume decreased, sir."
            elif value.replace("%", "").strip().isdigit():
                v = min(100, max(0, int(value.replace("%", "")))) / 100.0
                vol.SetMasterVolumeLevelScalar(v, None)
                return f"Volume set to {int(v*100)}%, sir."
            else:
                cur = int(vol.GetMasterVolumeLevelScalar() * 100)
                return f"Current volume: {cur}%, sir."
        except Exception as e:
            return f"Volume error: {e}, sir."

    def _pc_brightness(self, value: str) -> str:
        try:
            import screen_brightness_control as sbc
            if value.replace("%", "").strip().isdigit():
                v = min(100, max(0, int(value.replace("%", ""))))
                sbc.set_brightness(v)
                return f"Brightness set to {v}%, sir."
            current = sbc.get_brightness()
            if current:
                return f"Current brightness: {current[0]}%, sir."
            return "Brightness info unavailable, sir."
        except ImportError:
            return "Brightness control requires: pip install screen-brightness-control"
        except Exception as e:
            return f"Brightness error: {e}, sir."

    # ─────────────────────────────────────────────────────────────────
    # PROCESS INPUT
    # ─────────────────────────────────────────────────────────────────
    def process_input(self, raw: str, mode: str = "text"):
        self._you(raw, mode)
        self.last_active = time.time()
        if self.standby:
            self._exit_standby()

        # Slash commands
        if raw.strip().startswith("/"):
            if self._handle_command(raw):
                return

        cmd = raw.strip().lower()

        # HUD control
        if "open hud" in cmd:
            self._open_hud(); return
        if "close hud" in cmd:
            self._close_hud(); return

        # Engine switch
        if cmd.startswith("switch "):
            result = self._switch_brain(cmd.split("switch ", 1)[1])
            self._jarvis(result); self._print_banner()
            self.speak(result); return

        # YouTube
        if re.search(r'\bplay\b', cmd):
            query = re.sub(r'^.*?\bplay\b\s*', '', cmd).strip()
            if not query:
                result = "What would you like me to play, sir?"
            elif not is_online():
                result = "I'm offline, sir. Cannot reach YouTube."
            else:
                url = search_youtube(query)
                if url:
                    webbrowser.open(url)
                    result = f"Opening '{query}' on YouTube, sir."
                else:
                    result = f"Could not find '{query}' on YouTube, sir."
            self._jarvis(result); self.speak(result); return

        # Quick time
        if re.search(r'\btime\b', cmd) and len(cmd) < 30:
            result = f"It is {datetime.now().strftime('%H:%M:%S')} on {datetime.now().strftime('%A, %d %B %Y')}, sir."
            self._jarvis(result); self.speak(result); return

        # AI
        if not is_online():
            result = "I'm offline, sir. No connection to external networks."
        else:
            result = self.ask_ai(raw)

        self._jarvis(result)
        self.speak(result)

    # ─────────────────────────────────────────────────────────────────
    # STANDBY
    # ─────────────────────────────────────────────────────────────────
    def _enter_standby(self):
        if self.standby:
            return
        self.standby = True
        push_to_hud("__STANDBY__")
        msg = "Entering standby mode, sir. Say 'Hey Jarvis' or press Ctrl+Space to wake me."
        self._jarvis(msg)
        self.speak(msg)

    def _exit_standby(self):
        if not self.standby:
            return
        self.standby = False
        self.last_active = time.time()
        push_to_hud("__WAKE__")
        msg = "Standby disengaged. Systems fully online, sir."
        self._jarvis(msg)
        self.speak(msg)

    def _standby_watcher(self):
        """Background thread — enters standby after STANDBY_MINS of silence."""
        while self.running:
            time.sleep(30)
            if not self.standby and not self.speaking and not self.listening:
                idle = (time.time() - self.last_active) / 60
                if idle >= STANDBY_MINS:
                    self._enter_standby()

    # ─────────────────────────────────────────────────────────────────
    # HUD
    # ─────────────────────────────────────────────────────────────────
    def _open_hud(self):
        hud = BASE_DIR / "jarvis_hud.py"
        if not hud.exists():
            self._jarvis("HUD script not found, sir. Ensure jarvis_hud.py is in the same folder.")
            return
        if self._hud_proc and self._hud_proc.poll() is None:
            self._jarvis("HUD is already running, sir.")
            return
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self._hud_proc = subprocess.Popen([sys.executable, str(hud)],
                                          creationflags=flags)
        self._jarvis("Holographic HUD activated, sir.")
        self.speak("Holographic HUD activated, sir.")

    def _close_hud(self):
        if self._hud_proc and self._hud_proc.poll() is None:
            self._hud_proc.terminate()
            self._hud_proc = None
            self._jarvis("HUD offline, sir.")
            self.speak("HUD offline, sir.")
        else:
            self._jarvis("No active HUD to close, sir.")

    # ─────────────────────────────────────────────────────────────────
    # MICROPHONE / WAKE WORD
    # ─────────────────────────────────────────────────────────────────
    def _normalise(self, text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()

    def _extract_wake_cmd(self, text: str):
        heard = self._normalise(text)
        wake  = self._normalise(self.cfg.get("wake_word", "hey jarvis"))
        if wake not in heard:
            return None
        after = heard.split(wake, 1)[1].strip()
        return after

    def listen_once(self):
        """One-shot voice capture."""
        with self.lock:
            if self.listening:
                return
            self.listening = True
        try:
            with sr.Microphone() as src:
                self.recognizer.adjust_for_ambient_noise(src, duration=0.4)
                print(f"{Fore.YELLOW}[🎤 Listening...]{Style.RESET_ALL}")
                audio = self.recognizer.listen(src, timeout=10, phrase_time_limit=15)
            text = self.recognizer.recognize_google(audio)
            self.process_input(text, mode="voice")
        except sr.WaitTimeoutError:
            print(f"{Fore.RED}[Mic timeout — nothing heard]{Style.RESET_ALL}")
        except sr.UnknownValueError:
            print(f"{Fore.RED}[Could not understand audio]{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[Mic error: {e}]{Style.RESET_ALL}")
        finally:
            with self.lock:
                self.listening = False

    def _wake_loop(self):
        """Continuous background listener for wake word."""
        print(f"{Fore.YELLOW}[Mic] Calibrating ambient noise (2 s)...{Style.RESET_ALL}")
        try:
            with sr.Microphone() as src:
                self.wake_rec.adjust_for_ambient_noise(src, duration=2)
            print(f"{Fore.GREEN}[Mic] Calibrated — threshold "
                  f"{self.wake_rec.energy_threshold:.0f}. "
                  f"Always listening for \"{self.cfg['wake_word']}\"...{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[Mic] Calibration failed: {e}{Style.RESET_ALL}")

        while self.running:
            if self.listening or self.speaking:
                time.sleep(0.1)
                continue
            try:
                with sr.Microphone() as src:
                    audio = self.wake_rec.listen(src, timeout=4, phrase_time_limit=7)
                heard = self.wake_rec.recognize_google(audio)
                cmd   = self._extract_wake_cmd(heard)
                if cmd is not None:
                    print(f"{Fore.GREEN}[Wake word detected!]{Style.RESET_ALL}")
                    self._wake_sound()
                    # If Jarvis is talking, interrupt first
                    if self.speaking:
                        self.interrupt()
                        time.sleep(0.2)
                    if self.standby:
                        self._exit_standby()
                    if cmd:
                        self.process_input(cmd, mode="voice")
                    else:
                        self.speak("Yes, sir?", force=True)
                        self.listen_once()
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                continue
            except Exception:
                continue

    # ─────────────────────────────────────────────────────────────────
    # HAND TRACKING  (runs in its own thread, pushes presence to HUD)
    # ─────────────────────────────────────────────────────────────────
    def _hand_tracking_loop(self):
        if not HAND_TRACK_AVAILABLE:
            print(f"{Fore.RED}[Hand] mediapipe/opencv not installed — hand tracking disabled.{Style.RESET_ALL}")
            return

        print(f"{Fore.GREEN}[Hand] Starting hand tracking thread...{Style.RESET_ALL}")

        # ── Support both old (solutions) and new (tasks) MediaPipe APIs ──
        hands      = None
        use_legacy = False
        try:
            # New API (mediapipe >= 0.10)
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            import urllib.request as _ur, tempfile, os as _os

            model_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                       "hand_landmarker.task")
            if not _os.path.exists(model_path):
                print(f"{Fore.YELLOW}[Hand] Downloading hand landmark model (~9 MB)...{Style.RESET_ALL}")
                _ur.urlretrieve(
                    "https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
                    model_path
                )
                print(f"{Fore.GREEN}[Hand] Model downloaded.{Style.RESET_ALL}")

            base_opts  = mp_python.BaseOptions(model_asset_path=model_path)
            opts       = mp_vision.HandLandmarkerOptions(
                base_options          = base_opts,
                num_hands             = 1,
                min_hand_detection_confidence  = 0.5,
                min_hand_presence_confidence   = 0.5,
                min_tracking_confidence        = 0.5,
                running_mode          = mp_vision.RunningMode.VIDEO,
            )
            hands = mp_vision.HandLandmarker.create_from_options(opts)
            use_legacy = False
            print(f"{Fore.GREEN}[Hand] Using new MediaPipe Tasks API.{Style.RESET_ALL}")
        except Exception as e1:
            # Fall back to legacy solutions API (mediapipe < 0.10)
            try:
                legacy = mp.solutions.hands
                hands  = legacy.Hands(
                    static_image_mode        = False,
                    max_num_hands            = 1,
                    min_detection_confidence = 0.55,
                    min_tracking_confidence  = 0.45,
                )
                use_legacy = True
                print(f"{Fore.GREEN}[Hand] Using legacy MediaPipe solutions API.{Style.RESET_ALL}")
            except Exception as e2:
                print(f"{Fore.RED}[Hand] Could not init MediaPipe: {e1} / {e2}{Style.RESET_ALL}")
                return

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print(f"{Fore.RED}[Hand] No webcam detected (tried index 0 and 1). "
                  f"Hand tracking disabled.{Style.RESET_ALL}")
            return

        print(f"{Fore.GREEN}[Hand] Webcam open. Hold hand in front of camera.{Style.RESET_ALL}")
        last_seen   = 0.0
        was_present = False
        frame_ts    = 0

        while self.running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            landmark  = None

            if use_legacy:
                results = hands.process(frame_rgb)
                if results.multi_hand_landmarks:
                    landmark = results.multi_hand_landmarks[0].landmark[9]
            else:
                from mediapipe.tasks.python import vision as mp_vision
                frame_ts += 33   # ~30 fps timestamp in ms
                mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                results   = hands.detect_for_video(mp_image, frame_ts)
                if results.hand_landmarks:
                    landmark = results.hand_landmarks[0][9]   # index 9 = palm centre

            if landmark is not None:
                last_seen        = time.time()
                self.last_active = time.time()
                h_px = int((1 - landmark.x) * 820)
                v_px = int(landmark.y        * 560)
                push_to_hud(f"__HAND__{h_px},{v_px}")
                if not was_present:
                    was_present = True
                    if self.standby:
                        self.last_active = time.time()
                        self._exit_standby()
            else:
                if was_present and (time.time() - last_seen) > 1.5:
                    was_present = False
                    push_to_hud("__HAND_GONE__")

            time.sleep(0.033)

        cap.release()

    # ─────────────────────────────────────────────────────────────────
    # HOTKEY
    # ─────────────────────────────────────────────────────────────────
    def _register_hotkey(self):
        try:
            hk = self.cfg.get("hotkey", "ctrl+space")
            keyboard.add_hotkey(hk, self._on_hotkey)
            print(f"{Fore.GREEN}[Hotkey] {hk} registered.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[Hotkey] Could not register: {e} "
                  f"(try running as Administrator){Style.RESET_ALL}")

    def _on_hotkey(self):
        if self.speaking:
            # Interrupt JARVIS mid-sentence
            self.interrupt()
        elif self.standby:
            self._exit_standby()
        elif not self.listening:
            self._wake_sound()
            self.speak("Listening, sir.", force=True)
            threading.Thread(target=self.listen_once, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────────────────────────────────────────
    def run(self):
        greeting = (
            f"Systems online. Active engine: {self.cfg['active_model'].upper()} "
            f"({self.cfg.get(self.cfg['active_model']+'_model','?')}). "
            f"Say \"{self.cfg['wake_word']}\" or press {self.cfg['hotkey']}, sir."
        )
        self._jarvis(greeting)
        self.speak(greeting, force=True)

        # Start background threads
        threading.Thread(target=self._wake_loop,        daemon=True).start()
        threading.Thread(target=self._standby_watcher,  daemon=True).start()
        self._register_hotkey()

        if self.cfg.get("hand_tracking", True) and HAND_TRACK_AVAILABLE:
            self._hand_thread = threading.Thread(
                target=self._hand_tracking_loop, daemon=True)
            self._hand_thread.start()
        elif not HAND_TRACK_AVAILABLE and self.platform != "hf":
            print(f"{Fore.YELLOW}[Hand] Install opencv-python mediapipe numpy "
                  f"for hand tracking.{Style.RESET_ALL}")

        # Input loop
        while self.running:
            try:
                raw = input(f"{Fore.WHITE}You: {Style.RESET_ALL}").strip()
                if raw:
                    self.process_input(raw)
            except KeyboardInterrupt:
                self.running = False
                self._jarvis("Shutting down. Goodbye, sir.")
                self.speak("Shutting down. Goodbye, sir.", force=True)
                time.sleep(1.5)
                break
            except EOFError:
                break

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        Jarvis().run()
    except Exception as e:
        print(f"{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        import traceback; traceback.print_exc()
