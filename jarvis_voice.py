"""
J.A.R.V.I.S Custom Voice — Coqui TTS XTTSv2 voice cloning
"""
import os, tempfile, threading, time, wave, io
from pathlib import Path

VOICE_SAMPLE = r"C:\Users\zyth\Downloads\New folder\voice_training\audio\reference\jarvis_reference.wav"
_tts = None
_lock = threading.Lock()
_ready = False

def load_model():
    global _tts, _ready
    if _ready:
        return True
    with _lock:
        if _ready:
            return True
        try:
            from TTS.api import TTS
            print("[Voice] Loading XTTSv2 model (1.78GB)...")
            t0 = time.time()
            _tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
            print(f"[Voice] Model loaded in {time.time()-t0:.1f}s on GPU")
            _ready = True
            return True
        except Exception as e:
            print(f"[Voice] Model load failed: {e}")
            return False

def speak_to_file(text: str, output_path: str) -> str:
    if not _ready:
        load_model()
    if not _ready:
        return None
    try:
        _tts.tts_to_file(
            text=text,
            speaker_wav=VOICE_SAMPLE,
            language="en",
            file_path=output_path,
        )
        return output_path
    except Exception as e:
        print(f"[Voice] TTS failed: {e}")
        return None

def speak_to_bytes(text: str) -> bytes:
    if not _ready:
        load_model()
    if not _ready:
        return None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            out = tmp.name
        _tts.tts_to_file(
            text=text,
            speaker_wav=VOICE_SAMPLE,
            language="en",
            file_path=out,
        )
        with open(out, "rb") as f:
            data = f.read()
        os.unlink(out)
        return data
    except Exception as e:
        print(f"[Voice] TTS failed: {e}")
        return None

def is_ready():
    return _ready
