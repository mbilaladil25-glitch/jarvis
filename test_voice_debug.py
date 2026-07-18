import os, time
from TTS.api import TTS

wav = r'C:\Users\zyth\Downloads\New folder\george_test.wav'
print(f'Voice sample: {os.path.exists(wav)}, {os.path.getsize(wav)} bytes')

# Check WAV file
with open(wav, 'rb') as f:
    h = f.read(44)
    import struct
    channels = struct.unpack('<H', h[22:24])[0]
    sr = struct.unpack('<I', h[24:28])[0]
    bits = struct.unpack('<H', h[34:36])[0]
    print(f'WAV: {sr}Hz, {channels}ch, {bits}bit')

tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t0 = time.time()
tts.tts_to_file(
    text='Hello sir, this is JARVIS speaking with your voice.',
    speaker_wav=wav,
    language='en',
    file_path=r'C:\Users\zyth\test_clone.wav'
)
print(f'Generated in {time.time()-t0:.1f}s')
out = r'C:\Users\zyth\test_clone.wav'
print(f'Output: {os.path.getsize(out)} bytes')
