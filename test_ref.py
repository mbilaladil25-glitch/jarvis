import time, os
from TTS.api import TTS

wav = r'C:\Users\zyth\Downloads\New folder\voice_training\audio\reference\jarvis_reference.wav'
out = r'C:\Users\zyth\test_ref_output.wav'

tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)
t0 = time.time()
tts.tts_to_file(
    text='Hello sir, this is JARVIS speaking with your trained voice.',
    speaker_wav=wav,
    language='en',
    file_path=out
)
elapsed = time.time() - t0
size = os.path.getsize(out)
print(f'{elapsed:.1f}s output={size}b')
