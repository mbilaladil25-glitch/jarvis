import torch, os, time
from TTS.api import TTS

wav = r'C:\Users\zyth\Downloads\New folder\voice_training\audio\reference\jarvis_reference.wav'
latent_dir = r'C:\Users\zyth\Downloads\New folder\voice_training\model\jarvis_latents'
gpt_file = os.path.join(latent_dir, 'gpt_cond_latent.pt')
spk_file = os.path.join(latent_dir, 'speaker_embedding.pt')

print(f'Using WAV: {os.path.getsize(wav)} bytes')
print(f'Latent:  {os.path.getsize(gpt_file)} bytes')
print(f'Speaker: {os.path.getsize(spk_file)} bytes')

# Load with latents
tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2', gpu=True)

# Try using the latent directly via low-level model
print('Using pre-computed latents...')
t0 = time.time()
model = tts.synthesizer.tts_model

gpt_cond_latent = torch.load(gpt_file, map_location='cuda')
speaker_embedding = torch.load(spk_file, map_location='cuda')

print(f'Loaded latents in {time.time()-t0:.1f}s')

# Generate with latents
t0 = time.time()
out = model.synthesize(
    text='Hello sir, this is JARVIS speaking with your trained voice.',
    config=tts.synthesizer.tts_config,
    gpt_cond_latent=gpt_cond_latent,
    speaker_embedding=speaker_embedding,
    language='en',
)
print(f'Synthesis: {time.time()-t0:.1f}s')

wav = out['wav']
import soundfile as sf
sf.write(r'C:\Users\zyth\test_latent_output.wav', wav, 24000)
print(f'Output: {os.path.getsize(r"C:\Users\zyth\test_latent_output.wav")} bytes')
