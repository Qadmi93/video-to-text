import numpy as np
import whisper
model = whisper.load_model('base')
print('Model loaded')
# Create a dummy audio array
audio = np.zeros(16000).astype(np.float32)
res = model.transcribe(audio, fp16=False)
print('Transcription result:', res['text'])
