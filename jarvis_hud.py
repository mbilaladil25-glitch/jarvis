"""
J.A.R.V.I.S HUD — Clean Circle Edition
Design from Huw Prosser TikTok screenshot:
  - Dark grid background
  - Single clean white circle ring centred
  - "JARVIS" text in the middle
  - Pulsating blue glow radiating from circle
  - Floating white particles/dots scattered around
  - No tick marks, no crosshairs, no corner panels
  - Standby dims everything
  - Typewriter response text below "JARVIS"
  - Voice waveform around bottom arc (subtle)
  - Hand tracking reticle if webcam
  - Socket protocol: __HAND__x,y __HAND_GONE__ __STANDBY__ __WAKE__ __STOP_TYPE__
"""

import tkinter as tk
import json, os, math, random, time, threading, socket
from datetime import datetime

try:
    import cv2
    import mediapipe as mp
    HAND_TRACK_OK = True
except ImportError:
    HAND_TRACK_OK = False

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud_position.json")
HUD_PORT = 9988
W, H = 800, 800
CX, CY = W // 2, H // 2
STANDBY_TIMEOUT = 8

C_BG      = "#000000"
C_GRID    = "#0a1620"
C_RING    = "#d0e8ff"
C_GLOW    = "#2088d0"
C_JARVIS  = "#ffffff"
C_TEXT    = "#80c8e8"
C_GREEN   = "#40ffaa"
C_WARN    = "#ff8833"
C_DIM     = "#0d1a28"
C_PARTICLE = "#a0d0f0"

R_RING = 220
GLOW_MAX_R = 320


class JarvisHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("J.A.R.V.I.S")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", C_BG)
        self.root.configure(bg=C_BG)
        self._load_position()

        self.canvas = tk.Canvas(self.root, width=W, height=H, bg=C_BG, highlightthickness=0)
        self.canvas.pack()

        self.standby = False
        self.last_presence = time.time()
        self.response_text = "SYSTEMS ONLINE"
        self.waveform = [0.0] * 40
        self.pulse = 0.0
        self.glow_phase = 0.0

        self.hand_x = CX
        self.hand_y = CY
        self.hand_visible = False

        self._type_target = ""
        self._type_shown = ""
        self._type_pos = 0
        self._type_cursor = True
        self._typing = False

        self.particles = []
        for _ in range(60):
            a = random.uniform(0, 360)
            d = random.uniform(R_RING + 30, GLOW_MAX_R + 100)
            s = random.uniform(0.1, 0.4)
            self.particles.append([a, d, s])

        self._build_static()
        self._make_draggable()

        threading.Thread(target=self._socket_listener, daemon=True).start()
        threading.Thread(target=self._mic_monitor, daemon=True).start()
        if HAND_TRACK_OK:
            import sys
            if not getattr(sys, '_called_from_master', False):
                threading.Thread(target=self._hand_tracker, daemon=True).start()

        self._animate()
        self._tick_time()
        self.root.after(800, lambda: self._type_set(self.response_text))

    def _pt(self, cx, cy, r, deg):
        a = math.radians(deg)
        return cx + r * math.cos(a), cy - r * math.sin(a)

    def _bright(self, hex_c, factor):
        h = hex_c.lstrip("#")
        r = min(255, int(int(h[0:2], 16) * factor))
        g = min(255, int(int(h[2:4], 16) * factor))
        b = min(255, int(int(h[4:6], 16) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _build_static(self):
        c = self.canvas
        self.id_grid_lines = []
        for i in range(0, W + 1, 40):
            self.id_grid_lines.append(c.create_line(i, 0, i, H, fill=C_GRID, width=1))
            self.id_grid_lines.append(c.create_line(0, i, W, i, fill=C_GRID, width=1))
        self.id_glow = c.create_oval(0, 0, 0, 0, outline="", fill="")
        self.id_glow2 = c.create_oval(0, 0, 0, 0, outline="", fill="")
        self.id_ring = c.create_oval(
            CX - R_RING, CY - R_RING, CX + R_RING, CY + R_RING,
            outline=C_RING, fill="", width=2)
        self.id_ring_inner = c.create_oval(
            CX - R_RING + 12, CY - R_RING + 12, CX + R_RING - 12, CY + R_RING - 12,
            outline="", fill="", width=1)
        self.id_jarvis = c.create_text(CX, CY - 6, text="J.A.R.V.I.S",
            fill=C_JARVIS, font=("Courier New", 28, "bold"), anchor="center")
        self.id_resp = c.create_text(CX, CY + 38, text="",
            fill=C_GREEN, font=("Courier New", 9), anchor="center", width=R_RING * 2 - 40)
        self.id_status = c.create_text(W - 20, 18, text="ONLINE",
            fill=C_GREEN, font=("Courier New", 8, "bold"), anchor="ne")
        self.id_time = c.create_text(CX, H - 18, text="",
            fill=C_TEXT, font=("Courier New", 8), anchor="s")
        self.id_hand_label = c.create_text(20, H - 18, text="",
            fill=C_DIM, font=("Courier New", 7), anchor="sw")

        self.id_particles = []
        for _ in self.particles:
            self.id_particles.append(c.create_oval(0, 0, 0, 0, fill=C_PARTICLE, outline=""))

        self.id_hand_h = c.create_line(0, 0, 0, 0, fill=C_WARN, width=1)
        self.id_hand_v = c.create_line(0, 0, 0, 0, fill=C_WARN, width=1)
        self.id_hand_c = c.create_oval(0, 0, 0, 0, outline=C_WARN, fill="", width=2)
        self.id_standby = c.create_text(CX, CY + 80, text="",
            fill=C_DIM, font=("Courier New", 9), anchor="center")
        self.id_wave = [c.create_line(0, 0, 1, 1, fill=C_TEXT, width=1) for _ in range(40)]
        self.id_close = c.create_text(W - 12, 12, text="\u2715",
            fill=C_DIM, font=("Courier New", 11, "bold"), anchor="ne")
        c.tag_bind(self.id_close, "<Button-1>", lambda e: self._on_close())
        c.tag_bind(self.id_close, "<Enter>", lambda e: c.itemconfig(self.id_close, fill=C_WARN))
        c.tag_bind(self.id_close, "<Leave>", lambda e: c.itemconfig(self.id_close, fill=C_DIM))

    def _animate(self):
        c = self.canvas
        speed = 0.1 if self.standby else 1.0
        self.pulse = (self.pulse + 0.03 * speed) % (2 * math.pi)
        self.glow_phase = (self.glow_phase + 0.02 * speed) % (2 * math.pi)

        dim = self.standby
        gf = 0.4 + 0.6 * math.sin(self.glow_phase) if not dim else 0.1
        pf = 0.5 + 0.5 * math.sin(self.pulse)

        glow_r = int(R_RING + 10 + pf * 90)
        glow_alpha = int(30 + pf * 50) if not dim else 5
        glow_col = f"#{'%02x' % 0}{'%02x' % int(80 + pf * 60)}{'%02x' % int(160 + pf * 60)}"
        c.coords(self.id_glow,
            CX - glow_r, CY - glow_r, CX + glow_r, CY + glow_r)
        c.itemconfig(self.id_glow,
            outline=glow_col if not dim else C_DIM, width=int(12 + pf * 16))

        glow_r2 = int(R_RING + 30 + pf * 50)
        glow_col2 = f"#{'%02x' % 0}{'%02x' % int(40 + pf * 40)}{'%02x' % int(100 + pf * 40)}"
        c.coords(self.id_glow2,
            CX - glow_r2, CY - glow_r2, CX + glow_r2, CY + glow_r2)
        c.itemconfig(self.id_glow2,
            outline=glow_col2 if not dim else C_DIM, width=int(6 + pf * 8))

        ring_col = self._bright(C_RING, 0.7 + 0.3 * pf) if not dim else C_DIM
        c.itemconfig(self.id_ring, outline=ring_col, width=int(2 + pf * 2))

        inner_vis = not dim and pf > 0.3
        inner_col = self._bright(C_RING, 0.2 * pf) if not dim else ""
        c.itemconfig(self.id_ring_inner,
            outline=inner_col if inner_vis else "")

        jarvis_col = self._bright(C_JARVIS, 0.8 + 0.2 * pf) if not dim else C_DIM
        c.itemconfig(self.id_jarvis, fill=jarvis_col)

        if not dim:
            c.itemconfig(self.id_status, text="ONLINE", fill=C_GREEN)
        else:
            c.itemconfig(self.id_status, text="STANDBY", fill=C_DIM)

        for i, pid in enumerate(self.id_particles):
            p = self.particles[i]
            p[0] = (p[0] + p[2] * speed * 0.5) % 360
            d = p[1] + math.sin(self.pulse * 0.5 + i) * 3
            size = 2 + math.sin(self.pulse + i * 0.5) * 1
            brightness = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.pulse + i))
            x, y = self._pt(CX, CY, d, p[0])
            col = self._bright(C_PARTICLE, brightness * gf) if not dim else C_DIM
            c.coords(pid, x - size, y - size, x + size, y + size)
            c.itemconfig(pid, fill=col, outline=col)

        if self.hand_visible and not dim:
            hx, hy = self.hand_x, self.hand_y
            cr = 12
            c.coords(self.id_hand_h, hx - 24, hy, hx + 24, hy)
            c.coords(self.id_hand_v, hx, hy - 24, hx, hy + 24)
            c.coords(self.id_hand_c, hx - cr, hy - cr, hx + cr, hy + cr)
            c.itemconfig(self.id_hand_h, fill=C_WARN)
            c.itemconfig(self.id_hand_v, fill=C_WARN)
            c.itemconfig(self.id_hand_c, outline=C_WARN)
            c.itemconfig(self.id_hand_label, text="HAND LOCKED", fill=C_WARN)
        else:
            c.coords(self.id_hand_h, 0, 0, 0, 0)
            c.coords(self.id_hand_v, 0, 0, 0, 0)
            c.coords(self.id_hand_c, 0, 0, 0, 0)
            if not dim:
                c.itemconfig(self.id_hand_label, text="", fill=C_DIM)

        for i, wid in enumerate(self.id_wave):
            deg = 210 + i * (120 / len(self.id_wave))
            amp = self.waveform[i] * 15 + 2
            x1, y1 = self._pt(CX, CY, R_RING + 6, deg)
            x2, y2 = self._pt(CX, CY, R_RING + 6 + amp, deg)
            c.coords(wid, x1, y1, x2, y2)
            bright = 0.3 + 0.7 * self.waveform[i]
            c.itemconfig(wid, fill=self._bright(C_TEXT, bright * gf) if not dim else C_DIM)

        if dim:
            c.itemconfig(self.id_standby, text="[ STANDBY ]", fill=C_DIM)
        else:
            c.itemconfig(self.id_standby, text="")

        self.root.after(33, self._animate)

    def _tick_time(self):
        now = datetime.now().strftime("%H:%M   %d %b %Y")
        self.canvas.itemconfig(self.id_time, text=now)
        self.root.after(1000, self._tick_time)

    def _enter_standby(self):
        self.standby = True
        self.canvas.itemconfig(self.id_status, text="STANDBY", fill=C_DIM)

    def _exit_standby(self):
        self.standby = False
        self.last_presence = time.time()
        self.canvas.itemconfig(self.id_status, text="ONLINE", fill=C_GREEN)

    def _mic_monitor(self):
        try:
            import speech_recognition as sr
            rec = sr.Recognizer()
            rec.energy_threshold = 300
            rec.dynamic_energy_threshold = True
            with sr.Microphone() as source:
                rec.adjust_for_ambient_noise(source, duration=1)
                while True:
                    try:
                        audio = rec.record(source, duration=0.1)
                        raw = audio.get_raw_data()
                        arr = [abs(int.from_bytes(raw[i:i + 2], 'little', signed=True)) / 32768
                               for i in range(0, len(raw) - 1, 2)]
                        n = len(self.waveform)
                        chunk = max(len(arr) // n, 1)
                        self.waveform = [
                            min(1.0, sum(arr[j * chunk:(j + 1) * chunk]) / chunk * 3)
                            for j in range(n)
                        ]
                        if max(self.waveform) > 0.05:
                            self.last_presence = time.time()
                            if self.standby:
                                self.root.after(0, self._exit_standby)
                    except Exception:
                        self.waveform = [random.uniform(0, 0.05) for _ in range(len(self.waveform))]
        except Exception:
            while True:
                t = time.time()
                self.waveform = [
                    abs(math.sin(t * (1.5 + i * 0.2) + i)) * 0.3 + random.uniform(0, 0.04)
                    for i in range(len(self.waveform))
                ]
                time.sleep(0.08)

    def _hand_tracker(self):
        hands = None
        use_legacy = False
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision
            import urllib.request as _ur
            model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
            if not os.path.exists(model_path):
                _ur.urlretrieve(
                    "https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
                    model_path)
            base_opts = mp_python.BaseOptions(model_asset_path=model_path)
            opts = mp_vision.HandLandmarkerOptions(
                base_options=base_opts, num_hands=1,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                running_mode=mp_vision.RunningMode.VIDEO)
            hands = mp_vision.HandLandmarker.create_from_options(opts)
        except Exception:
            try:
                hands = mp.solutions.hands.Hands(
                    static_image_mode=False, max_num_hands=1,
                    min_detection_confidence=0.6, min_tracking_confidence=0.5)
                use_legacy = True
            except Exception:
                return
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            return
        frame_ts = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            lm = None
            if use_legacy:
                res = hands.process(rgb)
                if res.multi_hand_landmarks:
                    lm = res.multi_hand_landmarks[0].landmark[9]
            else:
                from mediapipe.tasks.python import vision as mp_vision
                frame_ts += 33
                mi = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                res = hands.detect_for_video(mi, frame_ts)
                if res.hand_landmarks:
                    lm = res.hand_landmarks[0][9]
            if lm:
                self.hand_visible = True
                self.hand_x = int((1 - lm.x) * W)
                self.hand_y = int(lm.y * H)
                self.last_presence = time.time()
                if self.standby:
                    self.root.after(0, self._exit_standby)
            else:
                self.hand_visible = False
            time.sleep(0.035)

    def _type_set(self, text):
        self._type_target = text
        self._type_shown = ""
        self._type_pos = 0
        self._typing = True
        self._type_step()

    def _type_step(self):
        if not self._typing:
            return
        if self._type_pos < len(self._type_target):
            self._type_pos += 1
            self._type_shown = self._type_target[:self._type_pos]
            self.canvas.itemconfig(self.id_resp, text=self._type_shown + "\u2588")
            self.root.after(18, self._type_step)
        else:
            self._typing = False
            self.response_text = self._type_target
            self._blink_cursor()

    def _blink_cursor(self):
        if self._typing:
            return
        if self._type_cursor:
            self.canvas.itemconfig(self.id_resp, text=self.response_text + "\u2588")
        else:
            self.canvas.itemconfig(self.id_resp, text=self.response_text)
        self._type_cursor = not self._type_cursor
        self.root.after(530, self._blink_cursor)

    def _socket_listener(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", HUD_PORT))
            srv.listen(10)
            while True:
                conn, _ = srv.accept()
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                conn.close()
                if not data:
                    continue
                msg = data.decode("utf-8", errors="ignore").strip()
                if msg == "__STANDBY__":
                    self.root.after(0, self._enter_standby)
                    continue
                if msg == "__WAKE__":
                    self.root.after(0, self._exit_standby)
                    continue
                if msg.startswith("__HAND__"):
                    try:
                        hx, hy = map(int, msg[8:].split(","))
                        self.hand_x = hx
                        self.hand_y = hy
                        self.hand_visible = True
                        self.last_presence = time.time()
                        if self.standby:
                            self.root.after(0, self._exit_standby)
                    except Exception:
                        pass
                    continue
                if msg == "__HAND_GONE__":
                    self.hand_visible = False
                    continue
                if msg == "__STOP_TYPE__":
                    self._typing = False
                    self.root.after(0, lambda: (
                        self.canvas.itemconfig(self.id_resp, text=self._type_shown + " [interrupted]"),
                        setattr(self, "response_text", self._type_shown + " [interrupted]")
                    ))
                    continue
                self.last_presence = time.time()
                if self.standby:
                    self.root.after(0, self._exit_standby)
                self.root.after(0, lambda m=msg[:200]: self._type_set(m))
        except Exception as e:
            print(f"[HUD socket] {e}")

    def _make_draggable(self):
        self.root.bind("<Button-1>", self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)
        self.root.bind("<ButtonRelease-1>", lambda e: self._save_position())

    def _drag_start(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _load_position(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                pos = json.load(f)
            x, y = pos.get("x", 100), pos.get("y", 100)
        else:
            x, y = 100, 100
        self.root.geometry(f"{W}x{H}+{x}+{y}")

    def _save_position(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"x": self.root.winfo_x(), "y": self.root.winfo_y()}, f)

    def _on_close(self):
        self._save_position()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    JarvisHUD().run()
